"""Fluxos automaticos da CLI com camera, janela e relogio dublados."""

from __future__ import annotations

import datetime as dt

import pytest

from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import ModeloIndisponivel, NenhumRostoDetectado, RostoSemNitidez
from src.domain.services.captura_automatica import ParametrosCapturaAutomatica
from src.domain.services.consistencia_temporal import ParametrosTemporais
from tests.fakes import FakeFaceRecognition, FakeJanela
from tests.unit.test_menu import ANA, TZ, RelogioIncremental, emb, montar, texto


def _parametros() -> ParametrosCapturaAutomatica:
    return ParametrosCapturaAutomatica(
        espera_segundos=0.08,
        intervalo_amostragem_segundos=0.01,
        idade_maxima_segundos=1.0,
    )


def test_cadastro_automatico_valida_observacoes_e_prepara_uma_unica_vez() -> None:
    from src.presentation.cli.teclas import ENTER, ESPACO

    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[ENTER, ESPACO, 0, 0, 0],
        frames=20,
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert len(ctx.alunos.alunos) == 1  # type: ignore[attr-defined]
    assert ctx.reconhecimento.preparacoes == 1  # type: ignore[attr-defined]
    gravacoes = ctx.storage.gravacoes  # type: ignore[attr-defined]
    assert len(gravacoes) == 1 and gravacoes[0].endswith(".jpg")
    assert gravacoes[0] != "42.jpg"
    assert "ESPACO captura" not in texto(ctx)
    assert texto(ctx).count("CONSENTIMENTO") == 1
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert ctx.janela.fechada is True  # type: ignore[attr-defined]


@pytest.mark.parametrize("teclas", [[27], [0, 27]])
def test_esc_na_busca_ou_contagem_cancela_sem_persistir(teclas: list[int]) -> None:
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=teclas,
        frames=20,
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == []  # type: ignore[attr-defined]
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]


def test_recusar_consentimento_com_automatico_nao_abre_camera() -> None:
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "n", "6"],
        teclas=[],
        captura_automatica=_parametros(),
    )

    menu.executar()

    assert ctx.camera.aberta is False  # type: ignore[attr-defined]
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]


def test_recusa_de_sondagem_reinicia_a_contagem_e_recupera_na_mesma_sessao() -> None:
    class RecusaInicial(FakeFaceRecognition):
        def __init__(self) -> None:
            super().__init__()
            self._recusar = True

        def extrair_face_unica(self, imagem: object) -> object:
            self.extracoes += 1
            if self._recusar:
                self._recusar = False
                raise NenhumRostoDetectado()
            return self.face

    reconhecimento = RecusaInicial()
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[0] * 100,
        frames=100,
        reconhecimento_fake=reconhecimento,
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert len(ctx.alunos.alunos) == 1  # type: ignore[attr-defined]
    assert reconhecimento.preparacoes == 1
    assert reconhecimento.extracoes >= 4
    assert texto(ctx).count("CONSENTIMENTO") == 1


def test_recusa_na_preparacao_final_descarta_preparacao_e_reinicia() -> None:
    reconhecimento = FakeFaceRecognition()
    reconhecimento.erros_ao_preparar = [RostoSemNitidez(), None]
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[0] * 100,
        frames=100,
        reconhecimento_fake=reconhecimento,
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert reconhecimento.preparacoes == 2
    assert len(ctx.alunos.alunos) == 1  # type: ignore[attr-defined]
    gravacoes = ctx.storage.gravacoes  # type: ignore[attr-defined]
    assert len(gravacoes) == 1 and gravacoes[0].endswith(".jpg")
    assert gravacoes[0] != "42.jpg"
    assert texto(ctx).count("CONSENTIMENTO") == 1


def test_esc_na_confirmacao_final_descarta_face_preparada_sem_gravar() -> None:
    from src.presentation.cli.teclas import ESC

    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[0, 0, 0, ESC],
        frames=20,
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert ctx.reconhecimento.preparacoes == 1  # type: ignore[attr-defined]
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == []  # type: ignore[attr-defined]
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]


def test_overlay_lento_invalida_captura_final_antes_de_persistir() -> None:
    from src.presentation.cli.teclas import ESC

    relogio = RelogioIncremental()

    class JanelaLenta(FakeJanela):
        def mostrar(
            self, frame: object, linhas: list[tuple[str, tuple[int, int, int]]]
        ) -> int:
            tecla = super().mostrar(frame, linhas)
            if len(self.exibicoes) == 4:
                relogio.avancar(1.1)
            return tecla

    janela = JanelaLenta([0, 0, 0, 0, ESC])
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[],
        frames=20,
        captura_automatica=_parametros(),
        relogio=relogio,
        janela_fake=janela,
    )

    menu.executar()

    assert ctx.reconhecimento.preparacoes == 1  # type: ignore[attr-defined]
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == []  # type: ignore[attr-defined]


def test_inferencia_final_lenta_nao_persiste_cadastro_vencido() -> None:
    from src.domain.services.face_recognition import FacePreparada
    from src.presentation.cli.teclas import ESC

    relogio = RelogioIncremental()

    class PreparacaoLenta(FakeFaceRecognition):
        def preparar_cadastro(self, imagem: object) -> FacePreparada:
            preparada = super().preparar_cadastro(imagem)
            relogio.avancar(1.1)
            return preparada

    reconhecimento = PreparacaoLenta()
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[0, 0, 0, 0, ESC],
        frames=20,
        reconhecimento_fake=reconhecimento,
        captura_automatica=_parametros(),
        relogio=relogio,
    )

    menu.executar()

    assert reconhecimento.preparacoes == 1
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == []  # type: ignore[attr-defined]


def test_temporal_habilitado_acrescenta_requisito_antes_do_frame_final() -> None:
    from src.presentation.cli.teclas import ESC

    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[0, 0, 0, ESC],
        frames=20,
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
        captura_automatica=_parametros(),
        temporal=ParametrosTemporais(
            min_observacoes=5,
            janela_segundos=5.0,
            validade_segundos=1.0,
        ),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert ctx.presencas.chamadas == []  # type: ignore[attr-defined]
    assert ctx.reconhecimento.inferencias == 4  # type: ignore[attr-defined]


def test_galeria_vazia_nao_abre_camera_no_modo_automatico() -> None:
    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[],
        captura_automatica=_parametros(),
    )

    menu.executar()

    assert ctx.camera.aberta is False  # type: ignore[attr-defined]
    assert "Nenhum aluno com embedding cadastrado." in texto(ctx)


def test_falha_tecnica_no_cadastro_automatico_encerra_sem_repetir() -> None:
    reconhecimento = FakeFaceRecognition(erro_ao_extrair=ModeloIndisponivel("erro"))
    menu, ctx = montar(
        respostas=["1", "Maria", "42", "s", "6"],
        teclas=[0],
        frames=5,
        reconhecimento_fake=reconhecimento,
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert reconhecimento.extracoes == 1
    assert ctx.alunos.alunos == []  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == []  # type: ignore[attr-defined]
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert "Modelo de reconhecimento indisponivel." in texto(ctx)


def test_reconhecimento_automatico_ignora_enter_e_espaco_e_registra_uma_vez() -> None:
    from src.presentation.cli.teclas import ENTER, ESPACO

    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[ENTER, ESPACO, 0, 0],
        frames=20,
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert len(ctx.presencas.chamadas) == 1  # type: ignore[attr-defined]
    assert ctx.presencas.chamadas[0][0] == ANA.id  # type: ignore[attr-defined]
    assert ctx.reconhecimento.inferencias == 4  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == []  # type: ignore[attr-defined]
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]


def test_candidato_desconhecido_nao_registra_presenca() -> None:
    from src.presentation.cli.teclas import ESC

    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[0, ESC],
        frames=20,
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([0.0, 1.0, 0.0]),
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert ctx.presencas.chamadas == []  # type: ignore[attr-defined]
    assert ctx.storage.gravacoes == []  # type: ignore[attr-defined]


def test_inferencia_final_lenta_nao_registra_candidato_vencido() -> None:
    from src.presentation.cli.teclas import ESC

    relogio = RelogioIncremental()

    class ReconhecimentoLento(FakeFaceRecognition):
        def gerar_embedding(self, imagem: object) -> FaceEmbedding:
            embedding = super().gerar_embedding(imagem)
            if self.inferencias == 4:
                relogio.avancar(1.1)
            return embedding

    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[0, 0, 0, ESC],
        frames=20,
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        reconhecimento_fake=ReconhecimentoLento(embedding=emb([1.0, 0.0, 0.0])),
        captura_automatica=_parametros(),
        relogio=relogio,
    )

    menu.executar()

    assert ctx.reconhecimento.inferencias == 4  # type: ignore[attr-defined]
    assert ctx.presencas.chamadas == []  # type: ignore[attr-defined]
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]


def test_presenca_duplicada_consulta_banco_uma_vez_e_fecha_sessao() -> None:
    from src.presentation.cli.teclas import ENTER, ESPACO

    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[ENTER, ESPACO, 0, 0],
        frames=20,
        alunos=[ANA],
        embeddings={1: emb([1.0, 0.0, 0.0])},
        consulta=emb([1.0, 0.0, 0.0]),
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )
    hoje = dt.datetime.now(TZ).date()
    ctx.presencas.registros.add((ANA.id, hoje))  # type: ignore[attr-defined]

    menu.executar()

    assert len(ctx.presencas.chamadas) == 1  # type: ignore[attr-defined]
    assert "Presenca ja registrada hoje: Ana" in texto(ctx)
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]


@pytest.mark.parametrize("operacao", ["cadastro", "presenca"])
def test_falha_de_persistencia_nao_e_repetida_e_libera_camera(
    monkeypatch: pytest.MonkeyPatch,
    operacao: str,
) -> None:
    chamadas = 0
    if operacao == "cadastro":
        menu, ctx = montar(
            respostas=["1", "Maria", "42", "s", "6"],
            teclas=[0] * 20,
            frames=20,
            captura_automatica=_parametros(),
            relogio=RelogioIncremental(),
        )

        def salvar(_nome_arquivo: str, _imagem: object) -> str:
            nonlocal chamadas
            chamadas += 1
            raise RuntimeError("storage offline")

        monkeypatch.setattr(ctx.storage, "salvar", salvar)  # type: ignore[attr-defined]
    else:
        menu, ctx = montar(
            respostas=["2", "6"],
            teclas=[0] * 20,
            frames=20,
            alunos=[ANA],
            embeddings={1: emb([1.0, 0.0, 0.0])},
            consulta=emb([1.0, 0.0, 0.0]),
            captura_automatica=_parametros(),
            relogio=RelogioIncremental(),
        )

        def registrar_se_ausente(
            _aluno_id: int,
            _dia: dt.date,
            _momento: dt.datetime,
            *,
            turma_id: int,
        ) -> bool:
            nonlocal chamadas
            chamadas += 1
            raise RuntimeError("database offline")

        monkeypatch.setattr(
            ctx.presencas,  # type: ignore[attr-defined]
            "registrar_se_ausente",
            registrar_se_ausente,
        )

    with pytest.raises(RuntimeError):
        menu.executar()

    assert chamadas == 1
    assert ctx.camera.liberada is True  # type: ignore[attr-defined]
    assert ctx.janela.fechada is True  # type: ignore[attr-defined]


def test_reconhecimento_automatico_recusa_troca_de_identidade_final() -> None:
    from src.presentation.cli.teclas import ESC

    bruna = Aluno(id=2, matricula="2", nome="Bruna")

    class EmbeddingsEmSequencia(FakeFaceRecognition):
        def __init__(self) -> None:
            super().__init__()
            self._fila = [
                emb([1.0, 0.0, 0.0]),
                emb([1.0, 0.0, 0.0]),
                emb([1.0, 0.0, 0.0]),
                emb([0.0, 1.0, 0.0]),
            ]

        def gerar_embedding(self, _imagem: object) -> FaceEmbedding:
            self.inferencias += 1
            return self._fila.pop(0) if len(self._fila) > 1 else self._fila[0]

    menu, ctx = montar(
        respostas=["2", "6"],
        teclas=[0, 0, 0, ESC],
        frames=20,
        alunos=[ANA, bruna],
        embeddings={
            1: emb([1.0, 0.0, 0.0]),
            2: emb([0.0, 1.0, 0.0]),
        },
        reconhecimento_fake=EmbeddingsEmSequencia(),
        captura_automatica=_parametros(),
        relogio=RelogioIncremental(),
    )

    menu.executar()

    assert ctx.presencas.chamadas == []  # type: ignore[attr-defined]
    assert ctx.reconhecimento.inferencias == 4  # type: ignore[attr-defined]
    assert any(
        "Identidade mudou" in linha
        for exibicao in ctx.janela.exibicoes  # type: ignore[attr-defined]
        for linha, _ in exibicao
    )
