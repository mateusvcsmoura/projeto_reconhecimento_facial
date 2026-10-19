from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.application.use_cases.gerenciar_links import GerenciarLinks
from src.application.use_cases.solicitar_cadastro_web import (
    ConsentimentoWeb,
    ContextoConvite,
    DadosCadastroWeb,
    SolicitarCadastroWeb,
)
from src.domain.services.autorizacao import AtorWeb
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_link_repository import (
    PostgresLinkRepository,
)
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    PostgresSolicitacaoRepository,
)

AGORA = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)
SEGREDO = "sintetico-sem-uso-em-producao"
ATOR = AtorWeb(1, "professor", True, False, 1)


@pytest.fixture
def db() -> Any:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def sqlite_btrim(connection: Any, _record: Any) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip())

    models.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session, session.begin():
        session.add(
            models.ContaWeb(
                id=1,
                usuario_normalizado="professor",
                senha_hash="nao-usado-em-login",
                papel="professor",
                ativa=True,
                troca_senha_obrigatoria=False,
                versao_credencial=1,
                criado_em=AGORA,
            )
        )
        session.add(models.ProfessorWeb(id=1, conta_id=1, criado_em=AGORA))
        session.add(
            models.Turma(
                id=14,
                materia="Inteligência Artificial",
                periodo="noturno",
                responsavel_professor_id=1,
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()


def _novo_link(repository: PostgresLinkRepository) -> tuple[str, UUID]:
    fim = AGORA + timedelta(days=12)
    link = GerenciarLinks(repository, relogio=lambda: AGORA).criar(
        ATOR, 14, finalidade_ate=fim
    )
    return link.token, link.id


def _criar_solicitacao(
    engine: Any, link_repository: PostgresLinkRepository, token: str
) -> tuple[int, str]:
    acesso = GerenciarLinks(link_repository, relogio=lambda: AGORA).trocar(token)
    assert acesso is not None
    hash_acesso = hashlib.sha256(acesso.credencial.encode()).hexdigest()
    contexto = ContextoConvite(
        referencia=str(acesso.link_id),
        turma_id=acesso.turma_id,
        expira_em=AGORA + timedelta(days=7),
        finalidade_ate=AGORA + timedelta(days=12),
    )
    solicitacao = SolicitarCadastroWeb(
        PostgresSolicitacaoRepository(engine), relogio=lambda: AGORA
    ).criar(
        DadosCadastroWeb("000123", "Pessoa Sintética"),
        contexto,
        ConsentimentoWeb(True, "aviso-v1"),
        credencial_acesso_hash=hash_acesso,
    )
    return solicitacao.id, acesso.credencial


def test_link_persiste_somente_hash_e_credencial_vincula_uma_solicitacao(
    db: Any,
) -> None:
    links = PostgresLinkRepository(db)
    token, link_id = _novo_link(links)
    solicitacao_id, acesso = _criar_solicitacao(db, links, token)
    hash_link = hashlib.sha256(token.encode()).hexdigest()
    hash_acesso = hashlib.sha256(acesso.encode()).hexdigest()

    with Session(db) as session:
        link = session.get(models.LinkCadastroWeb, link_id)
        credencial = session.get(models.CredencialLinkCadastroWeb, hash_acesso)
        solicitacao = session.get(models.SolicitacaoCadastroWeb, solicitacao_id)
        assert link is not None and link.token_hash == hash_link
        assert link.token_hash != token
        assert credencial is not None and credencial.solicitacao_id == solicitacao_id
        assert credencial.token_hash != acesso
        assert solicitacao is not None and solicitacao.link_id == link_id
        assert solicitacao.estado == "em_coleta"
        assert solicitacao.expira_em.replace(tzinfo=UTC) == AGORA + timedelta(days=7)

    contexto = links.contexto_credencial(
        hash_acesso,
        agora=AGORA,
        solicitacao_id=solicitacao_id,
        exigir_link_ativo=True,
    )
    assert contexto is not None
    assert contexto["finalidade"] == "cadastro"


def test_link_expirado_nao_troca_token_mas_credencial_da_solicitacao_permanece(
    db: Any,
) -> None:
    links = PostgresLinkRepository(db)
    token, link_id = _novo_link(links)
    solicitacao_id, acesso = _criar_solicitacao(db, links, token)
    hash_acesso = hashlib.sha256(acesso.encode()).hexdigest()
    expiracao_link = AGORA + timedelta(days=7)
    expiracao_solicitacao = AGORA + timedelta(days=10)
    with Session(db) as session, session.begin():
        link = session.get(models.LinkCadastroWeb, link_id)
        assert link is not None
        link.expira_em = expiracao_link
        credencial = session.get(models.CredencialLinkCadastroWeb, hash_acesso)
        solicitacao = session.get(models.SolicitacaoCadastroWeb, solicitacao_id)
        assert credencial is not None and solicitacao is not None
        credencial.expira_em = expiracao_solicitacao
        solicitacao.expira_em = expiracao_solicitacao

    assert (
        GerenciarLinks(
            links, relogio=lambda: expiracao_link + timedelta(seconds=1)
        ).trocar(token)
        is None
    )
    contexto = links.contexto_credencial(
        hash_acesso,
        agora=expiracao_link + timedelta(seconds=1),
        solicitacao_id=solicitacao_id,
        exigir_link_ativo=False,
    )
    assert contexto is not None
    assert (
        links.contexto_credencial(
            hash_acesso,
            agora=expiracao_link + timedelta(seconds=1),
            solicitacao_id=solicitacao_id,
            exigir_link_ativo=True,
        )
        is None
    )


def test_revogacao_cancela_solicitacao_e_job_enfileirado(db: Any) -> None:
    links = PostgresLinkRepository(db)
    token, link_id = _novo_link(links)
    solicitacao_id, _acesso = _criar_solicitacao(db, links, token)
    job_id = uuid4()
    with Session(db) as session, session.begin():
        session.add(
            models.JobFacialWeb(
                id=job_id,
                dono_id=str(solicitacao_id),
                tipo="cadastro",
                estado="enfileirada",
                idempotencia_hash="1" * 64,
                credencial_hash="2" * 64,
                manifesto={"capturas": []},
                bytes_reservados=24,
                prazo_reserva=AGORA + timedelta(minutes=5),
                prazo_execucao=AGORA + timedelta(minutes=15),
                criada_em=AGORA,
                atualizada_em=AGORA,
                enfileirada_em=AGORA,
                iniciada_em=None,
                finalizada_em=None,
                lease_hash=None,
                lease_expira_em=None,
                cancelamento_solicitado=False,
                resultado_codigo=None,
            )
        )
        solicitacao = session.get(models.SolicitacaoCadastroWeb, solicitacao_id)
        assert solicitacao is not None
        solicitacao.estado = "em_validacao"
        solicitacao.job_id = job_id

    assert links.revogar(ATOR, link_id, agora=AGORA) == (1, (solicitacao_id,))
    with Session(db) as session:
        solicitacao = session.get(models.SolicitacaoCadastroWeb, solicitacao_id)
        job = session.get(models.JobFacialWeb, job_id)
        assert solicitacao is not None and solicitacao.estado == "cancelada"
        assert job is not None and job.estado == "cancelada"
        assert job.manifesto is None
        auditorias = session.scalars(
            select(models.EventoAuditoriaWeb).where(
                models.EventoAuditoriaWeb.acao == "link_cadastro_web_revogado"
            )
        ).all()
        assert len(auditorias) == 1


def test_professor_de_outra_turma_nao_emite_ou_revoga_link(db: Any) -> None:
    links = PostgresLinkRepository(db)
    token, link_id = _novo_link(links)
    estranho = AtorWeb(9, "professor", True, False, 99)

    with pytest.raises(PermissionError):
        links.criar_link(
            ator=estranho,
            turma_id=14,
            finalidade="cadastro",
            token_hash="3" * 64,
            criado_em=AGORA,
            expira_em=AGORA + timedelta(days=1),
            finalidade_ate=AGORA + timedelta(days=8),
        )
    with pytest.raises(PermissionError):
        links.revogar(estranho, link_id, agora=AGORA)
    assert GerenciarLinks(links, relogio=lambda: AGORA).trocar(token) is not None


def test_consentimento_atualizacao_persiste_hash_e_emite_desafio_uma_vez(
    db: Any,
) -> None:
    with Session(db) as session, session.begin():
        session.add(
            models.Aluno(
                id=29,
                matricula="aluno-29",
                nome="Pessoa Sintética",
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )
        session.add(
            models.AlunoTurma(
                turma_id=14,
                aluno_id=29,
                ativo=True,
                vinculado_em=AGORA,
                desvinculado_em=None,
            )
        )
    repository = PostgresSolicitacaoRepository(db)
    hash_credencial = "a" * 64
    solicitacao = repository.solicitar_atualizacao_biometrica(
        ATOR,
        29,
        14,
        expira_em=AGORA + timedelta(days=7),
        agora=AGORA,
        credencial_captura_hash=hash_credencial,
    )
    nonce_hash = hashlib.sha256(b"nonce-atualizacao").hexdigest()
    challenge_expiry = AGORA + timedelta(seconds=120)

    registrada = repository.registrar_consentimento_atualizacao(
        solicitacao.id,
        hash_credencial,
        "aviso-v1",
        agora=AGORA + timedelta(seconds=1),
        desafio_nonce_hash=nonce_hash,
        desafio_direcao="esquerda",
        desafio_expira_em=challenge_expiry,
    )

    assert registrada.consentimento_versao == "aviso-v1"
    assert registrada.desafio_nonce_hash == nonce_hash
    assert registrada.desafio_direcao == "esquerda"
    assert registrada.desafio_expira_em == challenge_expiry
    with Session(db) as session:
        row = session.get(models.SolicitacaoCadastroWeb, solicitacao.id)
        assert row is not None and row.desafio_nonce_hash == nonce_hash
    with pytest.raises(ValueError, match="consentimento já foi registrado"):
        repository.registrar_consentimento_atualizacao(
            solicitacao.id,
            hash_credencial,
            "aviso-v1",
            agora=AGORA + timedelta(seconds=2),
            desafio_nonce_hash="b" * 64,
            desafio_direcao="direita",
            desafio_expira_em=challenge_expiry,
        )
