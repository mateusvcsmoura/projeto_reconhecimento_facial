"""Rotas de autenticacao, administracao de contas e ownership de turmas."""

import hmac
import ipaddress
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.application.use_cases.administrar_contas import AdministrarContas
from src.application.use_cases.autenticar_professor import (
    AutenticarProfessor,
    ContextoCliente,
)
from src.config.web_settings import WebSettings
from src.domain.services.autorizacao import AcessoTurmaNegado, AutorizarTurma
from src.infrastructure.repositories.postgres_conta_repository import (
    COOKIE_SESSAO,
    ConflitoConta,
    ContaAutenticada,
    CredenciaisInvalidas,
    LoginLimitado,
    OperacaoNaoAutorizada,
    PoliticaSenhaInvalida,
    PostgresContaRepository,
    ResultadoLogin,
    normalizar_usuario,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_Schema):
    usuario: str = Field(min_length=1, max_length=160)
    senha: str = Field(min_length=1, max_length=256)

    @field_validator("usuario")
    @classmethod
    def _normalizar_usuario(cls, value: str) -> str:
        try:
            return normalizar_usuario(value)
        except ValueError as exc:
            raise ValueError("Usuario invalido.") from exc


class TrocarSenhaRequest(_Schema):
    senha_atual: str | None = Field(default=None, max_length=256)
    nova_senha: str = Field(min_length=12, max_length=256)


class CriarContaRequest(_Schema):
    usuario: str = Field(min_length=1, max_length=160)
    papel: Literal["professor", "admin"]
    justificativa: str = Field(min_length=1, max_length=500)

    @field_validator("usuario")
    @classmethod
    def _normalizar_usuario(cls, value: str) -> str:
        try:
            return normalizar_usuario(value)
        except ValueError as exc:
            raise ValueError("Usuario invalido.") from exc


class RedefinirSenhaRequest(_Schema):
    justificativa: str = Field(min_length=1, max_length=500)
    referencia_verificacao: str = Field(min_length=1, max_length=160)


class DesativarContaRequest(_Schema):
    justificativa: str = Field(min_length=1, max_length=500)


class TransferirTurmaRequest(_Schema):
    professor_id: int = Field(gt=0)
    justificativa: str = Field(min_length=1, max_length=500)


def criar_rotas_auth(
    settings: WebSettings,
    repository: PostgresContaRepository | None,
    *,
    gestao_repository: Any | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["auth"])

    def exigir_repository() -> PostgresContaRepository:
        if repository is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Autenticacao indisponivel.",
            )
        return repository

    def exigir_origem(request: Request) -> None:
        origem = request.headers.get("origin")
        esperada = settings.public_origin
        if (
            origem is None
            or esperada is None
            or not hmac.compare_digest(origem, esperada)
        ):
            raise HTTPException(status_code=403, detail="Origem recusada.")

    def exigir_conta(request: Request) -> ContaAutenticada:
        repositorio = exigir_repository()
        token = request.cookies.get(COOKIE_SESSAO)
        conta = repositorio.autenticar_sessao(token)
        if conta is None:
            raise HTTPException(status_code=401, detail="Autenticacao necessaria.")
        return conta

    def exigir_mutacao_autenticada(
        request: Request,
        conta: Annotated[ContaAutenticada, Depends(exigir_conta)],
    ) -> ContaAutenticada:
        exigir_origem(request)
        repositorio = exigir_repository()
        token_csrf = request.headers.get("x-csrf-token")
        if not repositorio.validar_csrf(conta, token_csrf):
            raise HTTPException(status_code=403, detail="Verificacao CSRF recusada.")
        return conta

    def exigir_admin(
        conta: Annotated[ContaAutenticada, Depends(exigir_conta)],
    ) -> ContaAutenticada:
        if conta.papel != "admin" or conta.troca_senha_obrigatoria:
            raise HTTPException(status_code=403, detail="Operacao nao autorizada.")
        return conta

    def erro_operacao(error: Exception) -> HTTPException:
        if isinstance(error, CredenciaisInvalidas):
            return HTTPException(status_code=401, detail="Usuario ou senha invalidos.")
        if isinstance(error, LoginLimitado):
            return HTTPException(
                status_code=429, detail="Tentativas temporariamente limitadas."
            )
        if isinstance(error, ConflitoConta):
            return HTTPException(status_code=409, detail="Conta nao pode ser criada.")
        if isinstance(error, PoliticaSenhaInvalida | ValueError):
            return HTTPException(
                status_code=422, detail="Dados nao atendem a politica."
            )
        if isinstance(error, OperacaoNaoAutorizada | AcessoTurmaNegado):
            return HTTPException(status_code=404, detail="Recurso nao encontrado.")
        return HTTPException(status_code=403, detail="Operacao nao autorizada.")

    def _cookie(response: Response, token: str) -> None:
        response.set_cookie(
            key=COOKIE_SESSAO,
            value=token,
            max_age=8 * 60 * 60,
            path="/api/v1",
            secure=True,
            httponly=True,
            samesite="lax",
        )

    def _limpar_cookie(response: Response) -> None:
        response.delete_cookie(
            key=COOKIE_SESSAO,
            path="/api/v1",
            secure=True,
            httponly=True,
            samesite="lax",
        )

    def _endereco_cliente(request: Request) -> str | None:
        peer = request.client.host if request.client is not None else None
        redes_confiaveis = tuple(
            ipaddress.ip_network(item.strip(), strict=False)
            for item in (settings.trusted_proxy_cidrs or "").split(",")
            if item.strip()
        )
        if peer is None or not redes_confiaveis:
            return peer
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return peer
        if not any(peer_ip in rede for rede in redes_confiaveis):
            return str(peer_ip)
        encaminhados = request.headers.get("x-forwarded-for", "").split(",")
        cadeia: list[str] = []
        for item in encaminhados:
            try:
                cadeia.append(str(ipaddress.ip_address(item.strip())))
            except ValueError:
                continue
        cadeia.append(str(peer_ip))
        for endereco in reversed(cadeia):
            ip = ipaddress.ip_address(endereco)
            if not any(ip in rede for rede in redes_confiaveis):
                return str(ip)
        return str(peer_ip)

    @router.post("/auth/login", status_code=200)
    def login(
        body: LoginRequest,
        request: Request,
        response: Response,
        repositorio: Annotated[PostgresContaRepository, Depends(exigir_repository)],
    ) -> dict[str, object]:
        exigir_origem(request)
        try:
            resultado: ResultadoLogin = AutenticarProfessor(repositorio).executar(
                body.usuario,
                body.senha,
                ContextoCliente(
                    endereco_ip=_endereco_cliente(request),
                    token_sessao_anterior=request.cookies.get(COOKIE_SESSAO),
                ),
            )
        except (CredenciaisInvalidas, LoginLimitado) as exc:
            raise erro_operacao(exc) from None
        _cookie(response, resultado.token_sessao)
        return {
            "conta": {
                "id": resultado.conta_id,
                "papel": resultado.papel,
                "troca_senha_obrigatoria": resultado.troca_senha_obrigatoria,
            },
            "csrf_token": resultado.token_csrf,
        }

    @router.post("/auth/logout", status_code=204)
    def logout(
        response: Response,
        repositorio: Annotated[PostgresContaRepository, Depends(exigir_repository)],
        conta: Annotated[ContaAutenticada, Depends(exigir_mutacao_autenticada)],
    ) -> Response:
        repositorio.encerrar_sessao(conta)
        _limpar_cookie(response)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.post("/auth/trocar-senha", status_code=204)
    def trocar_senha(
        body: TrocarSenhaRequest,
        request: Request,
        response: Response,
        repositorio: Annotated[PostgresContaRepository, Depends(exigir_repository)],
        conta: Annotated[ContaAutenticada, Depends(exigir_mutacao_autenticada)],
    ) -> Response:
        try:
            repositorio.trocar_senha(
                conta,
                body.nova_senha,
                body.senha_atual,
                request_id=getattr(request.state, "request_id", None),
            )
        except (CredenciaisInvalidas, OperacaoNaoAutorizada, ValueError) as exc:
            raise erro_operacao(exc) from None
        _limpar_cookie(response)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.get("/me", status_code=200)
    def me(
        conta: Annotated[ContaAutenticada, Depends(exigir_conta)],
    ) -> dict[str, object]:
        return {
            "id": conta.id,
            "papel": conta.papel,
            "ativo": conta.ativa,
            "troca_senha_obrigatoria": conta.troca_senha_obrigatoria,
        }

    @router.get("/auth/csrf", status_code=200)
    def csrf(
        conta: Annotated[ContaAutenticada, Depends(exigir_conta)],
    ) -> dict[str, str]:
        return {"csrf_token": conta.csrf_token}

    @router.post("/admin/contas", status_code=201)
    def criar_conta(
        body: CriarContaRequest,
        request: Request,
        conta: Annotated[ContaAutenticada, Depends(exigir_mutacao_autenticada)],
        _admin: Annotated[ContaAutenticada, Depends(exigir_admin)],
        repositorio: Annotated[PostgresContaRepository, Depends(exigir_repository)],
    ) -> dict[str, object]:
        try:
            conta_id, temporaria, expiracao = AdministrarContas(repositorio).criar(
                conta.id,
                body.usuario,
                body.papel,
                body.justificativa,
                request_id=getattr(request.state, "request_id", None),
            )
        except (ConflitoConta, OperacaoNaoAutorizada, ValueError) as exc:
            raise erro_operacao(exc) from None
        return {
            "id": conta_id,
            "credencial_temporaria": temporaria,
            "expira_em": expiracao.isoformat(),
            "troca_senha_obrigatoria": True,
        }

    @router.post("/admin/contas/{conta_id}/redefinir-senha", status_code=200)
    def redefinir_senha(
        conta_id: int,
        body: RedefinirSenhaRequest,
        request: Request,
        conta: Annotated[ContaAutenticada, Depends(exigir_mutacao_autenticada)],
        _admin: Annotated[ContaAutenticada, Depends(exigir_admin)],
        repositorio: Annotated[PostgresContaRepository, Depends(exigir_repository)],
    ) -> dict[str, object]:
        try:
            temporaria, expiracao = AdministrarContas(repositorio).redefinir_senha(
                conta.id,
                conta_id,
                body.justificativa,
                body.referencia_verificacao,
                request_id=getattr(request.state, "request_id", None),
            )
        except (ConflitoConta, OperacaoNaoAutorizada, ValueError) as exc:
            raise erro_operacao(exc) from None
        return {
            "credencial_temporaria": temporaria,
            "expira_em": expiracao.isoformat(),
            "troca_senha_obrigatoria": True,
        }

    @router.post("/admin/contas/{conta_id}/desativar", status_code=204)
    def desativar_conta(
        conta_id: int,
        body: DesativarContaRequest,
        request: Request,
        response: Response,
        conta: Annotated[ContaAutenticada, Depends(exigir_mutacao_autenticada)],
        _admin: Annotated[ContaAutenticada, Depends(exigir_admin)],
        repositorio: Annotated[PostgresContaRepository, Depends(exigir_repository)],
    ) -> Response:
        try:
            AdministrarContas(repositorio).desativar(
                conta.id,
                conta_id,
                body.justificativa,
                request_id=getattr(request.state, "request_id", None),
            )
        except (OperacaoNaoAutorizada, ValueError) as exc:
            raise erro_operacao(exc) from None
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.post("/admin/turmas/{turma_id}/responsavel", status_code=204)
    def transferir_turma(
        turma_id: int,
        body: TransferirTurmaRequest,
        request: Request,
        response: Response,
        conta: Annotated[ContaAutenticada, Depends(exigir_mutacao_autenticada)],
        _admin: Annotated[ContaAutenticada, Depends(exigir_admin)],
        repositorio: Annotated[PostgresContaRepository, Depends(exigir_repository)],
    ) -> Response:
        try:
            AdministrarContas(repositorio).transferir_turma(
                conta.id,
                turma_id,
                body.professor_id,
                body.justificativa,
                request_id=getattr(request.state, "request_id", None),
            )
        except (OperacaoNaoAutorizada, ValueError) as exc:
            raise erro_operacao(exc) from None
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.get("/turmas/{turma_id}", status_code=200)
    def consultar_turma(
        turma_id: int,
        conta: Annotated[ContaAutenticada, Depends(exigir_conta)],
        repositorio: Annotated[PostgresContaRepository, Depends(exigir_repository)],
    ) -> dict[str, object]:
        if gestao_repository is not None:
            from src.application.use_cases.gerenciar_turmas_web import (
                GerenciarTurmasWeb,
            )

            try:
                return GerenciarTurmasWeb(gestao_repository).obter(
                    conta.como_ator(), turma_id
                )
            except (AcessoTurmaNegado, LookupError):
                raise HTTPException(
                    status_code=404, detail="Recurso nao encontrado."
                ) from None
            except PermissionError:
                raise HTTPException(
                    status_code=403, detail="Operacao nao autorizada."
                ) from None
            except ValueError:
                raise HTTPException(
                    status_code=422, detail="Requisicao invalida."
                ) from None
        turma = repositorio.autorizar_turma(turma_id)
        if turma is None:
            raise HTTPException(status_code=404, detail="Recurso nao encontrado.")
        try:
            AutorizarTurma.exigir(conta.como_ator(), turma, "ler")
        except AcessoTurmaNegado:
            raise HTTPException(
                status_code=404, detail="Recurso nao encontrado."
            ) from None
        return {
            "id": turma.id,
            "materia": turma.materia,
            "periodo": turma.periodo,
            "responsavel_professor_id": turma.responsavel_professor_id,
        }

    return router
