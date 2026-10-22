"""Persistencia transacional das contas e sessoes do runtime web."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from sqlalchemy import Table, case, delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from src.domain.services.autorizacao import AtorWeb
from src.infrastructure.database import models

COOKIE_SESSAO = "facediff_session"
TEMPO_INATIVIDADE = timedelta(minutes=30)
TEMPO_ABSOLUTO_SESSAO = timedelta(hours=8)
JANELA_LOGIN = timedelta(minutes=15)
TEMPO_BLOQUEIO_LOGIN = timedelta(minutes=15)
MAX_FALHAS_LOGIN = 5


class CredenciaisInvalidas(Exception):
    """Usuario/senha invalidos, sem indicar qual campo falhou."""


class LoginLimitado(Exception):
    """O limite de tentativas do usuario ou endereco de rede foi atingido."""


class OperacaoNaoAutorizada(Exception):
    """Conta inativa, ator sem privilegio ou alvo indisponivel."""


class ConflitoConta(Exception):
    """Usuario normalizado ja cadastrado ou operacao concorrente."""


class PoliticaSenhaInvalida(ValueError):
    """A senha nao atende a politica web."""


class BootstrapJaConfigurado(RuntimeError):
    """Ja existe uma conta administrativa diferente do bootstrap solicitado."""


@dataclass(frozen=True)
class ContaAutenticada:
    id: int
    papel: str
    ativa: bool
    troca_senha_obrigatoria: bool
    professor_id: int | None
    sessao_id: int
    csrf_hash: str
    csrf_token: str
    usuario: str = ""

    def como_ator(self) -> AtorWeb:
        return AtorWeb(
            conta_id=self.id,
            papel=self.papel,
            ativa=self.ativa,
            troca_senha_obrigatoria=self.troca_senha_obrigatoria,
            professor_id=self.professor_id,
        )


@dataclass(frozen=True)
class ResultadoLogin:
    conta_id: int
    papel: str
    troca_senha_obrigatoria: bool
    token_sessao: str
    token_csrf: str


@dataclass(frozen=True)
class TurmaWeb:
    id: int
    materia: str
    periodo: str
    responsavel_professor_id: int | None


AuditoriaWriter = Callable[[Session, dict[str, Any]], None]


def _agora_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _escrever_auditoria(session: Session, evento: dict[str, Any]) -> None:
    session.add(models.EventoAuditoriaWeb(**evento))
    session.flush()


class PostgresContaRepository:
    """Operacoes de autenticacao que compartilham uma unica transacao SQL."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        segredo: str,
        clock: Callable[[], datetime] | None = None,
        parametros_hash: tuple[int, int, int] = (3, 65536, 4),
        gravar_auditoria: AuditoriaWriter = _escrever_auditoria,
    ) -> None:
        self.session_factory = session_factory
        self._segredo = segredo.encode("utf-8")
        self._clock = clock or (lambda: datetime.now(UTC))
        time_cost, memory_cost, parallelism = parametros_hash
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            type=Type.ID,
        )
        self._senha_falsa = self._hasher.hash(secrets.token_urlsafe(24))
        self._gravar_auditoria = gravar_auditoria

    def _now(self) -> datetime:
        return _agora_utc(self._clock())

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _csrf_para_sessao(self, token_sessao: str) -> str:
        mensagem = f"csrf:{token_sessao}".encode()
        return hmac.new(self._segredo, mensagem, hashlib.sha256).hexdigest()

    def _rate_key(self, categoria: str, valor: str) -> str:
        mensagem = f"login:{categoria}:{valor}".encode()
        return hmac.new(self._segredo, mensagem, hashlib.sha256).hexdigest()

    def _verificar_hash(self, password_hash: str, senha: str) -> bool:
        try:
            return self._hasher.verify(password_hash, senha)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def verificar_senha(self, usuario: str, senha: str) -> bool:
        usuario_normalizado = normalizar_usuario(usuario)
        with self.session_factory() as session:
            conta = session.scalar(
                select(models.ContaWeb).where(
                    models.ContaWeb.usuario_normalizado == usuario_normalizado
                )
            )
            return bool(conta and self._verificar_hash(conta.senha_hash, senha))

    def _event(
        self,
        session: Session,
        *,
        ator: int | None,
        acao: str,
        alvo_tipo: str,
        alvo_id: int | str,
        justificativa: str | None = None,
        antes: dict[str, Any] | None = None,
        depois: dict[str, Any] | None = None,
        request_id: str | None = None,
        instante: datetime | None = None,
    ) -> None:
        self._gravar_auditoria(
            session,
            {
                "ator_conta_id": ator,
                "acao": acao,
                "alvo_tipo": alvo_tipo,
                "alvo_id": str(alvo_id),
                "instante": instante or self._now(),
                "justificativa": justificativa,
                "antes": antes,
                "depois": depois,
                "request_id": request_id,
            },
        )

    @staticmethod
    def _conflito_usuario(exc: IntegrityError) -> bool:
        diagnostic = getattr(exc.orig, "diag", None)
        nome_constraint = getattr(diagnostic, "constraint_name", None)
        mensagem = str(exc.orig)
        return nome_constraint == "uq_contas_web_usuario_normalizado" or (
            "contas_web.usuario_normalizado" in mensagem
        )

    def _criar_senha_temporaria(
        self, conta: models.ContaWeb, *, agora: datetime
    ) -> str:
        senha = secrets.token_urlsafe(32)
        conta.senha_hash = self._hasher.hash(senha)
        conta.troca_senha_obrigatoria = True
        conta.credencial_temporaria_expira_em = agora + timedelta(minutes=30)
        conta.credencial_temporaria_usada_em = None
        conta.versao_credencial += 1
        return senha

    @staticmethod
    def _exigir_justificativa(value: str | None) -> str:
        justificativa = (value or "").strip()
        if not justificativa or len(justificativa) > 500:
            raise ValueError("Justificativa obrigatoria, com ate 500 caracteres.")
        return justificativa

    def criar_admin_bootstrap(self, usuario: str, senha: str) -> int:
        usuario_normalizado = normalizar_usuario(usuario)
        validar_senha(senha, usuario_normalizado)
        agora = self._now()
        with self.session_factory() as session, session.begin():
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                session.execute(text("SELECT pg_advisory_xact_lock(731041010)"))
            existente = session.scalar(
                select(models.ContaWeb).where(
                    models.ContaWeb.usuario_normalizado == usuario_normalizado
                )
            )
            if existente is not None and existente.papel == "admin":
                return existente.id
            if (
                session.scalar(
                    select(models.ContaWeb.id)
                    .where(models.ContaWeb.papel == "admin")
                    .limit(1)
                )
                is not None
            ):
                raise BootstrapJaConfigurado(
                    "Ja existe uma conta admin; bootstrap nao altera contas existentes."
                )
            if existente is not None:
                raise ConflitoConta("Usuario ja pertence a outra conta.")
            conta = models.ContaWeb(
                usuario_normalizado=usuario_normalizado,
                senha_hash=self._hasher.hash(senha),
                papel="admin",
                ativa=True,
                troca_senha_obrigatoria=False,
                versao_credencial=1,
            )
            session.add(conta)
            try:
                session.flush()
            except IntegrityError as exc:
                if self._conflito_usuario(exc):
                    raise ConflitoConta("Usuario ja cadastrado.") from exc
                raise
            self._event(
                session,
                ator=None,
                acao="admin_bootstrap_criado",
                alvo_tipo="conta",
                alvo_id=conta.id,
                depois={"papel": "admin", "ativa": True},
                instante=agora,
            )
            return conta.id

    def autenticar(
        self,
        usuario: str,
        senha: str,
        endereco_ip: str | None,
        token_sessao_anterior: str | None = None,
    ) -> ResultadoLogin:
        usuario_normalizado = normalizar_usuario(usuario)
        ip = (endereco_ip or "desconhecido").strip()[:128]
        chaves = (
            self._rate_key("conta", usuario_normalizado),
            self._rate_key("ip", ip),
        )
        agora = self._now()
        resultado: ResultadoLogin | None = None
        credenciais_invalidas = False
        limitado = False
        with self.session_factory() as session, session.begin():
            session.execute(
                delete(models.LimiteLoginWeb).where(
                    models.LimiteLoginWeb.janela_iniciada_em < agora - timedelta(days=1)
                )
            )
            limites = session.scalars(
                select(models.LimiteLoginWeb)
                .where(models.LimiteLoginWeb.chave_hash.in_(chaves))
                .with_for_update()
            ).all()
            limitado = any(
                _agora_utc(limite.janela_iniciada_em) > agora - JANELA_LOGIN
                and limite.bloqueada_ate is not None
                and _agora_utc(limite.bloqueada_ate) > agora
                for limite in limites
            )
            if not limitado:
                conta = session.scalar(
                    select(models.ContaWeb)
                    .where(models.ContaWeb.usuario_normalizado == usuario_normalizado)
                    .options(selectinload(models.ContaWeb.professor))
                    .with_for_update()
                )
                hash_a_verificar = (
                    conta.senha_hash if conta is not None else self._senha_falsa
                )
                senha_valida = self._verificar_hash(hash_a_verificar, senha)
                if conta is not None and conta.troca_senha_obrigatoria:
                    expiracao = conta.credencial_temporaria_expira_em
                    temporaria_valida = (
                        expiracao is not None
                        and conta.credencial_temporaria_usada_em is None
                        and _agora_utc(expiracao) > agora
                    )
                    senha_valida = senha_valida and temporaria_valida
                if conta is None or not conta.ativa or not senha_valida:
                    credenciais_invalidas = True
                    self._registrar_falha(session, chaves, agora)
                else:
                    for chave in chaves:
                        limite = session.get(models.LimiteLoginWeb, chave)
                        if limite is not None:
                            session.delete(limite)
                    if token_sessao_anterior:
                        session.execute(
                            delete(models.SessaoAutenticacaoWeb).where(
                                models.SessaoAutenticacaoWeb.token_hash
                                == self._hash(token_sessao_anterior)
                            )
                        )
                    if conta.troca_senha_obrigatoria:
                        conta.credencial_temporaria_usada_em = agora
                    token_sessao = secrets.token_urlsafe(32)
                    token_csrf = self._csrf_para_sessao(token_sessao)
                    sessao = models.SessaoAutenticacaoWeb(
                        token_hash=self._hash(token_sessao),
                        csrf_hash=self._hash(token_csrf),
                        conta_id=conta.id,
                        versao_credencial=conta.versao_credencial,
                        criada_em=agora,
                        atividade_em=agora,
                        expira_em=agora + TEMPO_ABSOLUTO_SESSAO,
                    )
                    session.add(sessao)
                    session.flush()
                    self._event(
                        session,
                        ator=conta.id,
                        acao="login_sucesso",
                        alvo_tipo="conta",
                        alvo_id=conta.id,
                        depois={"papel": conta.papel},
                        instante=agora,
                    )
                    resultado = ResultadoLogin(
                        conta_id=conta.id,
                        papel=conta.papel,
                        troca_senha_obrigatoria=conta.troca_senha_obrigatoria,
                        token_sessao=token_sessao,
                        token_csrf=token_csrf,
                    )

        if limitado:
            raise LoginLimitado
        if credenciais_invalidas or resultado is None:
            raise CredenciaisInvalidas
        return resultado

    def _registrar_falha(
        self, session: Session, chaves: tuple[str, ...], agora: datetime
    ) -> None:
        bind = session.get_bind()
        dialeto = bind.dialect.name
        tabela: Table = cast(Table, models.LimiteLoginWeb.__table__)
        inserir: Any
        if dialeto == "postgresql":
            inserir = pg_insert(tabela)
        elif dialeto == "sqlite":
            inserir = sqlite_insert(tabela)
        else:
            raise RuntimeError("Dialeto SQL nao suportado para rate limit web.")

        cutoff = agora - JANELA_LOGIN
        bloqueio_ate = agora + TEMPO_BLOQUEIO_LOGIN
        janela_expirada = tabela.c.janela_iniciada_em <= cutoff
        novos_valores = {
            "janela_iniciada_em": case(
                (janela_expirada, agora), else_=tabela.c.janela_iniciada_em
            ),
            "falhas": case((janela_expirada, 1), else_=tabela.c.falhas + 1),
            "bloqueada_ate": case(
                (janela_expirada, None),
                (tabela.c.falhas + 1 >= MAX_FALHAS_LOGIN, bloqueio_ate),
                else_=tabela.c.bloqueada_ate,
            ),
            "tentativa_em": agora,
        }
        comando = inserir.values(
            [
                {
                    "chave_hash": chave,
                    "janela_iniciada_em": agora,
                    "falhas": 1,
                    "bloqueada_ate": None,
                    "tentativa_em": agora,
                }
                for chave in chaves
            ]
        )
        session.execute(
            comando.on_conflict_do_update(
                index_elements=[tabela.c.chave_hash], set_=novos_valores
            )
        )

    def autenticar_sessao(self, token: str | None) -> ContaAutenticada | None:
        if not token:
            return None
        agora = self._now()
        with self.session_factory() as session, session.begin():
            resultado = session.execute(
                select(models.SessaoAutenticacaoWeb, models.ContaWeb)
                .join(
                    models.ContaWeb,
                    models.ContaWeb.id == models.SessaoAutenticacaoWeb.conta_id,
                )
                .where(models.SessaoAutenticacaoWeb.token_hash == self._hash(token))
                .with_for_update()
            ).first()
            if resultado is None:
                return None
            sessao, conta = resultado
            inativa = _agora_utc(sessao.atividade_em) + TEMPO_INATIVIDADE <= agora
            absoluta = _agora_utc(sessao.expira_em) <= agora
            credencial_alterada = sessao.versao_credencial != conta.versao_credencial
            if not conta.ativa or inativa or absoluta or credencial_alterada:
                session.delete(sessao)
                return None
            sessao.atividade_em = agora
            professor_id = session.scalar(
                select(models.ProfessorWeb.id).where(
                    models.ProfessorWeb.conta_id == conta.id
                )
            )
            return ContaAutenticada(
                id=conta.id,
                usuario=conta.usuario_normalizado,
                papel=conta.papel,
                ativa=conta.ativa,
                troca_senha_obrigatoria=conta.troca_senha_obrigatoria,
                professor_id=professor_id,
                sessao_id=sessao.id,
                csrf_hash=sessao.csrf_hash,
                csrf_token=self._csrf_para_sessao(token),
            )

    def validar_csrf(self, conta: ContaAutenticada, token: str | None) -> bool:
        if not token:
            return False
        return hmac.compare_digest(conta.csrf_hash, self._hash(token))

    def encerrar_sessao(self, conta: ContaAutenticada) -> None:
        with self.session_factory() as session, session.begin():
            sessao = session.get(models.SessaoAutenticacaoWeb, conta.sessao_id)
            if sessao is not None and sessao.conta_id == conta.id:
                session.delete(sessao)
                self._event(
                    session,
                    ator=conta.id,
                    acao="logout",
                    alvo_tipo="sessao",
                    alvo_id=conta.sessao_id,
                )

    def trocar_senha(
        self,
        conta_contexto: ContaAutenticada,
        nova_senha: str,
        senha_atual: str | None,
        *,
        request_id: str | None = None,
    ) -> None:
        agora = self._now()
        with self.session_factory() as session, session.begin():
            conta = session.get(
                models.ContaWeb, conta_contexto.id, with_for_update=True
            )
            sessao = session.get(
                models.SessaoAutenticacaoWeb,
                conta_contexto.sessao_id,
                with_for_update=True,
            )
            if (
                conta is None
                or sessao is None
                or not conta.ativa
                or sessao.versao_credencial != conta.versao_credencial
            ):
                raise OperacaoNaoAutorizada
            if not conta.troca_senha_obrigatoria and (
                senha_atual is None
                or not self._verificar_hash(conta.senha_hash, senha_atual)
            ):
                raise CredenciaisInvalidas
            validar_senha(nova_senha, conta.usuario_normalizado)
            antes = {
                "versao_credencial": conta.versao_credencial,
                "troca_senha_obrigatoria": conta.troca_senha_obrigatoria,
            }
            conta.senha_hash = self._hasher.hash(nova_senha)
            conta.troca_senha_obrigatoria = False
            conta.versao_credencial += 1
            conta.credencial_temporaria_expira_em = None
            conta.credencial_temporaria_usada_em = None
            session.execute(
                delete(models.SessaoAutenticacaoWeb).where(
                    models.SessaoAutenticacaoWeb.conta_id == conta.id
                )
            )
            self._event(
                session,
                ator=conta.id,
                acao="senha_alterada",
                alvo_tipo="conta",
                alvo_id=conta.id,
                antes=antes,
                depois={
                    "versao_credencial": conta.versao_credencial,
                    "troca_senha_obrigatoria": False,
                },
                request_id=request_id,
                instante=agora,
            )

    def criar_conta(
        self,
        ator_id: int,
        usuario: str,
        papel: str,
        justificativa: str,
        *,
        request_id: str | None = None,
    ) -> tuple[int, str, datetime]:
        usuario_normalizado = normalizar_usuario(usuario)
        justificativa_validada = self._exigir_justificativa(justificativa)
        if papel not in {"professor", "admin"}:
            raise ValueError("Papel invalido.")
        agora = self._now()
        senha_temporaria = secrets.token_urlsafe(32)
        with self.session_factory() as session, session.begin():
            ator = self._exigir_admin(session, ator_id)
            if (
                session.scalar(
                    select(models.ContaWeb.id).where(
                        models.ContaWeb.usuario_normalizado == usuario_normalizado
                    )
                )
                is not None
            ):
                raise ConflitoConta
            conta = models.ContaWeb(
                usuario_normalizado=usuario_normalizado,
                senha_hash=self._hasher.hash(senha_temporaria),
                papel=papel,
                ativa=True,
                troca_senha_obrigatoria=True,
                versao_credencial=1,
                credencial_temporaria_expira_em=agora + timedelta(minutes=30),
            )
            session.add(conta)
            try:
                session.flush()
            except IntegrityError as exc:
                if self._conflito_usuario(exc):
                    raise ConflitoConta("Usuario ja cadastrado.") from exc
                raise
            if papel == "professor":
                session.add(models.ProfessorWeb(conta_id=conta.id))
                session.flush()
            expiracao = conta.credencial_temporaria_expira_em
            assert expiracao is not None
            self._event(
                session,
                ator=ator.id,
                acao="conta_criada",
                alvo_tipo="conta",
                alvo_id=conta.id,
                justificativa=justificativa_validada,
                depois={"papel": papel, "ativa": True, "troca_senha_obrigatoria": True},
                request_id=request_id,
                instante=agora,
            )
            return conta.id, senha_temporaria, expiracao

    def redefinir_senha(
        self,
        ator_id: int,
        conta_id: int,
        justificativa: str,
        referencia_verificacao: str,
        *,
        request_id: str | None = None,
    ) -> tuple[str, datetime]:
        justificativa_validada = self._exigir_justificativa(justificativa)
        referencia = referencia_verificacao.strip()
        if not referencia or len(referencia) > 160:
            raise ValueError("Referencia de verificacao independente obrigatoria.")
        agora = self._now()
        with self.session_factory() as session, session.begin():
            ator = self._exigir_admin(session, ator_id)
            conta = session.get(models.ContaWeb, conta_id, with_for_update=True)
            if conta is None or not conta.ativa or conta.id == ator.id:
                raise OperacaoNaoAutorizada
            antes = {
                "versao_credencial": conta.versao_credencial,
                "ativa": conta.ativa,
            }
            temporaria = self._criar_senha_temporaria(conta, agora=agora)
            expiracao = conta.credencial_temporaria_expira_em
            assert expiracao is not None
            session.execute(
                delete(models.SessaoAutenticacaoWeb).where(
                    models.SessaoAutenticacaoWeb.conta_id == conta.id
                )
            )
            self._event(
                session,
                ator=ator.id,
                acao="senha_redefinida",
                alvo_tipo="conta",
                alvo_id=conta.id,
                justificativa=justificativa_validada,
                antes=antes,
                depois={
                    "versao_credencial": conta.versao_credencial,
                    "troca_senha_obrigatoria": True,
                    "credencial_temporaria_expira_em": expiracao.isoformat(),
                    "referencia_verificacao": referencia,
                },
                request_id=request_id,
                instante=agora,
            )
            return temporaria, expiracao

    def desativar_conta(
        self,
        ator_id: int,
        conta_id: int,
        justificativa: str,
        *,
        request_id: str | None = None,
    ) -> None:
        justificativa_validada = self._exigir_justificativa(justificativa)
        agora = self._now()
        with self.session_factory() as session, session.begin():
            administradores = session.scalars(
                select(models.ContaWeb)
                .where(models.ContaWeb.papel == "admin")
                .order_by(models.ContaWeb.id)
                .with_for_update()
            ).all()
            ator = session.get(models.ContaWeb, ator_id, with_for_update=True)
            if (
                ator is None
                or not ator.ativa
                or ator.papel != "admin"
                or ator.troca_senha_obrigatoria
            ):
                raise OperacaoNaoAutorizada
            conta = session.get(models.ContaWeb, conta_id, with_for_update=True)
            if conta is None or not conta.ativa or conta.id == ator.id:
                raise OperacaoNaoAutorizada
            if conta.papel == "admin":
                quantidade_admins_ativos = sum(
                    1 for administrador in administradores if administrador.ativa
                )
                if quantidade_admins_ativos <= 1:
                    raise OperacaoNaoAutorizada
            antes = {"ativa": conta.ativa, "versao_credencial": conta.versao_credencial}
            conta.ativa = False
            conta.versao_credencial += 1
            session.execute(
                delete(models.SessaoAutenticacaoWeb).where(
                    models.SessaoAutenticacaoWeb.conta_id == conta.id
                )
            )
            self._event(
                session,
                ator=ator.id,
                acao="conta_desativada",
                alvo_tipo="conta",
                alvo_id=conta.id,
                justificativa=justificativa_validada,
                antes=antes,
                depois={"ativa": False, "versao_credencial": conta.versao_credencial},
                request_id=request_id,
                instante=agora,
            )

    def transferir_turma(
        self,
        ator_id: int,
        turma_id: int,
        professor_id: int,
        justificativa: str,
        *,
        request_id: str | None = None,
    ) -> None:
        justificativa_validada = self._exigir_justificativa(justificativa)
        agora = self._now()
        with self.session_factory() as session, session.begin():
            ator = self._exigir_admin(session, ator_id)
            turma = session.get(models.Turma, turma_id, with_for_update=True)
            professor = session.scalar(
                select(models.ProfessorWeb)
                .join(models.ContaWeb)
                .where(
                    models.ProfessorWeb.id == professor_id,
                    models.ContaWeb.ativa.is_(True),
                )
            )
            if turma is None or professor is None:
                raise OperacaoNaoAutorizada
            antes = {"responsavel_professor_id": turma.responsavel_professor_id}
            turma.responsavel_professor_id = professor.id
            self._event(
                session,
                ator=ator.id,
                acao="responsavel_turma_transferido",
                alvo_tipo="turma",
                alvo_id=turma.id,
                justificativa=justificativa_validada,
                antes=antes,
                depois={"responsavel_professor_id": professor.id},
                request_id=request_id,
                instante=agora,
            )

    def autorizar_turma(self, turma_id: int) -> TurmaWeb | None:
        with self.session_factory() as session:
            turma = session.get(models.Turma, turma_id)
            if turma is None:
                return None
            return TurmaWeb(
                id=turma.id,
                materia=turma.materia,
                periodo=turma.periodo,
                responsavel_professor_id=turma.responsavel_professor_id,
            )

    def _exigir_admin(self, session: Session, conta_id: int) -> models.ContaWeb:
        ator = session.get(models.ContaWeb, conta_id, with_for_update=True)
        if (
            ator is None
            or not ator.ativa
            or ator.papel != "admin"
            or ator.troca_senha_obrigatoria
        ):
            raise OperacaoNaoAutorizada
        return ator


def normalizar_usuario(usuario: str) -> str:
    normalizado = unicodedata.normalize("NFKC", usuario).strip().casefold()
    if (
        not normalizado
        or len(normalizado) > 80
        or any(
            ord(caractere) < 32 or ord(caractere) == 127 for caractere in normalizado
        )
    ):
        raise ValueError("Usuario invalido.")
    return normalizado


def validar_senha(senha: str, usuario: str | None = None) -> None:
    if len(senha) < 12 or len(senha) > 256 or len(senha.encode("utf-8")) > 1024:
        raise PoliticaSenhaInvalida("A senha deve ter entre 12 e 256 caracteres.")
    if usuario is not None and senha.casefold() == usuario.casefold():
        raise PoliticaSenhaInvalida("A senha nao pode ser igual ao usuario.")
