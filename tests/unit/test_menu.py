"""Fase 2 -- menu e lacos de video, com camera e janela dubles.

A suite roda sem OpenCV instalado. Se algum dia o menu voltar a importar
cv2 direto, estes testes deixam de importar -- e isso e proposital.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from zoneinfo import ZoneInfo

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.application.use_cases.consultar import (
    ListarAlunos,
    ListarPresencasDoDia,
)
from src.application.use_cases.excluir_aluno import ExcluirAluno
from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.application.use_cases.registrar_presenca import RegistrarPresenca
from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import (
    FalhaNaLeituraDaCamera,
    RostoSemNitidez,
)
from src.domain.services.captura_automatica import ParametrosCapturaAutomatica
from src.domain.services.consistencia_temporal import ParametrosTemporais
from src.domain.services.matcher import PoliticaAmbiguidade
from src.presentation.cli.menu import INTERVALO_DE_COMPARACAO, MenuCLI
from src.presentation.cli.teclas import ENTER, ESC, ESPACO
from tests.fakes import (
    FakeAlunoRepository,
    FakeCamera,
    FakeFaceRecognition,
    FakeGerenciarTurmas,
    FakeImageStorage,
    FakeJanela,
    FakePresencaRepository,
)

TZ = ZoneInfo("America/Sao_Paulo")
MODELO = "Facenet512"
ANA = Aluno(id=1, matricula="1", nome="Ana", foto_arquivo="1.jpg")


def emb(valores: list[float]) -> FaceEmbedding:
    return FaceEmbedding.de_valores(valores, MODELO)


class Contexto:
    """Junta os dubles para o teste inspecionar depois."""

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


class RelogioIncremental:
    def __init__(self, passo: float = 0.01) -> None:
        self.valor = 0.0
        self.passo = passo

    def __call__(self) -> float:
        self.valor += self.passo
        return self.valor

    def avancar(self, segundos: float) -> None:
        self.valor += segundos


def montar(
    *,
    respostas: list[str],
    teclas: list[int],
    frames: int = 40,
    alunos: list[Aluno] | None = None,
    embeddings: dict[int, FaceEmbedding] | None = None,
    consulta: FaceEmbedding | None = None,
    erro_ao_ler: Exception | None = None,
    reconhecimento_fake: FakeFaceRecognition | None = None,
    ambiguidade: PoliticaAmbiguidade | None = None,
    temporal: ParametrosTemporais | None = None,
    captura_automatica: ParametrosCapturaAutomatica | None = None,
    relogio: Callable[[], float] | None = None,
    janela_fake: FakeJanela | None = None,
    turma_id: int = 1,
) -> tuple[MenuCLI, Contexto]:
    repo_alunos = FakeAlunoRepository(alunos or [], embeddings or {})
    repo_presencas = FakePresencaRepository()
    storage = FakeImageStorage()
    gerenciar_turmas = FakeGerenciarTurmas(repo_alunos, turma_id)
    reconhecimento = reconhecimento_fake or FakeFaceRecognition(embedding=consulta)

    camera = FakeCamera([object() for _ in range(frames)], erro_ao_ler=erro_ao_ler)
    janela = janela_fake or FakeJanela(teclas)
    saida: list[str] = []
    fila = list(respostas)

    def ler(rotulo: str) -> str:
        if rotulo == "Escolha: ":
            resposta = fila.pop(0)
            # Scripts da suite ainda descrevem os numeros do menu anterior;
            # converte somente no prompt de opcao, nunca em matriculas/IDs.
            return {"2": "4", "4": "5", "5": "6", "6": "9", "9": "0"}.get(
                resposta, resposta
            )
        if rotulo.startswith("Dia (AAAA-MM-DD") and fila and fila[0] == "6":
            return ""
        return fila.pop(0)

    menu = MenuCLI(
        cadastrar_aluno=CadastrarAluno(repo_alunos, reconhecimento, storage, TZ),
        reconhecer_aluno=ReconhecerAluno(
            repo_alunos,
            reconhecimento,
            modelo=MODELO,
            limiar=0.30,
            ambiguidade=ambiguidade,
        ),
        registrar_presenca=RegistrarPresenca(repo_presencas, TZ),
        excluir_aluno=ExcluirAluno(repo_alunos, storage),
        listar_alunos=ListarAlunos(repo_alunos, MODELO),
        listar_presencas=ListarPresencasDoDia(repo_presencas, TZ),
        turma=Turma(id=turma_id, materia="IA", periodo=Periodo.DIURNO),
        gerenciar_turmas=gerenciar_turmas,
        limiar=0.30,
        abrir_camera=lambda: camera,
        abrir_janela=lambda _titulo: janela,
        ler=ler,
        escrever=saida.append,
        temporal=temporal,
        captura_automatica=captura_automatica,
        **({"relogio": relogio} if relogio is not None else {}),
    )
    contexto = Contexto(
        alunos=repo_alunos,
        turmas=gerenciar_turmas,
        presencas=repo_presencas,
        storage=storage,
        camera=camera,
        janela=janela,
        reconhecimento=reconhecimento,
        saida=saida,
    )
    return menu, contexto


def texto(contexto: Contexto) -> str:
    return "\n".join(contexto.saida)  # type: ignore[attr-defined]


# -- menu ------------------------------------------------------------------


def test_voltar_encerra_sessao_da_turma() -> None:
    menu, ctx = montar(respostas=["6"], teclas=[])
    menu.executar()
    assert "Encerrando..." in texto(ctx)


def test_opcao_invalida_avisa_e_continua() -> None:
    menu, ctx = montar(respostas=["9", "6"], teclas=[])
    menu.executar()
    assert "Opcao invalida." in texto(ctx)


def test_erro_de_dominio_vira_mensagem_e_o_menu_sobrevive() -> None:
    """Matricula duplicada nao pode derrubar a aplicacao."""
    menu, ctx = montar(respostas=["1", "Outro Nome", "1", "6"], teclas=[], alunos=[ANA])
    menu.executar()

    assert "ERRO:" in texto(ctx)
    assert "Encerrando..." in texto(ctx)


# -- cadastro --------------------------------------------------------------


def test_espaco_captura_e_cadastra() -> None:
    menu, ctx = montar(respostas=["1", "Maria Silva", "42", "s", "6"], teclas=[ESPACO])
    menu.executar()

    assert "CADASTRO REALIZADO COM SUCESSO!" in texto(ctx)
    assert len(ctx.alunos.alunos) == 1  # type: ignore[attr-defined]
    gravacoes = ctx.storage.gravacoes  # type: ignore[attr-defined]
    assert len(gravacoes) == 1 and gravacoes[0].endswith(".jpg")
    assert gravacoes[0] != "42.jpg"


def test_esc_cancela_o_cadastro() -> None:
    menu, ctx = montar(respostas=["1", "Maria Silva", "42", "s", "6"], teclas=[ESC])
    menu.executar()

    assert "Cadastro cancelado." in texto(ctx)
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]


def test_camera_e_liberada_no_cadastro() -> None:
    """Problema A17: o prototipo vazava o dispositivo em caso de excecao."""
    menu, ctx = montar(respostas=["1", "Maria", "42", "s", "6"], teclas=[ESC])
    menu.executar()

    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert ctx.janela.fechada is True  # type: ignore[attr-defined]


def test_camera_e_liberada_mesmo_com_falha_de_leitura() -> None:
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[],
        erro_ao_ler=FalhaNaLeituraDaCamera("cabo removido"),
    )
    menu.executar()

    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert "A camera parou de responder." in texto(ctx)


def test_cadastro_repete_captura_ruim_sem_repetir_identificacao_ou_consentimento() -> (
    None
):
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[ESPACO, ESPACO],
        frames=2,
    )
    ctx.reconhecimento.erros_ao_preparar = [RostoSemNitidez()]  # type: ignore[attr-defined]

    menu.executar()

    assert "Rosto sem nitidez." in texto(ctx)
    assert texto(ctx).count("CONSENTIMENTO") == 1
    assert ctx.reconhecimento.preparacoes == 2  # type: ignore[attr-defined]
    assert len(ctx.alunos.alunos) == 1  # type: ignore[attr-defined]
    gravacoes = ctx.storage.gravacoes  # type: ignore[attr-defined]
    assert len(gravacoes) == 1 and gravacoes[0].endswith(".jpg")
    assert gravacoes[0] != "42.jpg"


def test_esc_apos_recusa_de_qualidade_libera_camera_sem_persistir() -> None:
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[ESPACO, ESC],
        frames=2,
    )
    ctx.reconhecimento.erros_ao_preparar = [RostoSemNitidez()]  # type: ignore[attr-defined]

    menu.executar()

    assert "Cadastro cancelado." in texto(ctx)
    assert ctx.reconhecimento.preparacoes == 1  # type: ignore[attr-defined]
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == []  # type: ignore[attr-defined]
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert ctx.janela.fechada is True  # type: ignore[attr-defined]


# -- reconhecimento --------------------------------------------------------


def test_sem_candidatos_nao_abre_a_camera() -> None:
    menu, ctx = montar(respostas=["2", "6"], teclas=[])
    menu.executar()

    assert "Nenhum aluno com embedding cadastrado." in texto(ctx)
    assert ctx.camera.aberta is False  # type: ignore[attr-defined]


def test_reconhecimento_nao_considera_aluno_de_outra_turma() -> None:
    bruno = Aluno(id=2, matricula="2", nome="Bruno")
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[0] * 7 + [ENTER, ESC],
        alunos=[ANA, bruno],
        embeddings={1: emb([0.0, 1.0, 0.0]), 2: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
    )
    ctx.alunos.vinculos = {(1, ANA.id), (2, bruno.id)}  # type: ignore[attr-defined]
    ctx.alunos.turmas_ativas.add(2)  # type: ignore[attr-defined]

    menu.executar()

    assert ctx.presencas.chamadas == []  # type: ignore[attr-defined]
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]


def test_vincular_aluno_existente_nao_abre_camera_nem_duplica_cadastro() -> None:
    consentiu_em = dt.datetime(2026, 3, 10, 8, 0, tzinfo=dt.UTC)
    ana = Aluno(
        id=1,
        matricula="1",
        nome="Ana",
        foto_arquivo="ana.jpg",
        consentimento_em=consentiu_em,
    )
    menu, ctx = montar(respostas=["1", "s"], teclas=[], alunos=[ana], turma_id=2)

    menu.vincular()

    assert ctx.alunos.alunos == [ana]  # type: ignore[attr-defined]
    assert (2, ana.id) in ctx.alunos.vinculos  # type: ignore[attr-defined]
    assert ctx.camera.aberta is False  # type: ignore[attr-defined]


def test_enter_registra_a_presenca_do_reconhecido() -> None:
    teclas = [0] * (INTERVALO_DE_COMPARACAO - 1) + [0, ENTER, ESC]
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=teclas,
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
    )
    menu.executar()

    assert "Presenca registrada: Ana" in texto(ctx)
    assert len(ctx.presencas.registros) == 1  # type: ignore[attr-defined]


def test_segundo_enter_no_mesmo_dia_avisa_em_vez_de_duplicar() -> None:
    teclas = [0] * (INTERVALO_DE_COMPARACAO - 1) + [0, ENTER, ENTER, ESC]
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=teclas,
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
    )
    menu.executar()

    assert "Presenca ja registrada hoje: Ana" in texto(ctx)
    assert len(ctx.presencas.registros) == 1  # type: ignore[attr-defined]


def test_enter_sem_reconhecimento_nao_registra_nada() -> None:
    teclas = [0] * (INTERVALO_DE_COMPARACAO - 1) + [0, ENTER, ESC]
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=teclas,
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([0.0, 1.0, 0.0]),
    )
    menu.executar()

    assert ctx.presencas.registros == set()  # type: ignore[attr-defined]


def test_recusa_de_qualidade_limpa_candidato_e_recupera_no_proximo_ciclo() -> None:
    teclas = (
        [0] * INTERVALO_DE_COMPARACAO
        + [0] * (INTERVALO_DE_COMPARACAO - 1)
        + [ENTER]
        + [0] * (INTERVALO_DE_COMPARACAO - 1)
        + [ENTER, ESC]
    )
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=teclas,
        frames=len(teclas),
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
    )
    ctx.reconhecimento.erros_ao_gerar = [  # type: ignore[attr-defined]
        None,
        RostoSemNitidez(),
        None,
    ]

    menu.executar()

    orientacoes = [
        (texto, cor)
        for exibicao in ctx.janela.exibicoes  # type: ignore[attr-defined]
        for texto, cor in exibicao
        if "Rosto sem nitidez." in texto
    ]
    assert orientacoes
    assert all(
        orientacao
        == (
            "Rosto sem nitidez. Fique parado, ajuste o foco e tente novamente.",
            (0, 255, 255),
        )
        for orientacao in orientacoes
    )
    assert len(ctx.presencas.chamadas) == 1  # type: ignore[attr-defined]
    assert len(ctx.presencas.registros) == 1  # type: ignore[attr-defined]


def test_recusa_ambigua_limpa_candidato_mantem_orientacao_e_recupera() -> None:
    class EmbeddingsPorCiclo(FakeFaceRecognition):
        def __init__(self) -> None:
            super().__init__()
            self._embeddings = [
                emb([1.0, 0.0, 0.0]),
                emb([1.0, 1.0, 0.0]),
                emb([1.0, 0.0, 0.0]),
            ]

        def gerar_embedding(self, _imagem: object) -> FaceEmbedding:
            self.inferencias += 1
            return self._embeddings.pop(0)

    teclas = [0] * 15 + [ENTER] + [0] * 7 + [ENTER, ESC]
    bruna = Aluno(id=2, matricula="2", nome="Bruna")
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=teclas,
        frames=len(teclas),
        alunos=[ANA, bruna],
        embeddings={1: emb([1.0, 0.0, 0.0]), 2: emb([0.0, 1.0, 0.0])},
        reconhecimento_fake=EmbeddingsPorCiclo(),
        ambiguidade=PoliticaAmbiguidade(0.0),
    )

    menu.executar()

    orientacao = (
        "Identificacao ambigua. Olhe de frente para a camera, ajuste a posicao "
        "e tente novamente."
    )
    exibicoes = ctx.janela.exibicoes  # type: ignore[attr-defined]
    assert exibicoes[15][0] == (orientacao, (0, 255, 255))
    assert exibicoes[16][0] == (orientacao, (0, 255, 255))
    assert ctx.reconhecimento.inferencias == 3  # type: ignore[attr-defined]
    assert len(ctx.presencas.chamadas) == 1  # type: ignore[attr-defined]
    assert ctx.presencas.chamadas[0][0] == ANA.id  # type: ignore[attr-defined]
    assert "Presenca registrada: Ana" in texto(ctx)
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]


def test_esc_sai_do_reconhecimento() -> None:
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[ESC],
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
    )
    menu.executar()

    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert "Encerrando..." in texto(ctx)


# -- desvinculo do aluno da turma -----------------------------------------


def test_desvincular_pede_confirmacao_e_preserva_cadastro_global() -> None:
    menu, ctx = montar(
        respostas=["5", "1", "s", "6"],
        teclas=[],
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
    )
    menu.executar()

    assert "Aluno removido desta turma" in texto(ctx)
    assert ctx.alunos.alunos == [ANA]  # type: ignore[attr-defined]
    assert (1, ANA.id) not in ctx.alunos.vinculos  # type: ignore[attr-defined]


def test_exclusao_mostra_quem_sera_apagado_antes_de_apagar() -> None:
    menu, ctx = montar(respostas=["5", "1", "s", "6"], teclas=[], alunos=[ANA])
    menu.executar()

    saida = texto(ctx)
    assert "Ana" in saida
    assert saida.index("Ana") < saida.index("removido desta turma")


def test_resposta_diferente_de_sim_cancela_a_exclusao() -> None:
    menu, ctx = montar(respostas=["5", "1", "n", "6"], teclas=[], alunos=[ANA])
    menu.executar()

    assert "Remocao cancelada." in texto(ctx)
    assert len(ctx.alunos.alunos) == 1  # type: ignore[attr-defined]


def test_enter_vazio_nao_confirma_a_exclusao() -> None:
    """Confirmacao destrutiva nao pode ter o "sim" como padrao."""
    menu, ctx = montar(respostas=["5", "1", "", "6"], teclas=[], alunos=[ANA])
    menu.executar()

    assert "Remocao cancelada." in texto(ctx)
    assert len(ctx.alunos.alunos) == 1  # type: ignore[attr-defined]


def test_matricula_inexistente_vira_mensagem_sem_derrubar_o_menu() -> None:
    menu, ctx = montar(respostas=["5", "999", "6"], teclas=[], alunos=[ANA])
    menu.executar()

    assert "ERRO:" in texto(ctx)
    assert "Encerrando..." in texto(ctx)


# -- consentimento no fluxo da CLI -----------------------------------------


def test_recusar_o_consentimento_nao_liga_a_camera() -> None:
    menu, ctx = montar(respostas=["1", "Maria", "42", "n", "6"], teclas=[])
    menu.executar()

    assert "Cadastro cancelado: sem consentimento." in texto(ctx)
    assert ctx.camera.aberta is False  # type: ignore[attr-defined]
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]


def test_termo_de_consentimento_e_exibido_antes_da_captura() -> None:
    menu, ctx = montar(respostas=["1", "Maria", "42", "s", "6"], teclas=[ESPACO])
    menu.executar()

    saida = texto(ctx)
    assert "CONSENTIMENTO" in saida
    assert saida.index("CONSENTIMENTO") < saida.index("Posicione o rosto")


# -- falha de camera no reconhecimento -------------------------------------


def test_falha_de_leitura_no_reconhecimento_encerra_com_mensagem() -> None:
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[],
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
        erro_ao_ler=FalhaNaLeituraDaCamera("cabo removido"),
    )
    menu.executar()

    assert "A camera parou de responder." in texto(ctx)
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]


# -- consultas (Fase 8) ----------------------------------------------------


def test_listagem_vazia_orienta_o_operador() -> None:
    menu, ctx = montar(respostas=["3", "6"], teclas=[])
    menu.executar()

    assert "Nenhum aluno cadastrado ainda. Use a opcao 1." in texto(ctx)


def test_listagem_mostra_matricula_nome_e_situacao() -> None:
    menu, ctx = montar(
        respostas=["3", "6"],
        teclas=[],
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
    )
    menu.executar()

    saida = texto(ctx)
    assert "Ana" in saida
    assert "pronto" in saida
    assert "Total: 1 aluno(s)" in saida


def test_listagem_avisa_sobre_alunos_sem_embedding() -> None:
    """Eles nao serao reconhecidos; melhor descobrir antes da aula."""
    menu, ctx = montar(respostas=["3", "6"], teclas=[], alunos=[ANA])
    menu.executar()

    saida = texto(ctx)
    assert "sem embedding" in saida
    assert "backfill_embeddings" in saida


def test_presencas_de_hoje_sem_registros() -> None:
    menu, ctx = montar(respostas=["4", "6"], teclas=[], alunos=[ANA])
    menu.executar()

    assert "Nenhuma presenca registrada hoje." in texto(ctx)


def test_presencas_de_hoje_lista_o_que_foi_registrado() -> None:
    import datetime as dt

    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[0] * (INTERVALO_DE_COMPARACAO - 1) + [0, ENTER, ESC],
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
    )
    menu.executar()
    assert len(ctx.presencas.registros) == 1  # type: ignore[attr-defined]

    menu2, ctx2 = montar(respostas=["4", "6"], teclas=[], alunos=[ANA])
    ctx2.presencas.registros = {  # type: ignore[attr-defined]
        (1, dt.datetime.now(TZ).date())
    }
    menu2.executar()

    assert "Total: 1 presenca(s)" in texto(ctx2)


def test_overlay_mostra_confianca_e_nao_a_distancia_crua() -> None:
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[0] * (INTERVALO_DE_COMPARACAO - 1) + [0, ESC],
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
    )
    menu.executar()

    linhas = [t for exib in ctx.janela.exibicoes for t, _ in exib]  # type: ignore[attr-defined]
    assert any("Ana" in linha and "%" in linha for linha in linhas)
    assert not any("dist" in linha for linha in linhas)
