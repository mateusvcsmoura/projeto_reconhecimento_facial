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
    def __init__(self, modelo: str, detector: str) -> None:
        self._modelo = modelo
        self._detector = detector

    @property
    def modelo(self) -> str:
        return self._modelo

    def extrair_face_unica(self, imagem: Any) -> Any:
        try:
            faces = DeepFace.extract_faces(
                img_path=imagem,
                detector_backend=self._detector,
                enforce_detection=True,
                align=True,
            )
        except Exception as exc:
            raise _traduzir(exc, "detectar rosto") from exc

        if len(faces) != 1:
            raise MultiplosRostosDetectados(len(faces))

        # O prototipo descartava este recorte e gravava o frame inteiro
        # (problema A14): mais dado biometrico guardado do que o necessario,
        # e uma redeteccao a cada comparacao.
        return _para_bgr_uint8(np.asarray(faces[0]["face"]))

    def gerar_embedding(self, imagem: Any) -> FaceEmbedding:
        try:
            representacoes = DeepFace.represent(
                img_path=imagem,
                model_name=self._modelo,
                detector_backend=self._detector,
                enforce_detection=True,
                align=True,
            )
        except Exception as exc:
            raise _traduzir(exc, "gerar embedding") from exc

        if not representacoes:
            raise NenhumRostoDetectado("O modelo nao devolveu nenhum vetor.")
        if len(representacoes) > 1:
            raise MultiplosRostosDetectados(len(representacoes))

        # `represent()` nao devolve vetor normalizado; FaceEmbedding
        # normaliza na construcao, para que a distancia cosseno seja um
        # simples 1 - produto escalar em qualquer ponto do sistema.
        return FaceEmbedding.de_valores(
            representacoes[0]["embedding"], self._modelo
        )
