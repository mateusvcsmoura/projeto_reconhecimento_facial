"""Fabrica HTTP independente do pipeline de captura e reconhecimento."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from src.application.services.fila_facial import FilaCheia, FilaFacial
from src.config.web_settings import WebSettings
from src.domain.services.desafio_captura import DesafioCaptura
from src.infrastructure.repositories.postgres_conta_repository import (
    PostgresContaRepository,
)
from src.infrastructure.storage.private_reference_storage import (
    PrivateReferenceStorageLocal,
)
from src.infrastructure.storage.temporary_capture_storage import TemporaryCaptureStorage
from src.infrastructure.workers.maintenance_gate import (
    ManutencaoAtiva,
    ManutencaoWeb,
)
from src.presentation.web.rate_limit import (
    aplicar_limite,
    bearer_token,
    endereco_cliente,
)
from src.presentation.web.routes.auth import criar_rotas_auth
from src.presentation.web.routes.cadastros import criar_rotas_cadastros
from src.presentation.web.routes.gestao import criar_rotas_gestao
from src.presentation.web.routes.links import criar_rotas_links
from src.presentation.web.routes.operations import criar_rotas_operacoes
from src.presentation.web.routes.presencas import criar_rotas_presencas
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
    presenca_repository: Any | None = None
    gestao_repository: Any | None = None
    legacy_image_storage: Any | None = None
    desafio_captura: DesafioCaptura | None = None
    rate_limit_secret: bytes | None = None
    maintenance_gate: ManutencaoWeb | None = None
    backup_exclusions: Any | None = None
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


def _classificar_erro_http(status_code: int, detail: object) -> tuple[str, str]:
    """Converte erros HTTP em códigos estáveis e mensagens próprias para a API."""
    defaults = {
        400: ("requisicao_invalida", "A requisição é inválida."),
        401: (
            "autenticacao_necessaria",
            "Sua sessão expirou ou você precisa entrar novamente.",
        ),
        403: (
            "operacao_nao_autorizada",
            "Você não tem permissão para realizar esta ação.",
        ),
        404: ("recurso_nao_encontrado", "Recurso não encontrado."),
        405: ("metodo_nao_permitido", "Método não permitido."),
        409: (
            "conflito_estado",
            "A operação não pode ser concluída neste estado.",
        ),
        410: ("acesso_expirado", "Este acesso expirou."),
        413: ("conteudo_excedeu_limite", "O envio excede o limite permitido."),
        415: ("tipo_midia_nao_suportado", "O formato enviado não é aceito."),
        422: (
            "requisicao_invalida",
            "Revise os dados enviados e tente novamente.",
        ),
        429: (
            "limite_requisicoes",
            "Muitas tentativas. Aguarde e tente novamente.",
        ),
        500: ("erro_interno", "Ocorreu um erro interno."),
        502: (
            "servico_indisponivel",
            "O serviço está temporariamente indisponível. "
            "Tente novamente em instantes.",
        ),
        503: (
            "servico_indisponivel",
            "O serviço está temporariamente indisponível. "
            "Tente novamente em instantes.",
        ),
        504: (
            "servico_indisponivel",
            "O serviço está temporariamente indisponível. "
            "Tente novamente em instantes.",
        ),
    }
    codigo, mensagem = defaults.get(
        status_code,
        ("requisicao_recusada", "A requisição não pode ser atendida."),
    )
    detalhe = detail.strip() if isinstance(detail, str) else ""
    detalhe_normalizado = (
        unicodedata.normalize("NFKD", detalhe)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
        .rstrip(".")
    )

    if status_code == 401:
        if detalhe_normalizado in {
            "usuario ou senha invalidos",
            "credenciais invalidas",
        }:
            return "credenciais_invalidas", "Usuário ou senha inválidos."
        return codigo, mensagem
    if status_code == 403:
        if "csrf" in detalhe_normalizado:
            return (
                "csrf_recusado",
                "Não foi possível validar sua sessão. "
                "Atualize a página e tente novamente.",
            )
        if "origem" in detalhe_normalizado:
            return (
                "origem_recusada",
                "A origem da solicitação não foi autorizada. "
                "Atualize a página e tente novamente.",
            )
        return codigo, mensagem

    if (
        status_code < 500
        and detalhe
        and len(detalhe) <= 256
        and all(caractere.isprintable() for caractere in detalhe)
        and detalhe_normalizado not in {"not found", "method not allowed"}
    ):
        return codigo, detalhe
    return codigo, mensagem


def _acao_cadastro_publico(metodo: str, caminho: str) -> str | None:
    if metodo == "POST" and caminho == "/api/v1/acessos-link":
        return "troca_credencial"
    elif metodo == "POST" and caminho == "/api/v1/cadastros":
        return "solicitacao"
    elif metodo == "POST" and re.fullmatch(
        r"/api/v1/cadastros/\d+/(capturas|consentimento|desafio)", caminho
    ):
        return caminho.rsplit("/", 1)[-1]
    elif metodo == "GET" and re.fullmatch(r"/api/v1/cadastros/\d+", caminho):
        return "consulta"
    return None


def _limitar_cadastro_publico(
    request: Request, settings: WebSettings, services: WebServices
) -> Response | None:
    acao = _acao_cadastro_publico(request.method.upper(), request.url.path)
    if acao is None:
        return None

    segredo = services.rate_limit_secret
    repositorio = services.presenca_repository
    if repositorio is None or not isinstance(segredo, bytes) or len(segredo) < 32:
        if settings.environment != "production":
            return None
        resposta = _erro_publico(
            request,
            codigo="limite_indisponivel",
            mensagem="O serviço está temporariamente indisponível.",
            status_code=503,
        )
        resposta.headers["Retry-After"] = "60"
        return resposta

    origem = endereco_cliente(request, settings.trusted_proxy_cidrs)
    agora = services.now_utc()
    espera = aplicar_limite(
        repositorio,
        segredo,
        namespace="cadastro:origem:publica",
        origin=origem,
        context="publico",
        now=agora,
        limit=settings.public_registration_origin_limit_per_minute,
    )
    if espera is None:
        token = bearer_token(request)
        if acao == "consulta":
            if token is not None:
                espera = aplicar_limite(
                    repositorio,
                    segredo,
                    namespace="cadastro:consulta:credencial",
                    origin="",
                    context=token,
                    now=agora,
                    limit=settings.public_registration_query_limit_per_minute,
                )
        elif acao != "troca_credencial":
            espera = aplicar_limite(
                repositorio,
                segredo,
                namespace=f"cadastro:mutacao:{acao}",
                origin=origem,
                context=token or "credencial-ausente",
                now=agora,
                limit=settings.public_registration_context_limit_per_minute,
            )

    if espera is None:
        return None
    resposta = _erro_publico(
        request,
        codigo="limite_requisicoes",
        mensagem="Limite temporário de requisições atingido.",
        status_code=429,
    )
    resposta.headers["Retry-After"] = str(max(1, espera))
    return resposta


# Modelo do guia facial: fica fora do Git (/models/*.task); vem do repositório
# local ou empacotado em static/ na imagem web.
MODELO_LANDMARKS: tuple[Path, ...] = (
    Path(__file__).resolve().parents[3] / "models" / "face_landmarker.task",
    Path(__file__).resolve().parent / "static" / "models" / "face_landmarker.task",
)


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
    web_dir = Path(__file__).resolve().parent
    arquivo_interface = web_dir / "templates" / "index.html"

    async def modelo_landmarks() -> FileResponse:
        """Entrega o modelo local apenas para o guia visual transitório da câmera."""
        for arquivo in MODELO_LANDMARKS:
            if arquivo.is_file():
                return FileResponse(
                    arquivo,
                    media_type="application/octet-stream",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        raise HTTPException(
            status_code=404, detail="Modelo do guia facial indisponível."
        )

    app.add_api_route(
        "/assets/models/face_landmarker.task",
        modelo_landmarks,
        methods=["GET"],
        include_in_schema=False,
    )
    app.mount(
        "/assets",
        StaticFiles(directory=web_dir / "static", check_dir=True),
        name="web-assets",
    )
    app.include_router(
        criar_rotas_auth(
            settings,
            services.auth_repository,
            gestao_repository=services.gestao_repository,
        )
    )
    app.include_router(criar_rotas_operacoes(services.fila_facial))
    app.include_router(criar_rotas_links(settings, services))
    app.include_router(criar_rotas_cadastros(settings, services))
    app.include_router(criar_rotas_presencas(settings, services))
    app.include_router(criar_rotas_gestao(settings, services))

    async def pagina_interface() -> FileResponse:
        return FileResponse(arquivo_interface, media_type="text/html; charset=utf-8")

    app.add_api_route("/", pagina_interface, methods=["GET"], include_in_schema=False)
    app.add_api_route(
        "/login", pagina_interface, methods=["GET"], include_in_schema=False
    )
    app.add_api_route(
        "/trocar-senha", pagina_interface, methods=["GET"], include_in_schema=False
    )
    app.add_api_route(
        "/professor", pagina_interface, methods=["GET"], include_in_schema=False
    )
    app.add_api_route(
        "/professor/{caminho:path}",
        pagina_interface,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/cadastro", pagina_interface, methods=["GET"], include_in_schema=False
    )
    app.add_api_route(
        "/cadastro/{credencial}",
        pagina_interface,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/presenca", pagina_interface, methods=["GET"], include_in_schema=False
    )
    app.add_api_route(
        "/presenca/{credencial}",
        pagina_interface,
        methods=["GET"],
        include_in_schema=False,
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        response: Response

        async def executar_com_rate_limit() -> Response:
            if _acao_cadastro_publico(request.method.upper(), request.url.path) is None:
                return await call_next(request)
            limite = await run_in_threadpool(
                _limitar_cadastro_publico, request, settings, services
            )
            if limite is not None:
                return limite
            return await call_next(request)

        try:
            if (
                settings.purpose_end_at is not None
                and request.url.path.startswith("/api/v1/")
                and request.url.path != "/api/v1/openapi.json"
                and services.now_utc() >= settings.purpose_end_at.astimezone(UTC)
            ):
                response = _erro_publico(
                    request,
                    codigo="finalidade_encerrada",
                    mensagem="O periodo de uso do servico terminou.",
                    status_code=410,
                )
            elif (
                services.maintenance_gate is not None
                and request.url.path.startswith("/api/v1/")
                and request.url.path != "/api/v1/openapi.json"
            ):
                try:
                    with services.maintenance_gate.mutacao_http():
                        response = await executar_com_rate_limit()
                except ManutencaoAtiva:
                    response = _erro_publico(
                        request,
                        codigo="manutencao",
                        mensagem="O serviço está temporariamente indisponível.",
                        status_code=503,
                    )
                    response.headers["Retry-After"] = "60"
            else:
                response = await executar_com_rate_limit()
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
                "/api/v1/sessoes/",
                "/api/v1/tentativas/",
                "/api/v1/revisoes",
                "/api/v1/alunos/",
            )
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(self), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            # wasm-unsafe-eval só libera compilar WebAssembly (guia MediaPipe);
            # eval de JavaScript continua bloqueado.
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
            "worker-src 'self' blob:; style-src 'self'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; "
            "connect-src 'self'; font-src 'self'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        if (
            request.url.path == "/"
            or request.url.path in {"/login", "/trocar-senha", "/professor"}
            or request.url.path.startswith(("/professor/", "/cadastro", "/presenca"))
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        if request.url.path.startswith("/assets/"):
            # Os módulos que app.mjs importa não levam ?v=: revalidar evita juntar
            # app.mjs novo com camera.mjs antigo vindo do cache heurístico.
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @app.exception_handler(StarletteHTTPException)
    async def tratar_erro_http(
        request: Request, erro: StarletteHTTPException
    ) -> JSONResponse:
        codigo, mensagem = _classificar_erro_http(erro.status_code, erro.detail)
        resposta = _erro_publico(
            request,
            codigo=codigo,
            mensagem=mensagem,
            status_code=erro.status_code,
        )
        retry_after = (erro.headers or {}).get("Retry-After")
        if (
            erro.status_code in {429, 503}
            and retry_after is not None
            and retry_after.isascii()
            and retry_after.isdigit()
        ):
            resposta.headers["Retry-After"] = retry_after
        return resposta

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
