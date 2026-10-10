from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from scripts.identificacao_aberta import (
    Amostra,
    EstrategiaGaleria,
    FaseProtocolo,
    Galeria,
    IntervaloConfianca,
    MetricasIdentificacao,
    MotivoIdentificacao,
    Protocolo,
    avaliar_protocolo,
    bootstrap_por_identidade,
    construir_protocolo,
    contar_quase_duplicatas_por_identidade,
    dividir_identidades,
    reduzir_referencias,
    selecionar_limiar_fpir,
)
from src.domain.entities.face_embedding import FaceEmbedding


def _embedding(valores: list[float], modelo: str = "Facenet512") -> FaceEmbedding:
    return FaceEmbedding.de_valores(valores, modelo)


def _amostra(identidade: str, imagem: str, valores: list[float]) -> Amostra:
    return Amostra(identidade, imagem, _embedding(valores))


def test_galeria_identifica_o_vizinho_mais_proximo() -> None:
    galeria = Galeria.criar(
        [_amostra("id-a", "img-a", [1.0, 0.0]), _amostra("id-b", "img-b", [0.0, 1.0])]
    )

    resultado = galeria.identificar(_embedding([1.0, 0.01]), limiar=0.1)

    assert resultado.candidato_id == "id-a"
    assert resultado.identidade_aceita == "id-a"
    assert resultado.motivo is MotivoIdentificacao.IDENTIFICADA
    assert resultado.distancia == pytest.approx(0.00005, abs=0.0001)


def test_galeria_rejeita_candidato_acima_do_limiar() -> None:
    galeria = Galeria.criar([_amostra("id-a", "img-a", [1.0, 0.0])])

    resultado = galeria.identificar(_embedding([0.0, 1.0]), limiar=0.3)

    assert resultado.candidato_id == "id-a"
    assert resultado.identidade_aceita is None
    assert resultado.motivo is MotivoIdentificacao.ACIMA_DO_LIMIAR


def test_galeria_vazia_nao_inventa_candidato() -> None:
    resultado = Galeria.criar([]).identificar(_embedding([1.0, 0.0]), limiar=0.3)

    assert resultado.candidato_id is None
    assert resultado.identidade_aceita is None
    assert resultado.distancia is None
    assert resultado.motivo is MotivoIdentificacao.GALERIA_VAZIA


def test_empate_entre_identidades_e_rejeitado_sem_dependencia_da_ordem() -> None:
    referencias = [
        _amostra("id-a", "img-a", [1.0, 0.0]),
        _amostra("id-b", "img-b", [0.0, 1.0]),
    ]
    resultados = [
        Galeria.criar(ordem).identificar(_embedding([1.0, 1.0]), limiar=0.5)
        for ordem in (referencias, list(reversed(referencias)))
    ]

    assert all(r.candidato_id is None for r in resultados)
    assert all(r.identidade_aceita is None for r in resultados)
    assert all(r.motivo is MotivoIdentificacao.EMPATE for r in resultados)


def test_estrategia_menor_distancia_usa_a_referencia_mais_proxima() -> None:
    galeria = Galeria.criar(
        [
            _amostra("id-a", "img-a1", [0.0, 1.0]),
            _amostra("id-a", "img-a2", [1.0, 0.0]),
            _amostra("id-b", "img-b", [0.0, 1.0]),
        ],
        estrategia=EstrategiaGaleria.MENOR_DISTANCIA,
    )

    resultado = galeria.identificar(_embedding([1.0, 0.0]), limiar=0.1)

    assert resultado.identidade_aceita == "id-a"
    assert resultado.distancia == pytest.approx(0.0, abs=1e-7)


def test_estrategia_centroide_compara_com_media_normalizada() -> None:
    galeria = Galeria.criar(
        [
            _amostra("id-a", "img-a1", [1.0, 0.0]),
            _amostra("id-a", "img-a2", [0.0, 1.0]),
        ],
        estrategia=EstrategiaGaleria.CENTROIDE,
    )

    resultado = galeria.identificar(_embedding([1.0, 0.0]), limiar=0.4)

    assert resultado.identidade_aceita == "id-a"
    assert resultado.distancia == pytest.approx(1 - 2**-0.5, abs=1e-6)


def test_galeria_normaliza_vetores_de_entrada_na_fronteira() -> None:
    referencia = FaceEmbedding(np.array([7.0, 0.0]), "Facenet512")
    consulta = FaceEmbedding(np.array([3.0, 0.0]), "Facenet512")

    resultado = Galeria.criar([Amostra("id-a", "img-a", referencia)]).identificar(
        consulta, limiar=0.0
    )

    assert resultado.identidade_aceita == "id-a"
    assert resultado.distancia == pytest.approx(0.0, abs=1e-7)


def test_embedding_nao_finito_e_recusado() -> None:
    invalido = FaceEmbedding(np.array([np.nan, 0.0]), "Facenet512")

    with pytest.raises(ValueError, match="finito"):
        Galeria.criar([Amostra("id-a", "img-a", invalido)])


@pytest.mark.parametrize("limiar", [-0.01, 2.01, float("nan"), float("inf")])
def test_limiar_cosine_invalido_e_recusado(limiar: float) -> None:
    galeria = Galeria.criar([_amostra("id-a", "img-a", [1.0, 0.0])])

    with pytest.raises(ValueError, match="limiar"):
        galeria.identificar(_embedding([1.0, 0.0]), limiar=limiar)


def test_referencias_de_dimensoes_diferentes_sao_recusadas() -> None:
    referencias = [
        _amostra("id-a", "img-a", [1.0, 0.0]),
        _amostra("id-b", "img-b", [1.0, 0.0, 0.0]),
    ]

    with pytest.raises(ValueError, match="dimens"):
        Galeria.criar(referencias)


def test_consulta_de_modelo_incompativel_e_recusada() -> None:
    galeria = Galeria.criar([_amostra("id-a", "img-a", [1.0, 0.0])])

    with pytest.raises(ValueError, match="modelo"):
        galeria.identificar(_embedding([1.0, 0.0], modelo="ArcFace"), limiar=0.3)


def test_amostra_exige_embedding_ou_motivo_de_falha() -> None:
    with pytest.raises(ValueError, match=r"embedding|falha"):
        Amostra("id-a", "img-a", None)
    with pytest.raises(ValueError, match=r"embedding|falha"):
        Amostra("id-a", "img-a", _embedding([1.0, 0.0]), "sem rosto")


def _dataset_sintetico(
    identidades: int = 12, imagens_por_identidade: int = 3
) -> list[Amostra]:
    amostras = []
    for indice in range(identidades):
        valores = [1.0, float(indice + 1)]
        for foto in range(imagens_por_identidade):
            amostras.append(
                _amostra(f"id-{indice:02d}", f"img-{indice:02d}-{foto}", valores)
            )
    return amostras


def _assinatura_protocolo(protocolo: object) -> tuple[object, ...]:
    return (
        protocolo.identidades_conhecidas,
        protocolo.identidades_desconhecidas,
        tuple(a.imagem_id for a in protocolo.referencias),
        tuple(a.imagem_id for a in protocolo.consultas_conhecidas),
        tuple(a.imagem_id for a in protocolo.consultas_desconhecidas),
    )


def test_divisao_de_identidades_e_reprodutivel_e_sem_vazamento() -> None:
    identidades = [f"id-{indice}" for indice in range(30)]

    primeira = dividir_identidades(identidades, seed=73)
    segunda = dividir_identidades(list(reversed(identidades)), seed=73)
    teste = primeira.abrir_teste({"T0": 0.3})

    assert primeira.assinatura() == segunda.assinatura()
    assert not set(primeira.treino) & set(primeira.validacao)
    assert not set(primeira.treino) & set(teste)
    assert not set(primeira.validacao) & set(teste)


def test_construcao_de_protocolo_e_reprodutivel() -> None:
    dados = _dataset_sintetico()
    identidades = sorted({amostra.identidade_id for amostra in dados})

    protocolo_a = construir_protocolo(dados, identidades, seed=19)
    protocolo_b = construir_protocolo(list(reversed(dados)), identidades, seed=19)

    assert _assinatura_protocolo(protocolo_a) == _assinatura_protocolo(protocolo_b)


def test_reducao_de_referencias_pareia_identidades_e_consultas() -> None:
    dados = _dataset_sintetico(identidades=10, imagens_por_identidade=5)
    identidades = sorted({amostra.identidade_id for amostra in dados})
    protocolo_tres = construir_protocolo(
        dados, identidades, seed=19, referencias_por_identidade=3
    )

    protocolo_um = reduzir_referencias(protocolo_tres, 1)

    assert protocolo_um.identidades_conhecidas == protocolo_tres.identidades_conhecidas
    assert (
        protocolo_um.identidades_desconhecidas
        == protocolo_tres.identidades_desconhecidas
    )
    assert protocolo_um.consultas_conhecidas == protocolo_tres.consultas_conhecidas
    assert (
        protocolo_um.consultas_desconhecidas == protocolo_tres.consultas_desconhecidas
    )
    assert len(protocolo_um.referencias) == len(protocolo_um.identidades_conhecidas)
    assert {amostra.imagem_id for amostra in protocolo_um.referencias} <= {
        amostra.imagem_id for amostra in protocolo_tres.referencias
    }


def test_reducao_de_referencias_rejeita_quantidade_insuficiente() -> None:
    protocolo = construir_protocolo(
        _dataset_sintetico(identidades=10, imagens_por_identidade=5),
        [f"id-{indice:02d}" for indice in range(10)],
        seed=19,
        referencias_por_identidade=1,
    )

    with pytest.raises(ValueError, match="referências suficientes"):
        reduzir_referencias(protocolo, 2)


def test_desconhecidos_nao_aparecem_na_galeria_e_imagens_sao_disjuntas() -> None:
    dados = _dataset_sintetico()
    identidades = sorted({amostra.identidade_id for amostra in dados})
    protocolo = construir_protocolo(dados, identidades, seed=19)

    ids_galeria = {amostra.identidade_id for amostra in protocolo.referencias}
    ids_desconhecidos = {
        amostra.identidade_id for amostra in protocolo.consultas_desconhecidas
    }
    ids_referencias = {amostra.imagem_id for amostra in protocolo.referencias}
    todas_consultas = protocolo.consultas_conhecidas + protocolo.consultas_desconhecidas
    ids_consultas = {amostra.imagem_id for amostra in todas_consultas}

    assert ids_galeria == set(protocolo.identidades_conhecidas)
    assert ids_galeria.isdisjoint(ids_desconhecidos)
    assert ids_referencias.isdisjoint(ids_consultas)
    assert len(ids_consultas) == len(
        protocolo.consultas_conhecidas + protocolo.consultas_desconhecidas
    )


def test_falhas_de_extracao_sao_preservadas_uma_vez_no_protocolo() -> None:
    dados = _dataset_sintetico()
    dados[1] = Amostra("id-00", "img-00-1", None, "sem_rosto")
    identidades = sorted({amostra.identidade_id for amostra in dados})

    protocolo = construir_protocolo(dados, identidades, seed=19)

    todos = (
        protocolo.referencias
        + protocolo.consultas_conhecidas
        + protocolo.consultas_desconhecidas
    )
    assert sum(a.imagem_id == "img-00-1" for a in todos) == 1
    assert next(a for a in todos if a.imagem_id == "img-00-1").embedding is None


@pytest.mark.parametrize("n_identidades", [0, 1])
def test_protocolo_recusa_quantidade_insuficiente_de_identidades(
    n_identidades: int,
) -> None:
    dados = _dataset_sintetico(n_identidades, imagens_por_identidade=3)
    identidades = sorted({amostra.identidade_id for amostra in dados})

    with pytest.raises(ValueError, match=r"identidade|identidades|insuficientes"):
        construir_protocolo(dados, identidades, seed=19)


def test_protocolo_minimo_tem_identidade_conhecida_e_desconhecida() -> None:
    dados = _dataset_sintetico(2, imagens_por_identidade=3)
    identidades = sorted({amostra.identidade_id for amostra in dados})

    protocolo = construir_protocolo(dados, identidades, seed=19)

    assert len(protocolo.identidades_conhecidas) == 1
    assert len(protocolo.identidades_desconhecidas) == 1


def test_protocolo_recusa_ids_de_imagem_repetidos() -> None:
    dados = _dataset_sintetico()
    dados[1] = Amostra("id-01", dados[0].imagem_id, dados[1].embedding)

    with pytest.raises(ValueError, match="imagem"):
        construir_protocolo(dados, sorted({a.identidade_id for a in dados}), seed=19)


def _protocolo_metricas() -> Protocolo:
    return Protocolo(
        identidades_conhecidas=("id-a", "id-b", "id-c"),
        identidades_desconhecidas=("id-u1", "id-u2", "id-u3"),
        identidades_insuficientes=(),
        referencias=(
            _amostra("id-a", "ref-a", [1.0, 0.0]),
            _amostra("id-b", "ref-b", [0.0, 1.0]),
            Amostra("id-c", "ref-c", None, "sem_rosto"),
        ),
        consultas_conhecidas=(
            _amostra("id-a", "known-correct", [1.0, 0.0]),
            _amostra("id-a", "known-reject", [-1.0, 0.0]),
            _amostra("id-b", "known-swap", [1.0, 0.1]),
            _amostra("id-a", "known-tie", [1.0, 1.0]),
            Amostra("id-a", "known-failed", None, "imagem_invalida"),
            _amostra("id-c", "known-no-reference", [-1.0, 0.0]),
        ),
        consultas_desconhecidas=(
            _amostra("id-u1", "unknown-reject", [-1.0, 0.0]),
            _amostra("id-u2", "unknown-false-id", [1.0, 0.0]),
            Amostra("id-u3", "unknown-failed", None, "sem_rosto"),
        ),
    )


def test_metricas_contabilizam_c1_a_c8_e_falhas() -> None:
    relatorio = avaliar_protocolo(_protocolo_metricas(), limiar=0.3)

    assert relatorio.erros.identificacao_correta == 1
    assert relatorio.erros.rejeicao_conhecido_limiar == 2
    assert relatorio.erros.troca_identidade == 1
    assert relatorio.erros.rejeicao_desconhecido == 1
    assert relatorio.erros.falsa_identificacao_desconhecido == 1
    assert relatorio.erros.falha_extracao_consulta == 2
    assert relatorio.erros.galeria_vazia == 0
    assert relatorio.erros.empate == 1
    assert relatorio.erros.identidade_conhecida_sem_referencia == 1


def test_metricas_expoem_denominadores_end_to_end_e_condicionais() -> None:
    relatorio = avaliar_protocolo(_protocolo_metricas(), limiar=0.3)
    metricas: MetricasIdentificacao = relatorio.metricas

    assert metricas.consultas_conhecidas == 6
    assert metricas.consultas_conhecidas_extraidas == 5
    assert metricas.consultas_desconhecidas == 3
    assert metricas.consultas_desconhecidas_extraidas == 2
    assert metricas.fpir_end_to_end == pytest.approx(1 / 3)
    assert metricas.fpir_condicional_extracao == pytest.approx(1 / 2)
    assert metricas.fnir_end_to_end == pytest.approx(5 / 6)
    assert metricas.fnir_condicional_extracao == pytest.approx(4 / 5)
    assert metricas.identificacao_correta_end_to_end == pytest.approx(1 / 6)
    assert metricas.top1_accuracy_condicional_extracao == pytest.approx(1 / 5)
    assert metricas.rejeicao_desconhecido_end_to_end == pytest.approx(1 / 3)
    assert metricas.rejeicao_desconhecido_condicional_extracao == pytest.approx(1 / 2)
    assert relatorio.tempo_comparacao_ms_por_consulta >= 0.0
    assert relatorio.tempo_decisao_ms_por_consulta >= 0.0


def test_consultas_de_ids_removidos_da_galeria_viram_desconhecidas() -> None:
    protocolo = _protocolo_metricas()

    relatorio = avaliar_protocolo(protocolo, limiar=0.3, tamanho_galeria=1)

    assert relatorio.tamanho_galeria == 1
    assert relatorio.metricas.consultas_conhecidas == 4
    assert relatorio.metricas.consultas_desconhecidas == 5
    assert relatorio.erros.falsa_identificacao_desconhecido >= 1


def test_auditoria_quase_duplicatas_conta_apenas_pares_da_mesma_identidade() -> None:
    protocolo = Protocolo(
        identidades_conhecidas=("id-a",),
        identidades_desconhecidas=("id-u",),
        identidades_insuficientes=(),
        referencias=(_amostra("id-a", "ref", [1.0, 0.0]),),
        consultas_conhecidas=(_amostra("id-a", "known-near-copy", [1.0, 0.001]),),
        consultas_desconhecidas=(_amostra("id-u", "unknown", [1.0, 0.0]),),
    )

    assert contar_quase_duplicatas_por_identidade(protocolo) == 1


def test_galeria_vazia_conta_rejeicoes_sem_candidato_ficticio() -> None:
    protocolo = Protocolo(
        identidades_conhecidas=("id-a",),
        identidades_desconhecidas=("id-u",),
        identidades_insuficientes=(),
        referencias=(),
        consultas_conhecidas=(_amostra("id-a", "known", [1.0, 0.0]),),
        consultas_desconhecidas=(_amostra("id-u", "unknown", [0.0, 1.0]),),
    )

    relatorio = avaliar_protocolo(protocolo, limiar=0.3)

    assert relatorio.erros.galeria_vazia == 2
    assert relatorio.metricas.fnir_end_to_end == 1.0
    assert relatorio.metricas.fpir_end_to_end == 0.0


def _protocolo_calibracao(distancias: tuple[float, ...]) -> Protocolo:
    referencias = (
        _amostra("id-a", "ref-a", [1.0, 0.0]),
        _amostra("id-b", "ref-b", [0.0, 1.0]),
    )
    desconhecidas = []
    for indice, distancia_a in enumerate(distancias):
        desconhecidas.append(
            _amostra(
                f"id-u{indice}",
                f"unknown-{indice}",
                [np.sqrt(1.0 - distancia_a), np.sqrt(distancia_a)],
            )
        )
    return Protocolo(
        identidades_conhecidas=("id-a", "id-b"),
        identidades_desconhecidas=tuple(a.identidade_id for a in desconhecidas),
        identidades_insuficientes=(),
        referencias=referencias,
        consultas_conhecidas=(
            _amostra("id-a", "known-a", [1.0, 0.0]),
            _amostra("id-b", "known-b", [0.0, 1.0]),
        ),
        consultas_desconhecidas=tuple(desconhecidas),
    )


def test_threshold_t2_usa_somente_protocolo_e_controla_fpir_na_validacao() -> None:
    validacao = _protocolo_calibracao((0.2, 0.4))

    selecao = selecionar_limiar_fpir(validacao, far_maximo=0.5)

    assert selecao.limiar is not None
    assert 0.2 < selecao.limiar < 0.4
    assert selecao.fpir_validacao == pytest.approx(0.5)
    assert selecao.fnir_validacao == pytest.approx(0.0)
    assert selecao.identidades_desconhecidas == 2
    assert selecao.suficiencia == "amostra_insuficiente"


def test_threshold_fpir_conta_empates_no_denominador_sem_reduzir_orcamento() -> None:
    protocolo = Protocolo(
        identidades_conhecidas=("id-a", "id-b"),
        identidades_desconhecidas=("id-u1", "id-u2", "id-u3"),
        identidades_insuficientes=(),
        referencias=(
            _amostra("id-a", "ref-a", [1.0, 0.0]),
            _amostra("id-b", "ref-b", [0.0, 1.0]),
        ),
        consultas_conhecidas=(
            _amostra("id-a", "known-a", [1.0, 0.0]),
            _amostra("id-b", "known-b", [0.0, 1.0]),
        ),
        consultas_desconhecidas=(
            _amostra("id-u1", "unknown-near", [0.8, 0.6]),
            _amostra("id-u2", "unknown-far", [0.75, np.sqrt(1.0 - 0.75**2)]),
            _amostra("id-u3", "unknown-tie", [1.0, 1.0]),
        ),
    )

    selecao = selecionar_limiar_fpir(protocolo, far_maximo=0.34)

    assert selecao.limiar is not None
    assert 0.2 < selecao.limiar < 0.25
    assert selecao.fpir_validacao == pytest.approx(1 / 3)
    assert selecao.fpir_validacao <= 0.34


def test_threshold_sem_scores_nao_aceitaveis_usa_limiar_maximo_se_galeria_valida() -> (
    None
):
    protocolo = Protocolo(
        identidades_conhecidas=("id-a", "id-b"),
        identidades_desconhecidas=("id-u1", "id-u2"),
        identidades_insuficientes=(),
        referencias=(
            _amostra("id-a", "ref-a", [1.0, 0.0]),
            _amostra("id-b", "ref-b", [0.0, 1.0]),
        ),
        consultas_conhecidas=(
            _amostra("id-a", "known-a", [1.0, 0.0]),
            _amostra("id-b", "known-b", [0.0, 1.0]),
        ),
        consultas_desconhecidas=(
            _amostra("id-u1", "unknown-tie-1", [1.0, 1.0]),
            _amostra("id-u2", "unknown-tie-2", [1.0, 1.0]),
        ),
    )

    selecao = selecionar_limiar_fpir(protocolo, far_maximo=0.0)

    assert selecao.limiar == 2.0
    assert selecao.fpir_validacao == 0.0
    assert selecao.suficiencia == "sem_garantia"


def test_threshold_nao_aceita_impostor_no_teto_zero() -> None:
    selecao = selecionar_limiar_fpir(_protocolo_calibracao((0.2, 0.4)), far_maximo=0.0)

    assert selecao.limiar is not None
    assert selecao.fpir_validacao == 0.0
    assert selecao.fnir_validacao == 0.0
    assert selecao.suficiencia == "sem_garantia"


def test_threshold_indisponivel_quando_barreira_impossivel_de_respeitar() -> None:
    protocolo = _protocolo_calibracao((0.0, 0.4))

    selecao = selecionar_limiar_fpir(protocolo, far_maximo=0.0)

    assert selecao.limiar is None
    assert selecao.suficiencia == "threshold_indisponivel"


def test_selecao_de_limiar_recusa_protocolo_do_teste() -> None:
    teste = replace(_protocolo_calibracao((0.2, 0.4)), fase=FaseProtocolo.TESTE)

    with pytest.raises(ValueError, match="só aceita protocolos de validação"):
        selecionar_limiar_fpir(teste, far_maximo=0.5)


def test_bootstrap_agrupa_consultas_por_identidade_e_e_reprodutivel() -> None:
    relatorio = avaliar_protocolo(_protocolo_metricas(), limiar=0.3)

    primeiro = bootstrap_por_identidade(relatorio, "fpir", replicas=200, seed=31)
    segundo = bootstrap_por_identidade(relatorio, "fpir", replicas=200, seed=31)

    assert isinstance(primeiro, IntervaloConfianca)
    assert primeiro == segundo
    assert primeiro.identidades == 3
    assert primeiro.consultas == 3
    assert primeiro.inferior <= primeiro.pontual <= primeiro.superior


def test_bootstrap_sem_clusters_suficientes_nao_inventa_intervalo() -> None:
    protocolo = _protocolo_calibracao((0.2,))
    relatorio = avaliar_protocolo(protocolo, limiar=0.3)

    intervalo = bootstrap_por_identidade(relatorio, "fpir", replicas=50, seed=7)

    assert intervalo is None
