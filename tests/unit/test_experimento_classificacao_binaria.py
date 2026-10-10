"""Testes sem dados biométricos para o protocolo de preparação e congelamento."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import scripts.experimento_classificacao_binaria as experimento
from scripts.classificadores_binarios import caracteristicas_da_distancia
from scripts.experimento_classificacao_binaria import (
    ParesEtapa1,
    carregar_congelamento,
    carregar_pares_etapa1,
    main,
    preparar_experimento,
    validar_metadados_etapa1,
    validar_pares,
    validar_separacao,
)


def _pares(
    conjunto: str,
    base_imagem: int,
    base_identidade: int,
    distancias: tuple[float, float] = (0.1, 0.8),
) -> ParesEtapa1:
    return ParesEtapa1(
        conjunto=conjunto,
        imagem_a=np.array([base_imagem, base_imagem + 2]),
        imagem_b=np.array([base_imagem + 1, base_imagem + 3]),
        identidade_a=np.array([base_identidade, base_identidade]),
        identidade_b=np.array([base_identidade, base_identidade + 1]),
        distancia=np.array(distancias, dtype=np.float64),
        rotulo=np.array([1, 0], dtype=np.int8),
    )


def _arrays_do_split(
    prefixo: str,
    base_imagem: int,
    base_identidade: int,
    distancias_positivas: list[float],
    distancias_negativas: list[float],
) -> dict[str, np.ndarray]:
    quantidade = len(distancias_positivas)
    assert quantidade == len(distancias_negativas)
    imagem_a = np.arange(base_imagem, base_imagem + 2 * quantidade)
    imagem_b = imagem_a + 1
    identidade_a = np.full(2 * quantidade, base_identidade, dtype=np.int32)
    identidade_b = identidade_a.copy()
    identidade_b[quantidade:] += 1
    return {
        f"{prefixo}_imagem_a": imagem_a,
        f"{prefixo}_imagem_b": imagem_b,
        f"{prefixo}_identidade_a": identidade_a,
        f"{prefixo}_identidade_b": identidade_b,
        f"{prefixo}_distancia": np.array(
            distancias_positivas + distancias_negativas, dtype=np.float64
        ),
        f"{prefixo}_rotulo": np.array(
            [1] * quantidade + [0] * quantidade, dtype=np.int8
        ),
    }


def _criar_npz(caminho: Path) -> None:
    dados: dict[str, np.ndarray] = {}
    dados.update(
        _arrays_do_split(
            "treino", 100, 10, [0.1, 0.15, 0.2, 0.25], [0.65, 0.7, 0.75, 0.8]
        )
    )
    dados.update(
        _arrays_do_split(
            "validacao",
            200,
            20,
            [0.12, 0.17, 0.22, 0.27],
            [0.62, 0.68, 0.73, 0.79],
        )
    )
    dados.update(
        _arrays_do_split(
            "teste", 300, 30, [0.11, 0.16, 0.21, 0.26], [0.61, 0.67, 0.72, 0.78]
        )
    )
    np.savez_compressed(caminho, **dados)


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _metadata_sintetica(npz_path: Path) -> dict[str, Any]:
    proveniencia = {
        "dataset": "lfw-sintetico-de-teste",
        "seed_divisao": 42,
        "assinatura_da_divisao": "assinatura-sintetica",
        "limiar_m1_validacao": 0.42817932706540435,
        "conjuntos": {
            nome: {
                "identidades": 2,
                "imagens": 9,
                "pares_genuinos": 4,
                "impostores_usados": 4,
            }
            for nome in ("treino", "validacao", "teste")
        },
    }
    return {
        "sha256_pares_npz": _sha256(npz_path).upper(),
        "hash_proveniencia_s1": hashlib.sha256(
            json.dumps(
                proveniencia,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest().upper(),
        "proveniencia_s1": proveniencia,
        "metadados": {
            "dataset": "lfw-sintetico-de-teste",
            "seed": 42,
            "assinatura_da_divisao": "assinatura-sintetica",
            "teto_principal": 0.001,
            "extracao": {"modelo": "FaceNet512-sintetico", "normalizacao": "L2"},
        },
        "selecao": {"duplicatas_entre_identidades": 0},
        "extracao": {"recebidas": 16, "processadas": 16, "rejeitadas_por_motivo": {}},
        "conjuntos": [],
        "limiar_m1": 0.42817932706540435,
    }


def test_validar_pares_confere_rotulos_com_identidades() -> None:
    inconsistentes = replace(_pares("treino", 1, 10), rotulo=np.array([0, 0]))

    with pytest.raises(ValueError, match="identidades"):
        validar_pares(inconsistentes)


@pytest.mark.parametrize(
    ("validacao", "treino"),
    [
        (_pares("validacao", 20, 10), _pares("treino", 1, 10)),
        (_pares("validacao", 1, 20), _pares("treino", 1, 10)),
    ],
    ids=["identidade-cruzada", "imagem-cruzada"],
)
def test_validar_particoes_detecta_vazamento(
    validacao: ParesEtapa1, treino: ParesEtapa1
) -> None:
    teste = _pares("teste", 40, 30)

    with pytest.raises(ValueError, match="sobreposição"):
        validar_separacao(treino, validacao, teste)


def test_carregar_pares_etapa1_recusa_teste_sem_congelamento(
    tmp_path: Path,
) -> None:
    arquivo = tmp_path / "pares.npz"
    _criar_npz(arquivo)

    with pytest.raises(PermissionError, match="congelamento"):
        carregar_pares_etapa1(arquivo, "teste")


def test_preparar_nao_carrega_arrays_de_teste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.experimento_classificacao_binaria as experimento

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    arquivo_pares = entrada / "pares.npz"
    _criar_npz(arquivo_pares)
    autorizacao = tmp_path / "autorizacao.txt"
    autorizacao.write_text("autorização sintética de teste", encoding="utf-8")
    monkeypatch.setattr(
        experimento,
        "validar_metadados_etapa1",
        lambda _entrada: _metadata_sintetica(arquivo_pares),
    )

    np_load_original = np.load

    class NpzProtegido:
        def __init__(self, caminho: Path, *args: Any, **kwargs: Any) -> None:
            self._arquivo = np_load_original(caminho, *args, **kwargs)

        def __enter__(self) -> NpzProtegido:
            return self

        def __exit__(self, *_args: object) -> None:
            self._arquivo.close()

        def __getitem__(self, chave: str) -> np.ndarray:
            assert not chave.startswith("teste_"), (
                "a preparação acessou o split de teste"
            )
            return self._arquivo[chave]

    monkeypatch.setattr(experimento.np, "load", NpzProtegido)
    congelamento = preparar_experimento(
        entrada, tmp_path / "saida", autorizacao, seed=42
    )

    assert congelamento.is_file()
    assert not (tmp_path / "saida" / "resultados_teste.json").exists()


def test_preparacao_exige_documento_autorizacao_antes_de_np_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.experimento_classificacao_binaria as experimento

    def falha_se_carregar(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("np.load foi chamado antes do gate")

    monkeypatch.setattr(experimento.np, "load", falha_se_carregar)
    with pytest.raises(FileNotFoundError, match="autorização"):
        preparar_experimento(
            tmp_path / "entrada", tmp_path / "saida", tmp_path / "ausente.pdf"
        )

    documento_vazio = tmp_path / "vazio.pdf"
    documento_vazio.write_bytes(b"")
    with pytest.raises(ValueError, match="vazio"):
        preparar_experimento(tmp_path / "entrada", tmp_path / "saida", documento_vazio)


def test_metadados_s1_incompativeis_sao_recusados(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.experimento_classificacao_binaria as experimento

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    pares = entrada / "pares.npz"
    _criar_npz(pares)
    (entrada / "resultado.json").write_text(
        json.dumps(_metadata_sintetica(pares)), encoding="utf-8"
    )
    monkeypatch.setattr(experimento, "HASH_PARES_ETAPA1", _sha256(pares).upper())
    monkeypatch.setattr(experimento, "CONTAGENS_ESPERADAS", {})
    dados = json.loads((entrada / "resultado.json").read_text(encoding="utf-8"))
    dados["metadados"].update(
        {
            "dataset": "lfw",
            "seed": 41,
            "assinatura_da_divisao": experimento.ASSINATURA_DIVISAO_ETAPA1,
        }
    )
    (entrada / "resultado.json").write_text(json.dumps(dados), encoding="utf-8")

    with pytest.raises(ValueError, match=r"[Ss]eed"):
        # O dataset e a assinatura incompatíveis são rejeitados sem ler os pares.
        validar_metadados_etapa1(entrada)


def test_congelamento_serializa_e_recarrega_modelos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.experimento_classificacao_binaria as experimento

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    arquivo_pares = entrada / "pares.npz"
    _criar_npz(arquivo_pares)
    autorizacao = tmp_path / "autorizacao.txt"
    autorizacao.write_text("autorização sintética", encoding="utf-8")
    monkeypatch.setattr(
        experimento,
        "validar_metadados_etapa1",
        lambda _entrada: _metadata_sintetica(arquivo_pares),
    )
    treino = carregar_pares_etapa1(arquivo_pares, "treino")
    validacao = carregar_pares_etapa1(arquivo_pares, "validacao")
    from scripts.classificadores_binarios import treinar_e_selecionar_modelos

    esperados = treinar_e_selecionar_modelos(
        caracteristicas_da_distancia(treino.distancia),
        treino.rotulo,
        caracteristicas_da_distancia(validacao.distancia),
        validacao.rotulo,
        seed=42,
    )

    manifesto = preparar_experimento(entrada, tmp_path / "saida", autorizacao)
    modelos = carregar_congelamento(manifesto, arquivo_pares)
    X_validacao = caracteristicas_da_distancia(validacao.distancia)
    original = esperados["M2"].estimador.predict_proba(X_validacao)
    recarregado = modelos["M2"].estimador.predict_proba(X_validacao)

    np.testing.assert_allclose(original, recarregado)
    assert modelos["M2"].limiar_score == pytest.approx(
        json.loads(manifesto.read_text(encoding="utf-8"))["modelos"]["M2"]["limiar_score"]
    )


def test_carregar_congelamento_verifica_hash_e_metadados(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.experimento_classificacao_binaria as experimento

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    arquivo_pares = entrada / "pares.npz"
    _criar_npz(arquivo_pares)
    autorizacao = tmp_path / "autorizacao.txt"
    autorizacao.write_text("autorização sintética", encoding="utf-8")
    monkeypatch.setattr(
        experimento,
        "validar_metadados_etapa1",
        lambda _entrada: _metadata_sintetica(arquivo_pares),
    )
    manifesto = preparar_experimento(entrada, tmp_path / "saida", autorizacao)
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    modelo_path = manifesto.parent / dados["arquivo_modelos"]
    with modelo_path.open("ab") as arquivo:
        arquivo.write(b"alteracao")

    with pytest.raises(ValueError, match=r"[Hh]ash"):
        carregar_congelamento(manifesto, arquivo_pares)


def test_carregar_congelamento_recusa_metadado_adulterado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.experimento_classificacao_binaria as experimento

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    arquivo_pares = entrada / "pares.npz"
    _criar_npz(arquivo_pares)
    autorizacao = tmp_path / "autorizacao.txt"
    autorizacao.write_text("autorização sintética", encoding="utf-8")
    monkeypatch.setattr(
        experimento,
        "validar_metadados_etapa1",
        lambda _entrada: _metadata_sintetica(arquivo_pares),
    )
    manifesto = preparar_experimento(entrada, tmp_path / "saida", autorizacao)
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    dados["proveniencia_s1"]["seed_divisao"] = 99
    manifesto.write_text(
        json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    assinatura = hashlib.sha256(manifesto.read_bytes()).hexdigest().upper()
    manifesto.with_name("congelamento.sha256").write_text(
        assinatura + "\n", encoding="ascii"
    )

    with pytest.raises(ValueError, match=r"[Hh]ash da proveniência"):
        carregar_congelamento(manifesto, arquivo_pares)


def test_cli_preparar_exige_autorizacao(tmp_path: Path) -> None:
    codigo = main(
        [
            "preparar",
            "--entrada",
            str(tmp_path / "entrada"),
            "--saida",
            str(tmp_path / "saida"),
        ]
    )

    assert codigo == 2


def test_cli_avaliar_exige_congelamento(tmp_path: Path) -> None:
    codigo = main(
        [
            "avaliar",
            "--entrada",
            str(tmp_path / "entrada"),
            "--saida",
            str(tmp_path / "saida"),
        ]
    )

    assert codigo == 2


def test_avaliacao_teste_so_pode_ser_reservada_uma_vez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    etapa2 = tmp_path / "etapa2"
    entrada = tmp_path / "etapa1"
    entrada.mkdir()
    pares = entrada / "pares.npz"
    pares.write_bytes(b"synthetic-pairs")
    congelamento = etapa2 / "congelamento.json"
    congelamento.parent.mkdir()
    congelamento.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(experimento, "ETAPA2_ROOT", etapa2)

    marcador = experimento._reservar_avaliacao_teste(
        entrada, congelamento, seed=42, replicas=25
    )

    assert marcador.is_file()
    registro = json.loads(marcador.read_text(encoding="utf-8"))
    assert registro["seed_bootstrap"] == 42
    assert registro["replicas_bootstrap"] == 25
    with pytest.raises(FileExistsError, match="avaliação iniciada"):
        experimento._reservar_avaliacao_teste(
            entrada, congelamento, seed=99, replicas=50
        )
