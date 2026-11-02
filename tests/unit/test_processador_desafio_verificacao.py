from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import uuid4

import numpy as np
import pytest

from src.application.services.fila_facial import (
    ArquivoTemporario,
    EstadoJobFacial,
    JobFacial,
    ManifestoTemporario,
    TipoJobFacial,
)
from src.application.services.worker_facial import CodigoResultadoWorker
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    IluminacaoInsuficiente,
    MultiplosRostosDetectados,
    RostoSemNitidez,
)
from src.domain.services.desafio_captura import (
    ContextoDesafio,
    DesafioCaptura,
    EstadoDesafio,
    EvidenciaEtapa,
    OrientacaoPose,
)
from src.infrastructure.face_recognition.processador_desafio_verificacao import (
    ProcessadorDesafioVerificacao,
    decodificar_frame,
)
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    ReferenciaAtiva,
)

AGORA = datetime(2026, 10, 18, 12, tzinfo=UTC)


def test_frame_acima_do_limite_de_pixels_nao_chega_ao_opencv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CabecalhoImagem:
        size = (2049, 2048)

        def __enter__(self) -> CabecalhoImagem:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    pillow = ModuleType("PIL")
    pillow.Image = SimpleNamespace(open=lambda _conteudo: CabecalhoImagem())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", pillow)

    class Cv2Fake:
        IMREAD_COLOR = 1

        @staticmethod
        def imdecode(*_args: object) -> None:
            raise AssertionError("OpenCV não deve decodificar um frame acima do limite")

    monkeypatch.setitem(sys.modules, "cv2", Cv2Fake())

    with pytest.raises(ValueError, match="limite de pixels"):
        decodificar_frame(b"imagem-sintetica")


class RepositorioDesafioFake:
    def __init__(self) -> None:
        self.registros: dict[Any, Any] = {}

    def criar(self, registro: Any) -> Any:
        self.registros[registro.id] = registro
        return registro

    def obter(self, desafio_id: Any) -> Any | None:
        return self.registros.get(desafio_id)

    def registrar_recebimento(
        self, desafio_id: Any, sequencia: int, nonce_hash: str, agora: datetime
    ) -> Any | None:
        registro = self.registros[desafio_id]
        if (
            registro.estado is not EstadoDesafio.AGUARDANDO_ETAPA
            or sequencia != registro.etapa_validada + 1
            or registro.nonce_hash != nonce_hash
        ):
            return None
        resultado = replace(
            registro,
            etapa_recebida=sequencia,
            estado=EstadoDesafio.ETAPA_RECEBIDA,
            atualizada_em=agora,
        )
        self.registros[desafio_id] = resultado
        return resultado

    def validar_etapa(
        self,
        desafio_id: Any,
        sequencia: int,
        *,
        aprovada: bool,
        motivo: str | None,
        agora: datetime,
        repetir: bool = False,
    ) -> Any | None:
        registro = self.registros[desafio_id]
        estado = (
            EstadoDesafio.AGUARDANDO_ETAPA
            if not aprovada and repetir
            else EstadoDesafio.REJEITADO
            if not aprovada
            else EstadoDesafio.CONCLUIDO
            if sequencia == 3
            else EstadoDesafio.AGUARDANDO_ETAPA
        )
        atualizado = replace(
            registro,
            estado=estado,
            etapa_validada=sequencia if aprovada else registro.etapa_validada,
            etapa_recebida=(
                registro.etapa_validada if repetir else registro.etapa_recebida
            ),
            motivo=motivo,
            atualizada_em=agora,
        )
        self.registros[desafio_id] = atualizado
        return atualizado

    def encerrar(
        self,
        desafio_id: Any,
        estado: EstadoDesafio,
        *,
        motivo: str,
        agora: datetime,
    ) -> Any | None:
        registro = self.registros[desafio_id]
        atualizado = replace(
            registro,
            estado=estado,
            motivo=motivo,
            atualizada_em=agora,
        )
        self.registros[desafio_id] = atualizado
        return atualizado


class ReferenciasFake:
    def __init__(self, refs: tuple[ReferenciaAtiva, ...]) -> None:
        self.refs = refs
        self.consultas: list[tuple[int, ...]] = []

    def obter_referencias_ativas(self, aluno_ids: tuple[int, ...] | None = None):
        assert aluno_ids is not None
        self.consultas.append(aluno_ids)
        return self.refs


class FaceFake:
    def __init__(self, embeddings: dict[bytes, FaceEmbedding]) -> None:
        self.embeddings = embeddings

    def gerar_embedding(self, imagem: bytes) -> FaceEmbedding:
        return self.embeddings[imagem]


class PoseFake:
    def __init__(self, orientacao: OrientacaoPose, rostos: int = 1) -> None:
        self.orientacao = orientacao
        self.rostos = rostos
        self.fechado = False

    def analisar(self, _imagem: bytes) -> Any:
        return SimpleNamespace(
            orientacao=self.orientacao,
            quantidade_rostos=self.rostos,
        )

    def fechar(self) -> None:
        self.fechado = True


def _embedding(primeiro: float, segundo: float = 0.0) -> FaceEmbedding:
    vetor = np.zeros(512, dtype=np.float32)
    vetor[0] = primeiro
    vetor[1] = segundo
    return FaceEmbedding.de_valores(vetor, "Facenet512")


def _refs(embedding: FaceEmbedding) -> tuple[ReferenciaAtiva, ...]:
    return tuple(
        ReferenciaAtiva(12, 34, 2, embedding, ordinal) for ordinal in range(1, 4)
    )


def _preparar(etapa: int):
    job_id = uuid4()
    repositorio = RepositorioDesafioFake()
    desafio = DesafioCaptura(repositorio, segredo=b"s" * 32)
    emitido = desafio.emitir(
        ContextoDesafio(job_id, 12, 34, 2, AGORA + timedelta(minutes=2)),
        AGORA,
    )
    for sequencia in range(1, etapa):
        desafio.registrar_etapa_recebida(job_id, emitido.nonce, sequencia, AGORA)
        pose = (
            OrientacaoPose.FRENTE
            if sequencia in (1, 3)
            else OrientacaoPose(emitido.direcao.value)
        )
        desafio.validar_etapa(
            job_id,
            sequencia,
            EvidenciaEtapa(1, pose, True, True, True, 2),
            AGORA,
        )
    desafio.registrar_etapa_recebida(job_id, emitido.nonce, etapa, AGORA)
    refs = _refs(_embedding(1.0))
    return job_id, desafio, refs, emitido, repositorio


def _job(job_id: Any, stage: int, captures: tuple[bytes, ...]) -> JobFacial:
    return JobFacial(
        id=job_id,
        dono_id="conta:1",
        tipo=TipoJobFacial.PRESENCA,
        estado=EstadoJobFacial.PROCESSANDO,
        criada_em=AGORA,
        prazo=AGORA + timedelta(minutes=5),
        prazo_execucao=AGORA + timedelta(minutes=15),
        atualizada_em=AGORA,
        manifesto=ManifestoTemporario(
            job_id,
            tuple(
                ArquivoTemporario(i, f"captura-{i}.bin", len(data))
                for i, data in enumerate(captures, start=1)
            ),
        ),
        lease="lease",
        lease_expira_em=AGORA + timedelta(minutes=2),
        resultado_codigo=None,
        credencial_hash="a" * 64,
    )


def test_worker_confirma_identidade_pose_qualidade_e_antispoofing() -> None:
    job_id, desafio, refs, _, repositorio = _preparar(1)
    vetor = _embedding(1.0)
    processor = ProcessadorDesafioVerificacao(
        repositorio,
        ReferenciasFake(refs),
        desafio,
        FaceFake({b"frame-1": vetor}),
        PoseFake(OrientacaoPose.FRENTE),
        relogio=lambda: AGORA,
        decodificador=lambda content: content,
    )

    resultado = processor.processar(_job(job_id, 1, (b"frame-1",)), (b"frame-1",))

    assert resultado.aguardando_etapa is True
    assert resultado.resultado_facial is not None
    assert resultado.resultado_facial.identidade_ok is True
    assert resultado.resultado_facial.antispoofing_ok is True
    assert resultado.resultado_facial.qualidade_ok is True
    assert resultado.resultado_facial.desafio_ok is False
    assert not hasattr(resultado.resultado_facial, "embedding")


class FaceComRostoFalso:
    """Haar vê dois rostos; só a nova detecção com maior_rosto passa."""

    def __init__(self, vetor: FaceEmbedding) -> None:
        self.vetor = vetor
        self.chamadas: list[bool] = []

    def gerar_embedding(
        self, _imagem: bytes, *, maior_rosto: bool = False
    ) -> FaceEmbedding:
        self.chamadas.append(maior_rosto)
        if not maior_rosto:
            raise MultiplosRostosDetectados(2)
        return self.vetor


@pytest.mark.parametrize(("rostos_mediapipe", "aceita"), [(1, True), (2, False)])
def test_worker_usa_o_maior_rosto_so_quando_o_mediapipe_conta_um(
    rostos_mediapipe: int, aceita: bool
) -> None:
    job_id, desafio, refs, _, repositorio = _preparar(1)
    face = FaceComRostoFalso(_embedding(1.0))
    processor = ProcessadorDesafioVerificacao(
        repositorio,
        ReferenciasFake(refs),
        desafio,
        face,
        PoseFake(OrientacaoPose.FRENTE, rostos=rostos_mediapipe),
        relogio=lambda: AGORA,
        decodificador=lambda content: content,
    )

    resultado = processor.processar(_job(job_id, 1, (b"frame-1",)), (b"frame-1",))

    if aceita:
        assert face.chamadas == [False, True]
        assert resultado.resultado_facial is not None
        assert resultado.resultado_facial.identidade_ok is True
    else:
        # Duas pessoas para o MediaPipe também: a etapa volta, sem nova detecção.
        assert face.chamadas == [False]
        assert repositorio.obter(job_id).motivo == "face_unica_nao_confirmada"


class FaceRecusada:
    def __init__(self, erro: Exception) -> None:
        self._erro = erro

    def gerar_embedding(self, _imagem: bytes) -> FaceEmbedding:
        raise self._erro


@pytest.mark.parametrize(
    ("erro", "motivo"),
    [
        # Só o escuro tem motivo próprio: é ele que acende o flash frontal.
        (
            IluminacaoInsuficiente("luminosidade=50.0 nitidez=20.0"),
            "iluminacao_insuficiente",
        ),
        (RostoSemNitidez("nitidez=20.0 luminosidade=120.0"), "qualidade_insuficiente"),
    ],
)
def test_worker_devolve_a_etapa_quando_a_captura_esta_escura_ou_borrada(
    erro: Exception, motivo: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    job_id, desafio, refs, _, repositorio = _preparar(1)
    processor = ProcessadorDesafioVerificacao(
        repositorio,
        ReferenciasFake(refs),
        desafio,
        FaceRecusada(erro),
        PoseFake(OrientacaoPose.FRENTE),
        relogio=lambda: AGORA,
        decodificador=lambda content: content,
    )

    resultado = processor.processar(_job(job_id, 1, (b"frame-1",)), (b"frame-1",))

    # Luz insuficiente é corrigível: a tentativa continua e a etapa 1 volta.
    assert f"etapa=1: devolvida {motivo}." in caplog.text
    assert resultado.sucesso is False
    assert resultado.aguardando_etapa is True
    registro = repositorio.obter(job_id)
    assert registro.estado is EstadoDesafio.AGUARDANDO_ETAPA
    assert registro.etapa_recebida == registro.etapa_validada == 0
    assert registro.motivo == motivo


def test_worker_recusa_duas_pessoas_ou_face_landmarker_sem_face() -> None:
    job_id, desafio, refs, _, repositorio = _preparar(2)
    vetor = _embedding(1.0)
    processor = ProcessadorDesafioVerificacao(
        repositorio,
        ReferenciasFake(refs),
        desafio,
        FaceFake({b"frame-1": vetor, b"frame-2": vetor}),
        PoseFake(OrientacaoPose.MULTIPLOS, rostos=2),
        relogio=lambda: AGORA,
        decodificador=lambda content: content,
    )

    resultado = processor.processar(
        _job(job_id, 2, (b"frame-1", b"frame-2")),
        (b"frame-1", b"frame-2"),
    )

    assert resultado.sucesso is False
    assert resultado.aguardando_etapa is False
    assert resultado.codigo is CodigoResultadoWorker.RECUSA_BIOMETRICA
    assert repositorio.obter(job_id).estado is EstadoDesafio.REJEITADO
