"""Tipos neutros para resultados de landmarks faciais visuais.

Este módulo não importa bibliotecas de visão computacional para permanecer
seguro de importar quando o recurso opcional está desabilitado.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class PontoFacial:
    """Ponto facial normalizado produzido pelo provider de landmarks."""

    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class ResultadoLandmarks:
    """Landmarks transitórios de um frame, sem armazenar a imagem."""

    rostos: tuple[tuple[PontoFacial, ...], ...]
    conexoes: tuple[tuple[int, int], ...]


class LandmarksProvider(Protocol):
    """Contrato do detector opcional usado somente pela janela de cadastro."""

    def detectar(self, frame: Any, timestamp_ms: int) -> ResultadoLandmarks: ...

    def fechar(self) -> None: ...
