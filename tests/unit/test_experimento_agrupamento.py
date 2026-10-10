from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import experimento_agrupamento as experimento
from scripts.divisao_por_identidade import dividir_por_identidade
from src.domain.entities.face_embedding import FaceEmbedding


def test_gate_exige_revisao_explicita_sem_tocar_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = tmp_path / "dados"
    dataset.mkdir()
    monkeypatch.setattr(
        experimento,
        "inventariar",
        lambda _: pytest.fail("inventario acessado sem aprovacao declarada"),
    )

    status = experimento.main(
        [
            "preparar",
            "--dataset",
            str(dataset),
            "--autorizacao-dataset",
            str(tmp_path / "autorizacao.txt"),
            "--saida",
            str(tmp_path / "saida"),
        ]
    )

    assert status == 2
    assert not (tmp_path / "saida").exists()


def test_arquivo_de_autorizacao_nao_substitui_confirmacao_explicita(
    tmp_path: Path,
) -> None:
    autorizacao = tmp_path / "autorizacao.txt"
    autorizacao.write_text("documento para teste, sem valor juridico", encoding="utf-8")

    with pytest.raises(experimento.RevisaoAutorizacaoPendente):
        experimento.verificar_gate_autorizacao(autorizacao, revisao_confirmada=False)


def test_manifesto_congelado_contem_agregados_sem_ids_ou_caminhos(
    tmp_path: Path,
) -> None:
    manifesto = experimento.criar_manifesto_seguro(
        autorizacao_hash="a" * 64,
        dataset_hash="b" * 64,
        assinatura_divisao="c" * 16,
        execucao_hash="d" * 64,
        seed=42,
        configuracoes={"dbscan": {"eps": 0.2, "min_samples": 3}},
        contagens={"desenvolvimento": {"identidades": 10, "imagens": 20}},
        diagnosticos={"validacao": {}},
        extracao={"modelo": "FaceNet512", "dimensao": 512},
    )
    serializado = json.dumps(manifesto, ensure_ascii=False)

    assert manifesto["configuracoes_congeladas"]["dbscan"]["eps"] == 0.2
    assert "identidade-privada" not in serializado
    assert str(tmp_path) not in serializado
    assert "imagens_por_identidade" not in manifesto


def test_cache_separa_particoes_e_rejeita_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(experimento, "CACHE_ETAPA4", tmp_path / "cache")
    hash_execucao = "A" * 64
    assert experimento.caminho_cache_particao(hash_execucao, "desenvolvimento") == (
        tmp_path / "cache" / hash_execucao / "desenvolvimento"
    )
    assert experimento.caminho_cache_particao(hash_execucao, "teste") != (
        tmp_path / "cache" / hash_execucao / "validacao"
    )
    with pytest.raises(ValueError):
        experimento.caminho_cache_particao(hash_execucao, "../teste")


def test_prepara_parametros_sem_extrair_teste_e_avalia_holdout_uma_vez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    saida = tmp_path / "avaliacao" / "resultados" / "etapa4"
    cache_raiz = tmp_path / "avaliacao" / "cache" / "etapa4"
    monkeypatch.setattr(experimento, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(experimento, "CACHE_ETAPA4", cache_raiz)

    imagens_por_identidade = {
        f"pseudo-{indice:02d}": tuple(
            dataset / f"pseudo-{indice:02d}" / f"imagem-{foto}.jpg" for foto in range(4)
        )
        for indice in range(30)
    }
    divisao = dividir_por_identidade(imagens_por_identidade, seed=42)
    identidades_teste_esperadas = set(
        divisao.abrir_teste({"dbscan": 0.2, "kmeans": 2.0})
    )
    hashes = {
        caminho: hashlib.sha256(str(caminho).encode("utf-8")).hexdigest().upper()
        for caminhos in imagens_por_identidade.values()
        for caminho in caminhos
    }
    imagens_extraidas: list[Path] = []
    caches: dict[Path, dict[str, FaceEmbedding]] = {}

    class CacheSintetico:
        def __init__(self, diretorio: Path, _configuracao: object) -> None:
            self.diretorio = diretorio
            self.valores = caches.setdefault(diretorio, {})

        def obter(self, chave: str) -> FaceEmbedding | None:
            return self.valores.get(chave)

        def guardar(self, chave: str, embedding: FaceEmbedding) -> None:
            self.valores[chave] = embedding

        def salvar(self) -> None:
            return None

    class ExtratorSintetico:
        def preaquecer(self) -> None:
            return None

        def gerar_embedding(self, imagem: Path) -> FaceEmbedding:
            imagens_extraidas.append(imagem)
            indice = int(imagem.parent.name.split("-")[1])
            foto = int(imagem.stem.split("-")[1])
            vetor = np.zeros(512)
            vetor[indice] = 1.0
            vetor[(indice + 50) % 512] = 0.001 * foto
            return FaceEmbedding.de_valores(vetor, experimento.MODELO)

    monkeypatch.setattr(
        experimento,
        "inventariar",
        lambda _dataset: SimpleNamespace(imagens_por_pessoa=imagens_por_identidade),
    )
    monkeypatch.setattr(experimento, "hash_do_arquivo", lambda caminho: hashes[caminho])
    monkeypatch.setattr(experimento, "CacheDeEmbeddings", CacheSintetico)
    monkeypatch.setattr(experimento, "ler_imagem", lambda caminho: caminho)
    monkeypatch.setattr(experimento, "_criar_extrator", ExtratorSintetico)

    status_preparo = experimento._preparar(
        SimpleNamespace(dataset=dataset, saida=saida, seed=42), "a" * 64
    )

    assert status_preparo == 0
    manifesto = json.loads((saida / "congelamento.json").read_text(encoding="utf-8"))
    ids_preparados = {imagem.parent.name for imagem in imagens_extraidas}
    assert ids_preparados <= set(divisao.treino) | set(divisao.validacao)
    assert ids_preparados.isdisjoint(identidades_teste_esperadas)
    serializado = json.dumps(manifesto, ensure_ascii=False)
    assert "pseudo-" not in serializado
    assert str(dataset) not in serializado
    assert manifesto["contagens"]["teste"]["estado"] == "nao_extraido_ou_avaliado"

    from scripts import graficos_agrupamento

    monkeypatch.setattr(graficos_agrupamento, "gerar", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        experimento,
        "_carregar_cache_embeddings",
        lambda *_args: np.vstack(
            [
                embedding.vetor
                for cache in caches.values()
                for embedding in cache.values()
            ]
        ),
    )
    antes_teste = len(imagens_extraidas)
    args_avaliacao = SimpleNamespace(
        dataset=dataset,
        saida=saida,
        congelamento=saida / "congelamento.json",
    )
    status_avaliacao = experimento._avaliar(args_avaliacao, "a" * 64)

    assert status_avaliacao == 0
    ids_teste = {imagem.parent.name for imagem in imagens_extraidas[antes_teste:]}
    assert ids_teste == identidades_teste_esperadas
    assert ids_teste.isdisjoint(ids_preparados)
    resultado = json.loads((saida / "resultado.json").read_text(encoding="utf-8"))
    assert resultado["conjunto"] == "teste_independente_por_identidade"
    assert resultado["algoritmos"]["dbscan"]["metricas_externas"]["cobertura"] >= 0.0
    assert len(resultado["graficos"]) == 0

    quantidade_extraida = len(imagens_extraidas)
    assert experimento._avaliar(args_avaliacao, "a" * 64) == 2
    assert len(imagens_extraidas) == quantidade_extraida
