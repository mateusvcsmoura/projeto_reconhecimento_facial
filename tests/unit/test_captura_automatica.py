"""Contrato temporal da captura automatica, sem camera ou inferencia."""

from __future__ import annotations

import importlib
import importlib.util

import pytest

from src.domain.services.captura_automatica import (
    ConfirmadorCapturaAutomatica,
    ParametrosCapturaAutomatica,
)


def test_servico_publica_parametros_estado_e_confirmador() -> None:
    spec = importlib.util.find_spec("src.domain.services.captura_automatica")

    assert spec is not None, "o controlador temporal ainda nao foi criado"

    modulo = importlib.import_module("src.domain.services.captura_automatica")
    assert hasattr(modulo, "ParametrosCapturaAutomatica")
    assert hasattr(modulo, "EstadoCapturaAutomatica")
    assert hasattr(modulo, "ConfirmadorCapturaAutomatica")


def test_parametros_padrao_definem_espera_intervalo_e_validade() -> None:
    parametros = ParametrosCapturaAutomatica()

    assert parametros.espera_segundos == 5.0
    assert parametros.intervalo_amostragem_segundos == 0.5
    assert parametros.idade_maxima_segundos == 2.0


@pytest.mark.parametrize(
    "valores",
    [
        {"espera_segundos": 0.0},
        {"espera_segundos": float("nan")},
        {"espera_segundos": float("inf")},
        {"espera_segundos": True},
        {"intervalo_amostragem_segundos": 0.0},
        {"intervalo_amostragem_segundos": True},
        {"idade_maxima_segundos": 0.0},
        {"idade_maxima_segundos": float("inf")},
        {"idade_maxima_segundos": True},
        {"intervalo_amostragem_segundos": 2.0, "idade_maxima_segundos": 2.0},
    ],
)
def test_parametros_rejeitam_tempos_invalidos(valores: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ParametrosCapturaAutomatica(**valores)  # type: ignore[arg-type]


def test_tres_observacoes_e_espera_de_cinco_segundos_tornam_estado_pronto() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())

    estado = None
    for indice in range(11):
        instante = indice * 0.5
        estado = confirmador.observar("cadastro", instante, instante)

    assert estado is not None
    assert estado.chave == "cadastro"
    assert estado.observacoes == 11
    assert estado.tempo_restante == 0.0
    assert estado.pronto is True


def test_tres_observacoes_antes_da_espera_nao_tornam_estado_pronto() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    for instante in (0.0, 0.5, 1.0):
        estado = confirmador.observar("cadastro", instante, instante)

    assert estado.observacoes == 3
    assert estado.tempo_restante == 4.0
    assert estado.pronto is False


def test_espera_configurada_de_sete_segundos_precisa_de_nova_observacao() -> None:
    parametros = ParametrosCapturaAutomatica(
        espera_segundos=7.0,
        intervalo_amostragem_segundos=0.5,
        idade_maxima_segundos=2.0,
    )
    confirmador = ConfirmadorCapturaAutomatica(parametros)

    for indice in range(14):
        instante = indice * 0.5
        estado = confirmador.observar("cadastro", instante, instante)

    assert estado.observacoes == 14
    assert estado.pronto is False

    estado = confirmador.observar("cadastro", 7.0, 7.0)

    assert estado.pronto is True


def test_tempo_sem_tres_observacoes_nao_autoriza_captura() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    confirmador.observar("cadastro", 0.0, 0.0)
    confirmador.observar("cadastro", 0.5, 0.5)

    estado = confirmador.consultar(2.5)

    assert estado.observacoes == 2
    assert estado.pronto is False


def test_tempo_decorrido_sozinho_nao_cria_observacoes() -> None:
    parametros = ParametrosCapturaAutomatica(
        espera_segundos=5.0,
        intervalo_amostragem_segundos=0.5,
        idade_maxima_segundos=10.0,
    )
    confirmador = ConfirmadorCapturaAutomatica(parametros)
    confirmador.observar("cadastro", 0.0, 0.0)
    confirmador.observar("cadastro", 0.5, 0.5)

    estado = confirmador.consultar(5.0)

    assert estado.observacoes == 2
    assert estado.pronto is False


def test_intervalo_exatamente_na_validade_permite_continuar_sequencia() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    confirmador.observar("cadastro", 0.0, 0.0)

    estado = confirmador.observar("cadastro", 2.0, 2.0)

    assert estado.observacoes == 2


def test_intervalo_acima_da_validade_reinicia_na_observacao_nova() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    confirmador.observar("cadastro", 0.0, 0.0)

    estado = confirmador.observar("cadastro", 2.000001, 2.000001)

    assert estado.chave == "cadastro"
    assert estado.observacoes == 1
    assert estado.pronto is False


def test_chave_ausente_ou_trocada_interrompe_e_reinicia_sequencia() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    confirmador.observar("cadastro", 0.0, 0.0)
    ausente = confirmador.observar(None, 0.5, 0.5)
    trocada = confirmador.observar("aluno-2", 1.0, 1.0)

    assert ausente.chave is None
    assert ausente.observacoes == 0
    assert trocada.chave == "aluno-2"
    assert trocada.observacoes == 1


def test_observacao_lenta_demais_nao_inicia_sequencia_com_evidencia_vencida() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())

    estado = confirmador.observar("aluno-1", 0.0, 2.000001)

    assert estado.chave is None
    assert estado.observacoes == 0
    assert estado.pronto is False


@pytest.mark.parametrize(
    ("chave", "capturado_em", "agora"),
    [
        ("cadastro", -1.0, 0.0),
        ("cadastro", float("nan"), 0.0),
        ("cadastro", float("inf"), float("inf")),
        ("cadastro", True, 1.0),
        ("cadastro", 1.0, 0.999),
        ("", 0.0, 0.0),
        (1, 0.0, 0.0),
    ],
)
def test_observacoes_invalidas_sao_rejeitadas(
    chave: object, capturado_em: object, agora: object
) -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())

    with pytest.raises(ValueError):
        confirmador.observar(chave, capturado_em, agora)  # type: ignore[arg-type]


@pytest.mark.parametrize("segundo_instante", [1.0, 0.5])
def test_timestamp_repetido_ou_regressivo_nao_altera_sequencia(
    segundo_instante: float,
) -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    confirmador.observar("cadastro", 1.0, 1.0)
    antes = confirmador.consultar(1.0)

    with pytest.raises(ValueError):
        confirmador.observar("cadastro", segundo_instante, 2.0)

    assert confirmador.consultar(1.0) == antes


def test_agora_aceita_repeticao_e_rejeita_regressao_sem_mudar_estado() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    primeiro = confirmador.observar("cadastro", 1.0, 2.0)

    assert confirmador.consultar(2.0) == primeiro
    with pytest.raises(ValueError, match="regredir"):
        confirmador.observar("cadastro", 1.5, 1.6)
    with pytest.raises(ValueError, match="regredir"):
        confirmador.consultar(1.9)

    assert confirmador.consultar(2.0) == primeiro


def test_consultar_nao_cria_evidencia_e_expira_quando_a_ultima_vencer() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    confirmador.observar("cadastro", 0.0, 0.0)
    confirmador.observar("cadastro", 0.5, 0.5)

    ainda_valido = confirmador.consultar(2.5)
    vencido = confirmador.consultar(2.500001)

    assert ainda_valido.observacoes == 2
    assert ainda_valido.pronto is False
    assert vencido.chave is None
    assert vencido.observacoes == 0
    assert vencido.pronto is False


def test_reiniciar_descarta_chave_timestamps_e_contagem() -> None:
    confirmador = ConfirmadorCapturaAutomatica(ParametrosCapturaAutomatica())
    confirmador.observar("aluno-1", 0.0, 0.0)
    confirmador.reiniciar()

    estado = confirmador.consultar(100.0)

    assert estado.chave is None
    assert estado.observacoes == 0
    assert estado.pronto is False
    # Reiniciar também abre uma nova sequência temporal para o mesmo relógio.
    nova = confirmador.observar("aluno-1", 101.0, 101.0)
    assert nova.observacoes == 1
