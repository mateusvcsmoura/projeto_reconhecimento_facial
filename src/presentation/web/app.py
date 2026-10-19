"""Fabrica HTTP independente do pipeline de captura e reconhecimento."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from src.application.services.fila_facial import FilaCheia, FilaFacial
from src.config.web_settings import WebSettings
from src.infrastructure.repositories.postgres_conta_repository import (
    PostgresContaRepository,
)
from src.infrastructure.storage.private_reference_storage import (
    PrivateReferenceStorageLocal,
)
from src.infrastructure.storage.temporary_capture_storage import TemporaryCaptureStorage
from src.presentation.web.routes.auth import criar_rotas_auth
from src.presentation.web.routes.cadastros import criar_rotas_cadastros
from src.presentation.web.routes.links import criar_rotas_links
from src.presentation.web.routes.operations import criar_rotas_operacoes
from src.presentation.web.schemas import (
    ComponentStatus,
    HealthLiveResponse,
    HealthReadyResponse,
    PublicErrorResponse,
)

HealthProbe = Callable[[], bool]


def utc_now() -> datetime:
    """Retorna a hora atual com fuso UTC explicito."""

    return datetime.now(UTC)


@dataclass(frozen=True)
class WebServices:
    """Dependencias substituiveis da API; probes nunca retornam detalhes internos."""

    readiness_probes: Mapping[str, HealthProbe] = field(default_factory=dict)
    auth_repository: PostgresContaRepository | None = None
    link_repository: Any | None = None
    solicitacao_repository: Any | None = None
    reference_storage: PrivateReferenceStorageLocal | None = None
    capture_storage: TemporaryCaptureStorage | None = None
    fila_facial: FilaFacial | None = None
    clock: Callable[[], datetime] = utc_now
    on_shutdown: Callable[[], None] = field(default=lambda: None)

    def now_utc(self) -> datetime:
        """Lê o relogio injetado e exige um instante com fuso UTC."""

        instante = self.clock()
        if not isinstance(instante, datetime) or instante.utcoffset() != timedelta(0):
            raise ValueError("O relogio da aplicacao deve retornar datetime UTC aware.")
        return instante.astimezone(UTC)


def _erro_publico(
    request: Request, *, codigo: str, mensagem: str, status_code: int
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    payload = PublicErrorResponse(
        codigo=codigo,
        mensagem=mensagem,
        request_id=request_id,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def create_app(settings: WebSettings, services: WebServices) -> FastAPI:
    """Cria uma API sem importar modelos, camera, engine ou composicao da CLI."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            services.on_shutdown()

    app = FastAPI(
        title="FaceDiff API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    app.state.environment = settings.environment
    app.state.web_services = services
    app.include_router(criar_rotas_auth(settings, services.auth_repository))
    app.include_router(criar_rotas_operacoes(services.fila_facial))
    app.include_router(criar_rotas_links(settings, services))
    app.include_router(criar_rotas_cadastros(settings, services))

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            response = _erro_publico(
                request,
                codigo="erro_interno",
                mensagem="Ocorreu um erro interno.",
                status_code=500,
            )
        response.headers["X-Request-ID"] = request_id
        if request.url.path.startswith(
            (
                "/api/v1/auth/",
                "/api/v1/admin/",
                "/api/v1/me",
                "/api/v1/operacoes/",
                "/api/v1/cadastros",
                "/api/v1/links/",
                "/api/v1/acessos-link",
                "/api/v1/turmas/",
                "/api/v1/solicitacoes-biometria",
                "/api/v1/admin/solicitacoes-biometria/",
                "/api/v1/avisos/biometria",
            )
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def tratar_erro_http(
        request: Request, erro: StarletteHTTPException
    ) -> JSONResponse:
        if erro.status_code == 404:
            codigo, mensagem = "recurso_nao_encontrado", "Recurso não encontrado."
        elif erro.status_code == 405:
            codigo, mensagem = "metodo_nao_permitido", "Método não permitido."
        else:
            codigo, mensagem = (
                "requisicao_recusada",
                "A requisição não pode ser atendida.",
            )
        return _erro_publico(
            request,
            codigo=codigo,
            mensagem=mensagem,
            status_code=erro.status_code,
        )

    @app.exception_handler(FilaCheia)
    async def tratar_fila_cheia(request: Request, erro: FilaCheia) -> JSONResponse:
        resposta = _erro_publico(
            request,
            codigo="fila_cheia",
            mensagem="Não há capacidade de processamento no momento.",
            status_code=503,
        )
        resposta.headers["Retry-After"] = str(erro.retry_after_seconds)
        return resposta

    @app.exception_handler(RequestValidationError)
    async def tratar_validacao(
        request: Request, _erro: RequestValidationError
    ) -> JSONResponse:
        return _erro_publico(
            request,
            codigo="requisicao_invalida",
            mensagem="A requisição é inválida.",
            status_code=422,
        )

    @app.get("/health/live", response_model=HealthLiveResponse, tags=["health"])
    async def health_live() -> HealthLiveResponse:
        return HealthLiveResponse(status="live")

    @app.get("/health/ready", response_model=HealthReadyResponse, tags=["health"])
    async def health_ready() -> JSONResponse:
        componentes: dict[str, ComponentStatus] = {}
        for nome, probe in services.readiness_probes.items():
            try:
                disponivel = bool(probe())
            except Exception:
                disponivel = False
            componentes[nome] = "available" if disponivel else "unavailable"

        pronto = all(status == "available" for status in componentes.values())
        resposta = HealthReadyResponse(
            status="ready" if pronto else "not_ready",
            componentes=componentes,
        )
        return JSONResponse(
            status_code=200 if pronto else 503,
            content=resposta.model_dump(),
        )

    return app
