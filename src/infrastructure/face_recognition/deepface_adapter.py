"""Adaptador do DeepFace.

Unico modulo do sistema que importa `deepface`. Traduz as falhas da
biblioteca em erros de dominio nomeados -- e aqui que morreu o
`except Exception: continue` do prototipo (problema A6), que tornava
indistinguiveis "nenhum rosto no frame" e "TensorFlow quebrado".

Duas responsabilidades, ambas de UMA inferencia:

  * `extrair_face_unica` -- usado no cadastro, devolve o recorte alinhado;
  * `gerar_embedding`    -- usado no cadastro e a cada ciclo de video.

A comparacao nao esta aqui: virou aritmetica de vetores no
`domain/services/matcher.py`.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from deepface import DeepFace

from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
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
        self, modelo: str, detector: str, anti_spoofing: bool = True
    ) -> None:
        self._modelo = modelo
        self._detector = detector
        self._anti_spoofing = anti_spoofing

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
            raise _traduzir(exc, "detectar rosto") from exc

        if not faces:
            raise NenhumRostoDetectado("O detector nao devolveu nenhum rosto.")
        if len(faces) != 1:
            raise MultiplosRostosDetectados(len(faces))

        face = faces[0]

        if self._anti_spoofing and not face.get("is_real", True):
            pontuacao = face.get("antispoof_score")
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

        return face

    def preaquecer(self) -> None:
        """Forca a carga do modelo agora, e nao no meio do fluxo de camera."""
        try:
            DeepFace.build_model(self._modelo)
        except Exception as exc:
            raise _traduzir(exc, "carregar o modelo") from exc

    def extrair_face_unica(self, imagem: Any) -> Any:
        face = self._detectar_rosto_unico(imagem)
        # O prototipo descartava este recorte e gravava o frame inteiro
        # (problema A14): mais dado biometrico guardado do que o necessario,
        # e uma redeteccao a cada comparacao.
        return _para_bgr_uint8(np.asarray(face["face"]))

    def gerar_embedding(self, imagem: Any) -> FaceEmbedding:
        # Detecta (com prova de vida) e so entao gera o vetor sobre o
        # recorte ja validado. `detector_backend="skip"` evita redetectar o
        # que acabou de ser detectado -- continua sendo UMA inferencia do
        # modelo de embedding por ciclo.
        face = self._detectar_rosto_unico(imagem)
        recorte = _para_bgr_uint8(np.asarray(face["face"]))

        try:
            representacoes = DeepFace.represent(
                img_path=recorte,
                model_name=self._modelo,
                detector_backend="skip",
                enforce_detection=False,
                align=False,
            )
        except Exception as exc:
            raise _traduzir(exc, "gerar embedding") from exc

        if not representacoes:
            raise NenhumRostoDetectado("O modelo nao devolveu nenhum vetor.")

        # `represent()` nao devolve vetor normalizado; FaceEmbedding
        # normaliza na construcao, para que a distancia cosseno seja um
        # simples 1 - produto escalar em qualquer ponto do sistema.
        return FaceEmbedding.de_valores(
            representacoes[0]["embedding"], self._modelo
        )
