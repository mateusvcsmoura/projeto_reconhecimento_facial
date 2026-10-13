"""Fluxo temporal da CLI com camera, relogio e provider controlados."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from src.application.use_cases.reconhecer_aluno import (
    ReconhecerAluno,
    Reconhecimento,
)
from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    FalhaNaLeituraDaCamera,
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
    RostoSemNitidez,
)
from src.domain.services.consistencia_temporal import ParametrosTemporais
from src.domain.services.matcher import MatrizDeReferencia
from src.presentation.cli.menu import MenuCLI
from src.presentation.cli.teclas import ENTER, ESC
from tests.fakes import FakeAlunoRepository, FakeFaceRecognition

MODELO = "Facenet512"
TZ = ZoneInfo("America/Sao_Paulo")
ANA = Aluno(id=1, matricula="1", nome="Ana")
BIA = Aluno(id=2, matricula="2", nome="Bia")


@dataclass(frozen=True)
class Frame:
    numero: int


class RelogioManual:
    def __init__(self) -> None:
        self.agora = 0.0
        self.leituras: list[float] = []

    def __call__(self) -> float:
        self.leituras.append(self.agora)
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


class CameraRoteirizada:
    def __init__(
        self,
        quadros: list[Frame],
        *,
        ao_ler: Callable[[int], None] | None = None,
        falhar_nas_leituras: set[int] | None = None,
    ) -> None:
        self._quadros = list(quadros)
        self._ao_ler = ao_ler
        self._falhar = set(falhar_nas_leituras or set())
        self.leituras = 0
        self.aberta = False
        self.liberada = False

    def __enter__(self) -> CameraRoteirizada:
        self.aberta = True
        return self

    def __exit__(self, *_args: object) -> None:
        self.aberta = False
        self.liberada = True

    def ler_frame(self) -> Frame:
        self.leituras += 1
        if self._ao_ler is not None:
            self._ao_ler(self.leituras)
        if self.leituras in self._falhar:
            raise FalhaNaLeituraDaCamera("camera de teste")
        if not self._quadros:
            raise AssertionError("A camera consumiu mais quadros do que recebeu.")
        return self._quadros.pop(0)


class JanelaRoteirizada:
    def __init__(
        self,
        teclas: list[int],
        *,
        ao_mostrar: Callable[[int], None] | None = None,
    ) -> None:
        self._teclas = list(teclas)
        self._ao_mostrar = ao_mostrar
        self.frames: list[Frame] = []
        self.linhas: list[list[tuple[str, tuple[int, int, int]]]] = []
        self.fechada = False

    def __enter__(self) -> JanelaRoteirizada:
        return self

    def __exit__(self, *_args: object) -> None:
        self.fechada = True

    def mostrar(
        self, frame: Frame, linhas: list[tuple[str, tuple[int, int, int]]]
    ) -> int:
        self.frames.append(frame)
        self.linhas.append(list(linhas))
        if self._ao_mostrar is not None:
            self._ao_mostrar(len(self.frames))
        if not self._teclas:
            raise AssertionError("A janela consumiu mais teclas do que recebeu.")
        return self._teclas.pop(0)


class IdentificadorRoteirizado:
    def __init__(
        self,
        resultados: list[Reconhecimento | Exception | None],
        *,
        ao_identificar: Callable[[int, Frame], None] | None = None,
    ) -> None:
        self._resultados = list(resultados)
        self._ao_identificar = ao_identificar
        self.frames: list[Frame] = []
        self.carregamentos = 0

    def carregar_referencias(self) -> MatrizDeReferencia:
        self.carregamentos += 1
        return MatrizDeReferencia.de_embeddings(
            [(ANA.id, FaceEmbedding.de_valores([1.0, 0.0, 0.0], MODELO))]
        )

    def identificar(
        self, imagem: Frame, _referencias: MatrizDeReferencia
    ) -> Reconhecimento | None:
        self.frames.append(imagem)
        if self._ao_identificar is not None:
            self._ao_identificar(len(self.frames), imagem)
        if not self._resultados:
            raise AssertionError(
                "A identificacao recebeu mais chamadas que o esperado."
            )
        resultado = self._resultados.pop(0)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


class RegistroRoteirizado:
    def __init__(self, resultados: list[bool] | None = None) -> None:
        self.ids: list[int] = []
        self._resultados = list(resultados or [])

    def executar(self, aluno_id: int) -> bool:
        self.ids.append(aluno_id)
        if self._resultados:
            return self._resultados.pop(0)
        return True


def reconhecido(aluno: Aluno = ANA) -> Reconhecimento:
    return Reconhecimento(aluno=aluno, distancia=0.1)


def _montar_menu(
    reconhecedor: Any,
    cameras: list[CameraRoteirizada],
    janelas: list[JanelaRoteirizada],
    relogio: RelogioManual,
    *,
    registro: RegistroRoteirizado | None = None,
    temporal: ParametrosTemporais | None = None,
) -> tuple[MenuCLI, list[str], RegistroRoteirizado]:
    fila_cameras = iter(cameras)
    fila_janelas = iter(janelas)
    mensagens: list[str] = []
    registro = registro or RegistroRoteirizado()
    for camera in cameras:
        if camera._ao_ler is None:
            camera._ao_ler = lambda _numero: relogio.avancar(0.1)
    inerte = cast(Any, object())
    menu = MenuCLI(
        cadastrar_aluno=inerte,
        reconhecer_aluno=reconhecedor,
        registrar_presenca=registro,
        excluir_aluno=inerte,
        listar_alunos=inerte,
        listar_presencas=inerte,
        limiar=0.30,
        abrir_camera=lambda: next(fila_cameras),
        abrir_janela=lambda _titulo: next(fila_janelas),
        escrever=mensagens.append,
        temporal=temporal or ParametrosTemporais(),
        relogio=relogio,
    )
    return menu, mensagens, registro


def _quadros(quantidade: int) -> list[Frame]:
    return [Frame(indice) for indice in range(quantidade)]


def _teclas_ate(enter_no_frame: int | None, parar_no_frame: int) -> list[int]:
    teclas = [0] * parar_no_frame
    if enter_no_frame is not None:
        teclas[enter_no_frame - 1] = ENTER
    else:
        teclas[parar_no_frame - 1] = ESC
    if enter_no_frame is not None:
        teclas.append(ESC)
    return teclas


def _textos(janela: JanelaRoteirizada) -> list[str]:
    return [texto for linhas in janela.linhas for texto, _cor in linhas]


def test_enter_antes_do_minimo_nao_le_nem_identifica_frame_de_confirmacao() -> None:
    relogio = RelogioManual()
    quadros = _quadros(17)
    camera = CameraRoteirizada(quadros)
    janela = JanelaRoteirizada(_teclas_ate(16, 16))
    identificador = IdentificadorRoteirizado([reconhecido(), reconhecido()])
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert camera.leituras == 17
    assert len(identificador.frames) == 2
    assert registro.ids == []
    assert any("Aguarde a validacao da identidade." in t for t in _textos(janela))


def test_tres_observacoes_sem_enter_nao_registram_presenca() -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(_quadros(24))
    janela = JanelaRoteirizada(_teclas_ate(None, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido()]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 3
    assert registro.ids == []
    assert any("Identidade consistente: Ana." in t for t in _textos(janela))


@pytest.mark.parametrize("enter_no_frame", [24, 25])
def test_enter_elegivel_reidentifica_frame_novo_e_registra_mesma_pessoa(
    enter_no_frame: int,
) -> None:
    relogio = RelogioManual()
    quadros = _quadros(enter_no_frame + 2)
    camera = CameraRoteirizada(quadros)
    teclas = _teclas_ate(enter_no_frame, enter_no_frame)
    janela = JanelaRoteirizada(teclas)
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido(), reconhecido()]
    )
    menu, mensagens, registro = _montar_menu(identificador, [camera], [janela], relogio)

    menu.reconhecer()

    assert identificador.frames[:3] == quadros[7:24:8]
    assert identificador.frames[3] is quadros[enter_no_frame]
    assert identificador.frames[3] not in janela.frames
    assert camera.leituras == enter_no_frame + 2
    assert registro.ids == [ANA.id]
    assert "Presenca registrada: Ana" in mensagens


def test_esc_nao_executa_inferencia_adicional_de_confirmacao() -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(_quadros(24))
    janela = JanelaRoteirizada(_teclas_ate(None, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido()]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 3
    assert camera.leituras == 24
    assert registro.ids == []


@pytest.mark.parametrize(
    "interrupcao",
    [NenhumRostoDetectado(), MultiplosRostosDetectados(2)],
    ids=["sem-rosto", "multiplos-rostos"],
)
def test_reconhecer_aluno_real_interrompe_sequencia_para_none(
    interrupcao: Exception,
) -> None:
    relogio = RelogioManual()
    alunos = FakeAlunoRepository(
        [ANA], {ANA.id: FaceEmbedding.de_valores([1.0, 0.0, 0.0], MODELO)}
    )
    provider = FakeFaceRecognition(
        embedding=FaceEmbedding.de_valores([1.0, 0.0, 0.0], MODELO)
    )
    provider.erros_ao_gerar = [None, interrupcao, None]
    reconhecedor = ReconhecerAluno(alunos, provider, MODELO, 0.30)
    camera = CameraRoteirizada(_quadros(24))
    janela = JanelaRoteirizada(_teclas_ate(None, 24))
    menu, _mensagens, registro = _montar_menu(reconhecedor, [camera], [janela], relogio)

    menu.reconhecer()

    assert provider.inferencias == 3
    assert registro.ids == []
    assert any("Validando identidade: 1/3." in t for t in _textos(janela))
    assert not any("Ana" in t for t in _textos(janela))


def test_qualidade_apos_duas_observacoes_impede_enter_no_terceiro_ciclo() -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(_quadros(25))
    janela = JanelaRoteirizada(_teclas_ate(24, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), RostoSemNitidez()]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 3
    assert camera.leituras == 25
    assert registro.ids == []
    assert any("Rosto sem nitidez." in t for t in _textos(janela))
    assert camera.liberada and janela.fechada


def test_troca_de_identidade_no_frame_de_confirmacao_nao_registra() -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(_quadros(26))
    janela = JanelaRoteirizada(_teclas_ate(24, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido(), reconhecido(BIA)]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 4
    assert registro.ids == []
    assert any(
        "Identidade mudou. Aguarde nova validacao." in t for t in _textos(janela)
    )


@pytest.mark.parametrize(
    "resultado",
    [None, RostoSemNitidez()],
    ids=["desconhecido", "qualidade"],
)
def test_desconhecido_ou_qualidade_na_confirmacao_nao_registra(
    resultado: Exception | None,
) -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(_quadros(26))
    janela = JanelaRoteirizada(_teclas_ate(24, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido(), resultado]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 4
    assert registro.ids == []
    if isinstance(resultado, RostoSemNitidez):
        assert any("Rosto sem nitidez." in t for t in _textos(janela))


def test_expiracao_durante_leitura_entre_comparacoes_bloqueia_enter() -> None:
    relogio = RelogioManual()

    def avancar_na_leitura(numero: int) -> None:
        relogio.avancar(0.1)
        if numero == 25:
            relogio.avancar(2.1)

    camera = CameraRoteirizada(_quadros(26), ao_ler=avancar_na_leitura)
    janela = JanelaRoteirizada(_teclas_ate(25, 25))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido()]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 3
    assert registro.ids == []
    assert any("Reconhecimento expirado." in t for t in _textos(janela))


def test_expiracao_enquanto_janela_aguarda_enter_nao_faz_nova_inferencia() -> None:
    relogio = RelogioManual()

    def atrasar_na_janela(numero: int) -> None:
        if numero == 24:
            relogio.avancar(2.1)

    camera = CameraRoteirizada(_quadros(26))
    janela = JanelaRoteirizada(_teclas_ate(24, 24), ao_mostrar=atrasar_na_janela)
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido()]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 3
    assert registro.ids == []
    assert any("Reconhecimento expirado." in t for t in _textos(janela))


def test_inferencia_lenta_nao_data_observacao_ao_final_do_processamento() -> None:
    relogio = RelogioManual()

    def atrasar_terceira_inferencia(numero: int, _frame: Frame) -> None:
        if numero == 3:
            relogio.avancar(2.1)

    camera = CameraRoteirizada(_quadros(25), ao_ler=lambda _n: relogio.avancar(0.1))
    janela = JanelaRoteirizada(_teclas_ate(24, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido()],
        ao_identificar=atrasar_terceira_inferencia,
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 3
    assert registro.ids == []
    assert any("Reconhecimento expirado." in t for t in _textos(janela))


def test_leitura_lenta_de_confirmacao_expira_a_evidencia() -> None:
    relogio = RelogioManual()

    def atrasar_leitura_de_confirmacao(numero: int) -> None:
        relogio.avancar(0.1)
        if numero == 25:
            relogio.avancar(2.1)

    camera = CameraRoteirizada(_quadros(27), ao_ler=atrasar_leitura_de_confirmacao)
    janela = JanelaRoteirizada(_teclas_ate(24, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido(), reconhecido()]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 4
    assert registro.ids == []
    assert any("Reconhecimento expirado." in t for t in _textos(janela))


def test_inferencia_lenta_de_confirmacao_expira_a_evidencia() -> None:
    relogio = RelogioManual()

    def atrasar_quarta_inferencia(numero: int, _frame: Frame) -> None:
        if numero == 4:
            relogio.avancar(2.1)

    camera = CameraRoteirizada(_quadros(26))
    janela = JanelaRoteirizada(_teclas_ate(24, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido(), reconhecido()],
        ao_identificar=atrasar_quarta_inferencia,
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    menu.reconhecer()

    assert len(identificador.frames) == 4
    assert registro.ids == []
    assert any("Reconhecimento expirado." in t for t in _textos(janela))


def test_estado_confirmado_volta_a_progresso_se_evento_sair_da_janela() -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(
        _quadros(28), ao_ler=lambda _numero: relogio.avancar(0.05)
    )
    janela = JanelaRoteirizada(_teclas_ate(None, 28))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido()]
    )
    menu, _mensagens, _registro = _montar_menu(
        identificador,
        [camera],
        [janela],
        relogio,
        temporal=ParametrosTemporais(
            min_observacoes=3,
            janela_segundos=1.0,
            validade_segundos=0.8,
        ),
    )

    menu.reconhecer()

    assert "Identidade consistente: Ana. ENTER para confirmar." in _textos(janela)
    assert "Validando identidade: 2/3. Olhe para a camera." in _textos(janela)
    assert "Identidade consistente: Ana. ENTER para confirmar." not in [
        texto for texto, _cor in janela.linhas[-1]
    ]


def test_leitura_de_camera_falha_na_confirmacao_libera_recursos_sem_registro() -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(_quadros(26), falhar_nas_leituras={25})
    janela = JanelaRoteirizada(_teclas_ate(24, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido()]
    )
    menu, mensagens, registro = _montar_menu(identificador, [camera], [janela], relogio)

    menu.reconhecer()

    assert len(identificador.frames) == 3
    assert registro.ids == []
    assert any("ERRO:" in mensagem for mensagem in mensagens)
    assert camera.liberada and janela.fechada


@pytest.mark.parametrize("erro", [ModeloIndisponivel(), PossivelFraude()])
def test_falha_de_provider_na_confirmacao_propaga_e_libera_recursos(
    erro: Exception,
) -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(_quadros(26))
    janela = JanelaRoteirizada(_teclas_ate(24, 24))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido(), erro]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador, [camera], [janela], relogio
    )

    with pytest.raises(type(erro)):
        menu.reconhecer()

    assert registro.ids == []
    assert camera.liberada and janela.fechada


def test_presenca_duplicada_consume_sequencia_antes_de_enter_seguinte() -> None:
    relogio = RelogioManual()
    camera = CameraRoteirizada(_quadros(27))
    teclas = [0] * 23 + [ENTER, ENTER, ESC]
    janela = JanelaRoteirizada(teclas)
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido(), reconhecido()]
    )
    menu, mensagens, registro = _montar_menu(
        identificador,
        [camera],
        [janela],
        relogio,
        registro=RegistroRoteirizado([False]),
    )

    menu.reconhecer()

    assert registro.ids == [ANA.id]
    assert len(identificador.frames) == 4
    assert "Presenca ja registrada hoje: Ana" in mensagens
    assert any("Aguarde a validacao da identidade." in t for t in _textos(janela))


def test_reentrada_no_modo_temporal_cria_sequencia_independente() -> None:
    relogio = RelogioManual()
    primeira_camera = CameraRoteirizada(_quadros(16))
    segunda_camera = CameraRoteirizada(_quadros(9))
    primeira_janela = JanelaRoteirizada(_teclas_ate(None, 16))
    segunda_janela = JanelaRoteirizada(_teclas_ate(8, 8))
    identificador = IdentificadorRoteirizado(
        [reconhecido(), reconhecido(), reconhecido()]
    )
    menu, _mensagens, registro = _montar_menu(
        identificador,
        [primeira_camera, segunda_camera],
        [primeira_janela, segunda_janela],
        relogio,
    )

    menu.reconhecer()
    menu.reconhecer()

    assert identificador.carregamentos == 2
    assert len(identificador.frames) == 3
    assert registro.ids == []
    assert primeira_camera.liberada and segunda_camera.liberada
