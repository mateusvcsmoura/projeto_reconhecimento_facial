from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import experimento_identificacao_aberta as experimento
from scripts.divisao_por_identidade import dividir_por_identidade
from src.domain.entities.face_embedding import FaceEmbedding


def test_gate_autorizacao_rejeita_documento_ausente_antes_do_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    saida = tmp_path / "saida"
    monkeypatch.setattr(
        experimento,
        "inventariar",
        lambda _: pytest.fail("o dataset foi inventariado antes da autorização"),
    )

    status = experimento.main(
        [
            "preparar",
            "--dataset",
            str(dataset),
            "--autorizacao-dataset",
            str(tmp_path / "autorizacao-inexistente.pdf"),
            "--saida",
            str(saida),
        ]
    )

    assert status == 2
    assert not saida.exists()


def test_gate_autorizacao_rejeita_arquivo_vazio(tmp_path: Path) -> None:
    autorizacao = tmp_path / "autorizacao.txt"
    autorizacao.write_text("", encoding="utf-8")

    with pytest.raises(experimento.AutorizacaoAusente):
        experimento.verificar_autorizacao(autorizacao)


def test_saida_deve_permanecer_no_diretorio_ignorado_da_etapa3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raiz = tmp_path / "projeto"
    monkeypatch.setattr(experimento, "PROJECT_ROOT", raiz)

    assert (
        experimento.validar_diretorio_saida(
            raiz / "avaliacao" / "resultados" / "etapa3"
        )
        == raiz / "avaliacao" / "resultados" / "etapa3"
    )
    with pytest.raises(ValueError, match="avaliacao"):
        experimento.validar_diretorio_saida(raiz / "docs")


def test_reserva_de_teste_e_exclusiva_e_nao_grava_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(experimento, "PROJECT_ROOT", tmp_path)
    saida = tmp_path / "avaliacao" / "resultados" / "etapa3"
    congelamento = {"limiares": {"T0": 0.3}, "assinatura": "opaca"}

    marcador = experimento.reservar_teste_uma_vez(saida, congelamento)

    conteudo = json.loads(marcador.read_text(encoding="utf-8"))
    assert conteudo["hash_congelamento"] == experimento.hash_json(congelamento)
    assert not any("identidade" in chave.lower() for chave in conteudo)
    with pytest.raises(RuntimeError, match="uma única vez"):
        experimento.reservar_teste_uma_vez(saida, congelamento)


def test_manifesto_serializado_nao_inclui_caminhos_ou_identificadores(
    tmp_path: Path,
) -> None:
    manifesto = experimento.criar_manifesto_seguro(
        autorizacao_hash="a" * 64,
        dataset_hash="b" * 64,
        assinatura_divisao="c" * 16,
        seed=42,
        execucao_hash="d" * 64,
        contagens={"treino": {"identidades": 10, "imagens": 20}},
        limiar_t2=0.3,
        suficiencia_t2="amostra_insuficiente",
    )
    serializado = json.dumps(manifesto, ensure_ascii=False)

    assert "identidade-privada" not in serializado
    assert str(tmp_path) not in serializado
    assert manifesto["limiares_congelados"]["T2_validacao_1n"] == 0.3
    assert manifesto["protocolo"] == experimento._configuracao_protocolo()


def test_cache_da_etapa3_isola_dataset_e_particao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(experimento, "CACHE_ETAPA3", tmp_path / "etapa3")
    execucao_a = experimento._id_execucao("B" * 64, "split-a", "auth", 42, {})
    execucao_b = experimento._id_execucao("B" * 64, "split-b", "auth", 42, {})

    cache_validacao = experimento._caminho_cache_particao(execucao_a, "validacao")
    cache_teste = experimento._caminho_cache_particao(execucao_a, "teste")

    assert cache_validacao == tmp_path / "etapa3" / execucao_a / "validacao"
    assert cache_teste == tmp_path / "etapa3" / execucao_a / "teste"
    assert cache_validacao != cache_teste
    assert cache_validacao != experimento.CACHE_PADRAO
    assert experimento._caminho_cache_particao(execucao_b, "validacao") != (
        cache_validacao
    )
    with pytest.raises(ValueError, match="Partição inválida"):
        experimento._caminho_cache_particao(execucao_a, "../teste")


def test_preparar_extrai_somente_validacao_em_cache_isolado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    saida = tmp_path / "avaliacao" / "resultados" / "etapa3"
    cache_raiz = tmp_path / "avaliacao" / "cache" / "etapa3"
    monkeypatch.setattr(experimento, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(experimento, "CACHE_ETAPA3", cache_raiz)

    imagens_por_pessoa = {
        f"pessoa-{indice:02d}": tuple(
            dataset / f"pessoa-{indice:02d}" / f"foto-{foto}.jpg" for foto in range(4)
        )
        for indice in range(30)
    }
    divisao = dividir_por_identidade(imagens_por_pessoa, seed=42)
    hashes = {
        caminho: hashlib.sha256(str(caminho).encode()).hexdigest().upper()
        for imagens in imagens_por_pessoa.values()
        for caminho in imagens
    }
    geradas: list[Path] = []
    caches: list[Path] = []

    class CacheSintetico:
        def __init__(self, diretorio: Path, _config: object) -> None:
            caches.append(diretorio)
            self.valores: dict[str, FaceEmbedding] = {}

        def obter(self, hash_imagem: str) -> FaceEmbedding | None:
            return self.valores.get(hash_imagem)

        def guardar(self, hash_imagem: str, embedding: FaceEmbedding) -> None:
            self.valores[hash_imagem] = embedding

        def salvar(self) -> None:
            return None

    class ExtratorSintetico:
        def preaquecer(self) -> None:
            return None

        def gerar_embedding(self, imagem: Path) -> FaceEmbedding:
            geradas.append(imagem)
            indice = int(imagem.parent.name.split("-")[1])
            vetor = np.zeros(512)
            vetor[indice] = 1.0
            return FaceEmbedding.de_valores(vetor, experimento.MODELO)

    monkeypatch.setattr(
        experimento,
        "inventariar",
        lambda _dataset: SimpleNamespace(imagens_por_pessoa=imagens_por_pessoa),
    )
    monkeypatch.setattr(experimento, "hash_do_arquivo", lambda caminho: hashes[caminho])
    monkeypatch.setattr(experimento, "CacheDeEmbeddings", CacheSintetico)
    monkeypatch.setattr(experimento, "ler_imagem", lambda caminho: caminho)
    monkeypatch.setattr(experimento, "_criar_extrator", ExtratorSintetico)

    status = experimento._preparar(
        Namespace(dataset=dataset, saida=saida, seed=42), "autorizacao-sintetica"
    )

    assert status == 0
    manifesto = json.loads((saida / "congelamento.json").read_text(encoding="utf-8"))
    assert caches == [cache_raiz / manifesto["execucao_sha256"] / "validacao"]
    identidades_extraidas = {imagem.parent.name for imagem in geradas}
    assert identidades_extraidas <= set(divisao.validacao)
    assert identidades_extraidas.isdisjoint(divisao.treino)
    assert identidades_extraidas.isdisjoint(divisao.abrir_teste({"T0": 0.3}))
    assert (saida / "congelamento.json").is_file()

    import scripts.graficos_identificacao_aberta as graficos

    monkeypatch.setattr(graficos, "gerar", lambda *_args, **_kwargs: [])
    geradas.clear()
    status_avaliacao = experimento._avaliar(
        Namespace(
            dataset=dataset,
            saida=saida,
            congelamento=saida / "congelamento.json",
        ),
        "autorizacao-sintetica",
    )

    assert status_avaliacao == 0
    assert caches == [
        cache_raiz / manifesto["execucao_sha256"] / "validacao",
        cache_raiz / manifesto["execucao_sha256"] / "teste",
    ]
    identidades_teste_extraidas = {imagem.parent.name for imagem in geradas}
    assert identidades_teste_extraidas.isdisjoint(identidades_extraidas)
    assert identidades_teste_extraidas <= set(
        dividir_por_identidade(imagens_por_pessoa, seed=42).abrir_teste(
            {"T0": 0.3, "T1": 0.42817932706540435}
        )
    )

    resultado = json.loads((saida / "resultado.json").read_text(encoding="utf-8"))
    assert resultado["comparacao_referencias_status"] == "disponivel_pareada"
    comparacao = resultado["comparacao_referencias"]
    assert set(comparacao["1_referencias_pareadas"]) >= {"T0", "T1"}
    assert set(comparacao["3_referencias_pareadas"]) >= {"T0", "T1"}
    for nome_limiar in ("T0", "T1"):
        metricas_uma = comparacao["1_referencias_pareadas"][nome_limiar]["metricas"]
        metricas_tres = comparacao["3_referencias_pareadas"][nome_limiar]["metricas"]
        assert (
            metricas_uma["consultas_conhecidas"]
            == metricas_tres["consultas_conhecidas"]
        )
        assert (
            metricas_uma["consultas_desconhecidas"]
            == metricas_tres["consultas_desconhecidas"]
        )


def test_avaliar_reserva_holdout_antes_de_inventariar_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(experimento, "PROJECT_ROOT", tmp_path)
    saida = tmp_path / "avaliacao" / "resultados" / "etapa3"
    saida.mkdir(parents=True)
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    autorizacao = tmp_path / "autorizacao.txt"
    autorizacao.write_text("termo fornecido pelo usuário", encoding="utf-8")
    manifesto = {
        "esquema": 2,
        "autorizacao_sha256": experimento.verificar_autorizacao(autorizacao),
        "sem_ids_ou_caminhos": True,
        "protocolo": experimento._configuracao_protocolo(),
    }
    congelamento = saida / "congelamento.json"
    congelamento.write_text(json.dumps(manifesto), encoding="utf-8")
    (saida / "congelamento.sha256").write_text(
        experimento.hash_json(manifesto), encoding="ascii"
    )

    def falhar_apos_reserva(_: Path) -> None:
        assert (saida / ".teste-consumido.json").is_file()
        raise RuntimeError("inventário interceptado no teste")

    monkeypatch.setattr(experimento, "inventariar", falhar_apos_reserva)
    status = experimento.main(
        [
            "avaliar",
            "--dataset",
            str(dataset),
            "--autorizacao-dataset",
            str(autorizacao),
            "--congelamento",
            str(congelamento),
            "--saida",
            str(saida),
        ]
    )

    assert status == 2
    assert (saida / ".teste-consumido.json").is_file()


def test_avaliacao_rejeita_congelamento_alterado_antes_de_reservar_teste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(experimento, "PROJECT_ROOT", tmp_path)
    saida = tmp_path / "avaliacao" / "resultados" / "etapa3"
    saida.mkdir(parents=True)
    autorizacao = tmp_path / "autorizacao.txt"
    autorizacao.write_text("autorização de pesquisa", encoding="utf-8")
    manifesto = {
        "esquema": 2,
        "autorizacao_sha256": experimento.verificar_autorizacao(autorizacao),
        "sem_ids_ou_caminhos": True,
        "protocolo": experimento._configuracao_protocolo(),
    }
    congelamento = saida / "congelamento.json"
    congelamento.write_text(json.dumps(manifesto), encoding="utf-8")
    (saida / "congelamento.sha256").write_text("0" * 64, encoding="ascii")

    status = experimento.main(
        [
            "avaliar",
            "--dataset",
            str(tmp_path / "dataset"),
            "--autorizacao-dataset",
            str(autorizacao),
            "--congelamento",
            str(congelamento),
            "--saida",
            str(saida),
        ]
    )

    assert status == 2
    assert not (saida / ".teste-consumido.json").exists()
