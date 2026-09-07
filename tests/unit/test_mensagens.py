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
    errors.PossivelFraude(0.1),
    errors.ModeloIndisponivel("x"),
    errors.CameraIndisponivel(0),
    errors.FalhaNaLeituraDaCamera("x"),
    errors.ConsentimentoNaoRegistrado("x"),
    errors.AlunoNaoEncontrado("42"),
    errors.AlunoJaCadastrado("42"),
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
