"""Contratos do benchmark sintetico de matching; nao avalia biometria."""

from __future__ import annotations

import json
import os
import tracemalloc
import weakref
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from scripts import benchmark_matcher as benchmark
from src.domain.entities.face_embedding import DTYPE, FaceEmbedding
from src.domain.errors import IdentificacaoAmbigua
from src.domain.services.matcher import (
    Identificacao,
    MatrizDeReferencia,
    PoliticaAmbiguidade,
)

MODELO = "Facenet512"


def emb(vetor: list[float]) -> FaceEmbedding:
    return FaceEmbedding.de_valores(vetor, MODELO)


def test_corpus_e_deterministico_independente_da_ordem_e_tem_cenarios_artificiais() -> (
    None
):
    primeiro = benchmark.gerar_corpus(10, seed=1234, consultas_por_cenario=4)
    benchmark.gerar_corpus(50, seed=1234, consultas_por_cenario=4)
    repetido = benchmark.gerar_corpus(10, seed=1234, consultas_por_cenario=4)

    assert [i for i, _ in primeiro.pares] == list(range(1, 11))
    assert len(primeiro.consultas["referencia"]) == 4
    assert len(primeiro.consultas["ortogonal"]) == 4
    assert len(primeiro.consultas["empate"]) == 4
    for (_, a), (_, b) in zip(primeiro.pares, repetido.pares, strict=True):
        np.testing.assert_array_equal(a.vetor, b.vetor)
    for cenario in primeiro.consultas:
        for a, b in zip(
            primeiro.consultas[cenario], repetido.consultas[cenario], strict=True
        ):
            np.testing.assert_array_equal(a.vetor, b.vetor)

    np.testing.assert_array_equal(
        primeiro.pares[0][1].vetor, primeiro.pares[1][1].vetor
    )
    assert primeiro.pares[0][0] != primeiro.pares[1][0]
    for _, embedding in primeiro.pares:
        assert embedding.dimensao == 512
        assert np.isfinite(embedding.vetor).all()
        assert float(np.linalg.norm(embedding.vetor)) == pytest.approx(1.0, abs=2e-7)
        assert embedding.vetor.dtype == np.dtype(DTYPE)
        assert embedding.vetor[-1] == 0.0
    assert all(query.vetor[-1] == 1.0 for query in primeiro.consultas["ortogonal"])


def test_cenario_referencia_tem_vencedor_unico_da_propria_galeria() -> None:
    corpus = benchmark.gerar_corpus(10, seed=1234, consultas_por_cenario=7)
    referencia = MatrizDeReferencia.de_embeddings(corpus.pares)

    for indice, consulta in enumerate(corpus.consultas["referencia"]):
        resultado = referencia.melhor_candidato(consulta, 0.3)
        esperado = 3 + (indice % 8)
        assert resultado is not None
        assert resultado.aluno_id == esperado


def test_referencia_sequencial_e_independente_do_matcher_vetorizado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consulta = emb([1.0, 0.0])
    pares = [(4, emb([1.0, 0.0])), (8, emb([0.0, 1.0]))]

    def proibido(*_args: object, **_kwargs: object) -> None:
        pytest.fail("a referencia sequencial chamou o matcher vetorizado")

    monkeypatch.setattr(MatrizDeReferencia, "melhor_candidato", proibido)

    assert benchmark.comparar_sequencial(pares, consulta, 0.3, None) == Identificacao(
        aluno_id=4, distancia=0.0
    )


def test_referencia_cobre_galeria_vazia_desconhecido_e_precedencia_do_limiar() -> None:
    consulta = emb([1.0, 0.0])
    politica = PoliticaAmbiguidade(0.0)

    assert benchmark.comparar_sequencial([], consulta, 0.3, politica) is None
    assert (
        benchmark.comparar_sequencial([(7, emb([0.0, 1.0]))], consulta, 0.3, None)
        is None
    )
    assert benchmark.comparar_sequencial(
        [(3, consulta)], consulta, 0.0, politica
    ) == Identificacao(aluno_id=3, distancia=0.0)
    # Sem candidato abaixo do limiar, não deve existir recusa por ambiguidade.
    assert (
        benchmark.comparar_sequencial(
            [(1, emb([0.0, 1.0])), (2, emb([0.0, 1.0]))], consulta, 0.3, politica
        )
        is None
    )


@pytest.mark.parametrize("ordem", [(1, 2), (2, 1)])
def test_referencia_trata_empate_e_ids_repetidos_por_identidade(
    ordem: tuple[int, int],
) -> None:
    consulta = emb([1.0, 0.0])
    duplicatas = {1: emb([1.0, 0.0]), 2: emb([1.0, 0.0])}
    pares = [(aluno_id, duplicatas[aluno_id]) for aluno_id in ordem]

    assert benchmark.comparar_sequencial(pares, consulta, 0.3, None) == Identificacao(
        aluno_id=ordem[0], distancia=0.0
    )
    with pytest.raises(IdentificacaoAmbigua):
        benchmark.comparar_sequencial(pares, consulta, 0.3, PoliticaAmbiguidade(0.0))
    mesma_identidade = [(1, consulta), (1, consulta)]
    assert benchmark.comparar_sequencial(
        mesma_identidade, consulta, 0.3, PoliticaAmbiguidade(0.5)
    ) == Identificacao(aluno_id=1, distancia=0.0)


def test_referencia_aceita_fronteira_exata_de_margem_representavel() -> None:
    consulta = emb([1.0, 0.0])
    pares = [(1, emb([1.0, 0.0])), (2, emb([0.0, 1.0]))]

    resultado = benchmark.comparar_sequencial(
        pares, consulta, 0.3, PoliticaAmbiguidade(1.0)
    )

    assert resultado == Identificacao(aluno_id=1, distancia=0.0)


def test_concorrente_acima_do_limiar_ainda_participa_da_margem() -> None:
    consulta = emb([1.0, 0.0])
    pares = [(1, emb([1.0, 0.0])), (2, emb([0.0, 1.0]))]

    with pytest.raises(IdentificacaoAmbigua):
        benchmark.comparar_sequencial(pares, consulta, 0.3, PoliticaAmbiguidade(1.5))


def test_validacao_compara_decisoes_e_distancias_finitas() -> None:
    corpus = benchmark.gerar_corpus(10, seed=1234, consultas_por_cenario=2)
    referencia = MatrizDeReferencia.de_embeddings(corpus.pares)

    resultado = benchmark.validar_equivalencia(
        corpus.pares,
        referencia,
        corpus.consultas["referencia"] + corpus.consultas["ortogonal"],
        0.3,
        None,
    )

    assert resultado["status"] == "ok"
    assert resultado["comparacoes"] == 4
    assert resultado["divergencias_status_id"] == 0
    assert resultado["erro_maximo_absoluto"] <= 1e-5


def test_validacao_nao_aceita_id_diferente_mesmo_com_distancia_proxima(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = benchmark.gerar_corpus(3, seed=5, consultas_por_cenario=1)
    referencia = MatrizDeReferencia.de_embeddings(corpus.pares)
    resultado_original = MatrizDeReferencia.melhor_candidato

    def id_errado(
        self: MatrizDeReferencia,
        consulta: FaceEmbedding,
        limiar: float,
        *,
        ambiguidade: PoliticaAmbiguidade | None = None,
    ) -> Identificacao | None:
        resultado = resultado_original(self, consulta, limiar, ambiguidade=ambiguidade)
        if resultado is None:
            return None
        return Identificacao(resultado.aluno_id + 100, resultado.distancia)

    monkeypatch.setattr(MatrizDeReferencia, "melhor_candidato", id_errado)
    resultado = benchmark.validar_equivalencia(
        corpus.pares,
        referencia,
        corpus.consultas["referencia"],
        0.3,
        None,
    )

    assert resultado["status"] == "validacao_falhou"
    assert resultado["divergencias_status_id"] == 1


def test_validacao_falha_se_erro_numerico_exceder_tolerancia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = benchmark.gerar_corpus(3, seed=5, consultas_por_cenario=1)
    referencia = MatrizDeReferencia.de_embeddings(corpus.pares)
    original = benchmark._distancias_matriciais

    def deslocadas(
        pares: list[tuple[int, FaceEmbedding]], consulta: FaceEmbedding
    ) -> np.ndarray:
        return original(pares, consulta) + np.float32(1e-3)

    monkeypatch.setattr(benchmark, "_distancias_matriciais", deslocadas)
    resultado = benchmark.validar_equivalencia(
        corpus.pares, referencia, corpus.consultas["referencia"], 0.3, None
    )

    assert resultado["status"] == "validacao_falhou"
    assert resultado["erro_maximo_absoluto"] > 1e-5


def test_validacao_registra_distancias_nao_finitas_sem_aceita_las(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = benchmark.gerar_corpus(3, seed=5, consultas_por_cenario=1)
    referencia = MatrizDeReferencia.de_embeddings(corpus.pares)
    monkeypatch.setattr(
        benchmark,
        "_distancias_matriciais",
        lambda *_args: np.full(3, np.nan, dtype=np.float32),
    )

    resultado = benchmark.validar_equivalencia(
        corpus.pares, referencia, corpus.consultas["referencia"], 0.3, None
    )

    assert resultado["status"] == "validacao_falhou"
    assert resultado["distancias_nao_finitas"] == 1
    assert resultado["erro_maximo_absoluto"] is None
    json.dumps(resultado, allow_nan=False)


def test_wrapper_nao_abafa_excecao_inesperada(monkeypatch: pytest.MonkeyPatch) -> None:
    def quebrado(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("falha inesperada")

    monkeypatch.setattr(benchmark, "comparar_sequencial", quebrado)
    with pytest.raises(RuntimeError, match="falha inesperada"):
        benchmark._executar_com_status(
            "sequencial", [], emb([1.0, 0.0]), 0.3, None, None
        )


def test_resumo_tempos_calcula_percentis_por_chamada() -> None:
    resultado = benchmark.resumir_tempos([1000, 2000, 3000, 4000])

    assert resultado["quantidade"] == 4
    assert resultado["minimo_us"] == pytest.approx(1.0)
    assert resultado["media_us"] == pytest.approx(2.5)
    assert resultado["mediana_us"] == pytest.approx(2.5)
    assert resultado["p95_us"] == pytest.approx(3.85)
    assert resultado["maximo_us"] == pytest.approx(4.0)
    assert resultado["chamadas_por_segundo"] == pytest.approx(400000.0)


@pytest.mark.parametrize("amostras", [[], [0], [-1], [1, 0]])
def test_resumo_tempos_recusa_lista_vazia_e_duracao_nao_positiva(
    amostras: list[int],
) -> None:
    with pytest.raises(ValueError):
        benchmark.resumir_tempos(amostras)


def test_medicao_temporiza_cada_chamada_aquece_sem_amostras_e_alterna_metodos() -> None:
    eventos: list[tuple[str, object]] = []
    consultas = [emb([1.0, 0.0]), emb([0.0, 1.0])]
    consultas_por_identidade = [id(consulta) for consulta in consultas]
    relogio = iter(range(100, 200))

    def clock() -> int:
        valor = next(relogio)
        eventos.append(("clock", valor))
        return valor

    def executor(nome: str) -> Callable[[FaceEmbedding], None]:
        def executar(consulta: FaceEmbedding) -> None:
            eventos.append((nome, id(consulta)))

        return executar

    amostras = benchmark.medir_latencias(
        consultas,
        aquecimento=1,
        rodadas=2,
        executores={
            "sequencial": executor("sequencial"),
            "vetorizado": executor("vetorizado"),
        },
        clock=clock,
    )

    assert len(amostras["sequencial"]) == 4
    assert len(amostras["vetorizado"]) == 4
    assert all(duracao > 0 for valores in amostras.values() for duracao in valores)
    primeiro_relogio = next(
        i for i, evento in enumerate(eventos) if evento[0] == "clock"
    )
    assert all(evento[0] != "clock" for evento in eventos[:primeiro_relogio])
    chamadas = [evento for evento in eventos if evento[0] != "clock"]
    cronometradas = eventos[primeiro_relogio:]
    cronometradas_chamadas = [
        evento for evento in cronometradas if evento[0] != "clock"
    ]
    assert len(cronometradas_chamadas) == 8
    for rodada in range(2):
        bloco = cronometradas_chamadas[rodada * 4 : (rodada + 1) * 4]
        primeiro_metodo = "sequencial" if rodada == 0 else "vetorizado"
        esperado = [
            primeiro_metodo,
            "vetorizado" if primeiro_metodo == "sequencial" else "sequencial",
        ]
        assert [nome for nome, _ in bloco] == [esperado[0]] * 2 + [esperado[1]] * 2
        assert [consulta for _, consulta in bloco[:2]] == consultas_por_identidade
        assert [consulta for _, consulta in bloco[2:]] == consultas_por_identidade
    assert len(chamadas) == 10  # 2 de aquecimento + 8 cronometradas


def test_medicao_rejeita_relogio_com_duracao_nao_positiva() -> None:
    tempos = iter([5, 5])

    with pytest.raises(ValueError, match="dura"):
        benchmark.medir_latencias(
            [emb([1.0, 0.0])],
            aquecimento=1,
            rodadas=1,
            executores={"sequencial": lambda _q: None, "vetorizado": lambda _q: None},
            clock=lambda: next(tempos),
        )


def test_medicao_de_montagem_aquece_e_descarta_fora_do_timer() -> None:
    eventos: list[str] = []
    tempos = iter([10, 12, 20, 23])

    def factory() -> object:
        eventos.append("montagem")
        return object()

    duracoes = benchmark.medir_montagem(factory, rodadas=2, clock=lambda: next(tempos))

    assert len(duracoes) == 2
    assert duracoes == [2, 3]
    assert eventos == ["montagem", "montagem", "montagem"]


def test_protocolo_constroi_e_valida_antes_dos_timers_e_reusa_matriz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eventos: list[str] = []
    timer_ativo = False
    chamadas_matriz = 0
    gerar_original = benchmark.gerar_corpus
    validar_original = benchmark.validar_equivalencia
    matriz_original = MatrizDeReferencia.de_embeddings
    tracemalloc_original = benchmark.medir_pico_tracemalloc

    def gerar(*args: object, **kwargs: object) -> benchmark.CorpusSintetico:
        eventos.append("geracao")
        return gerar_original(*args, **kwargs)

    def validar(*args: object, **kwargs: object) -> dict[str, object]:
        eventos.append("validacao")
        return validar_original(*args, **kwargs)

    def construir_matriz(
        cls: type[MatrizDeReferencia], pares: list[tuple[int, FaceEmbedding]]
    ) -> MatrizDeReferencia:
        nonlocal chamadas_matriz
        chamadas_matriz += 1
        eventos.append("matriz")
        return matriz_original(pares)

    def medir_memoria(funcao: Callable[[], object]) -> int:
        assert not timer_ativo
        eventos.append("memoria")
        return tracemalloc_original(funcao)

    def clock() -> int:
        nonlocal timer_ativo
        timer_ativo = not timer_ativo
        eventos.append("relogio")
        return len(eventos) * 100

    monkeypatch.setattr(benchmark, "gerar_corpus", gerar)
    monkeypatch.setattr(benchmark, "validar_equivalencia", validar)
    monkeypatch.setattr(
        MatrizDeReferencia, "de_embeddings", classmethod(construir_matriz)
    )
    monkeypatch.setattr(benchmark, "medir_pico_tracemalloc", medir_memoria)

    resultado = benchmark._executar_benchmark(
        benchmark.ConfiguracaoBenchmark(
            tamanhos=[3],
            consultas_por_cenario=1,
            rodadas=1,
            aquecimento=1,
            seed=1234,
            margem_ambiguidade=None,
        ),
        clock,
    )

    primeiro_timer = eventos.index("relogio")
    assert all(
        evento in {"geracao", "matriz", "validacao"}
        for evento in eventos[:primeiro_timer]
    )
    assert "geracao" not in eventos[primeiro_timer:]
    assert "validacao" not in eventos[primeiro_timer:]
    assert not timer_ativo
    assert (
        chamadas_matriz == 4
    )  # referência + warm-up/rodada de montagem + passe de memória
    assert resultado["status"] == "ok"


def test_tracemalloc_liga_e_desliga_mesmo_em_erro() -> None:
    assert not tracemalloc.is_tracing()


def test_tracemalloc_descarta_referencia_de_resultado() -> None:
    class ValorMedido:
        pass

    referencia: list[object] = []

    def fabricar() -> object:
        valor = ValorMedido()
        referencia.append(weakref.ref(valor))
        return valor

    benchmark.medir_pico_tracemalloc(fabricar)

    assert referencia[0]() is None
    with pytest.raises(RuntimeError, match="falha medida"):
        benchmark.medir_pico_tracemalloc(
            lambda: (_ for _ in ()).throw(RuntimeError("falha medida"))
        )
    assert not tracemalloc.is_tracing()


def test_tracemalloc_recusa_interromper_tracing_externo() -> None:
    tracemalloc.start()
    try:
        with pytest.raises(RuntimeError, match="ja esta ativo"):
            benchmark.medir_pico_tracemalloc(lambda: None)
        assert tracemalloc.is_tracing()
    finally:
        tracemalloc.stop()


def test_metadados_exportam_apenas_threads_permitidas_e_nao_exigem_cpu_nomeada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark.platform, "processor", lambda: "")
    env = {
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "4",
        "DATABASE_URL": "postgresql://segredo",
        "TOKEN": "segredo",
        "USER": "pessoa",
    }

    ambiente, threads = benchmark.coletar_metadados_ambiente(env)

    assert ambiente["processador"] == "nao_disponivel"
    assert set(threads) == {
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
    }
    assert threads["OPENBLAS_NUM_THREADS"] == "1"
    serialized = json.dumps([ambiente, threads], ensure_ascii=False)
    assert "segredo" not in serialized
    assert "pessoa" not in serialized


def test_configuracao_cli_padrao_preserva_parametros_do_protocolo() -> None:
    args = benchmark._criar_parser().parse_args([])

    assert args.tamanhos == [10, 50, 200, 1000]
    assert args.consultas_por_cenario == 10
    assert args.rodadas == 10
    assert args.aquecimento == 3
    assert args.seed == 1234
    assert args.margem_ambiguidade is None
    assert [nome for nome, _ in benchmark._politicas(args.margem_ambiguidade)] == [
        "sem_politica",
        "empate",
    ]


def test_cli_rejeita_argumentos_invalidos_sem_iniciar_medicoes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        benchmark,
        "medir_latencias",
        lambda *_args, **_kwargs: pytest.fail("medicoes nao deveriam iniciar"),
    )
    invalidos = [
        ["--tamanhos", "3", "3"],
        ["--tamanhos", "2"],
        ["--consultas-por-cenario", "0"],
        ["--rodadas", "0"],
        ["--aquecimento", "0"],
        ["--seed", "-1"],
        ["--margem-ambiguidade", "0"],
        ["--margem-ambiguidade", "-0.1"],
        ["--margem-ambiguidade", "nan"],
        ["--margem-ambiguidade", "inf"],
        ["--margem-ambiguidade", "2.1"],
    ]
    for args in invalidos:
        assert benchmark.main(args) == 2
    assert "usage:" in capsys.readouterr().err


def test_cli_grava_json_agregado_valido_sem_segredos_ou_vetores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "resultado.json"
    monkeypatch.setenv("DATABASE_URL", "postgresql://nao-exportar")
    monkeypatch.setenv("TOKEN", "token-nao-exportar")

    codigo = benchmark.main(
        [
            "--tamanhos",
            "3",
            "--consultas-por-cenario",
            "1",
            "--rodadas",
            "1",
            "--aquecimento",
            "1",
            "--saida-json",
            str(destino),
        ]
    )

    artefato = json.loads(destino.read_text(encoding="utf-8"))
    assert codigo == 0
    assert artefato["schema_version"] == 1
    assert artefato["status"] == "ok"
    assert artefato["validacao"]["divergencias_status_id"] == 0
    assert artefato["validacao"]["comparacoes"] == 6
    assert len(artefato["matching"]) == 12
    assert len(artefato["montagem"]) == 1
    assert len(artefato["comparacoes"]) == 6
    assert all(
        sum(linha["contagens_status_validacao"].values()) == 1
        for linha in artefato["matching"]
    )
    montagem = artefato["montagem"][0]
    assert montagem["payload_embeddings_bytes"] == 3 * 512 * 4
    assert montagem["payload_matriz_teorico_bytes"] == 3 * 512 * 4
    assert {linha["modo"] for linha in artefato["matching"]} == {
        "sem_politica",
        "empate",
    }
    assert {linha["cenario"] for linha in artefato["matching"]} == {
        "referencia",
        "ortogonal",
        "empate",
    }
    texto = destino.read_text(encoding="utf-8")
    assert "nao-exportar" not in texto
    assert "token-nao-exportar" not in texto

    def verificar_agregado(valor: object) -> None:
        if isinstance(valor, dict):
            assert not {"vetor", "embedding"}.intersection(valor)
            for item in valor.values():
                verificar_agregado(item)
        elif isinstance(valor, list):
            assert not (
                len(valor) == 512
                and all(isinstance(item, (int, float)) for item in valor)
            )
            for item in valor:
                verificar_agregado(item)

    verificar_agregado(artefato)
    assert not {"hostname", "username", "caminho_saida"}.intersection(artefato)
    json.dumps(artefato, allow_nan=False)


def test_cli_nao_cria_json_quando_saida_nao_foi_solicitada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert (
        benchmark.main(
            [
                "--tamanhos",
                "3",
                "--consultas-por-cenario",
                "1",
                "--rodadas",
                "1",
                "--aquecimento",
                "1",
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert list(tmp_path.iterdir()) == []


def test_cli_margem_positiva_adiciona_modo_sem_substituir_os_padroes(
    tmp_path: Path,
) -> None:
    destino = tmp_path / "margem.json"
    assert (
        benchmark.main(
            [
                "--tamanhos",
                "3",
                "--consultas-por-cenario",
                "1",
                "--rodadas",
                "1",
                "--aquecimento",
                "1",
                "--margem-ambiguidade",
                "0.25",
                "--saida-json",
                str(destino),
            ]
        )
        == 0
    )
    artefato = json.loads(destino.read_text(encoding="utf-8"))
    assert {linha["modo"] for linha in artefato["matching"]} == {
        "sem_politica",
        "empate",
        "margem_explicita",
    }
    modo = next(
        linha
        for linha in artefato["comparacoes"]
        if linha["modo"] == "margem_explicita"
    )
    assert modo["margem"] == pytest.approx(0.25)


def test_cli_nao_sobrescreve_destino_existente_e_falha_antes_de_medir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "existente.json"
    destino.write_text("manter", encoding="utf-8")
    monkeypatch.setattr(
        benchmark,
        "medir_latencias",
        lambda *_args, **_kwargs: pytest.fail(
            "destino ocupado deve falhar antes da medicao"
        ),
    )

    assert benchmark.main(["--tamanhos", "3", "--saida-json", str(destino)]) == 2
    assert destino.read_text(encoding="utf-8") == "manter"


def test_cli_reserva_destino_exclusivamente_se_houver_corrida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "corrida.json"
    abrir_original = Path.open

    def abrir_com_corrida(
        self: Path, mode: str = "r", *args: object, **kwargs: object
    ) -> object:
        if self == destino and mode == "x":
            descritor = os.open(self, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(descritor, b"concorrente")
            finally:
                os.close(descritor)
        return abrir_original(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", abrir_com_corrida)
    monkeypatch.setattr(
        benchmark,
        "medir_latencias",
        lambda *_args, **_kwargs: pytest.fail("nao deve medir apos colisao de saida"),
    )

    assert benchmark.main(["--tamanhos", "3", "--saida-json", str(destino)]) == 2
    assert destino.read_bytes() == b"concorrente"


def test_cli_divergencia_interrompe_medicao_e_emite_json_sem_performance_valida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "falha.json"
    monkeypatch.setattr(
        MatrizDeReferencia,
        "melhor_candidato",
        lambda *_args, **_kwargs: Identificacao(aluno_id=999, distancia=0.0),
    )
    monkeypatch.setattr(
        benchmark,
        "medir_latencias",
        lambda *_args, **_kwargs: pytest.fail("equivalencia falhou antes da medicao"),
    )

    codigo = benchmark.main(
        [
            "--tamanhos",
            "3",
            "--consultas-por-cenario",
            "1",
            "--rodadas",
            "1",
            "--aquecimento",
            "1",
            "--saida-json",
            str(destino),
        ]
    )

    artefato = json.loads(destino.read_text(encoding="utf-8"))
    assert codigo == 1
    assert artefato["status"] == "validacao_falhou"
    assert artefato["matching"] == []
    assert artefato["comparacoes"] == []
    assert artefato["montagem"] == []
    assert artefato["validacao"]["divergencias_status_id"] > 0


def test_tabela_apresenta_razao_menor_que_um_sem_exigir_speedup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    benchmark._imprimir_tabelas(
        {
            "status": "ok",
            "validacao": {
                "status": "ok",
                "comparacoes": 1,
                "divergencias_status_id": 0,
                "erro_maximo_absoluto": 0.0,
                "tolerancia_absoluta": 1e-5,
                "diagnosticos": [],
            },
            "montagem": [],
            "matching": [],
            "comparacoes": [
                {
                    "n": 3,
                    "cenario": "referencia",
                    "modo": "sem_politica",
                    "razao_mediana_sequencial_sobre_vetorizado": 0.5,
                }
            ],
        }
    )

    assert "0.500" in capsys.readouterr().out


def test_import_da_interface_nao_persiste_artefatos() -> None:
    assert callable(benchmark.main)
