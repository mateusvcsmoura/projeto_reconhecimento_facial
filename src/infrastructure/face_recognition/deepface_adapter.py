"""Adaptador do DeepFace.

Unico modulo do sistema que importa `deepface`. Traduz as falhas da
biblioteca em erros de dominio nomeados.

Isto encerra o problema A6: no prototipo, `except Exception: continue`
transformava pesos ausentes, TensorFlow quebrado, JPG corrompido e "nenhum
rosto no frame" todos na mesma mensagem -- "Rosto nao reconhecido" --, sem
log e sem pista da causa real.

Escopo desta fase: reproduz o comportamento atual (comparacao imagem a
imagem via DeepFace.verify). A Fase 5 troca isso por embeddings
pre-calculados; a troca fica contida neste arquivo.
"""

from __future__ import annotations

import logging
from typing import Any

from deepface import DeepFace

from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
)

logger = logging.getLogger(__name__)

# O DeepFace sinaliza ausencia de rosto com ValueError e esta mensagem.
_MARCA_SEM_ROSTO = "could not be detected"


def _e_ausencia_de_rosto(exc: ValueError) -> bool:
    return _MARCA_SEM_ROSTO in str(exc).lower()


class DeepFaceAdapter:
    def __init__(self, modelo: str, detector: str) -> None:
        self._modelo = modelo
        self._detector = detector

    def validar_rosto_unico(self, imagem: Any) -> None:
        try:
            faces = DeepFace.extract_faces(
                img_path=imagem,
                detector_backend=self._detector,
                enforce_detection=True,
                align=True,
            )
        except ValueError as exc:
            if _e_ausencia_de_rosto(exc):
                raise NenhumRostoDetectado(str(exc)) from exc
            raise
        except Exception as exc:
            # Falha de infraestrutura de ML (pesos ausentes, backend
            # quebrado, memoria). Traduzida e registrada com stack trace --
            # nunca silenciada nem confundida com "sem rosto".
            logger.error("Falha ao detectar rosto: %s", exc, exc_info=True)
            raise ModeloIndisponivel(str(exc)) from exc

        if len(faces) != 1:
            raise MultiplosRostosDetectados(len(faces))

    def sao_a_mesma_pessoa(self, imagem: Any, caminho_referencia: str) -> bool:
        try:
            resultado = DeepFace.verify(
                img1_path=imagem,
                img2_path=caminho_referencia,
                model_name=self._modelo,
                detector_backend=self._detector,
                enforce_detection=True,
                align=True,
            )
        except ValueError as exc:
            if _e_ausencia_de_rosto(exc):
                raise NenhumRostoDetectado(str(exc)) from exc
            raise
        except Exception as exc:
            logger.error("Falha ao comparar rostos: %s", exc, exc_info=True)
            raise ModeloIndisponivel(str(exc)) from exc

        return bool(resultado.get("verified", False))
