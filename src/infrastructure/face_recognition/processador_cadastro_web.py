"""Worker de cadastro web: três referências privadas e sem resposta biométrica."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, Protocol

from src.application.services.fila_facial import JobFacial
from src.application.services.worker_facial import (
    CodigoResultadoWorker,
    ResultadoWorker,
)
from src.application.use_cases.anexar_referencias_web import (
    AnexarReferencias,
    ContextoJobReferencias,
)
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.referencia_facial import PreparacaoReferencia
from src.domain.entities.solicitacao_cadastro import SolicitacaoCadastro
from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
    QualidadeCapturaInsuficiente,
)
from src.domain.services.desafio_captura import (
    DirecaoMovimento,
    OrientacaoPose,
)
from src.domain.services.face_recognition import FacePreparada
from src.infrastructure.face_recognition.processador_desafio_verificacao import (
    decodificar_frame,
)

logger = logging.getLogger(__name__)
LIMIAR_CONTINUIDADE = 0.30


class AdaptadorCadastro(Protocol):
    def preparar_cadastro(self, imagem: Any) -> FacePreparada: ...

    def preaquecer(self) -> None: ...


class AdaptadorPoseCadastro(Protocol):
    def analisar(self, imagem: Any) -> Any: ...

    def preaquecer(self) -> None: ...

    def fechar(self) -> None: ...


class RepositorioCadastro(Protocol):
    def obter_solicitacao(self, solicitacao_id: int) -> SolicitacaoCadastro: ...

    def cancelar_coleta_cadastro(
        self,
        solicitacao_id: int,
        job_id: Any,
        *,
        motivo: str,
        agora: datetime,
    ) -> None: ...


def codificar_recorte_png(imagem: Any) -> bytes:
    """Codifica somente o recorte BGR produzido pelo provider facial."""
    import numpy as np
    from PIL import Image

    array = np.asarray(imagem)
    if (
        array.ndim != 3
        or array.shape[2] != 3
        or array.dtype != np.uint8
        or array.size == 0
    ):
        raise ValueError("O recorte facial não possui formato válido.")
    rgb = np.ascontiguousarray(array[..., ::-1])
    buffer = BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


class ProcessadorCadastroWeb:
    """Aplica face única, qualidade, anti-spoofing e continuidade no worker ML."""

    def __init__(
        self,
        face: AdaptadorCadastro,
        repositorio: RepositorioCadastro,
        anexar: AnexarReferencias,
        pose: AdaptadorPoseCadastro,
        *,
        relogio: Callable[[], datetime],
        decodificador: Callable[[bytes], Any] = decodificar_frame,
        codificador: Callable[[Any], bytes] = codificar_recorte_png,
    ) -> None:
        self._face = face
        self._repositorio = repositorio
        self._anexar = anexar
        self._pose = pose
        self._relogio = relogio
        self._decodificador = decodificador
        self._codificador = codificador

    def processar(self, job: JobFacial, capturas: tuple[bytes, ...]) -> ResultadoWorker:
        try:
            solicitacao_id = int(job.dono_id)
            if solicitacao_id <= 0 or len(capturas) != 3:
                return self._falhar(job, None, "capturas_invalidas", tecnico=False)
            solicitacao = self._repositorio.obter_solicitacao(solicitacao_id)
            if (
                solicitacao.tipo not in {"cadastro", "atualizacao"}
                or solicitacao.estado != "em_validacao"
                or solicitacao.consentimento_em is None
                or solicitacao.consentimento_versao is None
                or solicitacao.expira_em <= self._agora()
            ):
                return self._falhar(
                    job, solicitacao_id, "solicitacao_indisponivel", tecnico=False
                )
            if (
                solicitacao.desafio_nonce_hash is None
                or solicitacao.desafio_direcao
                not in {
                    DirecaoMovimento.ESQUERDA.value,
                    DirecaoMovimento.DIREITA.value,
                }
                or solicitacao.desafio_expira_em is None
            ):
                return self._falhar(
                    job, solicitacao_id, "desafio_indisponivel", tecnico=False
                )
            if solicitacao.desafio_expira_em <= self._agora():
                return self._falhar(
                    job, solicitacao_id, "desafio_expirado", tecnico=False
                )

            orientacoes = (
                OrientacaoPose.FRENTE,
                OrientacaoPose(solicitacao.desafio_direcao),
                OrientacaoPose.FRENTE,
            )
            preparacoes: list[PreparacaoReferencia] = []
            embeddings: list[FaceEmbedding] = []
            for ordinal, conteudo in enumerate(capturas, start=1):
                if solicitacao.desafio_expira_em <= self._agora():
                    return self._falhar(
                        job, solicitacao_id, "desafio_expirado", tecnico=False
                    )
                imagem = self._decodificador(conteudo)
                resultado_pose = self._pose.analisar(imagem)
                if (
                    type(resultado_pose.quantidade_rostos) is not int
                    or resultado_pose.quantidade_rostos != 1
                ):
                    return self._falhar(
                        job,
                        solicitacao_id,
                        "face_unica_nao_confirmada",
                        tecnico=False,
                    )
                if resultado_pose.orientacao is not orientacoes[ordinal - 1]:
                    return self._falhar(
                        job,
                        solicitacao_id,
                        "movimento_nao_confirmado",
                        tecnico=False,
                    )
                preparada = self._face.preparar_cadastro(imagem)
                if not isinstance(preparada, FacePreparada):
                    raise ModeloIndisponivel("O provider não preparou uma face válida.")
                if any(
                    preparada.embedding.distancia_cosseno(anterior)
                    > LIMIAR_CONTINUIDADE
                    for anterior in embeddings
                ):
                    return self._falhar(
                        job,
                        solicitacao_id,
                        "continuidade_nao_confirmada",
                        tecnico=False,
                    )
                embeddings.append(preparada.embedding)
                preparacoes.append(
                    PreparacaoReferencia(
                        ordinal=ordinal,
                        captura_id=f"{job.id}:{ordinal}",
                        recorte=self._codificador(preparada.imagem),
                        embedding=preparada.embedding,
                    )
                )

            if solicitacao.desafio_expira_em <= self._agora():
                return self._falhar(
                    job, solicitacao_id, "desafio_expirado", tecnico=False
                )
            estado = self._anexar.executar(
                solicitacao_id,
                tuple(preparacoes),
                ContextoJobReferencias(
                    job_id=job.id,
                    consentimento_em=solicitacao.consentimento_em,
                    consentimento_versao=solicitacao.consentimento_versao,
                ),
            )
            if estado != "pendente_aprovacao":
                return self._falhar(
                    job, solicitacao_id, "solicitacao_indisponivel", tecnico=False
                )
            return ResultadoWorker(True, CodigoResultadoWorker.CONCLUIDA)
        except (PossivelFraude, QualidadeCapturaInsuficiente):
            return self._falhar(
                job, self._id_solicitacao(job), "recusa_biometrica", tecnico=False
            )
        except (NenhumRostoDetectado, MultiplosRostosDetectados, ValueError):
            return self._falhar(
                job, self._id_solicitacao(job), "captura_invalida", tecnico=False
            )
        except ModeloIndisponivel:
            return self._falhar(
                job, self._id_solicitacao(job), "modelo_indisponivel", tecnico=True
            )
        except Exception:
            logger.exception("Falha ao processar coleta facial web.")
            return self._falhar(
                job, self._id_solicitacao(job), "falha_tecnica", tecnico=True
            )

    def preaquecer(self) -> None:
        self._face.preaquecer()
        self._pose.preaquecer()

    def fechar(self) -> None:
        self._pose.fechar()

    def _falhar(
        self,
        job: JobFacial,
        solicitacao_id: int | None,
        motivo: str,
        *,
        tecnico: bool,
    ) -> ResultadoWorker:
        if solicitacao_id is not None:
            try:
                self._repositorio.cancelar_coleta_cadastro(
                    solicitacao_id,
                    job.id,
                    motivo=motivo,
                    agora=self._agora(),
                )
            except Exception:
                logger.exception("Falha ao encerrar coleta facial web.")
        return ResultadoWorker(
            False,
            CodigoResultadoWorker.FALHA_TECNICA
            if tecnico
            else CodigoResultadoWorker.RECUSA_BIOMETRICA,
        )

    @staticmethod
    def _id_solicitacao(job: JobFacial) -> int | None:
        try:
            solicitacao_id = int(job.dono_id)
        except (TypeError, ValueError):
            return None
        return solicitacao_id if solicitacao_id > 0 else None

    def _agora(self) -> datetime:
        instante = self._relogio()
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O relógio do worker deve conter fuso horário.")
        return instante.astimezone(UTC)
