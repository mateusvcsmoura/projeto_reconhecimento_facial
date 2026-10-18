"""Regras de autorizacao de acesso a turmas no runtime web."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TurmaComResponsavel(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def responsavel_professor_id(self) -> int | None: ...


@dataclass(frozen=True)
class AtorWeb:
    conta_id: int
    papel: str
    ativa: bool
    troca_senha_obrigatoria: bool
    professor_id: int | None


@dataclass(frozen=True)
class ContextoTurma:
    turma_id: int
    acao: str
    ator_conta_id: int
    responsavel_professor_id: int | None


class AcessoTurmaNegado(Exception):
    """A turma nao pertence ao professor autenticado ou nao tem responsavel."""


class AutorizarTurma:
    """Autoriza a partir da turma consultada no servidor, nunca do payload."""

    @staticmethod
    def exigir(ator: AtorWeb, turma: TurmaComResponsavel, acao: str) -> ContextoTurma:
        if not ator.ativa or ator.troca_senha_obrigatoria:
            raise AcessoTurmaNegado
        if ator.papel == "admin":
            return ContextoTurma(
                turma_id=turma.id,
                acao=acao,
                ator_conta_id=ator.conta_id,
                responsavel_professor_id=turma.responsavel_professor_id,
            )
        if (
            ator.papel != "professor"
            or ator.professor_id is None
            or turma.responsavel_professor_id != ator.professor_id
        ):
            raise AcessoTurmaNegado
        return ContextoTurma(
            turma_id=turma.id,
            acao=acao,
            ator_conta_id=ator.conta_id,
            responsavel_professor_id=turma.responsavel_professor_id,
        )
