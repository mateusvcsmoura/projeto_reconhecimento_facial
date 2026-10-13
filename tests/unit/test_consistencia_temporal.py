"""Regras temporais puras, sem relógio real nem dependências de IO."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.domain.services.consistencia_temporal import (
    ConfirmadorTemporal,
    EstadoTemporal,
    ParametrosTemporais,
)


def test_parametros_temporais_tem_defaults_de_engenharia() -> None:
    assert ParametrosTemporais() == ParametrosTemporais(3, 5.0, 2.0)


def test_parametros_validos_aceitam_limites_iguais_e_sao_imutaveis() -> None:
    parametros = ParametrosTemporais(2, 1.0, 1.0)

    assert parametros.min_observacoes == 2
    with pytest.raises(FrozenInstanceError):
        parametros.min_observacoes = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_observacoes": 1},
        {"min_observacoes": 0},
        {"min_observacoes": -2},
        {"min_observacoes": 2.5},
        {"min_observacoes": True},
        {"janela_segundos": 0},
        {"janela_segundos": -1.0},
        {"janela_segundos": float("nan")},
        {"janela_segundos": float("inf")},
        {"janela_segundos": True},
        {"validade_segundos": 0},
        {"validade_segundos": -1.0},
        {"validade_segundos": float("nan")},
        {"validade_segundos": float("inf")},
        {"validade_segundos": False},
        {"janela_segundos": 1.0, "validade_segundos": 1.1},
    ],
)
def test_parametros_invalidos_falham_na_construcao(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ParametrosTemporais(**kwargs)  # type: ignore[arg-type]


def test_estado_inicial_nao_tem_candidato() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())

    assert confirmador.consultar(0.0) == EstadoTemporal(None, 0, False)


def test_tres_observacoes_da_mesma_identidade_confirmam() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())

    assert confirmador.observar(1, 0.0) == EstadoTemporal(1, 1, False)
    assert confirmador.observar(1, 0.5) == EstadoTemporal(1, 2, False)
    assert confirmador.observar(1, 1.0) == EstadoTemporal(1, 3, True)


def test_identidade_diferente_reinicia_contagem() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 0.0)
    confirmador.observar(1, 0.5)

    assert confirmador.observar(2, 1.0) == EstadoTemporal(2, 1, False)


def test_observacao_desconhecida_limpa_sequencia() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 0.0)
    confirmador.observar(1, 0.5)

    assert confirmador.observar(None, 1.0) == EstadoTemporal(None, 0, False)
    assert confirmador.observar(1, 1.5) == EstadoTemporal(1, 1, False)


def test_identidades_alternadas_nunca_confirmam() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais(2, 5.0, 2.0))

    assert confirmador.observar(1, 0.0) == EstadoTemporal(1, 1, False)
    assert confirmador.observar(2, 0.5) == EstadoTemporal(2, 1, False)
    assert confirmador.observar(1, 1.0) == EstadoTemporal(1, 1, False)
    assert confirmador.observar(2, 1.5) == EstadoTemporal(2, 1, False)


def test_desconhecido_entre_duas_observacoes_exige_recomecar() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 0.0)
    confirmador.observar(1, 0.5)
    confirmador.observar(None, 1.0)

    assert confirmador.observar(1, 1.5) == EstadoTemporal(1, 1, False)


def test_validade_aceita_a_igualdade_e_expira_imediatamente_depois() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    for momento in (0.0, 0.5, 1.0):
        confirmador.observar(1, momento)

    assert confirmador.consultar(3.0) == EstadoTemporal(1, 3, True)
    assert confirmador.consultar(3.0001) == EstadoTemporal(None, 0, False)


def test_consulta_repetida_nao_acrescenta_ou_renova_observacoes() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 0.0)
    confirmador.observar(1, 0.5)
    confirmador.observar(1, 1.0)

    assert confirmador.consultar(1.5) == EstadoTemporal(1, 3, True)
    assert confirmador.consultar(1.5) == EstadoTemporal(1, 3, True)
    assert confirmador.consultar(3.0001) == EstadoTemporal(None, 0, False)
    assert confirmador.consultar(3.0002) == EstadoTemporal(None, 0, False)


def test_expiracao_na_consulta_nao_ressuscita_ao_voltar_o_relogio() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 0.0)

    assert confirmador.consultar(2.0001) == EstadoTemporal(None, 0, False)
    assert confirmador.consultar(1.0) == EstadoTemporal(None, 0, False)


def test_idade_excedida_reinicia_contagem_na_nova_observacao() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 0.5)

    assert confirmador.observar(1, 3.0) == EstadoTemporal(1, 1, False)


def test_janela_remove_so_eventos_antigos_e_aceita_a_igualdade() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais(3, 1.0, 1.0))
    confirmador.observar(1, 0.0)
    confirmador.observar(1, 0.6)

    assert confirmador.observar(1, 1.0) == EstadoTemporal(1, 3, True)
    assert confirmador.observar(1, 1.2) == EstadoTemporal(1, 3, True)


def test_janela_curta_remove_eventos_sem_expirar_por_idade_maxima() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais(3, 1.0, 1.0))
    confirmador.observar(1, 0.0)
    confirmador.observar(1, 0.6)

    assert confirmador.observar(1, 1.2) == EstadoTemporal(1, 2, False)


def test_sequencia_longa_permanece_confirmada_com_estado_limitado() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais(3, 5.0, 2.0))

    estado = EstadoTemporal(None, 0, False)
    for indice in range(20):
        estado = confirmador.observar(1, indice * 0.5)

    assert estado == EstadoTemporal(1, 3, True)


def test_reiniciar_apaga_sequencia_e_marcador_de_tempo() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 8.0)
    confirmador.reiniciar()

    assert confirmador.consultar(0.0) == EstadoTemporal(None, 0, False)
    assert confirmador.observar(2, 0.0) == EstadoTemporal(2, 1, False)


@pytest.mark.parametrize("aluno_id", [0, -1, True, 1.5, "1"])
def test_id_invalido_nao_altera_estado(aluno_id: object) -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 1.0)

    with pytest.raises(ValueError):
        confirmador.observar(aluno_id, 2.0)  # type: ignore[arg-type]

    assert confirmador.consultar(2.0) == EstadoTemporal(1, 1, False)


@pytest.mark.parametrize("momento", [-1.0, float("nan"), float("inf"), True, "1"])
def test_timestamp_invalido_nao_altera_estado(momento: object) -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 1.0)

    with pytest.raises(ValueError):
        confirmador.observar(2, momento)  # type: ignore[arg-type]

    assert confirmador.consultar(1.0) == EstadoTemporal(1, 1, False)


@pytest.mark.parametrize("momento", [1.0, 0.5])
def test_timestamp_repetido_ou_regressivo_nao_muda_sequencia(momento: float) -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 1.0)
    confirmador.observar(1, 2.0)

    with pytest.raises(ValueError):
        confirmador.observar(2, momento)

    assert confirmador.consultar(2.0) == EstadoTemporal(1, 2, False)


@pytest.mark.parametrize("agora", [-1.0, float("nan"), float("inf"), True, "2"])
def test_instante_invalido_em_consulta_falha_sem_alterar_sequencia(
    agora: object,
) -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 1.0)

    with pytest.raises(ValueError):
        confirmador.consultar(agora)  # type: ignore[arg-type]

    assert confirmador.consultar(1.0) == EstadoTemporal(1, 1, False)


def test_consulta_anterior_a_ultima_observacao_e_rejeitada_sem_mutacao() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 2.0)

    with pytest.raises(ValueError):
        confirmador.consultar(1.999)

    assert confirmador.consultar(2.0) == EstadoTemporal(1, 1, False)


def test_observacao_apos_none_nao_pode_reutilizar_timestamp() -> None:
    confirmador = ConfirmadorTemporal(ParametrosTemporais())
    confirmador.observar(1, 1.0)
    confirmador.observar(None, 2.0)

    with pytest.raises(ValueError):
        confirmador.observar(1, 2.0)

    assert confirmador.observar(1, 2.1) == EstadoTemporal(1, 1, False)
