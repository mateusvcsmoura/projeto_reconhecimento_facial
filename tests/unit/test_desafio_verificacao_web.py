from __future__ import annotations

import importlib
import importlib.util
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.application.services.fila_facial import (
    ArquivoTemporario,
    EstadoJobFacial,
    JobFacial,
    ManifestoTemporario,
    ReservaFacial,
    StatusOperacao,
    TipoJobFacial,
)
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.services.desafio_captura import EstadoDesafio
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    ReferenciaAtiva,
)
from src.infrastructure.storage.temporary_capture_storage import (
    TemporaryCaptureStorage,
)

MODULO = "src.application.use_cases.desafio_verificacao_web"
AGORA = datetime(2026, 10, 18, 12, tzinfo=UTC)


class ReferenciasFake:
    def __init__(self, refs: tuple[ReferenciaAtiva, ...]) -> None:
        self.refs = refs
        self.consultas: list[tuple[int, ...]] = []

    def obter_referencias_ativas(
        self, aluno_ids: tuple[int, ...] | None = None
    ) -> tuple[ReferenciaAtiva, ...]:
        assert aluno_ids is not None
        self.consultas.append(aluno_ids)
        return self.refs if any(ref.aluno_id in aluno_ids for ref in self.refs) else ()


class FilaFake:
    def __init__(self) -> None:
        self.job_id = uuid4()
        self.reservas: list[tuple[Any, ...]] = []
        self.submissoes: list[ManifestoTemporario] = []
        self.cancelamentos: list[tuple[UUID, str]] = []
        self.estado_consultado = EstadoJobFacial.RECEBIDA

    @staticmethod
    def limitar_prazo_reserva(prazo: datetime, *, agora: datetime) -> datetime:
        return min(prazo, agora + timedelta(minutes=5))

    def reservar(self, tipo: Any, dono_id: str, idempotencia: str, prazo: datetime):
        self.reservas.append((tipo, dono_id, idempotencia, prazo))
        return ReservaFacial(self.job_id, "credencial-secreta", prazo)

    def consultar(self, job_id: UUID, _credencial: str) -> StatusOperacao:
        assert job_id == self.job_id
        return StatusOperacao(
            job_id,
            self.estado_consultado,
            AGORA,
            AGORA,
            None,
        )

    def submeter(self, job_id: UUID, manifesto: ManifestoTemporario) -> JobFacial:
        assert job_id == self.job_id
        self.submissoes.append(manifesto)
        return JobFacial(
            id=job_id,
            dono_id="conta:1",
            tipo=TipoJobFacial.PRESENCA,
            estado=EstadoJobFacial.ENFILEIRADA,
            criada_em=AGORA,
            prazo=AGORA + timedelta(minutes=5),
            prazo_execucao=AGORA + timedelta(minutes=15),
            atualizada_em=AGORA,
            manifesto=manifesto,
            lease=None,
            lease_expira_em=None,
            resultado_codigo=None,
            credencial_hash="a" * 64,
        )

    def cancelar(self, job_id: UUID, credencial: str) -> bool:
        self.cancelamentos.append((job_id, credencial))
        return True


class RepositorioDesafioFake:
    def __init__(self) -> None:
        self.registros: dict[UUID, Any] = {}

    def criar(self, registro: Any) -> Any:
        return self.registros.setdefault(registro.id, registro)

    def obter(self, desafio_id: UUID) -> Any | None:
        return self.registros.get(desafio_id)

    def registrar_recebimento(
        self, desafio_id: UUID, sequencia: int, nonce_hash: str, agora: datetime
    ) -> Any | None:
        registro = self.registros.get(desafio_id)
        if (
            registro is None
            or registro.estado is not EstadoDesafio.AGUARDANDO_ETAPA
            or registro.nonce_hash != nonce_hash
            or sequencia != registro.etapa_validada + 1
        ):
            return None
        resultado = replace(
            registro,
            estado=EstadoDesafio.ETAPA_RECEBIDA,
            etapa_recebida=sequencia,
            atualizada_em=agora,
        )
        self.registros[desafio_id] = resultado
        return resultado

    def validar_etapa(
        self,
        desafio_id: UUID,
        sequencia: int,
        *,
        aprovada: bool,
        motivo: str | None,
        agora: datetime,
    ) -> Any | None:
        registro = self.registros.get(desafio_id)
        if registro is None:
            return None
        estado = (
            EstadoDesafio.REJEITADO
            if not aprovada
            else EstadoDesafio.CONCLUIDO
            if sequencia == 3
            else EstadoDesafio.AGUARDANDO_ETAPA
        )
        atualizado = replace(
            registro,
            estado=estado,
            etapa_validada=sequencia if aprovada else registro.etapa_validada,
            motivo=motivo,
            atualizada_em=agora,
        )
        self.registros[desafio_id] = atualizado
        return atualizado

    def encerrar(
        self,
        desafio_id: UUID,
        estado: EstadoDesafio,
        *,
        motivo: str,
        agora: datetime,
    ) -> Any | None:
        registro = self.registros.get(desafio_id)
        if registro is None:
            return None
        atualizado = replace(
            registro, estado=estado, motivo=motivo, atualizada_em=agora
        )
        self.registros[desafio_id] = atualizado
        return atualizado


def _refs(*, aluno: int = 12, conjunto: int = 34, versao: int = 2):
    embedding = FaceEmbedding.de_valores([1.0, *([0.0] * 511)], "Facenet512")
    return tuple(
        ReferenciaAtiva(aluno, conjunto, versao, embedding, ordinal)
        for ordinal in range(1, 4)
    )


def _service(tmp_path: Path, refs: tuple[ReferenciaAtiva, ...]):
    assert importlib.util.find_spec(MODULO) is not None, "Caso de uso ainda ausente."
    modulo = importlib.import_module(MODULO)
    fila = FilaFake()
    armazenamento = TemporaryCaptureStorage(
        tmp_path / "temporarios", max_bytes_per_capture=128, max_captures=3
    )
    desafio = modulo.DesafioCaptura(RepositorioDesafioFake(), segredo=b"s" * 32)
    servico = modulo.DesafioVerificacaoWeb(
        fila,
        ReferenciasFake(refs),
        armazenamento,
        desafio,
        relogio=lambda: AGORA,
    )
    return modulo, servico, fila, armazenamento


def test_inicio_fecha_matricula_e_referencia_sem_fallback_1n(tmp_path: Path) -> None:
    _, service, queue, _ = _service(tmp_path, _refs())

    result = service.iniciar(
        aluno_id_autorizado=12,
        dono_id="conta:1",
        idempotencia="desafio-001",
        prazo=AGORA + timedelta(minutes=4),
        agora=AGORA,
        conjunto_id=34,
        versao_referencia=2,
    )

    assert queue.reservas[0][0] is TipoJobFacial.PRESENCA
    assert queue.reservas[0][2] == "desafio-001"
    assert result.desafio.primeira_orientacao.value == "frente"


def test_sem_trinca_ativa_exata_nao_reserva_nem_procura_outro_aluno(
    tmp_path: Path,
) -> None:
    _, service, queue, _ = _service(tmp_path, _refs(conjunto=99))

    with pytest.raises(ValueError, match="referências"):
        service.iniciar(
            aluno_id_autorizado=12,
            dono_id="conta:1",
            idempotencia="desafio-002",
            prazo=AGORA + timedelta(minutes=4),
            agora=AGORA,
            conjunto_id=34,
            versao_referencia=2,
        )

    assert queue.reservas == []


def test_idempotencia_nao_reemite_desafio_em_job_em_andamento(tmp_path: Path) -> None:
    _, service, queue, storage = _service(tmp_path, _refs())
    queue.estado_consultado = EstadoJobFacial.PROCESSANDO

    with pytest.raises(ValueError, match="já foi iniciada"):
        service.iniciar(
            aluno_id_autorizado=12,
            dono_id="conta:1",
            idempotencia="desafio-em-andamento",
            prazo=AGORA + timedelta(minutes=4),
            agora=AGORA,
            conjunto_id=34,
            versao_referencia=2,
        )

    assert queue.cancelamentos == []
    assert not any(storage.raiz.iterdir())


def test_prazo_do_contexto_e_cortado_sem_ser_ampliado(tmp_path: Path) -> None:
    _, service, queue, _ = _service(tmp_path, _refs())

    result = service.iniciar(
        aluno_id_autorizado=12,
        dono_id="conta:1",
        idempotencia="desafio-prazo",
        prazo=AGORA + timedelta(hours=1),
        agora=AGORA,
        conjunto_id=34,
        versao_referencia=2,
    )

    assert queue.reservas[0][3] == AGORA + timedelta(minutes=5)
    assert result.desafio.expira_em <= queue.reservas[0][3]


def test_etapas_sao_salvas_no_job_e_nonce_errado_cancela(tmp_path: Path) -> None:
    _, service, queue, storage = _service(tmp_path, _refs())
    emitido = service.iniciar(
        aluno_id_autorizado=12,
        dono_id="conta:1",
        idempotencia="desafio-003",
        prazo=AGORA + timedelta(minutes=4),
        agora=AGORA,
        conjunto_id=34,
        versao_referencia=2,
    )

    service.submeter_etapa(
        emitido.operacao_id,
        emitido.credencial_operacao,
        emitido.desafio.nonce,
        1,
        b"frame-sintetico",
    )
    rejected = service.submeter_etapa(
        emitido.operacao_id,
        emitido.credencial_operacao,
        "nonce-errado",
        2,
        b"frame-que-deve-ser-descartado",
    )

    assert len(queue.submissoes) == 1
    assert queue.submissoes[0].capturas == (
        ArquivoTemporario(1, "captura-1.bin", len(b"frame-sintetico")),
    )
    assert rejected.estado.value == "rejeitado"
    assert queue.cancelamentos == [(emitido.operacao_id, emitido.credencial_operacao)]
    assert not (storage.raiz / str(emitido.operacao_id)).exists()


def test_reenvio_concorrente_da_etapa_nao_cancela_captura_valida(
    tmp_path: Path,
) -> None:
    _, service, queue, storage = _service(tmp_path, _refs())
    emitido = service.iniciar(
        aluno_id_autorizado=12,
        dono_id="conta:1",
        idempotencia="desafio-reenvio-concorrente",
        prazo=AGORA + timedelta(minutes=4),
        agora=AGORA,
        conjunto_id=34,
        versao_referencia=2,
    )
    service.submeter_etapa(
        emitido.operacao_id,
        emitido.credencial_operacao,
        emitido.desafio.nonce,
        1,
        b"frame-original",
    )

    repetida = service.submeter_etapa(
        emitido.operacao_id,
        emitido.credencial_operacao,
        emitido.desafio.nonce,
        1,
        b"frame-repetido",
    )

    assert repetida.estado == "etapa_recebida"
    assert len(queue.submissoes) == 1
    assert queue.cancelamentos == []
    assert (
        storage.ler_captura(emitido.operacao_id, "captura-1.bin") == b"frame-original"
    )
