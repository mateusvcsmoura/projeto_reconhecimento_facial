"""Regras de entrada para gestão de turmas pela API web."""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from src.domain.entities.turma import Turma
from src.domain.services.autorizacao import AtorWeb


class RepositorioGestaoTurmasWeb(Protocol):
    def listar_turmas(self, ator: AtorWeb) -> list[dict[str, object]]: ...

    def obter_turma(self, ator: AtorWeb, turma_id: int) -> dict[str, object]: ...

    def criar_turma(self, **kwargs: object) -> dict[str, object]: ...

    def atualizar_turma(self, **kwargs: object) -> dict[str, object]: ...

    def excluir_turma(self, **kwargs: object) -> None: ...

    def listar_alunos_turma(
        self, ator: AtorWeb, turma_id: int
    ) -> list[dict[str, object]]: ...

    def vincular_aluno(self, **kwargs: object) -> dict[str, object]: ...

    def desvincular_aluno(self, **kwargs: object) -> None: ...

    def excluir_aluno_global(self, **kwargs: object) -> dict[str, object]: ...


class GerenciarTurmasWeb:
    def __init__(self, repositorio: RepositorioGestaoTurmasWeb) -> None:
        self._repositorio = repositorio

    def listar(self, ator: AtorWeb) -> list[dict[str, object]]:
        return self._repositorio.listar_turmas(ator)

    def obter(self, ator: AtorWeb, turma_id: int) -> dict[str, object]:
        if isinstance(turma_id, bool) or turma_id <= 0:
            raise LookupError("Turma não encontrada.")
        return self._repositorio.obter_turma(ator, turma_id)

    def criar(
        self,
        ator: AtorWeb,
        *,
        materia: str,
        periodo: str,
        responsavel_professor_id: int | None,
        agora: dt.datetime,
        confirmar: bool,
        justificativa: str | None,
        request_id: str | None,
    ) -> dict[str, object]:
        turma = Turma.nova(materia, periodo)
        return self._repositorio.criar_turma(
            ator=ator,
            materia=turma.materia,
            periodo=turma.periodo.value,
            responsavel_professor_id=responsavel_professor_id,
            agora=agora,
            confirmar=confirmar,
            justificativa=justificativa,
            request_id=request_id,
        )

    def atualizar(
        self,
        ator: AtorWeb,
        *,
        turma_id: int,
        materia: str | None,
        periodo: str | None,
        responsavel_professor_id: int | None,
        confirmar_transferencia: bool,
        justificativa: str | None,
        agora: dt.datetime,
        request_id: str | None,
    ) -> dict[str, object]:
        if isinstance(turma_id, bool) or turma_id <= 0:
            raise LookupError("Turma não encontrada.")
        if materia is not None and not materia.strip():
            raise ValueError("Informe a matéria da turma.")
        if periodo is not None:
            from src.domain.entities.turma import Periodo

            Periodo(periodo)
        if materia is None and periodo is None and responsavel_professor_id is None:
            raise ValueError("Informe ao menos um campo para atualizar.")
        return self._repositorio.atualizar_turma(
            ator=ator,
            turma_id=turma_id,
            materia=materia,
            periodo=periodo,
            responsavel_professor_id=responsavel_professor_id,
            confirmar_transferencia=confirmar_transferencia,
            justificativa=justificativa,
            agora=agora,
            request_id=request_id,
        )

    def excluir(
        self,
        ator: AtorWeb,
        *,
        turma_id: int,
        justificativa: str,
        agora: dt.datetime,
        request_id: str | None,
    ) -> None:
        self._repositorio.excluir_turma(
            ator=ator,
            turma_id=turma_id,
            justificativa=justificativa,
            agora=agora,
            request_id=request_id,
        )

    def listar_alunos(self, ator: AtorWeb, turma_id: int) -> list[dict[str, object]]:
        return self._repositorio.listar_alunos_turma(ator, turma_id)

    def vincular(
        self,
        ator: AtorWeb,
        *,
        turma_id: int,
        matricula: str,
        agora: dt.datetime,
        request_id: str | None,
    ) -> dict[str, object]:
        return self._repositorio.vincular_aluno(
            ator=ator,
            turma_id=turma_id,
            matricula=matricula,
            agora=agora,
            request_id=request_id,
        )

    def desvincular(
        self,
        ator: AtorWeb,
        *,
        turma_id: int,
        aluno_id: int,
        justificativa: str,
        agora: dt.datetime,
        request_id: str | None,
    ) -> None:
        self._repositorio.desvincular_aluno(
            ator=ator,
            turma_id=turma_id,
            aluno_id=aluno_id,
            justificativa=justificativa,
            agora=agora,
            request_id=request_id,
        )

    def excluir_globalmente(
        self,
        ator: AtorWeb,
        *,
        aluno_id: int,
        confirmacao: str,
        justificativa: str,
        agora: dt.datetime,
        request_id: str | None,
        armazenamento_referencias_disponivel: bool,
        armazenamento_legado_disponivel: bool,
        armazenamento_capturas_disponivel: bool,
    ) -> dict[str, object]:
        return self._repositorio.excluir_aluno_global(
            ator=ator,
            aluno_id=aluno_id,
            confirmacao=confirmacao,
            justificativa=justificativa,
            agora=agora,
            request_id=request_id,
            armazenamento_referencias_disponivel=armazenamento_referencias_disponivel,
            armazenamento_legado_disponivel=armazenamento_legado_disponivel,
            armazenamento_capturas_disponivel=armazenamento_capturas_disponivel,
        )
