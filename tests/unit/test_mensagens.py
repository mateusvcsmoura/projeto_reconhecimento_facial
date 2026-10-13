"""Fase 8 -- toda mensagem de erro precisa dizer o que fazer."""

from __future__ import annotations

import pytest

from src.domain import errors
from src.presentation.cli.mensagens import (
    _ORIENTACOES,
    orientacao_para,
    para_operador,
)

TODOS_OS_ERROS = [
    errors.NenhumRostoDetectado(),
    errors.MultiplosRostosDetectados(2),
    errors.IdentificacaoAmbigua(),
    errors.PossivelFraude(0.1),
    errors.ModeloIndisponivel("x"),
    errors.CameraIndisponivel(0),
    errors.FalhaNaLeituraDaCamera("x"),
    errors.ConsentimentoNaoRegistrado("x"),
    errors.AlunoNaoEncontrado("42"),
    errors.AlunoJaCadastrado("42"),
    errors.QualidadeCapturaInsuficiente(),
    errors.RostoMuitoPequeno(),
    errors.IluminacaoInsuficiente(),
    errors.IluminacaoExcessiva(),
    errors.RostoSemNitidez(),
]


@pytest.mark.parametrize("erro", TODOS_OS_ERROS, ids=lambda e: type(e).__name__)
def test_todo_erro_conhecido_tem_orientacao(erro: Exception) -> None:
    orientacao = orientacao_para(erro)

    assert orientacao is not None
    assert orientacao.problema
    assert orientacao.acao


@pytest.mark.parametrize("erro", TODOS_OS_ERROS, ids=lambda e: type(e).__name__)
def test_mensagem_contem_problema_e_acao(erro: Exception) -> None:
    mensagem = para_operador(erro)
    orientacao = orientacao_para(erro)

    assert orientacao is not None
    assert orientacao.problema in mensagem
    assert orientacao.acao in mensagem


def test_cada_erro_tem_mensagem_distinta() -> None:
    """O prototipo dizia 'rosto nao reconhecido' para tudo (problema A6)."""
    mensagens = {para_operador(erro) for erro in TODOS_OS_ERROS}

    assert len(mensagens) == len(TODOS_OS_ERROS)


def test_fraude_e_ausencia_de_rosto_nao_se_confundem() -> None:
    fraude = para_operador(errors.PossivelFraude(0.1))
    sem_rosto = para_operador(errors.NenhumRostoDetectado())

    assert fraude != sem_rosto
    assert "foto" in fraude.lower()
    assert "iluminacao" in sem_rosto.lower()


@pytest.mark.parametrize(
    ("erro", "mensagem"),
    [
        (
            errors.RostoMuitoPequeno(),
            "Rosto muito pequeno. Aproxime-se da camera e tente novamente.",
        ),
        (
            errors.IluminacaoInsuficiente(),
            "Rosto escuro. Melhore a iluminacao frontal e tente novamente.",
        ),
        (
            errors.IluminacaoExcessiva(),
            "Rosto muito claro. Reduza a luz direta e tente novamente.",
        ),
        (
            errors.RostoSemNitidez(),
            "Rosto sem nitidez. Fique parado, ajuste o foco e tente novamente.",
        ),
        (
            errors.QualidadeCapturaInsuficiente(),
            "Captura inadequada. Ajuste o enquadramento e tente novamente.",
        ),
    ],
)
def test_qualidade_de_captura_tem_orientacao_especifica(
    erro: Exception, mensagem: str
) -> None:
    assert para_operador(erro) == mensagem


def test_mensagem_de_fraude_nao_recomenda_desligar_antispoofing() -> None:
    mensagem = para_operador(errors.PossivelFraude())

    assert "FACE_ANTI_SPOOFING=false" not in mensagem
    assert "iluminacao" in mensagem
    assert "tente de novo" in mensagem


def test_ambiguidade_orienta_sem_expor_candidatos_ou_distancias() -> None:
    mensagem = para_operador(errors.IdentificacaoAmbigua())

    assert mensagem == (
        "Identificacao ambigua. Olhe de frente para a camera, ajuste a posicao "
        "e tente novamente."
    )
    assert "Ana" not in mensagem and "Bia" not in mensagem
    assert "distancia" not in mensagem.lower()


def test_dados_invalidos_usa_o_proprio_texto() -> None:
    """Estes erros ja nascem especificos: 'Informe a matricula.'"""
    mensagem = para_operador(errors.DadosInvalidos("Informe a matricula."))

    assert mensagem == "Informe a matricula."


def test_todo_erro_de_dominio_com_orientacao_esta_mapeado() -> None:
    """Guarda contra adicionar um erro novo e esquecer a mensagem."""
    mapeados = set(_ORIENTACOES)
    sem_orientacao = {
        errors.ErroDeDominio,
        errors.DadosInvalidos,  # traz texto proprio
    }

    def subclasses(cls: type) -> set[type]:
        diretas = set(cls.__subclasses__())
        return diretas | {n for d in diretas for n in subclasses(d)}

    todos = subclasses(errors.ErroDeDominio)
    faltando = todos - mapeados - sem_orientacao

    assert not faltando, f"erros sem mensagem ao operador: {faltando}"


# -- causa original nas falhas de infraestrutura de ML ----------------------


def test_modelo_indisponivel_mostra_a_causa_original() -> None:
    """A orientacao generica sozinha nao diagnostica nada.

    Caso real: o anti-spoofing exige torch, e sem ele TODO cadastro falha.
    Sem a causa anexada, o operador le "verifique a instalacao do DeepFace"
    e nunca descobre que falta um pacote diferente.
    """
    causa = "You must install torch to use face anti spoofing module"

    mensagem = para_operador(errors.ModeloIndisponivel(causa))

    assert "Modelo de reconhecimento indisponivel." in mensagem
    assert causa in mensagem


def test_outros_erros_nao_ganham_causa_anexada() -> None:
    """So ModeloIndisponivel embrulha falha arbitraria de biblioteca."""
    mensagem = para_operador(errors.NenhumRostoDetectado("detalhe interno"))

    assert "Causa:" not in mensagem


def test_modelo_indisponivel_sem_detalhe_nao_deixa_causa_vazia() -> None:
    mensagem = para_operador(errors.ModeloIndisponivel(""))

    assert "Causa:" not in mensagem
