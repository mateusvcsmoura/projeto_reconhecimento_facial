"""Transações de cadastro web com SQLite e identidades sintéticas."""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.application.use_cases.anexar_referencias_web import (
    AnexarReferencias,
    ContextoJobReferencias,
)
from src.application.use_cases.aprovar_atualizacao_biometrica import (
    AprovarAtualizacaoBiometrica,
)
from src.application.use_cases.aprovar_cadastro_web import AprovarCadastroWeb
from src.application.use_cases.limpar_referencias_provisorias import (
    LimparReferenciasProvisorias,
)
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
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.referencia_facial import PreparacaoReferencia
from src.domain.services.autorizacao import AcessoTurmaNegado, AtorWeb
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    PostgresSolicitacaoRepository,
)
from src.infrastructure.storage.private_reference_storage import (
    PrivateReferenceStorageLocal,
)

UTC = ZoneInfo("UTC")
AGORA = dt.datetime(2026, 10, 18, 12, tzinfo=UTC)


@pytest.fixture
def engine():
    banco = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(banco, "connect")
    def registrar_btrim(conexao, _registro):
        conexao.create_function(
            "btrim", 1, lambda valor: valor.strip() if valor else valor
        )
        conexao.execute("PRAGMA foreign_keys = ON")

    models.Base.metadata.create_all(banco)
    with Session(banco) as session:
        admin = models.ContaWeb(
            id=1,
            usuario_normalizado="admin",
            senha_hash="hash-sintetico",
            papel="admin",
            ativa=True,
            troca_senha_obrigatoria=False,
        )
        professor_a = models.ContaWeb(
            id=2,
            usuario_normalizado="professor-a",
            senha_hash="hash-sintetico",
            papel="professor",
            ativa=True,
            troca_senha_obrigatoria=False,
        )
        professor_b = models.ContaWeb(
            id=3,
            usuario_normalizado="professor-b",
            senha_hash="hash-sintetico",
            papel="professor",
            ativa=True,
            troca_senha_obrigatoria=False,
        )
        session.add_all((admin, professor_a, professor_b))
        session.flush()
        session.add_all(
            (
                models.ProfessorWeb(id=10, conta_id=2),
                models.ProfessorWeb(id=11, conta_id=3),
                models.Turma(
                    id=20,
                    materia="IA",
                    periodo="diurno",
                    responsavel_professor_id=10,
                ),
                models.Turma(
                    id=21,
                    materia="Visão",
                    periodo="noturno",
                    responsavel_professor_id=11,
                ),
                models.Aluno(
                    id=30,
                    matricula="000-existing",
                    nome="Cadastro Legado",
                    foto_arquivo="antiga.jpg",
                    embedding=FaceEmbedding.de_valores(
                        np.arange(1, 513), "FaceNet512"
                    ).para_bytes(),
                    embedding_modelo="FaceNet512",
                    embedding_dim=512,
                    consentimento_em=AGORA - dt.timedelta(days=10),
                ),
            )
        )
        session.commit()
    yield banco
    models.Base.metadata.drop_all(banco)
    banco.dispose()


def _preparacoes(prefixo: str = "novo") -> tuple[PreparacaoReferencia, ...]:
    return tuple(
        PreparacaoReferencia(
            ordinal=ordinal,
            captura_id=f"{prefixo}-{ordinal}",
            recorte=f"recorte-sintetico-{prefixo}-{ordinal}".encode(),
            embedding=FaceEmbedding.de_valores(
                np.arange(1, 513, dtype=np.float32) + ordinal,
                "FaceNet512",
            ),
        )
        for ordinal in (1, 2, 3)
    )


def _criar_solicitacao(repo, matricula: str, nome: str):
    caso = SolicitarCadastroWeb(repo, relogio=lambda: AGORA)
    return caso.criar(
        DadosCadastroWeb(matricula=matricula, nome=nome),
        ContextoConvite(
            referencia=f"convite-opaco-{uuid.uuid4()}",
            turma_id=20,
            expira_em=AGORA + dt.timedelta(days=4),
        ),
        ConsentimentoWeb(aceito=True, versao="termos-sinteticos-v1"),
    )


def _anexar(
    repo,
    storage,
    solicitacao_id: int,
    prefixo: str,
    *,
    job_id: uuid.UUID | None = None,
) -> None:
    AnexarReferencias(repo, storage, relogio=lambda: AGORA).executar(
        solicitacao_id,
        _preparacoes(prefixo),
        ContextoJobReferencias(
            job_id=job_id or uuid.uuid4(),
            consentimento_em=AGORA,
            consentimento_versao="termos-sinteticos-v1",
        ),
    )


def _preparar_atualizacao_para_coleta(
    engine, repo, aluno_id: int
) -> tuple[int, uuid.UUID]:
    credencial_hash = "a" * 64
    atualizacao = SolicitarAtualizacaoBiometrica(repo, relogio=lambda: AGORA).executar(
        AtorWeb(2, "professor", True, False, 10),
        aluno_id,
        20,
        expira_em=AGORA + dt.timedelta(days=3),
        credencial_captura_hash=credencial_hash,
    )
    repo.registrar_consentimento_atualizacao(
        atualizacao.id,
        credencial_hash,
        "termos-sinteticos-v1",
        agora=AGORA,
        desafio_nonce_hash="b" * 64,
        desafio_direcao="esquerda",
        desafio_expira_em=AGORA + dt.timedelta(minutes=2),
    )
    job_id = uuid.uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            models.JobFacialWeb(
                id=job_id,
                dono_id=str(atualizacao.id),
                tipo="cadastro",
                estado="recebida",
                idempotencia_hash="c" * 64,
                credencial_hash=credencial_hash,
                manifesto=None,
                bytes_reservados=1,
                prazo_reserva=AGORA + dt.timedelta(minutes=5),
                prazo_execucao=AGORA + dt.timedelta(minutes=15),
                criada_em=AGORA,
                atualizada_em=AGORA,
            )
        )
    repo.associar_job_cadastro(atualizacao.id, job_id, credencial_hash, agora=AGORA)
    return atualizacao.id, job_id


def test_aprovar_matricula_existente_preserva_aluno_e_descarta_trinca(
    engine, tmp_path: Path
) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")
    solicitacao = _criar_solicitacao(repo, "000-existing", "Nome Tentativa")
    _anexar(repo, storage, solicitacao.id, "existente")

    resultado = AprovarCadastroWeb(repo, storage, relogio=lambda: AGORA).executar(
        AtorWeb(1, "admin", True, False, None),
        solicitacao.id,
        "documento_presencial",
        "Conferência independente de identidade",
    )

    assert resultado.aluno_existente is True
    assert resultado.limpeza_pendente is False
    with Session(engine) as session:
        aluno = session.get(models.Aluno, 30)
        vinculo = session.get(models.AlunoTurma, (20, 30))
        conjunto = session.scalar(
            select(models.ConjuntoReferenciasWeb).where(
                models.ConjuntoReferenciasWeb.solicitacao_id == solicitacao.id
            )
        )
        referencias = session.scalars(
            select(models.ReferenciaFacialWeb).where(
                models.ReferenciaFacialWeb.conjunto_id == conjunto.id
            )
        ).all()
    assert aluno.nome == "Cadastro Legado"
    assert aluno.foto_arquivo == "antiga.jpg"
    assert aluno.embedding_modelo == "FaceNet512"
    assert vinculo is not None and vinculo.ativo
    assert conjunto.estado == "descartado"
    assert referencias == []
    assert repo.obter_referencias_ativas((30,)) == ()


def test_aprovacao_de_novo_aluno_ativa_tres_referencias_sem_foto_legacy(
    engine, tmp_path: Path
) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")
    solicitacao = _criar_solicitacao(repo, "000-new", "Pessoa Nova")
    _anexar(repo, storage, solicitacao.id, "novo")

    resultado = AprovarCadastroWeb(repo, storage, relogio=lambda: AGORA).executar(
        AtorWeb(1, "admin", True, False, None),
        solicitacao.id,
        "codigo_institucional",
        "Conferência independente realizada",
    )

    referencias = repo.obter_referencias_ativas((resultado.aluno_id,))
    assert resultado.aluno_existente is False
    assert len(referencias) == 3
    assert {item.versao for item in referencias} == {1}
    with Session(engine) as session:
        aluno = session.get(models.Aluno, resultado.aluno_id)
    assert aluno.foto_arquivo is None
    assert aluno.embedding is None
    assert aluno.consentimento_em.replace(tzinfo=UTC) == AGORA


def test_lista_de_cadastros_traz_data_da_solicitacao_e_do_link(engine) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    solicitacao = _criar_solicitacao(repo, "000-lista", "Pessoa Lista")
    link_id = uuid.uuid4()
    link_criado_em = AGORA - dt.timedelta(hours=3)
    with Session(engine) as session, session.begin():
        session.add(
            models.LinkCadastroWeb(
                id=link_id,
                turma_id=20,
                emitido_por_conta_id=2,
                token_hash="f" * 64,
                finalidade="cadastro",
                criado_em=link_criado_em,
                expira_em=AGORA + dt.timedelta(days=7),
                finalidade_ate=AGORA + dt.timedelta(days=10),
            )
        )
        session.flush()
        linha = session.get(models.SolicitacaoCadastroWeb, solicitacao.id)
        linha.link_id = link_id
        linha.estado = "pendente_aprovacao"

    itens = repo.listar_cadastros_turma(
        AtorWeb(2, "professor", True, False, 10), 20, estado="pendente_aprovacao"
    )

    assert [item.id for item in itens] == [solicitacao.id]
    assert itens[0].criada_em == AGORA
    assert itens[0].link_criado_em == link_criado_em


def test_renovar_desafio_substitui_nonce_somente_durante_a_coleta(engine) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    solicitacao = _criar_solicitacao(repo, "000-desafio", "Pessoa Desafio")
    prazo = AGORA + dt.timedelta(minutes=2)

    renovada = repo.renovar_desafio_coleta(
        solicitacao.id,
        agora=AGORA,
        desafio_nonce_hash="d" * 64,
        desafio_direcao="direita",
        desafio_expira_em=prazo,
    )
    with Session(engine) as session, session.begin():
        session.get(
            models.SolicitacaoCadastroWeb, solicitacao.id
        ).estado = "em_validacao"

    assert renovada.desafio_nonce_hash == "d" * 64
    assert renovada.desafio_direcao == "direita"
    assert renovada.desafio_expira_em == prazo
    with pytest.raises(ValueError):
        repo.renovar_desafio_coleta(
            solicitacao.id,
            agora=AGORA,
            desafio_nonce_hash="e" * 64,
            desafio_direcao="esquerda",
            desafio_expira_em=prazo,
        )
    with pytest.raises(PermissionError):
        repo.renovar_desafio_coleta(
            999,
            agora=AGORA,
            desafio_nonce_hash="e" * 64,
            desafio_direcao="esquerda",
            desafio_expira_em=prazo,
        )


def test_professor_de_outra_turma_nao_aprova_solicitacao(
    engine, tmp_path: Path
) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")
    solicitacao = _criar_solicitacao(repo, "000-private", "Pessoa")
    _anexar(repo, storage, solicitacao.id, "privado")

    with pytest.raises(AcessoTurmaNegado):
        AprovarCadastroWeb(repo, storage, relogio=lambda: AGORA).executar(
            AtorWeb(3, "professor", True, False, 11),
            solicitacao.id,
            "documento_presencial",
            "Conferência independente realizada",
        )


def test_rejeicao_descarta_e_limpa_referencias_temporarias(
    engine, tmp_path: Path
) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")
    solicitacao = _criar_solicitacao(repo, "000-rejected", "Pessoa")
    _anexar(repo, storage, solicitacao.id, "rejeitada")

    resultado = RejeitarCadastroWeb(repo, storage, relogio=lambda: AGORA).executar(
        AtorWeb(2, "professor", True, False, 10),
        solicitacao.id,
        justificativa="Identidade não confirmada pelo canal institucional",
    )

    assert resultado.estado == "rejeitada"
    assert resultado.limpeza_pendente is False
    with Session(engine) as session:
        linha = session.get(models.SolicitacaoCadastroWeb, solicitacao.id)
        conjunto = session.scalar(
            select(models.ConjuntoReferenciasWeb).where(
                models.ConjuntoReferenciasWeb.solicitacao_id == solicitacao.id
            )
        )
        total = session.scalar(
            select(func.count(models.ReferenciaFacialWeb.id)).where(
                models.ReferenciaFacialWeb.conjunto_id == conjunto.id
            )
        )
    assert linha.estado == "rejeitada"
    assert conjunto.estado == "descartado"
    assert total == 0


def test_limpeza_expira_pendencia_e_registra_estado(engine, tmp_path: Path) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")
    solicitacao = _criar_solicitacao(repo, "000-expired", "Pessoa")
    _anexar(repo, storage, solicitacao.id, "expirada")
    instante_limpeza = AGORA + dt.timedelta(days=8)

    resultado = LimparReferenciasProvisorias(
        repo, storage, relogio=lambda: instante_limpeza
    ).executar()

    assert resultado == (1, ())
    with Session(engine) as session:
        linha = session.get(models.SolicitacaoCadastroWeb, solicitacao.id)
        conjunto = session.scalar(
            select(models.ConjuntoReferenciasWeb).where(
                models.ConjuntoReferenciasWeb.solicitacao_id == solicitacao.id
            )
        )
        total = session.scalar(
            select(func.count(models.ReferenciaFacialWeb.id)).where(
                models.ReferenciaFacialWeb.conjunto_id == conjunto.id
            )
        )
        expiracao_auditada = session.scalar(
            select(func.count(models.EventoAuditoriaWeb.id)).where(
                models.EventoAuditoriaWeb.acao == "solicitacao_cadastro_web_expirada"
            )
        )
    assert linha.estado == "expirada"
    assert linha.limpa_em.replace(tzinfo=UTC) == instante_limpeza
    assert conjunto.estado == "descartado"
    assert total == 0
    assert expiracao_auditada == 1


def test_atualizacao_substitui_conjunto_atomicamente_sem_replicar_antigo(
    engine, tmp_path: Path
) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")
    cadastro = _criar_solicitacao(repo, "000-versioned", "Pessoa Versionada")
    _anexar(repo, storage, cadastro.id, "versao-1")
    aprovado = AprovarCadastroWeb(repo, storage, relogio=lambda: AGORA).executar(
        AtorWeb(1, "admin", True, False, None),
        cadastro.id,
        "documento_presencial",
        "Identidade confirmada em conferência",
    )
    solicitacao_update_id, job_id = _preparar_atualizacao_para_coleta(
        engine, repo, aprovado.aluno_id
    )
    _anexar(repo, storage, solicitacao_update_id, "versao-2", job_id=job_id)
    nova_versao = AprovarAtualizacaoBiometrica(
        repo, storage, relogio=lambda: AGORA + dt.timedelta(minutes=1)
    ).executar(
        AtorWeb(1, "admin", True, False, None),
        solicitacao_update_id,
        justificativa="Substituição aprovada por administrador",
    )

    ativas = repo.obter_referencias_ativas((aprovado.aluno_id,))
    assert nova_versao == 2
    assert len(ativas) == 3
    assert {item.versao for item in ativas} == {2}
    with Session(engine) as session:
        estados = session.scalars(
            select(models.ConjuntoReferenciasWeb.estado).where(
                models.ConjuntoReferenciasWeb.aluno_id == aprovado.aluno_id
            )
        ).all()
        total_referencias = session.scalar(
            select(func.count(models.ReferenciaFacialWeb.id))
        )
    assert sorted(estados) == ["ativo", "substituido"]
    assert total_referencias == 6


def test_falha_sql_na_troca_compensa_somente_candidato_e_preserva_ativa(
    engine, tmp_path: Path
) -> None:
    repo = PostgresSolicitacaoRepository(engine)
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")
    cadastro = _criar_solicitacao(repo, "000-sql-failure", "Pessoa")
    _anexar(repo, storage, cadastro.id, "ativa")
    aprovado = AprovarCadastroWeb(repo, storage, relogio=lambda: AGORA).executar(
        AtorWeb(1, "admin", True, False, None),
        cadastro.id,
        "documento_presencial",
        "Identidade confirmada em conferência",
    )
    update_id, job_id = _preparar_atualizacao_para_coleta(
        engine, repo, aprovado.aluno_id
    )
    _anexar(repo, storage, update_id, "candidata", job_id=job_id)
    with Session(engine) as session:
        candidato = session.scalar(
            select(models.ConjuntoReferenciasWeb).where(
                models.ConjuntoReferenciasWeb.solicitacao_id == update_id
            )
        )
        caminhos_candidatos = session.scalars(
            select(models.ReferenciaFacialWeb.caminho_privado_relativo).where(
                models.ReferenciaFacialWeb.conjunto_id == candidato.id
            )
        ).all()
    with engine.begin() as conexao:
        conexao.exec_driver_sql(
            "CREATE TRIGGER falhar_aprovacao_teste BEFORE INSERT "
            "ON eventos_auditoria_web "
            "WHEN NEW.acao = 'atualizacao_biometrica_aprovada' "
            "BEGIN SELECT RAISE(ABORT, 'falha SQL sintetica'); END"
        )

    with pytest.raises(SQLAlchemyError, match="falha SQL sintetica"):
        AprovarAtualizacaoBiometrica(
            repo, storage, relogio=lambda: AGORA + dt.timedelta(minutes=1)
        ).executar(
            AtorWeb(1, "admin", True, False, None),
            update_id,
            justificativa="Falha simulada de persistência SQL",
        )

    assert all(
        not (tmp_path / "privado" / caminho).exists() for caminho in caminhos_candidatos
    )
    ativos = repo.obter_referencias_ativas((aprovado.aluno_id,))
    assert len(ativos) == 3
    assert {item.versao for item in ativos} == {1}
    with Session(engine) as session:
        estado_candidato = session.scalar(
            select(models.ConjuntoReferenciasWeb.estado).where(
                models.ConjuntoReferenciasWeb.solicitacao_id == update_id
            )
        )
        referencias_candidatas = session.scalar(
            select(func.count(models.ReferenciaFacialWeb.id)).where(
                models.ReferenciaFacialWeb.conjunto_id == candidato.id
            )
        )
    assert estado_candidato == "descartado"
    assert referencias_candidatas == 0
