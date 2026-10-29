"""Adaptador do DeepFace.

Unico modulo do sistema que importa `deepface`. Traduz as falhas da
biblioteca em erros de dominio nomeados -- e aqui que morreu o
`except Exception: continue` do prototipo (problema A6), que tornava
indistinguiveis "nenhum rosto no frame" e "TensorFlow quebrado".

As operacoes publicas compartilham a mesma validacao de face e prova de vida:

  * `extrair_face_unica` -- devolve o recorte alinhado;
  * `gerar_embedding`    -- devolve um embedding por ciclo de video;
  * `preparar_cadastro`  -- retorna o recorte e o embedding dessa deteccao.

Quando ativada, a politica de qualidade roda antes de `represent()`.

A comparacao nao esta aqui: virou aritmetica de vetores no
`domain/services/matcher.py`.
"""

from __future__ import annotations

import logging
from numbers import Integral
from pathlib import Path
from typing import Any

import numpy as np
from deepface import DeepFace

from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
    QualidadeCapturaInsuficiente,
)
from src.domain.services.face_recognition import FacePreparada
from src.domain.services.qualidade_captura import (
    ParametrosQualidade,
    avaliar_qualidade,
)

logger = logging.getLogger(__name__)

# O DeepFace sinaliza ausencia de rosto com ValueError e esta mensagem.
_MARCA_SEM_ROSTO = "could not be detected"


def _traduzir(exc: Exception, acao: str) -> Exception:
    """Converte a falha da biblioteca no erro de dominio correspondente."""
    if isinstance(exc, ValueError) and _MARCA_SEM_ROSTO in str(exc).lower():
        return NenhumRostoDetectado(str(exc))

    # Falha de infraestrutura de ML: pesos ausentes, backend quebrado,
    # memoria. Registrada com stack trace -- nunca silenciada, nunca
    # confundida com "sem rosto".
    logger.error("Falha ao %s: %s", acao, exc, exc_info=True)
    return ModeloIndisponivel(str(exc))


def _para_bgr_uint8(face: np.ndarray) -> np.ndarray:
    """Converte o recorte do DeepFace para o formato que o cv2 grava.

    `extract_faces` devolve RGB em float [0, 1]; `cv2.imwrite` espera BGR em
    uint8. A inversao de canais e feita com slice de numpy para nao arrastar
    o cv2 para dentro deste modulo.
    """
    return (np.clip(face, 0.0, 1.0) * 255).astype(np.uint8)[..., ::-1]


class DeepFaceAdapter:
    def __init__(
        self,
        modelo: str,
        detector: str,
        anti_spoofing: bool = True,
        qualidade: ParametrosQualidade | None = None,
        strict_resultado_antispoofing: bool = False,
        sanitizar_erros: bool = False,
    ) -> None:
        self._modelo = modelo
        self._detector = detector
        self._anti_spoofing = anti_spoofing
        self._qualidade = qualidade
        self._strict_resultado_antispoofing = strict_resultado_antispoofing
        self._sanitizar_erros = sanitizar_erros

    @property
    def modelo(self) -> str:
        return self._modelo

    def _detectar_rosto_unico(self, imagem: Any) -> dict[str, Any]:
        """Deteccao, alinhamento e -- quando ligado -- prova de vida.

        Um unico ponto de entrada para as duas operacoes publicas, para que
        a verificacao de autenticidade nao possa ser esquecida em um dos
        caminhos.
        """
        try:
            faces = DeepFace.extract_faces(
                img_path=imagem,
                detector_backend=self._detector,
                enforce_detection=True,
                align=True,
                anti_spoofing=self._anti_spoofing,
            )
        except Exception as exc:
            raise self._traduzir_falha(exc, "detectar rosto") from exc

        if not faces:
            raise NenhumRostoDetectado("O detector nao devolveu nenhum rosto.")
        if len(faces) != 1:
            raise MultiplosRostosDetectados(len(faces))

        face = faces[0]

        if self._anti_spoofing and self._strict_resultado_antispoofing:
            resultado_real = face.get("is_real")
            if not isinstance(resultado_real, (bool, np.bool_)):
                raise ModeloIndisponivel(
                    "O anti-spoofing não devolveu um resultado válido."
                )
            if not resultado_real:
                self._recusar_fraude(face)
        elif self._anti_spoofing and not face.get("is_real", True):
            self._recusar_fraude(face)

        return face

    def _recusar_fraude(self, face: dict[str, Any]) -> None:
        pontuacao = face.get("antispoof_score")
        if self._sanitizar_erros:
            logger.warning("Captura recusada pelo anti-spoofing; score suprimido.")
            raise PossivelFraude()
        # A pontuacao e a confianca NA CLASSIFICACAO ESCOLHIDA, e nao
        # a probabilidade de ser real. Aqui a escolhida foi "fraude",
        # entao 0.96 significa "96% confiante de que e uma foto" -- o
        # oposto do que o numero sugere a quem le o log.
        logger.warning(
            "Frame recusado por anti-spoofing: modelo %.0f%% confiante "
            "de que NAO e uma pessoa ao vivo",
            (pontuacao or 0.0) * 100,
        )
        raise PossivelFraude(pontuacao)

    def preaquecer(self) -> None:
        """Forca a carga do modelo agora, e nao no meio do fluxo de camera."""
        try:
            DeepFace.build_model(self._modelo)
        except Exception as exc:
            raise self._traduzir_falha(exc, "carregar o modelo") from exc

    def preaquecer_para_web(self, diretorio_pesos: Path | None = None) -> None:
        """Carrega FaceNet512 e MiniFASNet sem permitir download implícito."""
        if self._modelo != "Facenet512" or not self._anti_spoofing:
            raise ModeloIndisponivel(
                "O worker web exige FaceNet512 e anti-spoofing habilitado."
            )
        if diretorio_pesos is None:
            try:
                from deepface.commons.folder_utils import get_deepface_home

                diretorio_pesos = (
                    Path(get_deepface_home()).expanduser() / ".deepface" / "weights"
                )
            except Exception as exc:
                raise self._traduzir_falha(exc, "localizar pesos locais") from exc

        pesos_necessarios = (
            "facenet512_weights.h5",
            "2.7_80x80_MiniFASNetV2.pth",
            "4_0_0_80x80_MiniFASNetV1SE.pth",
        )
        if any(not (diretorio_pesos / nome).is_file() for nome in pesos_necessarios):
            raise ModeloIndisponivel("Pesos locais do worker web estão ausentes.")
        try:
            DeepFace.build_model("Facenet512")
            DeepFace.build_model("Fasnet")
        except Exception as exc:
            raise self._traduzir_falha(exc, "aquecer o pipeline web") from exc

    def _traduzir_falha(self, exc: Exception, acao: str) -> Exception:
        if not self._sanitizar_erros:
            return _traduzir(exc, acao)
        if isinstance(exc, ValueError) and _MARCA_SEM_ROSTO in str(exc).lower():
            return NenhumRostoDetectado("Nenhum rosto foi detectado.")
        logger.error("Falha no provider facial ao %s; detalhes suprimidos.", acao)
        return ModeloIndisponivel("Falha técnica do provider facial.")

    def extrair_face_unica(self, imagem: Any) -> Any:
        return self._preparar_recorte(imagem)

    def _preparar_recorte(self, imagem: Any) -> np.ndarray:
        """Detecta uma vez, aplica a politica optativa e devolve o recorte."""
        face = self._detectar_rosto_unico(imagem)
        recorte = _para_bgr_uint8(np.asarray(face["face"]))
        if self._qualidade is not None:
            area = face.get("facial_area")
            if not isinstance(area, dict):
                raise ModeloIndisponivel(
                    "O provider devolveu facial_area.w/h ausentes ou invalidos."
                )
            largura = area.get("w")
            altura = area.get("h")
            if (
                isinstance(largura, bool)
                or isinstance(altura, bool)
                or not isinstance(largura, Integral)
                or not isinstance(altura, Integral)
                or largura <= 0
                or altura <= 0
            ):
                raise ModeloIndisponivel(
                    "O provider devolveu facial_area.w/h ausentes ou invalidos."
                )
            try:
                avaliar_qualidade(
                    recorte,
                    int(largura),
                    int(altura),
                    self._qualidade,
                )
            except QualidadeCapturaInsuficiente as exc:
                # Só o tipo e o valor medido: base para calibrar os limites.
                logger.warning(
                    "Captura recusada pela qualidade: %s (%s).",
                    type(exc).__name__,
                    exc,
                )
                raise
            except ValueError as exc:
                raise ModeloIndisponivel(
                    "O provider devolveu um recorte incompativel com a politica "
                    "de qualidade."
                ) from exc
        return recorte

    def _representar(self, recorte: np.ndarray) -> FaceEmbedding:
        """Gera e normaliza o embedding de um recorte ja validado."""
        try:
            representacoes = DeepFace.represent(
                img_path=recorte,
                model_name=self._modelo,
                detector_backend="skip",
                enforce_detection=False,
                align=False,
            )
        except Exception as exc:
            raise self._traduzir_falha(exc, "gerar embedding") from exc

        if not representacoes:
            raise NenhumRostoDetectado("O modelo nao devolveu nenhum vetor.")

        # `represent()` nao devolve vetor normalizado; FaceEmbedding
        # normaliza na construcao, para que a distancia cosseno seja um
        # simples 1 - produto escalar em qualquer ponto do sistema.
        return FaceEmbedding.de_valores(representacoes[0]["embedding"], self._modelo)

    def preparar_cadastro(self, imagem: Any) -> FacePreparada:
        """Detecta uma vez e usa o mesmo recorte no cadastro e no embedding."""
        recorte = self._preparar_recorte(imagem)
        return FacePreparada(imagem=recorte, embedding=self._representar(recorte))

    def gerar_embedding(self, imagem: Any) -> FaceEmbedding:
        # Detecta (com prova de vida), valida opcionalmente e gera o vetor
        # sobre o recorte. `detector_backend="skip"` evita redetectar o que
        # acabou de ser detectado.
        return self._representar(self._preparar_recorte(imagem))
