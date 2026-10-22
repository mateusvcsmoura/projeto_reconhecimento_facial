"""API de solicitações de cadastro; não serializa artefatos biométricos."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.application.services.fila_facial import (
    FilaFacial,
    TipoJobFacial,
)
from src.application.use_cases.aprovar_atualizacao_biometrica import (
    AprovarAtualizacaoBiometrica,
)
from src.application.use_cases.aprovar_cadastro_web import AprovarCadastroWeb
from src.application.use_cases.rejeitar_cadastro_web import RejeitarCadastroWeb
from src.application.use_cases.solicitar_atualizacao_biometrica import (
    SolicitarAtualizacaoBiometrica,
)
from src.application.use_cases.solicitar_cadastro_web import (
    ConsentimentoWeb,
    ContextoConvite,
    DadosCadastroWeb,
    SolicitarCadastroWeb,
)
from src.config.web_settings import WebSettings
from src.domain.entities.solicitacao_cadastro import SolicitacaoCadastro
from src.domain.services.autorizacao import AcessoTurmaNegado
from src.infrastructure.repositories.postgres_conta_repository import (
    ContaAutenticada,
)
from src.presentation.web.dependencies import DependenciasAuthWeb

if TYPE_CHECKING:
    from src.presentation.web.app import WebServices

AVISO_BIOMETRIA = (
    "Este cadastro é usado para registro de presença acadêmica. A coleta inclui "
    "três recortes faciais e representações matemáticas da face para comparação "
    "automatizada; não inclui inferência de emoção, idade ou gênero nem uso para "
    "treinar modelos. A solicitação fica pendente até conferência independente "
    "de identidade por professor responsável. A recusa impede a coleta facial; "
    "procure a instituição para solicitar uma forma alternativa de registro. "
    "Os dados provisórios são eliminados ao encerrar a solicitação ou a finalidade."
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CriarCadastroRequest(_Schema):
    nome: str = Field(min_length=1, max_length=255)
    matricula: str = Field(min_length=1, max_length=32)
    aviso_versao: str = Field(min_length=1, max_length=64)
    consentimento: bool


class DecisaoCadastroRequest(_Schema):
    metodo_identidade: Literal[
        "documento_presencial", "codigo_institucional", "contato_institucional"
    ]
    justificativa: str = Field(min_length=10, max_length=500)


class RejeitarCadastroRequest(_Schema):
    justificativa: str = Field(min_length=10, max_length=500)


class SolicitacaoBiometriaRequest(_Schema):
    turma_id: int = Field(gt=0)
    aluno_id: int = Field(gt=0)


class ConsentimentoAtualizacaoRequest(_Schema):
    aviso_versao: str = Field(min_length=1, max_length=64)
    consentimento: bool


class CapturasCadastroRequest(_Schema):
    nonce: str = Field(min_length=32, max_length=128)
    capturas: list[str] = Field(min_length=3, max_length=3)


DESAFIO_DURACAO = timedelta(seconds=120)


def _novo_desafio(
    agora: datetime, expira_em: datetime
) -> tuple[str, str, str, datetime]:
    nonce = secrets.token_urlsafe(32)
    direcao = secrets.choice(("esquerda", "direita"))
    expira_desafio = min(agora + DESAFIO_DURACAO, expira_em)
    return (
        nonce,
        hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        direcao,
        expira_desafio,
    )


def _payload_desafio(
    nonce: str, direcao: str, expira_em: datetime
) -> dict[str, object]:
    return {
        "nonce": nonce,
        "primeira_orientacao": "frente",
        "direcao": direcao,
        "ultima_orientacao": "frente",
        "sequencia": ["frente", direcao, "frente"],
        "expira_em": expira_em.isoformat(),
    }


def _payload_solicitacao(solicitacao: SolicitacaoCadastro) -> dict[str, object]:
    """DTO explícito de metadados, sem foto, embedding, job ou caminho."""
    return {
        "id": solicitacao.id,
        "tipo": solicitacao.tipo,
        "estado": solicitacao.estado,
        "turma_id": solicitacao.turma_id,
        "nome": solicitacao.nome,
        "matricula": solicitacao.matricula,
        "expira_em": solicitacao.expira_em.isoformat(),
    }


def _bearer(request: Request) -> str | None:
    esquema, separador, valor = request.headers.get("authorization", "").partition(" ")
    if esquema.lower() != "bearer" or not separador or not valor.strip():
        return None
    return valor.strip()


def criar_rotas_cadastros(settings: WebSettings, services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["cadastros"])
    auth = DependenciasAuthWeb(settings, services.auth_repository)

    def exigir_links() -> Any:
        if services.link_repository is None:
            raise HTTPException(status_code=503, detail="Links indisponíveis.")
        return services.link_repository

    def exigir_solicitacoes() -> Any:
        if services.solicitacao_repository is None:
            raise HTTPException(status_code=503, detail="Solicitações indisponíveis.")
        return services.solicitacao_repository

    def exigir_fila() -> FilaFacial:
        if services.fila_facial is None:
            raise HTTPException(status_code=503, detail="Captura indisponível.")
        return services.fila_facial

    def _contexto_credencial(
        request: Request, solicitacao_id: int | None = None, *, ativa: bool
    ) -> tuple[str, dict[str, object]]:
        credencial = _bearer(request)
        if credencial is None:
            raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
        hash_credencial = hashlib.sha256(credencial.encode("utf-8")).hexdigest()
        contexto = exigir_links().contexto_credencial(
            hash_credencial,
            agora=services.now_utc(),
            solicitacao_id=solicitacao_id,
            exigir_link_ativo=ativa,
        )
        if contexto is None:
            raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
        if (
            solicitacao_id is None and contexto.get("finalidade") != "cadastro"
        ) or contexto.get("finalidade") == "presenca":
            raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
        return hash_credencial, contexto

    def _consultar_solicitacao(
        repositorio: Any, solicitacao_id: int
    ) -> SolicitacaoCadastro:
        try:
            return repositorio.obter_solicitacao(solicitacao_id)
        except LookupError:
            raise HTTPException(
                status_code=404, detail="Solicitação não encontrada."
            ) from None

    def _autorizar_turma(conta: ContaAutenticada, turma_id: int) -> None:
        turma = auth.repository().autorizar_turma(turma_id)  # type: ignore[attr-defined]
        if turma is None:
            raise HTTPException(status_code=404, detail="Recurso não encontrado.")
        from src.domain.services.autorizacao import AutorizarTurma

        try:
            AutorizarTurma.exigir(conta.como_ator(), turma, "consultar cadastros web")
        except AcessoTurmaNegado:
            raise HTTPException(
                status_code=404, detail="Recurso não encontrado."
            ) from None

    @router.get("/avisos/biometria", status_code=200)
    def consultar_aviso_biometria() -> dict[str, object]:
        return {
            "versao": settings.consent_notice_version,
            "texto": AVISO_BIOMETRIA,
            "finalidade_ate": (
                settings.purpose_end_at.isoformat()
                if settings.purpose_end_at is not None
                else None
            ),
        }

    @router.post("/cadastros", status_code=status.HTTP_201_CREATED)
    def criar_cadastro(
        body: CriarCadastroRequest,
        request: Request,
    ) -> dict[str, object]:
        hash_credencial, contexto = _contexto_credencial(request, ativa=True)
        if body.aviso_versao != settings.consent_notice_version:
            raise HTTPException(status_code=409, detail="O aviso de privacidade mudou.")
        if not body.consentimento:
            raise HTTPException(status_code=422, detail="O consentimento é necessário.")
        try:
            agora = services.now_utc()
            prazo_finalidade = contexto["finalidade_ate"]
            turma_id = contexto["turma_id"]
            expira_link = contexto["expira_em"]
            if (
                not isinstance(prazo_finalidade, datetime)
                or type(turma_id) is not int
                or not isinstance(expira_link, datetime)
            ):
                raise ValueError("O prazo da finalidade é inválido.")
            nonce, nonce_hash, direcao, desafio_expira = _novo_desafio(
                agora, prazo_finalidade
            )
            cadastro = SolicitarCadastroWeb(
                exigir_solicitacoes(), relogio=services.now_utc
            ).criar(
                DadosCadastroWeb(matricula=body.matricula, nome=body.nome),
                ContextoConvite(
                    referencia=str(contexto["link_id"]),
                    turma_id=turma_id,
                    expira_em=expira_link,
                    finalidade_ate=prazo_finalidade,
                ),
                ConsentimentoWeb(True, body.aviso_versao),
                credencial_acesso_hash=hash_credencial,
                desafio_nonce_hash=nonce_hash,
                desafio_direcao=direcao,
                desafio_expira_em=desafio_expira,
            )
        except (PermissionError, LookupError):
            raise HTTPException(status_code=404, detail="Link indisponível.") from None
        except ValueError as erro:
            raise HTTPException(status_code=422, detail=str(erro)) from None
        payload = _payload_solicitacao(cadastro)
        payload["desafio"] = _payload_desafio(nonce, direcao, desafio_expira)
        return payload

    @router.get("/cadastros/{solicitacao_id}", status_code=200)
    def consultar_cadastro(solicitacao_id: int, request: Request) -> dict[str, object]:
        _contexto_credencial(request, solicitacao_id, ativa=False)
        cadastro = _consultar_solicitacao(exigir_solicitacoes(), solicitacao_id)
        estado: str = cadastro.estado
        if cadastro.expira_em <= services.now_utc() and estado in {
            "em_coleta",
            "em_validacao",
            "pendente_aprovacao",
        }:
            estado = "expirada"
        payload = _payload_solicitacao(cadastro)
        payload["estado"] = estado
        return payload

    @router.post("/cadastros/{solicitacao_id}/desafio", status_code=200)
    def renovar_desafio(solicitacao_id: int, request: Request) -> dict[str, object]:
        """Emite nova sequência ao iniciar a câmera; o nonce anterior deixa de valer."""
        _contexto_credencial(request, solicitacao_id, ativa=True)
        repositorio = exigir_solicitacoes()
        cadastro = _consultar_solicitacao(repositorio, solicitacao_id)
        agora = services.now_utc()
        nonce, nonce_hash, direcao, desafio_expira = _novo_desafio(
            agora, cadastro.expira_em
        )
        try:
            cadastro = repositorio.renovar_desafio_coleta(
                solicitacao_id,
                agora=agora,
                desafio_nonce_hash=nonce_hash,
                desafio_direcao=direcao,
                desafio_expira_em=desafio_expira,
            )
        except PermissionError:
            raise HTTPException(
                status_code=404, detail="Solicitação não encontrada."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="A coleta não está disponível."
            ) from None
        payload = _payload_solicitacao(cadastro)
        payload["desafio"] = _payload_desafio(nonce, direcao, desafio_expira)
        return payload

    @router.post(
        "/cadastros/{solicitacao_id}/capturas",
        status_code=status.HTTP_202_ACCEPTED,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["nonce", "capturas"],
                            "properties": {
                                "nonce": {
                                    "type": "string",
                                    "minLength": 32,
                                    "maxLength": 128,
                                },
                                "capturas": {
                                    "type": "array",
                                    "minItems": 3,
                                    "maxItems": 3,
                                    "items": {
                                        "type": "string",
                                        "contentEncoding": "base64",
                                    },
                                },
                            },
                        }
                    }
                },
            }
        },
    )
    async def enviar_capturas(
        solicitacao_id: int,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, object]:
        hash_credencial, _contexto = _contexto_credencial(
            request, solicitacao_id, ativa=True
        )
        repositorio = exigir_solicitacoes()
        cadastro = _consultar_solicitacao(repositorio, solicitacao_id)
        if (
            cadastro.tipo not in {"cadastro", "atualizacao"}
            or cadastro.estado != "em_coleta"
            or cadastro.consentimento_em is None
            or cadastro.consentimento_versao is None
            or cadastro.expira_em <= services.now_utc()
        ):
            raise HTTPException(status_code=409, detail="A coleta não está disponível.")
        armazenamento = services.capture_storage
        if armazenamento is None:
            raise HTTPException(status_code=503, detail="Captura indisponível.")

        # O corpo só é lido depois de validar autorização e consentimento.
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            raise HTTPException(
                status_code=415, detail="Envie capturas em JSON Base64."
            )
        max_bytes = settings.capture_max_bytes_per_capture
        limite_corpo = 3 * (((max_bytes + 2) // 3) * 4) + 4096
        corpo = bytearray()
        async for parte in request.stream():
            if len(corpo) + len(parte) > limite_corpo:
                raise HTTPException(status_code=413, detail="O envio excede o limite.")
            corpo.extend(parte)
        try:
            body = CapturasCadastroRequest.model_validate_json(bytes(corpo))
        except (ValidationError, ValueError):
            raise HTTPException(
                status_code=422, detail="Envie exatamente três capturas Base64."
            ) from None
        if (
            cadastro.desafio_nonce_hash is None
            or cadastro.desafio_direcao not in {"esquerda", "direita"}
            or cadastro.desafio_expira_em is None
            or cadastro.desafio_expira_em <= services.now_utc()
            or not hmac.compare_digest(
                hashlib.sha256(body.nonce.encode("utf-8")).hexdigest(),
                cadastro.desafio_nonce_hash,
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="O desafio de captura expirou ou é inválido.",
            )
        try:
            capturas = [base64.b64decode(item, validate=True) for item in body.capturas]
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=422, detail="Envie exatamente três capturas Base64."
            ) from None
        if any(not item or len(item) > max_bytes for item in capturas):
            raise HTTPException(
                status_code=422, detail="Captura vazia ou acima do limite."
            )

        agora = services.now_utc()
        idempotencia = idempotency_key or f"cadastro-{solicitacao_id}"
        if not idempotencia.strip() or len(idempotencia) > 256:
            raise HTTPException(status_code=422, detail="Chave de envio inválida.")
        fila = exigir_fila()
        reserva = fila.reservar(
            TipoJobFacial.CADASTRO,
            str(solicitacao_id),
            idempotencia,
            min(
                cadastro.expira_em,
                agora + timedelta(seconds=settings.job_reservation_seconds),
            ),
        )
        try:
            for ordinal, conteudo in enumerate(capturas, start=1):
                armazenamento.salvar_captura(reserva.id, ordinal, conteudo)
            manifesto = armazenamento.manifesto(reserva.id)
            repositorio.associar_job_cadastro(
                solicitacao_id,
                reserva.id,
                hash_credencial,
                agora=agora,
            )
            fila.submeter(reserva.id, manifesto)
        except (PermissionError, LookupError):
            fila.cancelar(reserva.id, reserva.credencial)
            armazenamento.remover_job(reserva.id)
            raise HTTPException(
                status_code=404, detail="Solicitação não encontrada."
            ) from None
        except (OSError, ValueError, RuntimeError):
            fila.cancelar(reserva.id, reserva.credencial)
            armazenamento.remover_job(reserva.id)
            raise HTTPException(
                status_code=422, detail="As capturas não foram aceitas."
            ) from None
        return {"operacao_id": str(reserva.id), "estado": "enfileirada"}

    @router.get("/turmas/{turma_id}/cadastros", status_code=200)
    def listar_cadastros_turma(
        turma_id: int,
        conta: ContaAutenticada = Depends(auth.exigir_conta),  # noqa: B008
        estado: Literal[
            "em_coleta", "em_validacao", "pendente_aprovacao"
        ] = "pendente_aprovacao",
        limite: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, object]:
        _autorizar_turma(conta, turma_id)
        solicitacoes = exigir_solicitacoes().listar_cadastros_turma(
            conta.como_ator(), turma_id, estado=estado, limite=limite
        )
        return {"itens": [_payload_solicitacao(item) for item in solicitacoes]}

    @router.post("/cadastros/{solicitacao_id}/aprovar", status_code=200)
    def aprovar_cadastro(
        solicitacao_id: int,
        body: DecisaoCadastroRequest,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        if services.reference_storage is None:
            raise HTTPException(status_code=503, detail="Armazenamento indisponível.")
        try:
            resultado = AprovarCadastroWeb(
                exigir_solicitacoes(),
                services.reference_storage,
                relogio=services.now_utc,
            ).executar(
                conta.como_ator(),
                solicitacao_id,
                body.metodo_identidade,
                body.justificativa,
            )
        except (PermissionError, LookupError):
            raise HTTPException(
                status_code=404, detail="Solicitação não encontrada."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="A solicitação não pode ser aprovada."
            ) from None
        return {
            "estado": resultado.estado,
            "limpeza_pendente": resultado.limpeza_pendente,
        }

    @router.post("/cadastros/{solicitacao_id}/rejeitar", status_code=200)
    def rejeitar_cadastro(
        solicitacao_id: int,
        body: RejeitarCadastroRequest,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        if services.reference_storage is None:
            raise HTTPException(status_code=503, detail="Armazenamento indisponível.")
        try:
            resultado = RejeitarCadastroWeb(
                exigir_solicitacoes(),
                services.reference_storage,
                relogio=services.now_utc,
            ).executar(
                conta.como_ator(), solicitacao_id, justificativa=body.justificativa
            )
        except (PermissionError, LookupError):
            raise HTTPException(
                status_code=404, detail="Solicitação não encontrada."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="A solicitação não pode ser rejeitada."
            ) from None
        return {
            "estado": resultado.estado,
            "limpeza_pendente": resultado.limpeza_pendente,
        }

    @router.post(
        "/admin/solicitacoes-biometria/{solicitacao_id}/aprovar", status_code=200
    )
    def aprovar_atualizacao_biometrica(
        solicitacao_id: int,
        body: RejeitarCadastroRequest,
        conta: ContaAutenticada = Depends(auth.exigir_admin),  # noqa: B008
    ) -> dict[str, object]:
        if services.reference_storage is None:
            raise HTTPException(status_code=503, detail="Armazenamento indisponível.")
        try:
            versao = AprovarAtualizacaoBiometrica(
                exigir_solicitacoes(),
                services.reference_storage,
                relogio=services.now_utc,
            ).executar(
                conta.como_ator(),
                solicitacao_id,
                justificativa=body.justificativa,
            )
        except PermissionError:
            raise HTTPException(
                status_code=403, detail="Operação não autorizada."
            ) from None
        except LookupError:
            raise HTTPException(
                status_code=404, detail="Solicitação não encontrada."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="A atualização não pode ser aprovada."
            ) from None
        return {"estado": "aprovada", "versao_ativa": versao}

    @router.post(
        "/cadastros/{solicitacao_id}/consentimento",
        status_code=status.HTTP_200_OK,
    )
    def consentir_atualizacao(
        solicitacao_id: int,
        body: ConsentimentoAtualizacaoRequest,
        request: Request,
    ) -> dict[str, object]:
        hash_credencial, _contexto = _contexto_credencial(
            request, solicitacao_id, ativa=False
        )
        if body.aviso_versao != settings.consent_notice_version:
            raise HTTPException(status_code=409, detail="O aviso de privacidade mudou.")
        if not body.consentimento:
            raise HTTPException(status_code=422, detail="O consentimento é necessário.")
        cadastro = _consultar_solicitacao(exigir_solicitacoes(), solicitacao_id)
        agora = services.now_utc()
        nonce, nonce_hash, direcao, desafio_expira = _novo_desafio(
            agora, cadastro.expira_em
        )
        try:
            cadastro = exigir_solicitacoes().registrar_consentimento_atualizacao(
                solicitacao_id,
                hash_credencial,
                body.aviso_versao,
                agora=agora,
                desafio_nonce_hash=nonce_hash,
                desafio_direcao=direcao,
                desafio_expira_em=desafio_expira,
            )
        except PermissionError:
            raise HTTPException(
                status_code=404, detail="Solicitação não encontrada."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="Consentimento já registrado."
            ) from None
        payload = _payload_solicitacao(cadastro)
        payload["desafio"] = _payload_desafio(nonce, direcao, desafio_expira)
        return payload

    @router.post("/solicitacoes-biometria", status_code=status.HTTP_201_CREATED)
    def solicitar_atualizacao_biometrica(
        body: SolicitacaoBiometriaRequest,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        finalidade_ate = settings.purpose_end_at
        if finalidade_ate is None:
            raise HTTPException(status_code=503, detail="Finalidade não configurada.")
        token_captura = secrets.token_urlsafe(32)
        hash_credencial = hashlib.sha256(token_captura.encode("utf-8")).hexdigest()
        try:
            solicitacao = SolicitarAtualizacaoBiometrica(
                exigir_solicitacoes(), relogio=services.now_utc
            ).executar(
                conta.como_ator(),
                body.aluno_id,
                body.turma_id,
                expira_em=finalidade_ate,
                credencial_captura_hash=hash_credencial,
            )
        except (PermissionError, LookupError):
            raise HTTPException(
                status_code=404, detail="Recurso não encontrado."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="Solicitação não pode ser criada."
            ) from None
        payload = _payload_solicitacao(solicitacao)
        payload["credencial_captura"] = token_captura
        return payload

    return router
