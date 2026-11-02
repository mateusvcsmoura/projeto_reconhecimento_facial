"""Rotas de sessao, link e tentativa de presenca sem fluxo de cadastro."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from src.application.services.fila_facial import FilaCheia, ReservaInvalida
from src.application.use_cases.gerenciar_links import AcessoLinkEmitido, GerenciarLinks
from src.application.use_cases.gerenciar_sessoes import GerenciarSessoes
from src.application.use_cases.iniciar_tentativa_presenca import IniciarTentativa
from src.application.use_cases.receber_captura_presenca import ReceberCaptura
from src.config.web_settings import WebSettings
from src.domain.services.autorizacao import AcessoTurmaNegado
from src.domain.services.desafio_captura import ContextoDesafio
from src.infrastructure.repositories.postgres_conta_repository import ContaAutenticada
from src.infrastructure.repositories.postgres_presenca_web_repository import (
    CapturaRepetidaDiferente,
    QuotaTentativasEsgotada,
    TentativaAtiva,
    TentativaIndisponivel,
)
from src.presentation.web.dependencies import DependenciasAuthWeb
from src.presentation.web.diagnostico_captura import (
    DiagnosticoCaptura,
    registrar_diagnostico,
)
from src.presentation.web.rate_limit import endereco_cliente

if TYPE_CHECKING:
    from src.presentation.web.app import WebServices


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CriarSessaoRequest(_Schema):
    titulo: str = Field(min_length=1, max_length=120)
    inicio_em: datetime
    fim_em: datetime


class ExcluirSessaoRequest(_Schema):
    confirmacao: str = Field(min_length=1, max_length=64)


class IniciarTentativaRequest(_Schema):
    matricula: str = Field(min_length=1, max_length=32)


class ReceberCapturaRequest(_Schema):
    etapa: int = Field(ge=1, le=3)
    nonce: str = Field(min_length=32, max_length=128)
    captura_base64: str = Field(min_length=1, max_length=11_184_812)
    diagnostico: list[DiagnosticoCaptura] = Field(default_factory=list, max_length=1)


def _bearer(request: Request) -> str | None:
    valor = request.headers.get("authorization", "")
    esquema, separador, token = valor.partition(" ")
    if not separador or esquema.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _responder_rate_limit(
    services: WebServices,
    request: Request,
    *,
    acao: str,
    link_id: UUID,
    agora: datetime,
    limite: int,
    trusted_proxy_cidrs: str | None,
) -> None:
    repositorio = services.presenca_repository
    segredo = services.rate_limit_secret
    if repositorio is None or not isinstance(segredo, bytes) or len(segredo) < 32:
        raise HTTPException(status_code=503, detail="Servico de presenca indisponivel.")
    host = endereco_cliente(request, trusted_proxy_cidrs)
    digest = hmac.new(
        segredo,
        f"presenca:{acao}:{link_id}:{host}".encode(),
        hashlib.sha256,
    ).hexdigest()
    espera = repositorio.limitar_requisicao(
        digest,
        agora=agora,
        limite=limite,
        janela=timedelta(minutes=15),
    )
    if espera is not None:
        raise HTTPException(
            status_code=429,
            detail="Limite temporario de requisicoes atingido.",
            headers={"Retry-After": str(espera)},
        )


def criar_rotas_presencas(settings: WebSettings, services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["presencas"])
    auth = DependenciasAuthWeb(settings, services.auth_repository)

    def exigir_repositorio() -> Any:
        if services.presenca_repository is None:
            raise HTTPException(status_code=503, detail="Sessoes indisponiveis.")
        return services.presenca_repository

    def exigir_links() -> Any:
        if services.link_repository is None:
            raise HTTPException(status_code=503, detail="Links indisponiveis.")
        return services.link_repository

    def exigir_fila() -> Any:
        if services.fila_facial is None or services.capture_storage is None:
            raise HTTPException(status_code=503, detail="Captura indisponivel.")
        return services.fila_facial

    def exigir_desafio() -> Any:
        if services.desafio_captura is None:
            raise HTTPException(status_code=503, detail="Verificacao indisponivel.")
        return services.desafio_captura

    @router.post("/turmas/{turma_id}/sessoes", status_code=status.HTTP_201_CREATED)
    def criar_sessao(
        turma_id: int,
        body: CriarSessaoRequest,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        if turma_id <= 0:
            raise HTTPException(status_code=404, detail="Turma nao encontrada.")
        try:
            criada = GerenciarSessoes(
                exigir_repositorio(), relogio=services.now_utc
            ).criar(
                conta.como_ator(),
                turma_id=turma_id,
                inicio_em=body.inicio_em,
                fim_em=body.fim_em,
                titulo=body.titulo,
            )
        except (LookupError, PermissionError, AcessoTurmaNegado):
            raise HTTPException(
                status_code=404, detail="Turma nao encontrada."
            ) from None
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail="A sessao e invalida."
            ) from None
        return {
            "id": criada.id,
            "turma_id": criada.turma_id,
            "titulo": criada.titulo,
            "inicio_em": criada.inicio_em.isoformat(),
            "fim_em": criada.fim_em.isoformat(),
            "versao": criada.versao,
        }

    @router.post("/sessoes/{sessao_id}/links", status_code=status.HTTP_201_CREATED)
    def criar_link_presenca(
        sessao_id: int,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        if sessao_id <= 0:
            raise HTTPException(status_code=404, detail="Sessao nao encontrada.")
        try:
            sessao = exigir_repositorio().obter_sessao_autorizada(
                conta.como_ator(), sessao_id
            )
        except (LookupError, PermissionError, AcessoTurmaNegado):
            raise HTTPException(
                status_code=404, detail="Sessao nao encontrada."
            ) from None
        if sessao is None or sessao.revogada:
            raise HTTPException(status_code=404, detail="Sessao nao encontrada.")
        fim = sessao.fim_em + timedelta(seconds=120)
        if settings.purpose_end_at is not None:
            fim = min(fim, settings.purpose_end_at.astimezone(sessao.fim_em.tzinfo))
        try:
            link = GerenciarLinks(exigir_links(), relogio=services.now_utc).criar(
                conta.como_ator(),
                sessao.turma_id,
                finalidade="presenca",
                sessao_id=sessao_id,
                finalidade_ate=fim,
            )
        except (LookupError, PermissionError, AcessoTurmaNegado, ValueError):
            raise HTTPException(status_code=409, detail="Link indisponivel.") from None
        return {
            "id": str(link.id),
            "token": link.token,
            "finalidade": link.finalidade,
            "sessao_id": link.sessao_id,
            "expira_em": link.expira_em.isoformat(),
        }

    @router.patch("/sessoes/{sessao_id}", status_code=status.HTTP_200_OK)
    def editar_sessao(
        sessao_id: int,
        body: CriarSessaoRequest,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        try:
            # Mesma regra da emissão do link: fim da sessão + 120 s, no máximo
            # até o fim da finalidade.
            fim_link = body.fim_em + timedelta(seconds=120)
            if settings.purpose_end_at is not None:
                fim_link = min(
                    fim_link, settings.purpose_end_at.astimezone(body.fim_em.tzinfo)
                )
            editada = GerenciarSessoes(
                exigir_repositorio(), relogio=services.now_utc
            ).editar(
                conta.como_ator(),
                sessao_id,
                titulo=body.titulo,
                inicio_em=body.inicio_em,
                fim_em=body.fim_em,
                fim_link=fim_link,
            )
        except (LookupError, PermissionError, AcessoTurmaNegado):
            raise HTTPException(
                status_code=404, detail="Sessao nao encontrada."
            ) from None
        except RuntimeError:
            raise HTTPException(
                status_code=409, detail="Sessao revogada nao pode ser editada."
            ) from None
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail="A sessao e invalida."
            ) from None
        return {
            "id": editada.id,
            "turma_id": editada.turma_id,
            "titulo": editada.titulo,
            "inicio_em": editada.inicio_em.isoformat(),
            "fim_em": editada.fim_em.isoformat(),
            "versao": editada.versao,
        }

    @router.delete("/sessoes/{sessao_id}", status_code=status.HTTP_200_OK)
    def excluir_sessao(
        sessao_id: int,
        body: ExcluirSessaoRequest,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        try:
            resultado = GerenciarSessoes(
                exigir_repositorio(), relogio=services.now_utc
            ).excluir(conta.como_ator(), sessao_id, confirmacao=body.confirmacao)
        except (LookupError, PermissionError, AcessoTurmaNegado):
            raise HTTPException(
                status_code=404, detail="Sessao nao encontrada."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=422, detail="A confirmacao nao corresponde a sessao."
            ) from None
        except RuntimeError:
            raise HTTPException(
                status_code=409,
                detail="Aguarde as verificacoes em processamento e tente novamente.",
            ) from None
        limpeza_pendente = False
        if services.capture_storage is not None:
            for job_id in cast(tuple[UUID, ...], resultado["jobs_temporarios"]):
                try:
                    services.capture_storage.remover_job(job_id)
                except OSError:
                    limpeza_pendente = True
        return {
            "id": sessao_id,
            "excluida": True,
            "presencas_removidas": resultado["presencas"],
            "tentativas_removidas": resultado["tentativas"],
            "limpeza_pendente": limpeza_pendente,
        }

    @router.post("/sessoes/{sessao_id}/revogar", status_code=status.HTTP_200_OK)
    def revogar_sessao(
        sessao_id: int,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        try:
            canceladas, temporarios = GerenciarSessoes(
                exigir_repositorio(), relogio=services.now_utc
            ).revogar(conta.como_ator(), sessao_id)
        except (LookupError, PermissionError, AcessoTurmaNegado):
            raise HTTPException(
                status_code=404, detail="Sessao nao encontrada."
            ) from None
        limpeza_pendente = False
        if services.capture_storage is not None:
            for job_id in temporarios:
                try:
                    services.capture_storage.remover_job(job_id)
                except OSError:
                    limpeza_pendente = True
        return {
            "id": sessao_id,
            "revogada": True,
            "tentativas_canceladas": canceladas,
            "limpeza_pendente": limpeza_pendente,
        }

    @router.post("/sessoes/{sessao_id}/tentativas", status_code=status.HTTP_201_CREATED)
    def iniciar_tentativa(
        sessao_id: int,
        body: IniciarTentativaRequest,
        request: Request,
        idempotency_key: str = Header(
            ..., alias="Idempotency-Key", min_length=16, max_length=256
        ),
    ) -> dict[str, object]:
        if sessao_id <= 0:
            raise HTTPException(status_code=404, detail="Sessao nao encontrada.")
        token = _bearer(request)
        if token is None:
            raise HTTPException(status_code=404, detail="Link indisponivel.")
        agora = services.now_utc()
        cred_hash = hashlib.sha256(token.encode()).hexdigest()
        contexto = exigir_links().contexto_credencial(
            cred_hash, agora=agora, exigir_link_ativo=True
        )
        if (
            contexto is None
            or contexto.get("finalidade") != "presenca"
            or contexto.get("sessao_id") != sessao_id
            or not isinstance(contexto.get("link_id"), UUID)
            or not isinstance(contexto.get("turma_id"), int)
        ):
            raise HTTPException(status_code=404, detail="Link indisponivel.")
        link_id = contexto["link_id"]
        _responder_rate_limit(
            services,
            request,
            acao="iniciar",
            link_id=link_id,
            agora=agora,
            limite=settings.presence_start_limit_per_window,
            trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
        )
        acesso = AcessoLinkEmitido(
            credencial=token,
            link_id=link_id,
            turma_id=contexto["turma_id"],
            finalidade="presenca",
            expira_em=contexto["expira_em"],
            finalidade_ate=contexto["finalidade_ate"],
            sessao_id=sessao_id,
        )
        try:
            inicio = IniciarTentativa(
                exigir_repositorio(), exigir_fila(), exigir_desafio()
            ).executar(
                acesso,
                body.matricula,
                idempotency_key,
                agora=agora,
            )
        except TentativaAtiva:
            raise HTTPException(
                status_code=409, detail="Tentativa em andamento."
            ) from None
        except QuotaTentativasEsgotada:
            raise HTTPException(
                status_code=409, detail="Tentativas indisponiveis."
            ) from None
        except FilaCheia as erro:
            raise HTTPException(
                status_code=503,
                detail="Processamento indisponivel.",
                headers={"Retry-After": str(erro.retry_after_seconds)},
            ) from None
        except (TentativaIndisponivel, LookupError, PermissionError):
            # Genérica de propósito: não revela se a matrícula existe na turma.
            raise HTTPException(
                status_code=404,
                detail=(
                    "Tentativa indisponível. Confira se a matrícula está correta, "
                    "vinculada a esta turma e com o cadastro facial aprovado pelo "
                    "professor. Se estiver tudo certo, procure o professor."
                ),
            ) from None
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail="A solicitacao e invalida."
            ) from None
        resposta: dict[str, object] = {
            "id": str(inicio.tentativa.id),
            "estado": inicio.tentativa.estado.value,
            "ordinal": inicio.tentativa.ordinal,
            "prazo_envio": inicio.tentativa.prazo_envio.isoformat(),
            "credencial_captura": inicio.credencial_captura,
        }
        if inicio.desafio is not None:
            resposta["desafio"] = {
                "nonce": inicio.desafio.nonce,
                "etapa": inicio.desafio.proxima_etapa,
                "orientacao": "frente",
                "direcao_movimento": inicio.desafio.direcao.value,
                "expira_em": inicio.desafio.expira_em.isoformat(),
            }
        return resposta

    @router.post(
        "/tentativas/{tentativa_id}/capturas", status_code=status.HTTP_202_ACCEPTED
    )
    def receber_captura(
        tentativa_id: UUID,
        body: ReceberCapturaRequest,
        request: Request,
    ) -> dict[str, object]:
        token = _bearer(request)
        if token is None:
            raise HTTPException(status_code=404, detail="Tentativa nao encontrada.")
        agora = services.now_utc()
        hash_credencial = hashlib.sha256(token.encode()).hexdigest()
        contexto = exigir_repositorio().consultar_tentativa(
            tentativa_id, hash_credencial
        )
        if contexto is None:
            raise HTTPException(status_code=404, detail="Tentativa nao encontrada.")
        _responder_rate_limit(
            services,
            request,
            acao="captura",
            link_id=contexto["link_id"],
            agora=agora,
            limite=settings.presence_capture_limit_per_window,
            trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
        )
        try:
            imagem = base64.b64decode(body.captura_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=422, detail="A captura e invalida."
            ) from None
        try:
            armazenamento = services.capture_storage
            if armazenamento is None:
                raise HTTPException(status_code=503, detail="Captura indisponivel.")
            recebida = ReceberCaptura(
                exigir_repositorio(),
                exigir_desafio(),
                exigir_fila(),
                armazenamento,
                max_bytes=settings.capture_max_bytes_per_capture,
            ).executar(
                tentativa_id,
                token,
                nonce=body.nonce,
                etapa=body.etapa,
                conteudo=imagem,
                recebida_em_servidor=agora,
            )
        except CapturaRepetidaDiferente:
            raise HTTPException(status_code=409, detail="Etapa ja recebida.") from None
        except TimeoutError:
            raise HTTPException(
                status_code=410, detail="Prazo de captura encerrado."
            ) from None
        except (LookupError, PermissionError, TentativaIndisponivel, ReservaInvalida):
            raise HTTPException(status_code=409, detail="Etapa nao aceita.") from None
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(
                status_code=503, detail="Captura indisponivel."
            ) from None
        # Mesmo id de job dos logs do worker ("Presença <job> ... etapa=N").
        registrar_diagnostico(
            f"Presença {recebida.job_id} etapa={recebida.etapa} recebida",
            body.diagnostico,
        )
        return {
            "tentativa_id": str(recebida.job_id),
            "etapa": recebida.etapa,
            "recebida": True,
            "repetida": recebida.repetida,
        }

    @router.get("/tentativas/{tentativa_id}", status_code=status.HTTP_200_OK)
    def consultar_tentativa(tentativa_id: UUID, request: Request) -> dict[str, object]:
        token = _bearer(request)
        if token is None:
            raise HTTPException(status_code=404, detail="Tentativa nao encontrada.")
        contexto = exigir_repositorio().consultar_tentativa(
            tentativa_id, hashlib.sha256(token.encode()).hexdigest()
        )
        if contexto is None:
            raise HTTPException(status_code=404, detail="Tentativa nao encontrada.")
        tentativa = contexto["tentativa"]
        resposta: dict[str, object] = {
            "id": str(tentativa.id),
            "estado": tentativa.estado.value,
            "prazo_envio": tentativa.prazo_envio.isoformat(),
            "motivo_tecnico": tentativa.motivo_tecnico,
        }
        if (
            tentativa.estado.value in {"iniciada", "recebida"}
            and contexto["estado_job"].value == "recebida"
        ):
            desafio = exigir_desafio().consultar(
                ContextoDesafio(
                    job_id=tentativa.id,
                    aluno_id=tentativa.aluno_id,
                    conjunto_id=tentativa.conjunto_id,
                    versao_referencia=tentativa.versao_referencia,
                    prazo_recebimento=tentativa.prazo_envio,
                ),
                services.now_utc(),
            )
            if desafio is not None:
                resposta["desafio"] = {
                    "nonce": desafio.nonce,
                    "etapa": desafio.proxima_etapa,
                    "orientacao": (
                        "frente"
                        if desafio.proxima_etapa in (1, 3)
                        else desafio.direcao.value
                    ),
                    "expira_em": desafio.expira_em.isoformat(),
                    # Preenchido quando a etapa voltou por recusa corrigível.
                    "motivo": desafio.motivo,
                }
        return resposta

    return router
