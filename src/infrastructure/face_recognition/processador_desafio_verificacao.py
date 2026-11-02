"""Worker da verificação 1:1; processa uma etapa sem gravar presença."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, Protocol
from uuid import UUID

from src.application.services.fila_facial import JobFacial
from src.application.services.worker_facial import (
    CodigoResultadoWorker,
    ResultadoWorker,
)
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    IluminacaoInsuficiente,
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
    QualidadeCapturaInsuficiente,
)
from src.domain.services.desafio_captura import (
    DesafioCaptura,
    EstadoDesafio,
    EvidenciaEtapa,
)
from src.domain.services.face_recognition import ResultadoFacial
from src.domain.services.verificacao_identidade import (
    POLITICA_VERIFICACAO,
    PoliticaVerificacaoIdentidade,
    ReferenciaIdentidade,
    VerificarIdentidade,
)
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    ReferenciaAtiva,
)

MAX_PIXELS_FRAME = 4_194_304
MAX_LADO_FRAME = 8192


class LeitorDesafio(Protocol):
    def obter(self, desafio_id: UUID) -> Any | None: ...


class LeitorReferencias(Protocol):
    def obter_referencias_ativas(
        self, aluno_ids: tuple[int, ...] | None = None
    ) -> tuple[ReferenciaAtiva, ...]: ...


class AdaptadorFace(Protocol):
    def gerar_embedding(self, imagem: Any) -> FaceEmbedding: ...


class AdaptadorPose(Protocol):
    def analisar(self, imagem: Any) -> Any: ...

    def fechar(self) -> None: ...


class AdaptadorPoseSobDemanda:
    """Abre o processo MediaPipe somente depois do lock único do worker."""

    def __init__(self, fabrica: Callable[[], AdaptadorPose]) -> None:
        self._fabrica = fabrica
        self._adaptador: AdaptadorPose | None = None

    def preaquecer(self) -> None:
        if self._adaptador is None:
            self._adaptador = self._fabrica()

    def analisar(self, imagem: Any) -> Any:
        self.preaquecer()
        assert self._adaptador is not None
        return self._adaptador.analisar(imagem)

    def fechar(self) -> None:
        if self._adaptador is not None:
            self._adaptador.fechar()
            self._adaptador = None


def decodificar_frame(conteudo: bytes) -> Any:
    """Valida dimensões antes de decodificar no worker ML."""
    import cv2
    import numpy as np
    from PIL import Image

    if not isinstance(conteudo, bytes) or not conteudo:
        raise ValueError("Frame vazio.")
    try:
        with Image.open(BytesIO(conteudo)) as cabecalho:
            largura, altura = cabecalho.size
    except (Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ValueError("Frame inválido.") from exc
    if (
        isinstance(largura, bool)
        or not isinstance(largura, int)
        or isinstance(altura, bool)
        or not isinstance(altura, int)
        or largura < 64
        or altura < 64
        or largura > MAX_LADO_FRAME
        or altura > MAX_LADO_FRAME
        or largura * altura > MAX_PIXELS_FRAME
    ):
        raise ValueError("Frame excede o limite de pixels ou dimensão.")
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if (
        imagem is None
        or imagem.ndim != 3
        or imagem.shape[2] != 3
        or imagem.shape[0] != altura
        or imagem.shape[1] != largura
    ):
        raise ValueError("Frame inválido.")
    return imagem


class ProcessadorDesafioVerificacao:
    """Valida identidade, qualidade, anti-spoofing, pose e continuidade."""

    def __init__(
        self,
        desafios: LeitorDesafio,
        referencias: LeitorReferencias,
        desafio: DesafioCaptura,
        face: AdaptadorFace,
        pose: AdaptadorPose,
        *,
        relogio: Callable[[], datetime],
        decodificador: Callable[[bytes], Any] = decodificar_frame,
    ) -> None:
        self._desafios = desafios
        self._referencias = referencias
        self._desafio = desafio
        self._face = face
        self._pose = pose
        self._relogio = relogio
        self._decodificador = decodificador
        self._verificador = VerificarIdentidade()

    def processar(self, job: JobFacial, capturas: tuple[bytes, ...]) -> ResultadoWorker:
        registro = self._desafios.obter(job.id)
        if (
            registro is None
            or registro.estado is not EstadoDesafio.ETAPA_RECEBIDA
            or not 1 <= registro.etapa_recebida <= 3
            or registro.etapa_recebida != registro.etapa_validada + 1
            or len(capturas) != registro.etapa_recebida
        ):
            return self._falha(registro, "protocolo_invalido", tecnico=False)

        politica = PoliticaVerificacaoIdentidade(
            registro.aluno_id,
            registro.conjunto_id,
            registro.versao_referencia,
        )
        referencias = self._carregar_referencias(politica)
        if referencias is None:
            return self._falha(registro, "referencias_incompativeis", tecnico=False)

        embeddings: list[FaceEmbedding] = []
        decisao_atual = None
        try:
            for conteudo in capturas:
                imagem = self._decodificador(conteudo)
                embedding = self._face.gerar_embedding(imagem)
                decisao = self._verificador.executar(embedding, referencias, politica)
                if not decisao.identidade_ok:
                    return self._falha(
                        registro,
                        "identidade_nao_confirmada",
                        tecnico=False,
                        identidade=False,
                        distancia=decisao.distancia_mediana,
                    )
                if any(
                    embedding.distancia_cosseno(anterior) > 0.30
                    for anterior in embeddings
                ):
                    return self._falha(
                        registro,
                        "continuidade_nao_confirmada",
                        tecnico=False,
                        identidade=False,
                    )
                embeddings.append(embedding)
                decisao_atual = decisao
            assert decisao_atual is not None
            pose = self._pose.analisar(imagem)
        except PossivelFraude:
            return self._falha(
                registro,
                "antispoofing_recusado",
                tecnico=False,
                identidade=True,
                antispoofing=False,
            )
        except IluminacaoInsuficiente:
            return self._repetir(registro, "iluminacao_insuficiente")
        except QualidadeCapturaInsuficiente:
            return self._repetir(registro, "qualidade_insuficiente")
        except (NenhumRostoDetectado, MultiplosRostosDetectados):
            return self._repetir(registro, "face_unica_nao_confirmada")
        except ModeloIndisponivel:
            return self._falha(registro, "modelo_indisponivel", tecnico=True)
        except Exception:
            return self._falha(registro, "falha_tecnica", tecnico=True)

        evidencia = EvidenciaEtapa(
            quantidade_rostos=pose.quantidade_rostos,
            orientacao=pose.orientacao,
            identidade_ok=True,
            qualidade_ok=True,
            antispoofing_ok=True,
            versao_referencia=registro.versao_referencia,
        )
        validacao = self._desafio.validar_etapa(
            job.id,
            registro.etapa_recebida,
            evidencia,
            self._utc(self._relogio()),
        )
        facial = ResultadoFacial(
            identidade_ok=True,
            desafio_ok=validacao.desafio_ok,
            antispoofing_ok=True,
            qualidade_ok=True,
            motivo_tecnico=validacao.motivo_tecnico,
            versao_referencia=registro.versao_referencia,
            politica=decisao_atual.politica,
            distancia_mediana=decisao_atual.distancia_mediana,
        )
        if validacao.estado is EstadoDesafio.REJEITADO:
            return ResultadoWorker(
                False,
                CodigoResultadoWorker.RECUSA_BIOMETRICA,
                resultado_facial=facial,
            )
        if validacao.estado is EstadoDesafio.EXPIRADO:
            return ResultadoWorker(
                False,
                CodigoResultadoWorker.RECUSA_BIOMETRICA,
                resultado_facial=facial,
            )
        if validacao.estado is EstadoDesafio.CONCLUIDO:
            return ResultadoWorker(
                True,
                CodigoResultadoWorker.CONCLUIDA,
                resultado_facial=facial,
            )
        return ResultadoWorker(
            False,
            CodigoResultadoWorker.RECUSA_BIOMETRICA,
            aguardando_etapa=True,
            resultado_facial=facial,
        )

    def _carregar_referencias(
        self, politica: PoliticaVerificacaoIdentidade
    ) -> tuple[ReferenciaIdentidade, ...] | None:
        ativos = self._referencias.obter_referencias_ativas((politica.aluno_id,))
        selecionadas = tuple(
            ReferenciaIdentidade(
                referencia.aluno_id,
                referencia.conjunto_id,
                referencia.versao,
                referencia.ordinal,
                referencia.embedding,
            )
            for referencia in ativos
            if referencia.aluno_id == politica.aluno_id
            and referencia.conjunto_id == politica.conjunto_id
            and referencia.versao == politica.versao_referencia
        )
        return (
            selecionadas
            if tuple(sorted(ref.ordinal for ref in selecionadas)) == (1, 2, 3)
            else None
        )

    def _falha(
        self,
        registro: Any,
        motivo: str,
        *,
        tecnico: bool,
        identidade: bool = False,
        antispoofing: bool = False,
        distancia: float | None = None,
    ) -> ResultadoWorker:
        facial = None
        if registro is not None:
            resultado = self._desafio.rejeitar(
                registro.id, motivo, self._utc(self._relogio())
            )
            facial = ResultadoFacial(
                identidade_ok=identidade,
                desafio_ok=False,
                antispoofing_ok=antispoofing,
                qualidade_ok=False,
                motivo_tecnico=motivo,
                versao_referencia=registro.versao_referencia,
                politica=POLITICA_VERIFICACAO,
                distancia_mediana=distancia,
            )
            if resultado.estado is EstadoDesafio.EXPIRADO:
                tecnico = False
        return ResultadoWorker(
            False,
            CodigoResultadoWorker.FALHA_TECNICA
            if tecnico
            else CodigoResultadoWorker.RECUSA_BIOMETRICA,
            resultado_facial=facial,
        )

    def _repetir(self, registro: Any, motivo: str) -> ResultadoWorker:
        """Recusa corrigível (luz, enquadramento): a etapa volta ao aluno."""
        resultado = self._desafio.repetir_etapa(
            registro.id,
            registro.etapa_recebida,
            motivo,
            self._utc(self._relogio()),
        )
        return ResultadoWorker(
            False,
            CodigoResultadoWorker.RECUSA_BIOMETRICA,
            aguardando_etapa=resultado.estado is EstadoDesafio.AGUARDANDO_ETAPA,
        )

    def fechar(self) -> None:
        self._pose.fechar()

    def preaquecer(self) -> None:
        preaquecer = getattr(self._pose, "preaquecer", None)
        if callable(preaquecer):
            preaquecer()

    @staticmethod
    def _utc(instante: datetime) -> datetime:
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O relógio do worker deve conter fuso horário.")
        return instante.astimezone(UTC)
