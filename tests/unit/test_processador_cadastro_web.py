from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np
import pytest

from src.application.services.fila_facial import (
    EstadoJobFacial,
    JobFacial,
    ManifestoTemporario,
    TipoJobFacial,
)
from src.application.services.worker_facial import CodigoResultadoWorker
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.solicitacao_cadastro import SolicitacaoCadastro
from src.domain.errors import IluminacaoInsuficiente, RostoSemNitidez
from src.domain.services.desafio_captura import OrientacaoPose
from src.domain.services.face_recognition import FacePreparada
from src.infrastructure.face_recognition.processador_cadastro_web import (
    ProcessadorCadastroWeb,
    codificar_recorte_png,
)

AGORA = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)


def _solicitacao(estado: str = "em_validacao") -> SolicitacaoCadastro:
    return SolicitacaoCadastro(
        id=71,
        tipo="cadastro",
        estado=estado,  # type: ignore[arg-type]
        turma_id=14,
        aluno_id=None,
        matricula="000123",
        nome="Pessoa Sintética",
        expira_em=AGORA + timedelta(days=6),
        consentimento_em=AGORA - timedelta(minutes=1),
        consentimento_versao="aviso-v1",
        desafio_nonce_hash=hashlib.sha256(b"nonce-teste").hexdigest(),
        desafio_direcao="direita",
        desafio_expira_em=AGORA + timedelta(minutes=2),
    )


def _job() -> JobFacial:
    return JobFacial(
        id=uuid4(),
        dono_id="71",
        tipo=TipoJobFacial.CADASTRO,
        estado=EstadoJobFacial.PROCESSANDO,
        criada_em=AGORA,
        prazo=AGORA + timedelta(minutes=5),
        prazo_execucao=AGORA + timedelta(minutes=15),
        atualizada_em=AGORA,
        manifesto=ManifestoTemporario(job_id=uuid4(), capturas=()),
        lease="lease",
        lease_expira_em=AGORA + timedelta(minutes=2),
        resultado_codigo=None,
        credencial_hash="0" * 64,
    )


class FaceFake:
    modelo = "Facenet512"

    def __init__(self, vectores: tuple[list[float], ...]) -> None:
        self.vectores = vectores
        self.chamadas = 0
        self.aquecimentos = 0

    def preparar_cadastro(self, imagem: bytes) -> FacePreparada:
        vetor = self.vectores[self.chamadas]
        self.chamadas += 1
        return FacePreparada(
            imagem=imagem,
            embedding=FaceEmbedding.de_valores(vetor, "Facenet512"),
        )

    def preaquecer(self) -> None:
        self.aquecimentos += 1


class SolicitacoesFake:
    def __init__(self, solicitacao: SolicitacaoCadastro | None = None) -> None:
        self.solicitacao = solicitacao or _solicitacao()
        self.cancelamentos: list[str] = []
        self.reaberturas: list[str] = []
        self.anexadas: list[tuple[object, ...]] = []

    def obter_solicitacao(self, _solicitacao_id: int) -> SolicitacaoCadastro:
        return self.solicitacao

    def estado_do_job(self, _solicitacao_id: int, _job_id: object) -> str | None:
        return None

    def anexar_referencias(self, _solicitacao_id: int, **kwargs: object) -> str:
        self.anexadas.append(tuple(kwargs["referencias"]))  # type: ignore[arg-type]
        return "pendente_aprovacao"

    def cancelar_coleta_cadastro(
        self, _solicitacao_id: int, _job_id: object, *, motivo: str, agora: datetime
    ) -> None:
        self.cancelamentos.append(motivo)

    def reabrir_coleta_cadastro(
        self, _solicitacao_id: int, _job_id: object, *, motivo: str, agora: datetime
    ) -> None:
        self.reaberturas.append(motivo)


class AnexarFake:
    def __init__(self, repository: SolicitacoesFake) -> None:
        self.repository = repository
        self.calls: list[tuple[object, ...]] = []

    def executar(
        self, solicitacao_id: int, preparacoes: tuple[object, ...], contexto: object
    ) -> str:
        self.calls.append(preparacoes)
        return self.repository.anexar_referencias(
            solicitacao_id,
            job_id=contexto.job_id,  # type: ignore[attr-defined]
            referencias=tuple(
                type("Ref", (), {"ordinal": i, "embedding": item.embedding})()
                for i, item in enumerate(preparacoes, 1)
            ),
            consentimento_em=contexto.consentimento_em,  # type: ignore[attr-defined]
            consentimento_versao=contexto.consentimento_versao,  # type: ignore[attr-defined]
            agora=AGORA,
        )


class PoseFake:
    def __init__(
        self,
        orientacoes: tuple[OrientacaoPose, ...],
        quantidade_rostos: int = 1,
    ) -> None:
        self.orientacoes = orientacoes
        self.quantidade_rostos = quantidade_rostos
        self.chamadas = 0
        self.aquecimentos = 0
        self.fechamentos = 0

    def analisar(self, _imagem: bytes) -> object:
        from src.infrastructure.face_recognition.desafio_movimento_adapter import (
            ResultadoPose,
        )

        orientacao = self.orientacoes[self.chamadas]
        self.chamadas += 1
        return ResultadoPose(self.quantidade_rostos, orientacao)

    def preaquecer(self) -> None:
        self.aquecimentos += 1

    def fechar(self) -> None:
        self.fechamentos += 1


def _processor(
    vectores: tuple[list[float], ...],
    repository: SolicitacoesFake,
    orientacoes: tuple[OrientacaoPose, ...] = (
        OrientacaoPose.FRENTE,
        OrientacaoPose.DIREITA,
        OrientacaoPose.FRENTE,
    ),
    quantidade_rostos: int = 1,
) -> ProcessadorCadastroWeb:
    return ProcessadorCadastroWeb(
        FaceFake(vectores),
        repository,
        AnexarFake(repository),
        PoseFake(orientacoes, quantidade_rostos),
        relogio=lambda: AGORA,
        decodificador=lambda content: content,
        codificador=lambda image: b"crop-" + image,
    )


def test_codificador_salva_png_sem_original_externo() -> None:
    recorte = np.array([[[10, 20, 30]]], dtype=np.uint8)

    resultado = codificar_recorte_png(recorte)

    assert resultado.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    "recorte",
    [
        np.array([], dtype=np.uint8),
        np.zeros((2, 2), dtype=np.uint8),
        np.zeros((1, 1, 4), dtype=np.uint8),
        np.zeros((1, 1, 3), dtype=np.float32),
    ],
)
def test_codificador_recusa_recorte_com_formato_invalido(recorte: np.ndarray) -> None:
    with pytest.raises(ValueError, match="recorte facial"):
        codificar_recorte_png(recorte)


def test_worker_expõe_aquecimento_e_fechamento_dos_providers() -> None:
    repository = SolicitacoesFake()
    vector = [1.0] + [0.0] * 511
    face = FaceFake((vector, vector, vector))
    pose = PoseFake(
        (OrientacaoPose.FRENTE, OrientacaoPose.DIREITA, OrientacaoPose.FRENTE)
    )
    processor = ProcessadorCadastroWeb(
        face,
        repository,
        AnexarFake(repository),
        pose,
        relogio=lambda: AGORA,
        decodificador=lambda content: content,
        codificador=lambda image: b"crop-" + image,
    )

    processor.preaquecer()
    processor.fechar()

    assert face.aquecimentos == 1
    assert pose.aquecimentos == 1
    assert pose.fechamentos == 1


def test_worker_recusa_desafio_expirado_antes_de_decodificar() -> None:
    solicitacao = replace(
        _solicitacao(), desafio_expira_em=AGORA - timedelta(seconds=1)
    )
    repository = SolicitacoesFake(solicitacao)
    vector = [1.0] + [0.0] * 511

    resultado = _processor((vector, vector, vector), repository).processar(
        _job(), (b"a", b"b", b"c")
    )

    assert not resultado.sucesso
    assert repository.cancelamentos == ["desafio_expirado"]


def test_worker_recusa_quando_pose_nao_confirma_face_unica() -> None:
    repository = SolicitacoesFake()
    vector = [1.0] + [0.0] * 511
    processor = _processor((vector, vector, vector), repository, quantidade_rostos=0)

    resultado = processor.processar(_job(), (b"a", b"b", b"c"))

    assert not resultado.sucesso
    # Rosto não confirmado é corrigível: a coleta reabre em vez de cancelar.
    assert repository.reaberturas == ["face_unica_nao_confirmada"]
    assert not repository.cancelamentos
    assert not repository.anexadas


class FaceRecusada(FaceFake):
    def __init__(self, erro: Exception) -> None:
        super().__init__(())
        self.erro = erro

    def preparar_cadastro(self, imagem: bytes) -> FacePreparada:
        raise self.erro


@pytest.mark.parametrize(
    ("erro", "motivo"),
    [
        (
            IluminacaoInsuficiente("luminosidade=50.0 nitidez=20.0"),
            "iluminacao_insuficiente",
        ),
        (RostoSemNitidez("nitidez=20.0 luminosidade=120.0"), "qualidade_insuficiente"),
    ],
)
def test_worker_reabre_coleta_separando_rosto_escuro_de_borrado(
    erro: Exception, motivo: str
) -> None:
    repository = SolicitacoesFake()
    processor = ProcessadorCadastroWeb(
        FaceRecusada(erro),
        repository,
        AnexarFake(repository),
        PoseFake(
            (OrientacaoPose.FRENTE, OrientacaoPose.DIREITA, OrientacaoPose.FRENTE)
        ),
        relogio=lambda: AGORA,
        decodificador=lambda content: content,
        codificador=lambda image: b"crop-" + image,
    )

    resultado = processor.processar(_job(), (b"a", b"b", b"c"))

    assert not resultado.sucesso
    assert repository.reaberturas == [motivo]
    assert not repository.cancelamentos


def test_worker_valida_tres_frames_e_entrega_referencias_pendentes() -> None:
    repository = SolicitacoesFake()
    vetor = [1.0] + [0.0] * 511
    processor = _processor((vetor, vetor, vetor), repository)
    job = _job()

    resultado = processor.processar(job, (b"a", b"b", b"c"))

    assert resultado.sucesso
    assert resultado.codigo is CodigoResultadoWorker.CONCLUIDA
    assert repository.anexadas and len(repository.anexadas[0]) == 3
    assert not hasattr(resultado, "embedding")


def test_worker_recusa_capturas_sem_continuidade_e_cancela_solicitacao() -> None:
    repository = SolicitacoesFake()
    a = [1.0] + [0.0] * 511
    b = [0.0, 1.0] + [0.0] * 510
    processor = _processor((a, b, a), repository)

    resultado = processor.processar(_job(), (b"a", b"b", b"c"))

    assert not resultado.sucesso
    assert resultado.codigo is CodigoResultadoWorker.RECUSA_BIOMETRICA
    assert repository.cancelamentos == ["continuidade_nao_confirmada"]
    assert not repository.anexadas


def test_worker_recusa_capturas_fora_da_sequencia_de_pose_do_desafio() -> None:
    repository = SolicitacoesFake()
    vetor = [1.0] + [0.0] * 511
    processor = _processor(
        (vetor, vetor, vetor),
        repository,
        (
            OrientacaoPose.FRENTE,
            OrientacaoPose.ESQUERDA,
            OrientacaoPose.FRENTE,
        ),
    )

    resultado = processor.processar(_job(), (b"a", b"b", b"c"))

    assert not resultado.sucesso
    assert resultado.codigo is CodigoResultadoWorker.RECUSA_BIOMETRICA
    assert repository.reaberturas == ["movimento_nao_confirmado"]
    assert not repository.cancelamentos
    assert not repository.anexadas


def test_worker_recusa_coleta_sem_desafio_emitido() -> None:
    repository = SolicitacoesFake(
        _solicitacao().__class__(
            id=71,
            tipo="cadastro",
            estado="em_validacao",
            turma_id=14,
            aluno_id=None,
            matricula="000123",
            nome="Pessoa Sintética",
            expira_em=AGORA + timedelta(days=6),
            consentimento_em=AGORA - timedelta(minutes=1),
            consentimento_versao="aviso-v1",
        )
    )
    vetor = [1.0] + [0.0] * 511

    resultado = _processor((vetor, vetor, vetor), repository).processar(
        _job(), (b"a", b"b", b"c")
    )

    assert not resultado.sucesso
    assert repository.cancelamentos == ["desafio_indisponivel"]
    assert not repository.anexadas


def test_worker_nao_processa_capturas_sem_consentimento() -> None:
    repository = SolicitacoesFake(
        _solicitacao().__class__(
            id=71,
            tipo="cadastro",
            estado="em_validacao",
            turma_id=14,
            aluno_id=None,
            matricula="000123",
            nome="Pessoa Sintética",
            expira_em=AGORA + timedelta(days=6),
            consentimento_em=None,
            consentimento_versao=None,
        )
    )
    vetor = [1.0] + [0.0] * 511
    resultado = _processor((vetor, vetor, vetor), repository).processar(
        _job(), (b"a", b"b", b"c")
    )

    assert not resultado.sucesso
    assert repository.cancelamentos
    assert not repository.anexadas
