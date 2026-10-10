"""Etapa 1 -- calibracao supervisionada do limiar (S1).

Teste de software, nao avaliacao do modelo: fixa que os pares tem o rotulo
certo, que o teste nao influencia a escolha do limiar, que o baseline e o
calibrado sao medidos no mesmo conjunto e que, sem dados suficientes,
nenhum numero sai. Embeddings sinteticos e adaptador duble: nenhum rosto,
nenhum DeepFace, nenhum banco.
"""

from __future__ import annotations

import itertools
import json
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import scripts.calibrar_limiar as cal
from scripts.divisao_por_identidade import (
    DadosInsuficientes,
    Divisao,
    UsoIndevidoDoTeste,
)
from scripts.evaluate_model import Motivo
from scripts.metricas import limiar_para_far_maximo
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import NenhumRostoDetectado
from src.domain.services.matcher import ModeloIncompativel

MODELO = "Facenet512"
DIMENSAO = 16
ADAPTADOR = "src.infrastructure.face_recognition.deepface_adapter"


def _vetor(pessoa: int, variacao: int, ruido: float = 0.15) -> np.ndarray:
    """Centro fixo por pessoa + ruido por imagem: genuinos perto, impostores longe."""
    centro = np.random.default_rng(pessoa).normal(size=DIMENSAO)
    da_imagem = np.random.default_rng(10_000 + 100 * pessoa + variacao)
    return centro + ruido * da_imagem.normal(size=DIMENSAO)


def _embedding(pessoa: int, variacao: int, ruido: float = 0.15) -> FaceEmbedding:
    return FaceEmbedding.de_valores(_vetor(pessoa, variacao, ruido), MODELO)


def _tabela(imagens: list[int], ruido: float = 0.15) -> cal.Tabela:
    nomes = tuple(f"p{i:02d}" for i in range(len(imagens)))
    ids, vetores = [], []
    for i, k in enumerate(imagens):
        for j in range(k):
            ids.append(i)
            vetores.append(_embedding(i, j, ruido).vetor)
    return cal.Tabela(nomes, np.array(ids, dtype=np.int32), np.vstack(vetores))


def _divisao(tabela: cal.Tabela, treino: int, validacao: int) -> Divisao:
    nomes = tabela.nomes
    return Divisao(
        seed=0,
        treino=nomes[:treino],
        validacao=nomes[treino : treino + validacao],
        teste=nomes[treino + validacao :],
    )


def _executar(
    tabela: cal.Tabela, divisao: Divisao, **opcoes: Any
) -> cal.Experimento:
    parametros: dict[str, Any] = {
        "baseline": 0.30,
        "tetos": cal.TETOS_DE_FAR,
        "teto_principal": 0.01,
        "max_impostores": None,
        "replicas": 200,
        "seed": 1,
    }
    return cal.executar(tabela, divisao, **(parametros | opcoes))


# -- selecao --------------------------------------------------------------


def test_selecao_remove_duplicata_exata_e_conta_onde_estava() -> None:
    a, b, c = Path("ana/a.jpg"), Path("ana/b.jpg"), Path("ana/c.jpg")
    d, e, f = Path("bia/d.jpg"), Path("bia/e.jpg"), Path("bia/f.jpg")
    hashes = {a: "h1", b: "h1", c: "h2", d: "h2", e: "h3", f: "h4"}

    selecao = cal.selecionar({"ana": [a, b, c], "bia": [d, e, f]}, hashes, 2, 10, 0)

    assert selecao.imagens_por_pessoa == {"ana": [a, c], "bia": [e, f]}
    assert selecao.duplicatas_na_identidade == 1  # b repete a
    assert selecao.duplicatas_entre_identidades == 1  # d repete c


def test_selecao_descarta_identidade_com_poucas_imagens() -> None:
    imagens = {
        "ana": [Path("ana/1.jpg")],
        "bia": [Path("bia/1.jpg"), Path("bia/2.jpg")],
    }
    hashes = {p: str(p) for lista in imagens.values() for p in lista}

    selecao = cal.selecionar(imagens, hashes, 2, 10, 0)

    assert list(selecao.imagens_por_pessoa) == ["bia"]
    assert selecao.identidades_com_poucas_imagens == 1


def test_teto_de_imagens_por_identidade_e_reprodutivel() -> None:
    imagens = {"ana": [Path(f"ana/{i:02d}.jpg") for i in range(20)]}
    hashes = {p: str(p) for p in imagens["ana"]}

    def sorteadas(seed: int) -> list[Path]:
        return cal.selecionar(imagens, hashes, 2, 5, seed).imagens_por_pessoa["ana"]

    assert sorteadas(7) == sorteadas(7)
    assert len(sorteadas(7)) == 5
    assert cal.selecionar(imagens, hashes, 2, 5, 7).imagens_excedentes == 15
    assert len({tuple(sorteadas(s)) for s in range(10)}) > 1


@pytest.mark.parametrize(("minimo", "maximo"), [(0, 10), (3, 2), (1, 1)])
def test_selecao_com_limites_invalidos_e_recusada(minimo: int, maximo: int) -> None:
    with pytest.raises(ValueError, match="min_imagens"):
        cal.selecionar({}, {}, minimo, maximo, 0)


# -- extracao e cache -----------------------------------------------------


def _config(**troca: str) -> cal.ConfiguracaoDaExtracao:
    campos = {
        "modelo": MODELO,
        "detector": "opencv",
        "deepface": "0.0.92",
        "opencv": "4.13.0.92",
        "tensorflow": "2.21.0",
    } | troca
    return cal.ConfiguracaoDaExtracao(**campos)


def _selecao(pessoas: int, imagens: int) -> tuple[cal.Selecao, dict[Path, str]]:
    por_pessoa = {
        f"pessoa-{i}": [Path(f"pessoa-{i}/foto-{j}.jpg") for j in range(imagens)]
        for i in range(pessoas)
    }
    hashes = {
        p: f"hash-{p.parent.name}-{p.stem}"
        for lista in por_pessoa.values()
        for p in lista
    }
    return cal.Selecao(por_pessoa, 0, 0, 0, 0), hashes


def _gerar_de_caminho(chamadas: list[Path]) -> Any:
    def gerar(caminho: Path) -> FaceEmbedding:
        chamadas.append(caminho)
        if caminho == Path("pessoa-1/foto-0.jpg"):
            raise NenhumRostoDetectado("nada")
        pessoa = int(caminho.parent.name.split("-")[1])
        return _embedding(pessoa, int(caminho.stem.split("-")[1]))

    return gerar


def test_extracao_conta_falhas_e_gera_um_embedding_por_imagem(tmp_path: Path) -> None:
    selecao, hashes = _selecao(pessoas=3, imagens=3)
    chamadas: list[Path] = []
    cache = cal.CacheDeEmbeddings(tmp_path, _config())

    tabela, resumo = cal.extrair(
        selecao, hashes, lambda p: p, _gerar_de_caminho(chamadas), cache
    )

    assert (resumo.recebidas, resumo.processadas) == (9, 8)
    assert resumo.por_motivo() == {Motivo.SEM_ROSTO: 1}
    assert len(chamadas) == 9  # uma inferencia por imagem, nao por par
    assert tabela.vetores.shape == (8, DIMENSAO)
    assert tabela.contagens() == {"pessoa-0": 3, "pessoa-1": 2, "pessoa-2": 3}
    assert len(cache) == 8  # falha nao vai para o cache


def test_cache_reaproveita_embeddings_sem_chamar_o_modelo(tmp_path: Path) -> None:
    selecao, hashes = _selecao(pessoas=3, imagens=3)

    def rodar(chamadas: list[Path]) -> tuple[cal.Tabela, Any]:
        cache = cal.CacheDeEmbeddings(tmp_path, _config())
        gerar = _gerar_de_caminho(chamadas)
        return cal.extrair(selecao, hashes, lambda p: p, gerar, cache)

    tabela_1, _ = rodar([])
    segunda: list[Path] = []
    tabela_2, resumo = rodar(segunda)

    # So a imagem que falhou e reprocessada: falhas sao recontadas.
    assert segunda == [Path("pessoa-1/foto-0.jpg")]
    assert resumo.por_motivo() == {Motivo.SEM_ROSTO: 1}
    np.testing.assert_allclose(tabela_1.vetores, tabela_2.vetores, atol=1e-6)


@pytest.mark.parametrize(
    "troca",
    [{"detector": "retinaface"}, {"tensorflow": "2.22.0"}, {"opencv": "5.0.0"}],
)
def test_qualquer_mudanca_de_versao_ou_configuracao_muda_o_cache(
    troca: dict[str, str],
) -> None:
    assert _config().chave() != _config(**troca).chave()


def test_cache_de_outra_configuracao_fica_em_outro_arquivo(tmp_path: Path) -> None:
    opencv = cal.CacheDeEmbeddings(tmp_path, _config())
    retina = cal.CacheDeEmbeddings(tmp_path, _config(detector="retinaface"))
    assert opencv.caminho != retina.caminho

    opencv.guardar("h", _embedding(0, 0))
    opencv.salvar()
    assert retina.obter("h") is None


def test_cache_com_configuracao_divergente_e_recusado(tmp_path: Path) -> None:
    cache = cal.CacheDeEmbeddings(tmp_path, _config())
    cache.guardar("h", _embedding(0, 0))
    cache.salvar()
    # Arquivo adulterado: nome de uma configuracao, conteudo de outra.
    with np.load(cache.caminho) as dados:
        conteudo = dict(dados)
    conteudo["config"] = np.array(_config(deepface="9.9").como_json())
    with cache.caminho.open("wb") as arquivo:
        np.savez(arquivo, **conteudo)

    with pytest.raises(cal.CacheIncompativel):
        cal.CacheDeEmbeddings(tmp_path, _config())


def test_cache_recusa_embedding_de_outro_modelo(tmp_path: Path) -> None:
    cache = cal.CacheDeEmbeddings(tmp_path, _config())
    with pytest.raises(ModeloIncompativel):
        cache.guardar("h", FaceEmbedding.de_valores(_vetor(0, 0), "ArcFace"))


# -- pares rotulados ------------------------------------------------------


def test_pares_genuinos_e_impostores_com_rotulo_correto() -> None:
    tabela = _tabela([3, 2, 4])
    pares = cal.gerar_pares(tabela, tabela.nomes, "x", None, 0)

    assert pares.genuinas.size == 3 + 1 + 6
    assert pares.impostoras.size == (9 * 9 - (9 + 4 + 16)) // 2
    mesma = pares.identidade_a == pares.identidade_b
    assert np.array_equal(pares.rotulo == 1, mesma)
    origem = tabela.identidade[pares.imagem_a]
    np.testing.assert_array_equal(origem, pares.identidade_a)
    assert np.all(pares.imagem_a < pares.imagem_b)  # sem auto-par, sem repeticao


def test_pares_cobrem_todas_as_combinacoes_sem_amostragem() -> None:
    tabela = _tabela([1, 2, 3])
    pares = cal.gerar_pares(tabela, tabela.nomes, "x", None, 0)
    obtidos = zip(pares.imagem_a.tolist(), pares.imagem_b.tolist(), strict=True)
    assert sorted(obtidos) == list(itertools.combinations(range(6), 2))


def test_distancia_dos_pares_e_a_do_dominio() -> None:
    tabela = _tabela([2, 2])
    pares = cal.gerar_pares(tabela, tabela.nomes, "x", None, 0)
    embeddings = [FaceEmbedding.de_valores(v, MODELO) for v in tabela.vetores]

    for i, j, d in zip(pares.imagem_a, pares.imagem_b, pares.distancia, strict=True):
        esperado = embeddings[i].distancia_cosseno(embeddings[j])
        assert d == pytest.approx(esperado, abs=1e-6)


def test_pares_so_usam_identidades_do_conjunto() -> None:
    tabela = _tabela([2, 2, 2, 2])
    pares = cal.gerar_pares(tabela, ["p01", "p03", "fora-da-tabela"], "x", None, 0)
    usadas = set(pares.identidade_a) | set(pares.identidade_b)
    assert usadas == {1, 3}


def test_amostragem_de_impostores_e_reprodutivel_e_mantem_genuinos() -> None:
    tabela = _tabela([3, 3, 3, 3])
    a = cal.gerar_pares(tabela, tabela.nomes, "x", max_impostores=10, seed=5)
    b = cal.gerar_pares(tabela, tabela.nomes, "x", max_impostores=10, seed=5)

    assert a.impostoras.size == 10
    assert a.impostores_possiveis == 54
    assert a.genuinas.size == 12  # genuinos nunca sao amostrados
    np.testing.assert_array_equal(a.distancia, b.distancia)


def test_pares_de_identidades_contam_pessoas_e_nao_comparacoes() -> None:
    tabela = _tabela([3, 3, 3])
    pares = cal.gerar_pares(tabela, tabela.nomes, "x", None, 0)
    assert pares.impostoras.size == 27
    assert pares.pares_de_identidades_impostores() == 3


# -- calibracao -----------------------------------------------------------


@pytest.mark.parametrize(
    ("teto", "impostores", "pares_de_identidades", "esperado"),
    [
        (0.0, 10**6, 10**6, "sem garantia"),
        (0.01, 299, 10**6, "insuficiente"),
        (0.01, 300, 299, "limitrofe"),
        (0.01, 300, 300, "minimo atendido"),
        (0.001, 2_999, 10**6, "insuficiente"),
    ],
)
def test_suficiencia_pela_regra_do_tres(
    teto: float, impostores: int, pares_de_identidades: int, esperado: str
) -> None:
    assert cal.avaliar_suficiencia(teto, impostores, pares_de_identidades) == esperado


def test_calibracao_usa_a_validacao_e_o_treino_so_como_analise() -> None:
    tabela = _tabela([4] * 12, ruido=0.6)  # sobreposicao: limiares diferem
    treino = cal.gerar_pares(tabela, tabela.nomes[:8], "treino", None, 0)
    validacao = cal.gerar_pares(tabela, tabela.nomes[8:], "validacao", None, 0)

    (calibracao,) = cal.calibrar(validacao, treino, [0.05])

    esperado = limiar_para_far_maximo(validacao.genuinas, validacao.impostoras, 0.05)
    assert calibracao.validacao == esperado
    assert calibracao.treino == limiar_para_far_maximo(
        treino.genuinas, treino.impostoras, 0.05
    )


# -- protocolo: teste lacrado ---------------------------------------------


def test_teste_e_aberto_uma_vez_com_todos_os_limiares_congelados() -> None:
    tabela = _tabela([4] * 12)
    divisao = _divisao(tabela, 8, 2)

    experimento = _executar(tabela, divisao)

    assert divisao.teste_utilizado
    assert divisao.limiares_congelados == experimento.congelados
    assert experimento.congelados[cal.BASELINE] == 0.30  # baseline preservado
    for c in experimento.calibracoes:
        if c.validacao is not None:
            nome = cal.nome_do_metodo(c.teto)
            assert experimento.congelados[nome] == c.validacao.limiar
    with pytest.raises(UsoIndevidoDoTeste):
        divisao.abrir_teste({"outra escolha": 0.5})


def test_dados_de_teste_nao_mudam_o_limiar_escolhido() -> None:
    """Trocar TODOS os vetores do teste nao pode mover nenhum limiar."""
    original = _tabela([4] * 12, ruido=0.5)
    teste = np.isin(original.identidade, [10, 11])
    outros = original.vetores.copy()
    aleatorios = np.random.default_rng(99).normal(size=(int(teste.sum()), DIMENSAO))
    outros[teste] = aleatorios / np.linalg.norm(aleatorios, axis=1, keepdims=True)
    trocada = cal.Tabela(original.nomes, original.identidade, outros)

    a = _executar(original, _divisao(original, 8, 2))
    b = _executar(trocada, _divisao(trocada, 8, 2))

    assert a.congelados == b.congelados
    assert a.resultados != b.resultados  # o teste mudou; a escolha, nao


def test_baseline_e_calibrado_medidos_nos_mesmos_pares() -> None:
    tabela = _tabela([4] * 12, ruido=0.5)
    experimento = _executar(tabela, _divisao(tabela, 8, 2))

    totais = {
        (r.matriz.tp + r.matriz.fn, r.matriz.fp + r.matriz.tn)
        for r in experimento.resultados
    }
    assert len(totais) == 1
    assert {r.metodo for r in experimento.resultados} >= {cal.BASELINE, "FAR<=1%"}


def test_conjunto_sem_pares_genuinos_nao_abre_o_teste() -> None:
    tabela = _tabela([4] * 8 + [1, 1] + [4, 4])  # validacao: 1 imagem por pessoa
    divisao = _divisao(tabela, 8, 2)

    with pytest.raises(DadosInsuficientes, match="validacao"):
        _executar(tabela, divisao)
    assert not divisao.teste_utilizado


def test_teto_principal_inalcancavel_nao_abre_o_teste() -> None:
    """Impostor identico a um genuino na validacao: nenhum tau respeita o teto."""
    tabela = _tabela([4] * 8 + [2, 2] + [4, 4])
    vetores = tabela.vetores.copy()
    base = np.eye(DIMENSAO)
    validacao = np.flatnonzero(np.isin(tabela.identidade, [8, 9]))
    vetores[validacao] = base[[0, 1, 0, 2]]  # p08: e0, e1 | p09: e0 (copia), e2
    trocada = cal.Tabela(tabela.nomes, tabela.identidade, vetores)
    divisao = _divisao(trocada, 8, 2)

    with pytest.raises(DadosInsuficientes, match="Nenhum limiar"):
        _executar(trocada, divisao, teto_principal=0.001)
    assert not divisao.teste_utilizado


# -- bootstrap por identidade ---------------------------------------------


def test_bootstrap_e_reprodutivel_e_o_ic_contem_a_estimativa() -> None:
    tabela = _tabela([4] * 30, ruido=0.6)
    pares = cal.gerar_pares(tabela, tabela.nomes, "teste", None, 0)

    a = cal.bootstrap_por_identidade(pares, {"x": 0.5}, replicas=300, seed=3)
    b = cal.bootstrap_por_identidade(pares, {"x": 0.5}, replicas=300, seed=3)
    np.testing.assert_array_equal(a["x"][0], b["x"][0])

    far_ic, frr_ic = (cal.intervalo_95(r) for r in a["x"])
    assert far_ic.contem(float(np.mean(pares.impostoras <= 0.5)))
    assert frr_ic.contem(float(np.mean(pares.genuinas > 0.5)))
    assert far_ic.superior > far_ic.inferior  # ha incerteza de verdade


def test_bootstrap_com_pesos_unitarios_reproduz_a_estimativa_pontual() -> None:
    """Sanidade da ponderacao: cada pessoa sorteada uma vez = o proprio conjunto."""
    tabela = _tabela([3, 4, 5], ruido=0.6)
    pares = cal.gerar_pares(tabela, tabela.nomes, "teste", None, 0)
    # Com 3 identidades, 2/9 das replicas sorteiam cada uma exatamente uma vez.
    far, frr = cal.bootstrap_por_identidade(pares, {"x": 0.5}, 2000, 0)["x"]

    alvo_far = float(np.mean(pares.impostoras <= 0.5))
    alvo_frr = float(np.mean(pares.genuinas > 0.5))
    assert np.any(np.isclose(far, alvo_far) & np.isclose(frr, alvo_frr))


def test_diferenca_entre_limiares_iguais_e_exatamente_zero() -> None:
    """Replicas pareadas: o mesmo sorteio de pessoas para todos os metodos."""
    tabela = _tabela([4] * 12, ruido=0.5)
    pares = cal.gerar_pares(tabela, tabela.nomes, "teste", None, 0)

    replicas = cal.bootstrap_por_identidade(pares, {"a": 0.4, "b": 0.4}, 100, 0)

    (far_a, frr_a), (far_b, frr_b) = replicas["a"], replicas["b"]
    assert cal.intervalo_95(far_a - far_b) == cal.Intervalo(0.0, 0.0)
    assert cal.intervalo_95(frr_a - frr_b) == cal.Intervalo(0.0, 0.0)


def test_sem_impostor_aceito_a_regra_do_tres_usa_pares_de_identidades() -> None:
    """16 comparacoes entre 2 pessoas sao 1 par de identidades, nao 16 provas."""
    tabela = _tabela([4] * 12)  # separacao limpa
    experimento = _executar(tabela, _divisao(tabela, 8, 2))
    base = next(r for r in experimento.resultados if r.metodo == cal.BASELINE)

    assert (base.matriz.fp, base.matriz.tn) == (0, 16)
    assert base.pares_de_identidades == 1
    assert base.far_maximo_regra_do_tres == pytest.approx(3.0)
    assert base.ic_far == cal.Intervalo(0.0, 0.0)


@pytest.mark.parametrize("tetos", [(0.0, 0.0004), (0.0005, 0.001), (0.01, 0.05)])
def test_tetos_diferentes_nunca_tem_o_mesmo_nome(tetos: tuple[float, float]) -> None:
    """Nomes iguais sobrescreveriam um limiar congelado por outro."""
    a, b = (cal.nome_do_metodo(t) for t in tetos)
    assert a != b


def test_nomes_dos_tetos_padrao() -> None:
    nomes = [cal.nome_do_metodo(t) for t in cal.TETOS_DE_FAR]
    assert nomes == ["FAR<=0%", "FAR<=0.1%", "FAR<=1%", "FAR<=5%"]


@pytest.mark.parametrize(
    ("inferior", "superior", "esperado"),
    [
        (float("nan"), float("nan"), "IC indefinido"),
        (-0.02, 0.01, "IC inclui 0 (diferenca nao sustentada)"),
        (-0.02, -0.01, "diminuiu (IC exclui 0)"),
        (0.001, 0.003, "aumentou (IC exclui 0)"),
    ],
)
def test_veredito_nunca_afirma_diferenca_com_ic_indefinido(
    inferior: float, superior: float, esperado: str
) -> None:
    assert cal._veredito(cal.Intervalo(inferior, superior)) == esperado


def test_rotulos_embaralhados_derrubam_a_auc_para_perto_de_meio() -> None:
    tabela = _tabela([5] * 40, ruido=0.3)
    experimento = _executar(tabela, _divisao(tabela, 24, 8))

    assert experimento.auc > 0.95
    assert abs(experimento.auc_rotulos_embaralhados - 0.5) < 0.1


# -- CLI ------------------------------------------------------------------


def _dataset(raiz: Path, pessoas: int, imagens: int) -> Path:
    dataset = raiz / "dataset"
    for i in range(pessoas):
        pasta = dataset / f"pessoa-{i}"
        pasta.mkdir(parents=True)
        for j in range(imagens):
            # Conteudo unico: arquivos iguais seriam removidos como duplicata.
            (pasta / f"foto-{j}.jpg").write_bytes(f"{i}-{j}".encode())
    return dataset


class AdaptadorFalso:
    instancias = 0
    chamadas = 0

    def __init__(
        self, modelo: str, detector: str, anti_spoofing: bool = True
    ) -> None:
        assert anti_spoofing is False  # Avaliacao A
        AdaptadorFalso.instancias += 1

    def preaquecer(self) -> None:
        pass

    def gerar_embedding(self, caminho: Path) -> FaceEmbedding:
        AdaptadorFalso.chamadas += 1
        if caminho.read_bytes() == b"sem-rosto":
            raise NenhumRostoDetectado("nada")
        pessoa = int(caminho.parent.name.split("-")[1])
        return _embedding(pessoa, int(caminho.stem.split("-")[1]), ruido=0.4)


@pytest.fixture
def ambiente(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Adaptador, leitura, settings e graficos dubles.

    Devolve a lista de experimentos entregues aos graficos.
    """
    modulo = types.ModuleType(ADAPTADOR)
    modulo.DeepFaceAdapter = AdaptadorFalso  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, ADAPTADOR, modulo)
    monkeypatch.setattr(AdaptadorFalso, "instancias", 0)
    monkeypatch.setattr(AdaptadorFalso, "chamadas", 0)
    monkeypatch.setattr(cal, "ler_imagem", lambda caminho: caminho)
    monkeypatch.setattr(cal, "configurar_logging", lambda _nivel: None)
    monkeypatch.setattr(
        cal,
        "get_settings",
        lambda: types.SimpleNamespace(
            face_model=MODELO, face_detector="opencv", face_threshold=0.30
        ),
    )
    desenhados: list[Any] = []

    def gerar(_destino: Path, experimento: Any) -> list[Path]:
        desenhados.append(experimento)
        return []

    monkeypatch.setattr(
        cal, "_carregar_graficos", lambda: types.SimpleNamespace(gerar=gerar)
    )
    return desenhados


def _argv(tmp_path: Path, dataset: Path) -> list[str]:
    return [
        "--dataset", str(dataset), "--saida", str(tmp_path / "saida"),
        "--cache", str(tmp_path / "cache"), "--replicas", "50", "--far-alvo", "0.01",
    ]  # fmt: skip


def test_cli_executa_o_protocolo_e_grava_resultados_sem_nomes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], ambiente: list[Any]
) -> None:
    dataset = _dataset(tmp_path, pessoas=12, imagens=4)
    (dataset / "pessoa-3" / "foto-0.jpg").write_bytes(b"sem-rosto")

    assert cal.main(_argv(tmp_path, dataset)) == 0

    saida = capsys.readouterr().out
    assert "Calibracao na VALIDACAO" in saida
    assert "TESTE (aberto uma unica vez)" in saida
    assert "sem rosto detectado" in saida
    assert len(ambiente) == 1  # graficos desenhados do experimento real

    texto = (tmp_path / "saida" / "resultado.json").read_text()
    resultado = json.loads(texto)
    assert "pessoa-" not in texto  # identidades so como indices
    assert resultado["limiares_congelados"]["baseline"] == 0.30
    assert resultado["metodo_principal"] == "FAR<=1%"
    assert resultado["extracao"]["rejeitadas_por_motivo"] == {"sem rosto detectado": 1}
    assert {m["metodo"] for m in resultado["teste"]} >= {"baseline", "FAR<=1%"}

    with np.load(tmp_path / "saida" / "pares.npz") as pares:
        esperados = {"teste_distancia", "validacao_rotulo", "treino_identidade_a"}
        assert esperados <= set(pares.files)

    # So escreve em --saida e --cache: nada de .env, settings ou banco.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cache", "dataset", "saida"]


def test_cli_segunda_execucao_reaproveita_o_cache_e_reproduz(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], ambiente: list[Any]
) -> None:
    dataset = _dataset(tmp_path, pessoas=12, imagens=4)
    argv = _argv(tmp_path, dataset)

    cal.main(argv)
    primeira = (tmp_path / "saida" / "resultado.json").read_text()
    chamadas = AdaptadorFalso.chamadas
    cal.main(argv)

    assert AdaptadorFalso.chamadas == chamadas  # nenhuma inferencia nova
    assert (tmp_path / "saida" / "resultado.json").read_text() == primeira


def test_cli_sem_matplotlib_aborta_antes_de_carregar_o_modelo(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    ambiente: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def sem_matplotlib() -> types.ModuleType:
        raise ImportError("No module named 'matplotlib'")

    monkeypatch.setattr(cal, "_carregar_graficos", sem_matplotlib)
    dataset = _dataset(tmp_path, pessoas=12, imagens=2)

    assert cal.main(_argv(tmp_path, dataset)) == 2
    assert "requirements-experimentos" in capsys.readouterr().err
    assert AdaptadorFalso.instancias == 0


def test_cli_com_dataset_pequeno_nao_imprime_metricas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], ambiente: list[Any]
) -> None:
    dataset = _dataset(tmp_path, pessoas=5, imagens=3)

    assert cal.main(_argv(tmp_path, dataset)) == 2

    capturado = capsys.readouterr()
    assert "ao menos 6" in capturado.err
    assert "FAR" not in capturado.out
    assert not (tmp_path / "saida").exists()


@pytest.mark.parametrize(
    "argumento", [["--far-alvo", "0"], ["--far-alvo", "1.5"], ["--replicas", "0"]]
)
def test_cli_recusa_parametros_invalidos(tmp_path: Path, argumento: list[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        cal.main(["--dataset", str(tmp_path), *argumento])
    assert saida.value.code == 2


# -- graficos (so com matplotlib, no ambiente experimental) ---------------


def test_graficos_sao_gerados_a_partir_do_experimento(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    from scripts import graficos_calibracao

    tabela = _tabela([4] * 12, ruido=0.5)
    experimento = _executar(tabela, _divisao(tabela, 8, 2))

    arquivos = graficos_calibracao.gerar(tmp_path, experimento)

    assert [a.name for a in arquivos] == [
        "1-histograma-distancias.svg",
        "2-far-frr-por-limiar.svg",
        "3-matrizes-de-confusao.svg",
        "4-roc.svg",
        "5-tabela-metricas.svg",
    ]
    for arquivo in arquivos:
        assert "<svg" in arquivo.read_text()


def test_curvas_grandes_sao_rarefeitas_sem_perder_as_pontas() -> None:
    pytest.importorskip("matplotlib")
    from scripts.graficos_calibracao import _rarear

    indices = _rarear(800_000)
    assert indices[0] == 0 and indices[-1] == 799_999
    assert indices.size <= 8000
    assert np.all(np.diff(indices) > 0)
    np.testing.assert_array_equal(_rarear(10), np.arange(10))
