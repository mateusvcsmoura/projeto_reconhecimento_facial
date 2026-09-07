"""Fase 2 -- menu e lacos de video, com camera e janela dubles.

A suite roda sem OpenCV instalado. Se algum dia o menu voltar a importar
cv2 direto, estes testes deixam de importar -- e isso e proposital.
"""

from __future__ import annotations

import pytest

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.application.use_cases.registrar_presenca import RegistrarPresenca
from src.domain.entities.aluno import Aluno
from src.domain.errors import FalhaNaLeituraDaCamera
from src.presentation.cli.menu import INTERVALO_DE_COMPARACAO, MenuCLI
from src.presentation.cli.teclas import ENTER, ESC, ESPACO
from tests.fakes import (
    FakeAlunoRepository,
    FakeCamera,
    FakeFaceRecognition,
    FakeImageStorage,
    FakeJanela,
    FakePresencaRepository,
)
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
ANA = Aluno(id=1, matricula="1", nome="Ana", foto_arquivo="1.jpg")


class Contexto:
    """Junta os dubles para o teste inspecionar depois."""

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


def montar(
    *,
    respostas: list[str],
    teclas: list[int],
    frames: int = 40,
    alunos: list[Aluno] | None = None,
    fotos: set[str] | None = None,
    casa_com: str | None = None,
    erro_ao_ler: Exception | None = None,
) -> tuple[MenuCLI, Contexto]:
    repo_alunos = FakeAlunoRepository(alunos or [])
    repo_presencas = FakePresencaRepository()
    storage = FakeImageStorage(existentes=fotos or set())
    reconhecimento = FakeFaceRecognition(casa_com=casa_com)

    camera = FakeCamera([object() for _ in range(frames)], erro_ao_ler=erro_ao_ler)
    janela = FakeJanela(teclas)
    saida: list[str] = []
    fila = list(respostas)

    menu = MenuCLI(
        cadastrar_aluno=CadastrarAluno(repo_alunos, reconhecimento, storage),
        reconhecer_aluno=ReconhecerAluno(repo_alunos, reconhecimento, storage),
        registrar_presenca=RegistrarPresenca(repo_presencas, TZ),
        abrir_camera=lambda: camera,
        abrir_janela=lambda _titulo: janela,
        ler=lambda _rotulo: fila.pop(0),
        escrever=saida.append,
    )
    contexto = Contexto(
        alunos=repo_alunos,
        presencas=repo_presencas,
        storage=storage,
        camera=camera,
        janela=janela,
        saida=saida,
    )
    return menu, contexto


def texto(contexto: Contexto) -> str:
    return "\n".join(contexto.saida)  # type: ignore[attr-defined]


# -- menu ------------------------------------------------------------------


def test_opcao_3_encerra() -> None:
    menu, ctx = montar(respostas=["3"], teclas=[])
    menu.executar()
    assert "Encerrando..." in texto(ctx)


def test_opcao_invalida_avisa_e_continua() -> None:
    menu, ctx = montar(respostas=["9", "3"], teclas=[])
    menu.executar()
    assert "Opcao invalida." in texto(ctx)


def test_erro_de_dominio_vira_mensagem_e_o_menu_sobrevive() -> None:
    """Matricula duplicada nao pode derrubar a aplicacao."""
    menu, ctx = montar(
        respostas=["1", "Outro Nome", "1", "3"], teclas=[], alunos=[ANA]
    )
    menu.executar()

    assert "ERRO:" in texto(ctx)
    assert "Encerrando..." in texto(ctx)


# -- cadastro --------------------------------------------------------------


def test_espaco_captura_e_cadastra() -> None:
    menu, ctx = montar(respostas=["1", "Maria Silva", "42", "3"], teclas=[ESPACO])
    menu.executar()

    assert "CADASTRO REALIZADO COM SUCESSO!" in texto(ctx)
    assert len(ctx.alunos.alunos) == 1  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == ["42.jpg"]  # type: ignore[attr-defined]


def test_esc_cancela_o_cadastro() -> None:
    menu, ctx = montar(respostas=["1", "Maria Silva", "42", "3"], teclas=[ESC])
    menu.executar()

    assert "Cadastro cancelado." in texto(ctx)
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]


def test_camera_e_liberada_no_cadastro() -> None:
    """Problema A17: o prototipo vazava o dispositivo em caso de excecao."""
    menu, ctx = montar(respostas=["1", "Maria", "42", "3"], teclas=[ESC])
    menu.executar()

    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert ctx.janela.fechada is True  # type: ignore[attr-defined]


def test_camera_e_liberada_mesmo_com_falha_de_leitura() -> None:
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "3"],
        teclas=[],
        erro_ao_ler=FalhaNaLeituraDaCamera("cabo removido"),
    )
    menu.executar()

    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert "A camera parou de responder." in texto(ctx)


# -- reconhecimento --------------------------------------------------------


def test_sem_candidatos_nao_abre_a_camera() -> None:
    menu, ctx = montar(respostas=["2", "3"], teclas=[])
    menu.executar()

    assert "Nenhum aluno com foto de referencia disponivel." in texto(ctx)
    assert ctx.camera.aberta is False  # type: ignore[attr-defined]


def test_enter_registra_a_presenca_do_reconhecido() -> None:
    teclas = [0] * (INTERVALO_DE_COMPARACAO - 1) + [0, ENTER, ESC]
    menu, ctx = montar(
        respostas=["2", "3"],
        teclas=teclas,
        alunos=[ANA],
        fotos={"1.jpg"},
        casa_com="1.jpg",
    )
    menu.executar()

    assert "Presenca registrada: Ana" in texto(ctx)
    assert len(ctx.presencas.registros) == 1  # type: ignore[attr-defined]


def test_segundo_enter_no_mesmo_dia_avisa_em_vez_de_duplicar() -> None:
    teclas = [0] * (INTERVALO_DE_COMPARACAO - 1) + [0, ENTER, ENTER, ESC]
    menu, ctx = montar(
        respostas=["2", "3"],
        teclas=teclas,
        alunos=[ANA],
        fotos={"1.jpg"},
        casa_com="1.jpg",
    )
    menu.executar()

    assert "Presenca ja registrada hoje: Ana" in texto(ctx)
    assert len(ctx.presencas.registros) == 1  # type: ignore[attr-defined]


def test_enter_sem_reconhecimento_nao_registra_nada() -> None:
    teclas = [0] * (INTERVALO_DE_COMPARACAO - 1) + [0, ENTER, ESC]
    menu, ctx = montar(
        respostas=["2", "3"],
        teclas=teclas,
        alunos=[ANA],
        fotos={"1.jpg"},
        casa_com=None,
    )
    menu.executar()

    assert ctx.presencas.registros == set()  # type: ignore[attr-defined]


def test_esc_sai_do_reconhecimento() -> None:
    menu, ctx = montar(
        respostas=["2", "3"],
        teclas=[ESC],
        alunos=[ANA],
        fotos={"1.jpg"},
    )
    menu.executar()

    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert "Encerrando..." in texto(ctx)
