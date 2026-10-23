"""CRUD autorizado, revisão manual, painel agregado e CSV de presença."""

from __future__ import annotations

import calendar
import hashlib
import hmac
import re
from contextlib import suppress
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, ConfigDict, Field

from src.application.use_cases.exportar_presencas import ExportarPresencas
from src.application.use_cases.gerenciar_turmas_web import GerenciarTurmasWeb
from src.application.use_cases.revisar_presenca import RevisarPresenca
from src.config.web_settings import WebSettings
from src.domain.entities.presenca_web import Presenca
from src.domain.services.autorizacao import AcessoTurmaNegado
from src.infrastructure.repositories.postgres_conta_repository import ContaAutenticada
from src.infrastructure.repositories.postgres_gestao_web_repository import (
    VersaoPresencaDesatualizada,
)
from src.presentation.web.dependencies import DependenciasAuthWeb

if TYPE_CHECKING:
    from src.presentation.web.app import WebServices


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CriarTurmaRequest(_Schema):
    materia: str = Field(min_length=1, max_length=120)
    periodo: Literal["matutino", "diurno", "noturno"]
    responsavel_professor_id: int | None = Field(default=None, gt=0)
    confirmar: bool = False
    justificativa: str | None = Field(default=None, max_length=500)


class AtualizarTurmaRequest(_Schema):
    materia: str | None = Field(default=None, min_length=1, max_length=120)
    periodo: Literal["matutino", "diurno", "noturno"] | None = None
    responsavel_professor_id: int | None = Field(default=None, gt=0)
    confirmar_transferencia: bool = False
    justificativa: str | None = Field(default=None, max_length=500)


class JustificativaRequest(_Schema):
    justificativa: str = Field(min_length=1, max_length=500)


class ExcluirAlunoGlobalRequest(JustificativaRequest):
    confirmacao: str = Field(min_length=1, max_length=64)


class VincularAlunoRequest(_Schema):
    matricula: str = Field(min_length=1, max_length=32)


class SolicitarRevisaoRequest(_Schema):
    sessao_id: int = Field(gt=0)
    matricula: str = Field(min_length=1, max_length=32)
    justificativa: str = Field(min_length=1, max_length=500)
    via_acessivel: bool = False


class DecidirRevisaoRequest(_Schema):
    decisao: Literal["presente", "anulada"]
    justificativa: str = Field(min_length=1, max_length=500)
    versao_esperada: int = Field(ge=0)
    identidade_confirmada: bool


class ReativarQuotaRequest(JustificativaRequest):
    confirmar: bool


def _bearer(request: Request) -> str | None:
    esquema, separador, valor = request.headers.get("authorization", "").partition(" ")
    if esquema.lower() != "bearer" or not separador or not valor.strip():
        return None
    return valor.strip()


def _request_id(request: Request) -> str | None:
    valor = getattr(request.state, "request_id", None)
    return valor if isinstance(valor, str) else None


def _exigir_autenticado(erro: Exception) -> HTTPException:
    if isinstance(erro, AcessoTurmaNegado):
        return HTTPException(status_code=404, detail="Recurso não encontrado.")
    if isinstance(erro, PermissionError):
        return HTTPException(status_code=403, detail="Operação não autorizada.")
    if isinstance(erro, LookupError):
        return HTTPException(status_code=404, detail="Recurso não encontrado.")
    if isinstance(erro, ValueError):
        return HTTPException(status_code=422, detail="A solicitação é inválida.")
    if isinstance(erro, RuntimeError):
        return HTTPException(
            status_code=503, detail="Operação temporariamente indisponível."
        )
    return HTTPException(
        status_code=503, detail="Operação temporariamente indisponível."
    )


def _intervalo(
    inicio: date | None, fim: date | None, mes: str | None
) -> tuple[date, date]:
    if mes is not None:
        if (
            inicio is not None
            or fim is not None
            or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes)
        ):
            raise ValueError("Informe mês ou início/fim, sem combinar os filtros.")
        ano, numero = (int(parte) for parte in mes.split("-"))
        ultimo_dia = calendar.monthrange(ano, numero)[1]
        return date(ano, numero, 1), date(ano, numero, ultimo_dia)
    if inicio is None or fim is None or inicio > fim:
        raise ValueError("Informe um intervalo inclusivo válido.")
    if (fim - inicio).days > 366:
        raise ValueError("O intervalo máximo do relatório é de 367 dias.")
    return inicio, fim


def criar_rotas_gestao(settings: WebSettings, services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["gestao"])
    auth = DependenciasAuthWeb(settings, services.auth_repository)

    def repositorio() -> Any:
        if services.gestao_repository is None:
            raise HTTPException(status_code=503, detail="Gestão indisponível.")
        return services.gestao_repository

    def gerenciar() -> GerenciarTurmasWeb:
        return GerenciarTurmasWeb(repositorio())

    @router.get("/turmas")
    def listar_turmas(
        conta: ContaAutenticada = Depends(auth.exigir_conta),  # noqa: B008
    ) -> list[dict[str, object]]:
        try:
            return gerenciar().listar(conta.como_ator())
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None

    @router.post("/turmas", status_code=201)
    def criar_turma(
        body: CriarTurmaRequest,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        try:
            return gerenciar().criar(
                conta.como_ator(),
                materia=body.materia,
                periodo=body.periodo,
                responsavel_professor_id=body.responsavel_professor_id,
                agora=services.now_utc(),
                confirmar=body.confirmar,
                justificativa=body.justificativa,
                request_id=_request_id(request),
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None

    @router.patch("/turmas/{turma_id}")
    def atualizar_turma(
        turma_id: int,
        body: AtualizarTurmaRequest,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        if (
            "responsavel_professor_id" in body.model_fields_set
            and body.responsavel_professor_id is None
        ):
            raise HTTPException(
                status_code=422, detail="Professor responsável inválido."
            )
        try:
            return gerenciar().atualizar(
                conta.como_ator(),
                turma_id=turma_id,
                materia=body.materia,
                periodo=body.periodo,
                responsavel_professor_id=body.responsavel_professor_id,
                confirmar_transferencia=body.confirmar_transferencia,
                justificativa=body.justificativa,
                agora=services.now_utc(),
                request_id=_request_id(request),
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None

    @router.delete("/turmas/{turma_id}", status_code=204)
    def excluir_turma(
        turma_id: int,
        body: JustificativaRequest,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> Response:
        try:
            gerenciar().excluir(
                conta.como_ator(),
                turma_id=turma_id,
                justificativa=body.justificativa,
                agora=services.now_utc(),
                request_id=_request_id(request),
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None
        return Response(status_code=204)

    @router.get("/turmas/{turma_id}/alunos")
    def listar_alunos_turma(
        turma_id: int,
        conta: ContaAutenticada = Depends(auth.exigir_conta),  # noqa: B008
    ) -> list[dict[str, object]]:
        try:
            return gerenciar().listar_alunos(conta.como_ator(), turma_id)
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None

    @router.post("/turmas/{turma_id}/alunos", status_code=201)
    def vincular_aluno(
        turma_id: int,
        body: VincularAlunoRequest,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        try:
            return gerenciar().vincular(
                conta.como_ator(),
                turma_id=turma_id,
                matricula=body.matricula,
                agora=services.now_utc(),
                request_id=_request_id(request),
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None

    @router.delete("/turmas/{turma_id}/alunos/{aluno_id}", status_code=204)
    def desvincular_aluno(
        turma_id: int,
        aluno_id: int,
        body: JustificativaRequest,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> Response:
        try:
            gerenciar().desvincular(
                conta.como_ator(),
                turma_id=turma_id,
                aluno_id=aluno_id,
                justificativa=body.justificativa,
                agora=services.now_utc(),
                request_id=_request_id(request),
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None
        return Response(status_code=204)

    @router.delete("/alunos/{aluno_id}", status_code=202)
    def excluir_aluno_global(
        aluno_id: int,
        body: ExcluirAlunoGlobalRequest,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        if conta.papel != "admin" or conta.troca_senha_obrigatoria:
            raise HTTPException(status_code=403, detail="Operação não autorizada.")
        registro_exclusoes = services.backup_exclusions
        exclusao_evento = None
        if registro_exclusoes is not None:
            exclusao_evento = registro_exclusoes.registrar_pendente("aluno", aluno_id)
        try:
            resultado = gerenciar().excluir_globalmente(
                conta.como_ator(),
                aluno_id=aluno_id,
                confirmacao=body.confirmacao,
                justificativa=body.justificativa,
                agora=services.now_utc(),
                request_id=_request_id(request),
                armazenamento_referencias_disponivel=services.reference_storage
                is not None,
                armazenamento_legado_disponivel=services.legacy_image_storage
                is not None,
                armazenamento_capturas_disponivel=services.capture_storage is not None,
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            if exclusao_evento is not None and registro_exclusoes is not None:
                with suppress(Exception):
                    registro_exclusoes.cancelar(exclusao_evento, "aluno", aluno_id)
            raise _exigir_autenticado(erro) from None
        limpeza_pendente = False
        if exclusao_evento is not None and registro_exclusoes is not None:
            try:
                registro_exclusoes.confirmar(exclusao_evento, "aluno", aluno_id)
            except Exception:
                # Pending exclusions prevent data resurrection on restore.
                limpeza_pendente = True
        if services.reference_storage is not None:
            caminhos = cast(tuple[str, ...], resultado["caminhos_referencias"])
            for caminho in caminhos:
                try:
                    services.reference_storage.remover(str(caminho))
                except (OSError, ValueError):
                    limpeza_pendente = True
        if (
            resultado["caminho_legado"] is not None
            and services.legacy_image_storage is not None
        ):
            try:
                services.legacy_image_storage.remover(str(resultado["caminho_legado"]))
            except (OSError, ValueError):
                limpeza_pendente = True
        if services.capture_storage is not None:
            jobs_temporarios = cast(tuple[str, ...], resultado["jobs_temporarios"])
            for job_id in jobs_temporarios:
                try:
                    services.capture_storage.remover_job(UUID(str(job_id)))
                except (OSError, ValueError):
                    limpeza_pendente = True
        return {"excluido": True, "limpeza_pendente": limpeza_pendente}

    @router.post("/revisoes", status_code=202)
    def solicitar_revisao(
        body: SolicitarRevisaoRequest,
        request: Request,
    ) -> dict[str, object]:
        token = _bearer(request)
        if token is None:
            raise HTTPException(status_code=404, detail="Revisão indisponível.")
        if services.link_repository is None:
            raise HTTPException(status_code=503, detail="Revisão indisponível.")
        agora = services.now_utc()
        contexto = services.link_repository.contexto_credencial(
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            agora=agora,
            exigir_link_ativo=True,
        )
        if (
            contexto is None
            or contexto.get("finalidade") != "presenca"
            or contexto.get("sessao_id") != body.sessao_id
            or not isinstance(contexto.get("link_id"), UUID)
            or not isinstance(contexto.get("turma_id"), int)
        ):
            raise HTTPException(status_code=404, detail="Revisão indisponível.")
        if services.presenca_repository is None or services.rate_limit_secret is None:
            raise HTTPException(status_code=503, detail="Revisão indisponível.")
        host = request.client.host if request.client else "unknown"
        chave = hmac.new(
            services.rate_limit_secret,
            f"revisao:{contexto['link_id']}:{host}".encode(),
            hashlib.sha256,
        ).hexdigest()
        espera = services.presenca_repository.limitar_requisicao(
            chave,
            agora=agora,
            limite=10,
            janela=timedelta(minutes=15),
        )
        if espera is not None:
            raise HTTPException(
                status_code=429,
                detail="Limite temporário de solicitações atingido.",
                headers={"Retry-After": str(espera)},
            )
        try:
            revisao = RevisarPresenca(repositorio()).solicitar(
                sessao_id=body.sessao_id,
                turma_id=int(contexto["turma_id"]),
                matricula=body.matricula,
                link_id=contexto["link_id"],
                justificativa=body.justificativa,
                via_acessivel=body.via_acessivel,
                agora=agora,
                request_id=_request_id(request),
            )
        except (LookupError, PermissionError, ValueError, RuntimeError) as erro:
            raise _exigir_autenticado(erro) from None
        return {"protocolo": str(revisao.id), "estado": revisao.estado}

    @router.get("/turmas/{turma_id}/revisoes")
    def listar_revisoes(
        turma_id: int,
        estado: Literal["aberta", "decidida", "todas"] = "aberta",
        limite: int = Query(default=100, ge=1, le=100),
        conta: ContaAutenticada = Depends(auth.exigir_conta),  # noqa: B008
    ) -> list[dict[str, object]]:
        try:
            return repositorio().listar_revisoes(
                conta.como_ator(), turma_id, estado=estado, limite=limite
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None

    @router.post("/revisoes/{revisao_id}/decidir")
    def decidir_revisao(
        revisao_id: UUID,
        body: DecidirRevisaoRequest,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        try:
            presenca: Presenca = RevisarPresenca(repositorio()).executar(
                conta.como_ator(),
                revisao_id,
                body.decisao,
                body.justificativa,
                body.versao_esperada,
                identidade_confirmada=body.identidade_confirmada,
                agora=services.now_utc(),
                request_id=_request_id(request),
            )
        except VersaoPresencaDesatualizada:
            raise HTTPException(
                status_code=409, detail="A presença foi alterada."
            ) from None
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None
        return {
            "presenca_id": presenca.id,
            "aluno_id": presenca.aluno_id,
            "turma_id": presenca.turma_id,
            "sessao_id": presenca.sessao_id,
            "status": presenca.status.value,
            "origem": presenca.origem.value,
            "versao": presenca.versao,
            "corrigida_em": (
                presenca.corrigida_em.isoformat() if presenca.corrigida_em else None
            ),
        }

    @router.get("/turmas/{turma_id}/painel")
    def consultar_painel(
        turma_id: int,
        conta: ContaAutenticada = Depends(auth.exigir_conta),  # noqa: B008
    ) -> dict[str, object]:
        try:
            return repositorio().consultar_painel(
                conta.como_ator(), turma_id, atualizado_em=services.now_utc()
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None

    @router.get("/turmas/{turma_id}/sessoes/{sessao_id}/presencas")
    def listar_presencas_sessao(
        turma_id: int,
        sessao_id: int,
        conta: ContaAutenticada = Depends(auth.exigir_conta),  # noqa: B008
    ) -> dict[str, object]:
        try:
            presencas = repositorio().listar_presencas_sessao(
                conta.como_ator(), turma_id, sessao_id
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None
        return {"sessao_id": sessao_id, "presencas": presencas}

    @router.get("/turmas/{turma_id}/presencas.csv")
    def exportar_presencas(
        turma_id: int,
        inicio: date | None = None,
        fim: date | None = None,
        mes: str | None = None,
        conta: ContaAutenticada = Depends(auth.exigir_conta),  # noqa: B008
    ) -> RawResponse:
        try:
            desde, ate = _intervalo(inicio, fim, mes)
            conteudo = ExportarPresencas(repositorio(), settings.app_timezone).executar(
                conta.como_ator(), turma_id=turma_id, inicio=desde, fim=ate
            )
        except (
            AcessoTurmaNegado,
            LookupError,
            PermissionError,
            ValueError,
            RuntimeError,
        ) as erro:
            raise _exigir_autenticado(erro) from None
        nome = f"presencas-turma-{turma_id}-{desde.isoformat()}-{ate.isoformat()}.csv"
        return RawResponse(
            content=conteudo,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{nome}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post(
        "/turmas/{turma_id}/sessoes/{sessao_id}/alunos/{aluno_id}/reativar-quota"
    )
    def reativar_quota(
        turma_id: int,
        sessao_id: int,
        aluno_id: int,
        body: ReativarQuotaRequest,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        if conta.papel != "admin" or conta.troca_senha_obrigatoria:
            raise HTTPException(status_code=403, detail="Operação não autorizada.")
        try:
            limite = repositorio().reativar_quota(
                ator=conta.como_ator(),
                turma_id=turma_id,
                sessao_id=sessao_id,
                aluno_id=aluno_id,
                confirmar=body.confirmar,
                justificativa=body.justificativa,
                agora=services.now_utc(),
                request_id=_request_id(request),
            )
        except (LookupError, PermissionError, ValueError, RuntimeError) as erro:
            raise _exigir_autenticado(erro) from None
        return {"limite_tentativas": limite, "reativada": True}

    return router
