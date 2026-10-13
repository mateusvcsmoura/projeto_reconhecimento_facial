"""Benchmark de engenharia do matching, apenas com embeddings sinteticos.

Compara o matcher vetorizado com um oraculo independente em laço, valida as
decisoes antes de cronometrar e separa latencia, montagem e memoria rastreada.
Os resultados nao medem inferencia, acuracia biometrica, FPS nem memoria RSS.

    python -m scripts.benchmark_matcher
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TextIO, cast

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.entities.face_embedding import DTYPE, FaceEmbedding
from src.domain.errors import IdentificacaoAmbigua
from src.domain.services.matcher import (
    Identificacao,
    MatrizDeReferencia,
    PoliticaAmbiguidade,
)

MODELO = "Facenet512"
DIMENSAO = 512
LIMIAR = 0.30
TAMANHOS_PADRAO = (10, 50, 200, 1000)
TOLERANCIA_ABSOLUTA = 1e-5
CENARIOS = ("referencia", "ortogonal", "empate")
METODOS = ("sequencial", "vetorizado")
VARIAVEIS_THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")

Clock = Callable[[], int]
TempoSummary = dict[str, float | int]
Executor = Callable[[FaceEmbedding], object]


@dataclass(frozen=True, slots=True)
class CorpusSintetico:
    pares: list[tuple[int, FaceEmbedding]]
    consultas: dict[str, list[FaceEmbedding]]


@dataclass(frozen=True, slots=True)
class ResultadoComparacao:
    status: str
    aluno_id: int | None = None
    distancia: float | None = None


@dataclass(frozen=True, slots=True)
class ConfiguracaoBenchmark:
    tamanhos: list[int]
    consultas_por_cenario: int
    rodadas: int
    aquecimento: int
    seed: int
    margem_ambiguidade: float | None


def gerar_corpus(n: int, seed: int, consultas_por_cenario: int) -> CorpusSintetico:
    """Gera corpus 512D deterministico; seus vetores nao representam rostos."""
    if n < 3:
        raise ValueError("O tamanho do corpus deve ser pelo menos 3.")
    if consultas_por_cenario < 1:
        raise ValueError("consultas_por_cenario deve ser pelo menos 1.")

    rng = np.random.default_rng(np.random.SeedSequence([seed, n]))
    valores = rng.normal(size=(n, DIMENSAO - 1))
    valores = np.column_stack((valores, np.zeros(n, dtype=np.float64)))
    embeddings = [FaceEmbedding.de_valores(linha, MODELO) for linha in valores]
    # Um empate artificial entre identidades distintas exercita o caminho de
    # rejeicao sem usar ou simular observacoes de pessoas.
    embeddings[1] = FaceEmbedding.de_valores(embeddings[0].vetor, MODELO)
    pares = [(indice + 1, embedding) for indice, embedding in enumerate(embeddings)]

    referencias = [pares[aluno_id - 1][1] for aluno_id in range(3, n + 1)]
    consultas_referencia = [
        FaceEmbedding.de_valores(referencias[indice % len(referencias)].vetor, MODELO)
        for indice in range(consultas_por_cenario)
    ]
    vetor_ortogonal = np.zeros(DIMENSAO, dtype=DTYPE)
    vetor_ortogonal[-1] = 1.0
    ortogonal = FaceEmbedding.de_valores(vetor_ortogonal, MODELO)
    consultas_ortogonais = [
        FaceEmbedding.de_valores(ortogonal.vetor, MODELO)
        for _ in range(consultas_por_cenario)
    ]
    consultas_empate = [
        FaceEmbedding.de_valores(embeddings[0].vetor, MODELO)
        for _ in range(consultas_por_cenario)
    ]
    return CorpusSintetico(
        pares=pares,
        consultas={
            "referencia": consultas_referencia,
            "ortogonal": consultas_ortogonais,
            "empate": consultas_empate,
        },
    )


def comparar_sequencial(
    pares: list[tuple[int, FaceEmbedding]],
    consulta: FaceEmbedding,
    limiar: float,
    ambiguidade: PoliticaAmbiguidade | None,
) -> Identificacao | None:
    """Referencia independente: um produto NumPy por referencia, em ordem."""
    if ambiguidade is not None and not isinstance(ambiguidade, PoliticaAmbiguidade):
        raise ValueError("ambiguidade deve ser PoliticaAmbiguidade ou None.")
    if not pares:
        return None

    melhor_id: int | None = None
    melhor_distancia = math.inf
    distancias: list[tuple[int, float]] = []
    for aluno_id, embedding in pares:
        distancia = consulta.distancia_cosseno(embedding)
        distancias.append((aluno_id, distancia))
        if distancia < melhor_distancia:
            melhor_id = aluno_id
            melhor_distancia = distancia

    if melhor_id is None or melhor_distancia > limiar:
        return None

    if ambiguidade is not None:
        segunda_distancia = min(
            (distancia for aluno_id, distancia in distancias if aluno_id != melhor_id),
            default=None,
        )
        if segunda_distancia is not None:
            gap = segunda_distancia - melhor_distancia
            if gap <= 0.0 or gap < ambiguidade.margem_minima:
                raise IdentificacaoAmbigua()

    return Identificacao(aluno_id=melhor_id, distancia=melhor_distancia)


def _distancias_matriciais(
    pares: list[tuple[int, FaceEmbedding]], consulta: FaceEmbedding
) -> np.ndarray:
    """Calcula independentemente a expressão e o dtype usados pelo matcher."""
    if not pares:
        return np.empty(0, dtype=DTYPE)
    matriz = np.vstack([embedding.vetor for _, embedding in pares]).astype(
        DTYPE, copy=False
    )
    return 1.0 - matriz @ consulta.vetor


def _executar_com_status(
    metodo: str,
    pares: list[tuple[int, FaceEmbedding]],
    consulta: FaceEmbedding,
    limiar: float,
    ambiguidade: PoliticaAmbiguidade | None,
    referencia: MatrizDeReferencia | None,
) -> ResultadoComparacao:
    """Converte os tres resultados de decisao no mesmo formato agregado."""
    try:
        if metodo == "sequencial":
            resultado = comparar_sequencial(pares, consulta, limiar, ambiguidade)
        elif metodo == "vetorizado":
            if referencia is None:
                raise ValueError("O matcher vetorizado exige uma matriz pronta.")
            resultado = referencia.melhor_candidato(
                consulta, limiar, ambiguidade=ambiguidade
            )
        else:
            raise ValueError(f"Metodo desconhecido: {metodo}.")
    except IdentificacaoAmbigua:
        return ResultadoComparacao(status="ambiguo")

    if resultado is None:
        return ResultadoComparacao(status="desconhecido")
    return ResultadoComparacao(
        status="aceito", aluno_id=resultado.aluno_id, distancia=resultado.distancia
    )


def validar_equivalencia(
    pares: list[tuple[int, FaceEmbedding]],
    referencia: MatrizDeReferencia,
    consultas: list[FaceEmbedding],
    limiar: float,
    ambiguidade: PoliticaAmbiguidade | None,
) -> dict[str, object]:
    """Valida status, ID aceito e distancias antes de qualquer medicao."""
    contagens = {
        metodo: {status: 0 for status in ("aceito", "desconhecido", "ambiguo")}
        for metodo in METODOS
    }
    divergencias_status_id = 0
    divergencias_numericas = 0
    distancias_nao_finitas = 0
    erro_maximo: float | None = None
    diagnosticos: list[str] = []

    for indice, consulta in enumerate(consultas):
        sequencial = _executar_com_status(
            "sequencial", pares, consulta, limiar, ambiguidade, None
        )
        vetorizado = _executar_com_status(
            "vetorizado", pares, consulta, limiar, ambiguidade, referencia
        )
        resultados = (("sequencial", sequencial), ("vetorizado", vetorizado))
        for metodo, resultado in resultados:
            contagens[metodo][resultado.status] += 1

        if sequencial.status != vetorizado.status or (
            sequencial.status == "aceito" and sequencial.aluno_id != vetorizado.aluno_id
        ):
            divergencias_status_id += 1
            if len(diagnosticos) < 20:
                diagnosticos.append(
                    f"consulta {indice}: sequencial={sequencial.status}/"
                    f"{sequencial.aluno_id}, vetorizado={vetorizado.status}/"
                    f"{vetorizado.aluno_id}"
                )
        if sequencial.status == "aceito" and vetorizado.status == "aceito":
            assert sequencial.distancia is not None and vetorizado.distancia is not None
            if not np.isclose(
                sequencial.distancia,
                vetorizado.distancia,
                rtol=0.0,
                atol=TOLERANCIA_ABSOLUTA,
            ):
                divergencias_numericas += 1
                if len(diagnosticos) < 20:
                    diagnosticos.append(
                        f"consulta {indice}: distancia aceita divergente"
                    )

        distancias_laco = np.asarray(
            [consulta.distancia_cosseno(embedding) for _, embedding in pares],
            dtype=np.float64,
        )
        distancias_matriz = np.asarray(
            _distancias_matriciais(pares, consulta), dtype=np.float64
        )
        distancias_finitas = (
            np.isfinite(distancias_laco).all() and np.isfinite(distancias_matriz).all()
        )
        if not distancias_finitas:
            distancias_nao_finitas += 1
            if len(diagnosticos) < 20:
                diagnosticos.append(f"consulta {indice}: distancia nao finita")
        elif distancias_laco.shape != distancias_matriz.shape:
            divergencias_numericas += 1
            if len(diagnosticos) < 20:
                diagnosticos.append(
                    f"consulta {indice}: dimensoes de distancia divergentes"
                )
        elif distancias_laco.size:
            erro = float(np.max(np.abs(distancias_laco - distancias_matriz)))
            erro_maximo = erro if erro_maximo is None else max(erro_maximo, erro)
            if erro > TOLERANCIA_ABSOLUTA:
                divergencias_numericas += 1
                if len(diagnosticos) < 20:
                    diagnosticos.append(
                        f"consulta {indice}: erro numerico maximo {erro:.9g}"
                    )

    falhou = bool(
        divergencias_status_id or divergencias_numericas or distancias_nao_finitas
    )
    return {
        "status": "validacao_falhou" if falhou else "ok",
        "comparacoes": len(consultas),
        "divergencias_status_id": divergencias_status_id,
        "divergencias_numericas": divergencias_numericas,
        "distancias_nao_finitas": distancias_nao_finitas,
        "erro_maximo_absoluto": erro_maximo,
        "tolerancia_absoluta": TOLERANCIA_ABSOLUTA,
        "contagens_status": contagens,
        "diagnosticos": diagnosticos,
    }


def resumir_tempos(amostras_ns: list[int]) -> TempoSummary:
    """Resume observacoes de chamadas individuais; entrada e nanossegundos."""
    if not amostras_ns or any(
        isinstance(amostra, bool) or not isinstance(amostra, int) or amostra <= 0
        for amostra in amostras_ns
    ):
        raise ValueError("As duracoes devem ser inteiros positivos e nao vazios.")
    total = sum(amostras_ns)
    percentil = float(np.percentile(np.asarray(amostras_ns), 95, method="linear"))
    return {
        "quantidade": len(amostras_ns),
        "minimo_us": min(amostras_ns) / 1000.0,
        "media_us": statistics.mean(amostras_ns) / 1000.0,
        "mediana_us": statistics.median(amostras_ns) / 1000.0,
        "p95_us": percentil / 1000.0,
        "maximo_us": max(amostras_ns) / 1000.0,
        "chamadas_por_segundo": len(amostras_ns) * 1_000_000_000 / total,
    }


def medir_latencias(
    consultas: Sequence[FaceEmbedding],
    aquecimento: int,
    rodadas: int,
    executores: Mapping[str, Callable[[FaceEmbedding], object]],
    clock: Clock | None = None,
) -> dict[str, list[int]]:
    """Mede uma chamada por amostra, alternando a ordem dos dois metodos."""
    if not consultas or aquecimento < 1 or rodadas < 1:
        raise ValueError("Consultas, aquecimento e rodadas devem ser positivos.")
    if set(executores) != set(METODOS):
        raise ValueError(
            "Sao necessarios exatamente os metodos sequencial e vetorizado."
        )
    relogio = clock or time.perf_counter_ns
    amostras: dict[str, list[int]] = {metodo: [] for metodo in METODOS}
    for metodo in METODOS:
        executar = executores[metodo]
        for indice in range(aquecimento):
            executar(consultas[indice % len(consultas)])

    for rodada in range(rodadas):
        ordem = METODOS if rodada % 2 == 0 else tuple(reversed(METODOS))
        for metodo in ordem:
            executar = executores[metodo]
            for consulta in consultas:
                inicio = relogio()
                executar(consulta)
                duracao = relogio() - inicio
                if duracao <= 0:
                    raise ValueError("O relogio produziu duracao nao positiva.")
                amostras[metodo].append(duracao)
    return amostras


def medir_montagem(
    factory: Callable[[], object], rodadas: int, clock: Clock | None = None
) -> list[int]:
    """Cronometra construcoes com entradas prontas e descarta cada instancia."""
    if rodadas < 1:
        raise ValueError("rodadas deve ser pelo menos 1.")
    relogio = clock or time.perf_counter_ns
    aquecimento = factory()
    del aquecimento
    duracoes: list[int] = []
    for _ in range(rodadas):
        inicio = relogio()
        resultado = factory()
        duracao = relogio() - inicio
        del resultado
        if duracao <= 0:
            raise ValueError("O relogio produziu duracao nao positiva.")
        duracoes.append(duracao)
    return duracoes


def medir_pico_tracemalloc(funcao: Callable[[], object]) -> int:
    """Mede pico Python rastreado em um passe isolado, sem tocar em tracing externo."""
    if tracemalloc.is_tracing():
        raise RuntimeError("tracemalloc ja esta ativo; o benchmark nao o reiniciara.")
    tracemalloc.start()
    try:
        resultado = funcao()
        del resultado
        _, pico = tracemalloc.get_traced_memory()
        return int(pico)
    finally:
        tracemalloc.stop()


def coletar_metadados_ambiente(
    ambiente: Mapping[str, str] | None = None,
) -> tuple[dict[str, object], dict[str, str]]:
    """Retorna somente identificacao tecnica autorizada, sem exportar todo env."""
    env = os.environ if ambiente is None else ambiente
    processador = platform.processor().strip() or "nao_disponivel"
    relogio = time.get_clock_info("perf_counter")
    metadados: dict[str, object] = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "sistema": platform.system(),
        "release": platform.release(),
        "arquitetura": platform.machine() or "nao_disponivel",
        "processador": processador,
        "cpus_logicas": os.cpu_count(),
        "relogio": {
            "implementacao": relogio.implementation,
            "resolucao_segundos": relogio.resolution,
            "monotonico": relogio.monotonic,
            "ajustavel": relogio.adjustable,
        },
    }
    threads = {nome: env.get(nome, "nao_definido") for nome in VARIAVEIS_THREADS}
    return metadados, threads


def _descartar_resultados_matching(
    consultas: Sequence[FaceEmbedding],
    executar: Callable[[FaceEmbedding], object],
) -> None:
    for consulta in consultas:
        resultado = executar(consulta)
        del resultado


def _construir_matriz(
    pares: list[tuple[int, FaceEmbedding]],
) -> MatrizDeReferencia:
    return MatrizDeReferencia.de_embeddings(pares)


def _criar_executores_matching(
    pares: list[tuple[int, FaceEmbedding]],
    referencia: MatrizDeReferencia,
    politica: PoliticaAmbiguidade | None,
) -> dict[str, Callable[[FaceEmbedding], object]]:
    def executar_sequencial(consulta: FaceEmbedding) -> object:
        return _executar_com_status(
            "sequencial", pares, consulta, LIMIAR, politica, None
        )

    def executar_vetorizado(consulta: FaceEmbedding) -> object:
        return _executar_com_status(
            "vetorizado", pares, consulta, LIMIAR, politica, referencia
        )

    return {
        "sequencial": executar_sequencial,
        "vetorizado": executar_vetorizado,
    }


def _inteiro_positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("informe um inteiro") from exc
    if valor < 1:
        raise argparse.ArgumentTypeError("informe um inteiro maior ou igual a 1")
    return valor


def _tamanho(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("informe um inteiro") from exc
    if valor < 3:
        raise argparse.ArgumentTypeError("cada tamanho deve ser inteiro >= 3")
    return valor


def _seed(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("informe um inteiro") from exc
    if valor < 0:
        raise argparse.ArgumentTypeError("a seed deve ser >= 0")
    return valor


def _margem(texto: str) -> float:
    try:
        valor = float(texto)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("informe um numero") from exc
    if not math.isfinite(valor) or not 0.0 < valor <= 2.0:
        raise argparse.ArgumentTypeError("a margem deve ser finita e estar em (0, 2]")
    return valor


def _codigo_saida(exc: SystemExit) -> int:
    return exc.code if isinstance(exc.code, int) else 2


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compara matching vetorizado e sequencial em dados sinteticos; "
            "nao mede inferencia nem desempenho biometrico."
        )
    )
    parser.add_argument(
        "--tamanhos",
        nargs="+",
        type=_tamanho,
        default=list(TAMANHOS_PADRAO),
        help="tamanhos unicos de galeria (padrao: 10 50 200 1000)",
    )
    parser.add_argument("--consultas-por-cenario", type=_inteiro_positivo, default=10)
    parser.add_argument("--rodadas", type=_inteiro_positivo, default=10)
    parser.add_argument("--aquecimento", type=_inteiro_positivo, default=3)
    parser.add_argument("--seed", type=_seed, default=1234)
    parser.add_argument("--margem-ambiguidade", type=_margem)
    parser.add_argument(
        "--saida-json",
        type=Path,
        help="arquivo JSON agregado novo; um destino existente nunca e sobrescrito",
    )
    return parser


def _politicas(
    margem: float | None,
) -> list[tuple[str, PoliticaAmbiguidade | None]]:
    politicas: list[tuple[str, PoliticaAmbiguidade | None]] = [
        ("sem_politica", None),
        ("empate", PoliticaAmbiguidade(0.0)),
    ]
    if margem is not None:
        politicas.append(("margem_explicita", PoliticaAmbiguidade(margem)))
    return politicas


def _nova_validacao() -> dict[str, object]:
    return {
        "status": "ok",
        "comparacoes": 0,
        "divergencias_status_id": 0,
        "divergencias_numericas": 0,
        "distancias_nao_finitas": 0,
        "erro_maximo_absoluto": None,
        "tolerancia_absoluta": TOLERANCIA_ABSOLUTA,
        "contagens_status": {
            metodo: {status: 0 for status in ("aceito", "desconhecido", "ambiguo")}
            for metodo in METODOS
        },
        "diagnosticos": [],
    }


def _somar_validacao(total: dict[str, object], parcial: dict[str, object]) -> None:
    for chave in (
        "comparacoes",
        "divergencias_status_id",
        "divergencias_numericas",
        "distancias_nao_finitas",
    ):
        total_valor = total[chave]
        parcial_valor = parcial[chave]
        assert isinstance(total_valor, int) and isinstance(parcial_valor, int)
        total[chave] = total_valor + parcial_valor
    erros = [
        valor
        for valor in (total["erro_maximo_absoluto"], parcial["erro_maximo_absoluto"])
        if isinstance(valor, (int, float))
    ]
    total["erro_maximo_absoluto"] = max(erros) if erros else None
    total_contagens = total["contagens_status"]
    parcial_contagens = parcial["contagens_status"]
    assert isinstance(total_contagens, dict) and isinstance(parcial_contagens, dict)
    for metodo in METODOS:
        alvo = total_contagens[metodo]
        fonte = parcial_contagens[metodo]
        assert isinstance(alvo, dict) and isinstance(fonte, dict)
        for status in ("aceito", "desconhecido", "ambiguo"):
            alvo[status] += fonte[status]
    diagnosticos = cast(list[str], total["diagnosticos"])
    diagnosticos.extend(cast(list[str], parcial["diagnosticos"]))
    if len(diagnosticos) > 20:
        del diagnosticos[20:]
    if parcial["status"] != "ok":
        total["status"] = "validacao_falhou"


def _executar_benchmark(
    config: ConfiguracaoBenchmark, clock: Clock | None = None
) -> dict[str, object]:
    relogio = clock or time.perf_counter_ns
    politicas = _politicas(config.margem_ambiguidade)
    corpus_por_tamanho: dict[int, CorpusSintetico] = {}
    referencia_por_tamanho: dict[int, MatrizDeReferencia] = {}
    validacao_total = _nova_validacao()
    validacao_por_combinacao: dict[tuple[int, str, str], dict[str, object]] = {}

    # Corpus e todas as decisoes sao preparados/validados antes de qualquer timer.
    for n in config.tamanhos:
        corpus = gerar_corpus(n, config.seed, config.consultas_por_cenario)
        referencia = MatrizDeReferencia.de_embeddings(corpus.pares)
        corpus_por_tamanho[n] = corpus
        referencia_por_tamanho[n] = referencia
        for cenario in CENARIOS:
            for nome_politica, politica in politicas:
                parcial = validar_equivalencia(
                    corpus.pares,
                    referencia,
                    corpus.consultas[cenario],
                    LIMIAR,
                    politica,
                )
                validacao_por_combinacao[(n, cenario, nome_politica)] = parcial
                _somar_validacao(validacao_total, parcial)

    resultado: dict[str, object] = {
        "schema_version": 1,
        "status": validacao_total["status"],
        "config": {
            "tamanhos": config.tamanhos,
            "consultas_por_cenario": config.consultas_por_cenario,
            "rodadas": config.rodadas,
            "aquecimento": config.aquecimento,
            "seed": config.seed,
            "dimensao": DIMENSAO,
            "dtype": DTYPE,
            "modelo_rotulo": MODELO,
            "limiar_local": LIMIAR,
            "modos": [
                {
                    "nome": nome,
                    "margem": (None if politica is None else politica.margem_minima),
                }
                for nome, politica in politicas
            ],
            "distribuicao_artificial": (
                "normal em 511 componentes, componente final zero; IDs 1 e 2 repetidos"
            ),
        },
        "ambiente": {},
        "threads_configuradas": {},
        "validacao": validacao_total,
        "limitacoes": [
            "matching isolado; nao inclui captura nem inferencia",
            "dados sinteticos nao representam pessoas nem populacao biometrica",
            "tracemalloc nao mede RSS nem toda memoria nativa",
            "nbytes e payload dos vetores, nao memoria total do processo",
            "tempos locais sujeitos a ruido, cache, ordem e configuracao do BLAS",
            "sem avaliacao biometrica, alegacao de acuracia ou recomendacao de margem",
        ],
    }
    ambiente, threads = coletar_metadados_ambiente()
    resultado["ambiente"] = ambiente
    resultado["threads_configuradas"] = threads

    if validacao_total["status"] != "ok":
        resultado["montagem"] = []
        resultado["matching"] = []
        resultado["comparacoes"] = []
        return resultado

    montagem: list[dict[str, object]] = []
    matching: list[dict[str, object]] = []
    comparacoes: list[dict[str, object]] = []
    for n in config.tamanhos:
        corpus = corpus_por_tamanho[n]
        referencia = referencia_por_tamanho[n]
        construir = partial(_construir_matriz, corpus.pares)
        duracoes_montagem = medir_montagem(construir, config.rodadas, relogio)
        pico_montagem = medir_pico_tracemalloc(construir)
        montagem.append(
            {
                "n": n,
                "tempos": resumir_tempos(duracoes_montagem),
                "payload_embeddings_bytes": sum(
                    int(embedding.vetor.nbytes) for _, embedding in corpus.pares
                ),
                "payload_matriz_teorico_bytes": n * DIMENSAO * np.dtype(DTYPE).itemsize,
                "montagem_pico_rastreado_bytes": pico_montagem,
            }
        )

        for cenario in CENARIOS:
            consultas = corpus.consultas[cenario]
            for nome_politica, politica in politicas:
                executores = _criar_executores_matching(
                    corpus.pares, referencia, politica
                )
                duracoes = medir_latencias(
                    consultas,
                    config.aquecimento,
                    config.rodadas,
                    executores,
                    relogio,
                )
                resumo_por_metodo: dict[str, TempoSummary] = {
                    metodo: resumir_tempos(duracoes[metodo]) for metodo in METODOS
                }
                validacao = validacao_por_combinacao[(n, cenario, nome_politica)]
                contagens = cast(
                    dict[str, dict[str, int]], validacao["contagens_status"]
                )
                for metodo in METODOS:
                    pico_matching = medir_pico_tracemalloc(
                        partial(
                            _descartar_resultados_matching,
                            consultas,
                            executores[metodo],
                        )
                    )
                    matching.append(
                        {
                            "n": n,
                            "cenario": cenario,
                            "modo": nome_politica,
                            "margem": (
                                None if politica is None else politica.margem_minima
                            ),
                            "metodo": metodo,
                            "tempos": resumo_por_metodo[metodo],
                            "matching_pico_rastreado_bytes": pico_matching,
                            "contagens_status_validacao": contagens[metodo],
                        }
                    )
                mediana_seq = float(resumo_por_metodo["sequencial"]["mediana_us"])
                mediana_vec = float(resumo_por_metodo["vetorizado"]["mediana_us"])
                comparacoes.append(
                    {
                        "n": n,
                        "cenario": cenario,
                        "modo": nome_politica,
                        "margem": None if politica is None else politica.margem_minima,
                        "mediana_sequencial_us": mediana_seq,
                        "mediana_vetorizado_us": mediana_vec,
                        "razao_mediana_sequencial_sobre_vetorizado": mediana_seq
                        / mediana_vec,
                    }
                )
    resultado["montagem"] = montagem
    resultado["matching"] = matching
    resultado["comparacoes"] = comparacoes
    return resultado


def _imprimir_tabelas(resultado: dict[str, object]) -> None:
    validacao = resultado["validacao"]
    assert isinstance(validacao, dict)
    print(
        "Validacao: "
        f"{validacao['status']} | comparacoes={validacao['comparacoes']} | "
        f"divergencias status/ID={validacao['divergencias_status_id']} | "
        f"erro maximo={validacao['erro_maximo_absoluto']} "
        f"(tolerancia absoluta {validacao['tolerancia_absoluta']})"
    )
    if resultado["status"] != "ok":
        for diagnostico in validacao["diagnosticos"]:
            print(f"  {diagnostico}")
        return

    print("\nMontagem por N (tempos em us; memoria rastreada nao e RSS):")
    print(
        "N | mediana us | p95 us | payload embeddings B | "
        "matriz teorica B | pico montagem B"
    )
    montagem = cast(list[dict[str, object]], resultado["montagem"])
    for linha in montagem:
        tempos = cast(TempoSummary, linha["tempos"])
        print(
            f"{linha['n']} | {tempos['mediana_us']:.3f} | {tempos['p95_us']:.3f} | "
            f"{linha['payload_embeddings_bytes']} | "
            f"{linha['payload_matriz_teorico_bytes']} | "
            f"{linha['montagem_pico_rastreado_bytes']}"
        )
    print("\nMatching por chamada (us); throughput e apenas das chamadas medidas:")
    print(
        "N | cenario | modo | metodo | mediana us | p95 us | chamadas/s | "
        "pico rastreado B"
    )
    matching = cast(list[dict[str, object]], resultado["matching"])
    for linha in matching:
        tempos = cast(TempoSummary, linha["tempos"])
        print(
            f"{linha['n']} | {linha['cenario']} | {linha['modo']} | "
            f"{linha['metodo']} | "
            f"{tempos['mediana_us']:.3f} | {tempos['p95_us']:.3f} | "
            f"{tempos['chamadas_por_segundo']:.1f} | "
            f"{linha['matching_pico_rastreado_bytes']}"
        )
    print("\nRazao de medianas sequencial/vetorizado (sem piso de speedup):")
    comparacoes = cast(list[dict[str, object]], resultado["comparacoes"])
    for linha in comparacoes:
        print(
            f"N={linha['n']} {linha['cenario']} {linha['modo']}: "
            f"{linha['razao_mediana_sequencial_sobre_vetorizado']:.3f}"
        )
    print(
        "\nA referencia e um laco Python com NumPy dot por embedding. "
        "Tracemalloc nao mede RSS nem toda memoria nativa; "
        "payload nao e memoria total."
    )


def _descartar_reserva(caminho: Path, arquivo: TextIO) -> None:
    try:
        stat_descritor = os.fstat(arquivo.fileno())
    except OSError:
        stat_descritor = None
    arquivo.close()
    if stat_descritor is not None:
        try:
            stat_caminho = caminho.stat()
            if (stat_descritor.st_dev, stat_descritor.st_ino) == (
                stat_caminho.st_dev,
                stat_caminho.st_ino,
            ):
                caminho.unlink()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = _criar_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return _codigo_saida(exc)
    if len(set(args.tamanhos)) != len(args.tamanhos):
        try:
            parser.error("--tamanhos deve conter inteiros unicos")
        except SystemExit as exc:
            return _codigo_saida(exc)
    if tracemalloc.is_tracing():
        print("Erro: tracemalloc ja esta ativo; benchmark cancelado.", file=sys.stderr)
        return 2

    arquivo: TextIO | None = None
    caminho: Path | None = args.saida_json
    if caminho is not None:
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            arquivo = caminho.open("x", encoding="utf-8", newline="\n")
        except OSError as exc:
            print(f"Erro ao reservar saida JSON: {exc}", file=sys.stderr)
            return 2

    config = ConfiguracaoBenchmark(
        tamanhos=list(args.tamanhos),
        consultas_por_cenario=args.consultas_por_cenario,
        rodadas=args.rodadas,
        aquecimento=args.aquecimento,
        seed=args.seed,
        margem_ambiguidade=args.margem_ambiguidade,
    )
    try:
        resultado = _executar_benchmark(config, time.perf_counter_ns)
        _imprimir_tabelas(resultado)
        if arquivo is not None:
            json.dump(resultado, arquivo, ensure_ascii=False, allow_nan=False, indent=2)
            arquivo.write("\n")
            arquivo.flush()
            arquivo.close()
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        print(f"Erro no benchmark: {exc}", file=sys.stderr)
        return 2
    finally:
        if arquivo is not None and caminho is not None and not arquivo.closed:
            _descartar_reserva(caminho, arquivo)
    return 0 if resultado["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
