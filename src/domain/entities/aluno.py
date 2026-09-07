"""Entidade Aluno.

Dataclass pura: sem SQLAlchemy, sem cv2, sem deepface. E o que atravessa a
fronteira entre a infraestrutura e o resto do sistema.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Aluno:
    id: int
    matricula: str
    nome: str
    # Nome do arquivo, relativo a STORAGE_DIR. None enquanto o aluno nao tem
    # imagem de referencia utilizavel.
    foto_arquivo: str | None = None
