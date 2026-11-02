from __future__ import annotations

import csv
import datetime as dt
import hashlib
from io import StringIO
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.application.services.fila_facial import (
    EstadoJobFacial,
    JobFacial,
    TipoJobFacial,
)
from src.application.use_cases.exportar_presencas import ExportarPresencas
from src.domain.entities.presenca_web import StatusPresenca
from src.domain.services.autorizacao import AcessoTurmaNegado, AtorWeb
from src.domain.services.face_recognition import ResultadoFacial
from src.infrastructure.database import models
from src.infrastructure.repositories import (
    postgres_presenca_web_repository as presenca_web,
)
from src.infrastructure.repositories.postgres_gestao_web_repository import (
    PostgresGestaoWebRepository,
    VersaoPresencaDesatualizada,
)
from src.infrastructure.repositories.postgres_presenca_web_repository import (
    PostgresPresencaWebRepository,
)

AGORA = dt.datetime(2026, 10, 18, 15, 0, tzinfo=dt.UTC)
ATOR = AtorWeb(1, "professor", True, False, 1)
ADMIN = AtorWeb(3, "admin", True, False, None)


@pytest.fixture
def db() -> Any:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def sqlite_functions(connection: Any, _record: Any) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.execute("PRAGMA foreign_keys=ON")

    models.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session, session.begin():
        session.add(
            models.ContaWeb(
                id=1,
                usuario_normalizado="professor",
                senha_hash="hash-sintetico",
                papel="professor",
                ativa=True,
                troca_senha_obrigatoria=False,
                versao_credencial=1,
                criado_em=AGORA,
            )
        )
        session.add(
            models.ContaWeb(
                id=2,
                usuario_normalizado="outro-professor",
                senha_hash="hash-sintetico-2",
                papel="professor",
                ativa=True,
                troca_senha_obrigatoria=False,
                versao_credencial=1,
                criado_em=AGORA,
            )
        )
        session.add(
            models.ContaWeb(
                id=3,
                usuario_normalizado="admin",
                senha_hash="hash-admin-sintetico",
                papel="admin",
                ativa=True,
                troca_senha_obrigatoria=False,
                versao_credencial=1,
                criado_em=AGORA,
            )
        )
        session.flush()
        session.add(models.ProfessorWeb(id=1, conta_id=1, criado_em=AGORA))
        session.add(models.ProfessorWeb(id=2, conta_id=2, criado_em=AGORA))
        session.add(
            models.Turma(
                id=7,
                materia="IA sintética",
                periodo="noturno",
                responsavel_professor_id=1,
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )
        session.add(
            models.Turma(
                id=8,
                materia="Outra turma",
                periodo="diurno",
                responsavel_professor_id=2,
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )
        session.add(
            models.Aluno(
                id=11,
                matricula="SINT-11",
                nome="Pessoa de teste",
                consentimento_em=AGORA,
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )
        session.add(
            models.Aluno(
                id=12,
                matricula="SINT-12",
                nome="Segunda pessoa de teste",
                consentimento_em=AGORA,
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )
        session.flush()
        session.add(
            models.AlunoTurma(
                turma_id=7,
                aluno_id=11,
                ativo=True,
                vinculado_em=AGORA,
            )
        )
        session.add(
            models.AlunoTurma(
                turma_id=8,
                aluno_id=11,
                ativo=True,
                vinculado_em=AGORA,
            )
        )
        session.add(
            models.SessaoPresencaWeb(
                id=21,
                turma_id=7,
                criada_por_conta_id=1,
                titulo="Sessão sintética",
                inicio_em=AGORA - dt.timedelta(minutes=30),
                fim_em=AGORA + dt.timedelta(minutes=30),
                criada_em=AGORA - dt.timedelta(hours=1),
            )
        )
        session.flush()
        session.add(
            models.LinkCadastroWeb(
                id=uuid4(),
                turma_id=7,
                emitido_por_conta_id=1,
                token_hash="a" * 64,
                finalidade="presenca",
                sessao_id=21,
                criado_em=AGORA - dt.timedelta(hours=1),
                expira_em=AGORA + dt.timedelta(hours=1),
                finalidade_ate=AGORA + dt.timedelta(hours=2),
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()


def test_revisao_acessivel_registra_presenca_manual_e_audita_sem_biometria(
    db: Any,
) -> None:
    repository = PostgresGestaoWebRepository(db)
    with db.connect() as connection:
        link_id = connection.execute(select(models.LinkCadastroWeb.id)).scalar_one()

    with pytest.raises(LookupError):
        repository.solicitar_revisao(
            sessao_id=21,
            turma_id=7,
            link_id=link_id,
            matricula="SINT-11",
            justificativa="Solicitação antes da quota.",
            via_acessivel=False,
            agora=AGORA,
        )

    solicitacao = repository.solicitar_revisao(
        sessao_id=21,
        turma_id=7,
        link_id=link_id,
        matricula="SINT-11",
        justificativa="Leitor de tela; preciso de ajuda.",
        via_acessivel=True,
        agora=AGORA,
    )
    duplicada = repository.solicitar_revisao(
        sessao_id=21,
        turma_id=7,
        link_id=link_id,
        matricula="SINT-11",
        justificativa="Não deve substituir o protocolo aberto.",
        via_acessivel=True,
        agora=AGORA + dt.timedelta(seconds=1),
    )
    assert duplicada.id == solicitacao.id

    with pytest.raises(ValueError, match="verificação independente"):
        repository.decidir_revisao(
            ator=ATOR,
            revisao_id=solicitacao.id,
            decisao=StatusPresenca.PRESENTE,
            justificativa="Identidade conferida presencialmente.",
            versao_esperada=0,
            identidade_confirmada=False,
            agora=AGORA + dt.timedelta(minutes=1),
        )

    with pytest.raises(VersaoPresencaDesatualizada):
        repository.decidir_revisao(
            ator=ATOR,
            revisao_id=solicitacao.id,
            decisao=StatusPresenca.PRESENTE,
            justificativa="Identidade conferida presencialmente.",
            versao_esperada=1,
            identidade_confirmada=True,
            agora=AGORA + dt.timedelta(minutes=1),
        )

    presenca = repository.decidir_revisao(
        ator=ATOR,
        revisao_id=solicitacao.id,
        decisao=StatusPresenca.PRESENTE,
        justificativa="Identidade conferida presencialmente.",
        versao_esperada=0,
        identidade_confirmada=True,
        agora=AGORA + dt.timedelta(minutes=1),
    )

    assert presenca.aluno_id == 11
    assert presenca.status is StatusPresenca.PRESENTE
    assert presenca.origem.value == "manual"
    assert presenca.versao == 1
    assert presenca.horario_evidencia is None
    assert presenca.corrigida_por_conta_id == 1

    with sessionmaker(bind=db)() as session:
        auditoria = session.scalar(
            select(models.EventoAuditoriaWeb).where(
                models.EventoAuditoriaWeb.acao == "presenca_corrigida_manual"
            )
        )
        revisao = session.scalar(
            select(models.RevisaoPresencaWeb).where(
                models.RevisaoPresencaWeb.id == solicitacao.id
            )
        )

    assert auditoria is not None
    assert revisao is not None

    assert auditoria.antes is None
    assert auditoria.depois == {
        "status": "presente",
        "origem": "manual",
        "versao": 1,
        "identidade_confirmada": True,
    }
    assert revisao.estado == "decidida"
    assert revisao.decidida_por_conta_id == 1
    assert "embedding" not in str(auditoria.depois)
    assert "horario_evidencia" not in str(auditoria.depois)


def test_presencas_da_sessao_listam_nome_e_matricula_so_ao_responsavel(
    db: Any,
) -> None:
    with sessionmaker(bind=db)() as session, session.begin():
        session.add(
            models.Presenca(
                id=61,
                aluno_id=11,
                turma_id=7,
                sessao_id=21,
                tentativa_id=None,
                registrado_em=AGORA,
                data_referencia=AGORA.date(),
                status="presente",
                origem="manual",
                versao=1,
                horario_evidencia=None,
                corrigida_em=AGORA,
                corrigida_por_conta_id=1,
            )
        )
    repository = PostgresGestaoWebRepository(db)

    itens = repository.listar_presencas_sessao(ATOR, 7, 21)

    assert itens == [
        {
            "nome": "Pessoa de teste",
            "matricula": "SINT-11",
            "status": "presente",
            "origem": "manual",
            "registrado_em": AGORA.isoformat(),
        }
    ]
    with pytest.raises(LookupError):
        repository.listar_presencas_sessao(ATOR, 7, 999)
    with pytest.raises(AcessoTurmaNegado):
        repository.listar_presencas_sessao(ATOR, 8, 21)


def _utc_lido(instante: dt.datetime) -> dt.datetime:
    return instante if instante.tzinfo else instante.replace(tzinfo=dt.UTC)


def _tentativa_e_presenca_na_sessao(db: Any, *, estado_job: str) -> Any:
    job_id = uuid4()
    with db.connect() as connection:
        link_id = connection.execute(select(models.LinkCadastroWeb.id)).scalar_one()
    processando = estado_job == "processando"
    with sessionmaker(bind=db)() as session, session.begin():
        session.add(
            models.SolicitacaoCadastroWeb(
                id=72,
                tipo="atualizacao",
                estado="aprovada",
                convite_ref=None,
                turma_id=7,
                aluno_id=11,
                matricula=None,
                nome=None,
                expira_em=AGORA + dt.timedelta(days=1),
                criada_em=AGORA - dt.timedelta(days=1),
            )
        )
        session.flush()
        session.add(
            models.ConjuntoReferenciasWeb(
                id=32,
                solicitacao_id=72,
                aluno_id=11,
                versao=1,
                estado="ativo",
                job_id=str(uuid4()),
                embedding_modelo="Facenet512",
                embedding_dim=512,
                criado_em=AGORA - dt.timedelta(days=1),
                ativado_em=AGORA - dt.timedelta(days=1),
            )
        )
        session.add(
            models.JobFacialWeb(
                id=job_id,
                dono_id="presenca:21:11",
                tipo="presenca",
                estado=estado_job,
                idempotencia_hash="i" * 64,
                credencial_hash="c" * 64,
                manifesto={"capturas": []} if processando else None,
                bytes_reservados=1,
                prazo_reserva=AGORA + dt.timedelta(minutes=1),
                prazo_execucao=AGORA + dt.timedelta(minutes=5),
                criada_em=AGORA - dt.timedelta(minutes=1),
                atualizada_em=AGORA,
                lease_hash=("l" * 64) if processando else None,
                lease_expira_em=(AGORA + dt.timedelta(minutes=1))
                if processando
                else None,
            )
        )
        session.flush()
        session.add(
            models.TentativaPresencaWeb(
                id=job_id,
                sessao_id=21,
                turma_id=7,
                aluno_id=11,
                ordinal=1,
                conjunto_id=32,
                versao_referencia=1,
                versao_sessao=1,
                link_id=link_id,
                idempotencia_hash="t" * 64,
                estado="processando" if processando else "concluida",
                iniciada_em=AGORA - dt.timedelta(minutes=1),
                prazo_envio=AGORA + dt.timedelta(minutes=1),
                recebida_em=AGORA - dt.timedelta(seconds=30),
                concluida_em=None if processando else AGORA,
            )
        )
        session.add(
            models.Presenca(
                id=81,
                aluno_id=11,
                turma_id=7,
                sessao_id=21,
                tentativa_id=None,
                registrado_em=AGORA,
                data_referencia=AGORA.date(),
                status="presente",
                origem="manual",
                versao=1,
                horario_evidencia=None,
                corrigida_em=AGORA,
                corrigida_por_conta_id=1,
            )
        )
    return job_id


def test_editar_sessao_atualiza_janela_versao_e_validade_dos_links(db: Any) -> None:
    repository = PostgresPresencaWebRepository(db)
    inicio = AGORA + dt.timedelta(hours=1)
    fim = AGORA + dt.timedelta(hours=3)
    fim_link = fim + dt.timedelta(seconds=120)

    editada = repository.editar_sessao(
        ATOR,
        21,
        titulo="  Aula   revisada ",
        inicio_em=inicio,
        fim_em=fim,
        fim_link=fim_link,
        agora=AGORA,
    )
    so_titulo = repository.editar_sessao(
        ATOR,
        21,
        titulo="Aula final",
        inicio_em=inicio,
        fim_em=fim,
        fim_link=fim_link,
        agora=AGORA,
    )

    assert (editada.titulo, editada.inicio_em, editada.fim_em) == (
        "Aula revisada",
        inicio,
        fim,
    )
    assert editada.versao == 2
    assert (so_titulo.titulo, so_titulo.versao) == ("Aula final", 2)
    with sessionmaker(bind=db)() as session:
        link = session.scalars(select(models.LinkCadastroWeb)).one()
        assert _utc_lido(link.expira_em) == fim_link
        assert _utc_lido(link.finalidade_ate) == fim_link
    with pytest.raises(ValueError):
        repository.editar_sessao(
            ATOR,
            21,
            titulo="Invertida",
            inicio_em=fim,
            fim_em=inicio,
            fim_link=fim_link,
            agora=AGORA,
        )
    with pytest.raises(AcessoTurmaNegado):
        repository.editar_sessao(
            AtorWeb(2, "professor", True, False, 2),
            21,
            titulo="Alheia",
            inicio_em=inicio,
            fim_em=fim,
            fim_link=fim_link,
            agora=AGORA,
        )
    repository.revogar_sessao(ATOR, 21, agora=AGORA)
    with pytest.raises(RuntimeError):
        repository.editar_sessao(
            ATOR,
            21,
            titulo="Revogada",
            inicio_em=inicio,
            fim_em=fim,
            fim_link=fim_link,
            agora=AGORA,
        )


def test_excluir_sessao_apaga_presencas_tentativas_jobs_links_e_audita(
    db: Any,
) -> None:
    job_id = _tentativa_e_presenca_na_sessao(db, estado_job="concluida")
    repository = PostgresPresencaWebRepository(db)

    resultado = repository.excluir_sessao(ATOR, 21, agora=AGORA)

    assert resultado == {
        "presencas": 1,
        "tentativas": 1,
        "revisoes": 0,
        "links": 1,
        "jobs_temporarios": (job_id,),
    }
    with sessionmaker(bind=db)() as session:
        assert session.get(models.SessaoPresencaWeb, 21) is None
        assert session.get(models.Presenca, 81) is None
        assert session.get(models.TentativaPresencaWeb, job_id) is None
        assert session.get(models.JobFacialWeb, job_id) is None
        assert session.scalars(select(models.LinkCadastroWeb)).all() == []
        assert session.scalar(
            select(models.EventoAuditoriaWeb.id).where(
                models.EventoAuditoriaWeb.acao == "sessao_presenca_excluida"
            )
        )
    with pytest.raises(LookupError):
        repository.excluir_sessao(ATOR, 21, agora=AGORA)


def test_excluir_sessao_aguarda_verificacao_em_processamento(db: Any) -> None:
    _tentativa_e_presenca_na_sessao(db, estado_job="processando")
    repository = PostgresPresencaWebRepository(db)

    with pytest.raises(RuntimeError):
        repository.excluir_sessao(ATOR, 21, agora=AGORA)
    with sessionmaker(bind=db)() as session:
        assert session.get(models.SessaoPresencaWeb, 21) is not None
        assert session.get(models.Presenca, 81) is not None


def test_professor_nao_le_revisao_de_turma_de_outro_responsavel(db: Any) -> None:
    repository = PostgresGestaoWebRepository(db)

    with pytest.raises(AcessoTurmaNegado):
        repository.listar_revisoes(ATOR, 8)


def test_crud_turma_e_desvinculo_preservam_historico_e_escopo(db: Any) -> None:
    repository = PostgresGestaoWebRepository(db)

    minhas = repository.listar_turmas(ATOR)
    assert [turma["id"] for turma in minhas] == [7]
    with pytest.raises(AcessoTurmaNegado):
        repository.obter_turma(ATOR, 8)

    criada = repository.criar_turma(
        ator=ATOR,
        materia="  Aprendizado de máquina  ",
        periodo="diurno",
        responsavel_professor_id=None,
        agora=AGORA,
        confirmar=False,
        justificativa=None,
        request_id="req-test-1",
    )
    assert criada["materia"] == "Aprendizado de máquina"
    assert criada["responsavel_professor_id"] == 1

    atualizada = repository.atualizar_turma(
        ator=ATOR,
        turma_id=7,
        materia="Visão computacional",
        periodo=None,
        responsavel_professor_id=None,
        confirmar_transferencia=False,
        justificativa=None,
        agora=AGORA + dt.timedelta(minutes=1),
        request_id="req-test-2",
    )
    assert atualizada["materia"] == "Visão computacional"

    vinculo_novo = repository.vincular_aluno(
        ator=ATOR,
        turma_id=7,
        matricula="SINT-12",
        agora=AGORA + dt.timedelta(minutes=2),
        request_id="req-test-3",
    )
    assert vinculo_novo["vinculado"] is True
    vinculo_existente = repository.vincular_aluno(
        ator=ATOR,
        turma_id=7,
        matricula="SINT-12",
        agora=AGORA + dt.timedelta(minutes=3),
        request_id="req-test-4",
    )
    assert vinculo_existente["vinculado"] is False

    repository.desvincular_aluno(
        ator=ATOR,
        turma_id=7,
        aluno_id=11,
        justificativa="Mudança de turma.",
        agora=AGORA + dt.timedelta(minutes=4),
        request_id="req-test-5",
    )
    repository.excluir_turma(
        ator=ATOR,
        turma_id=7,
        justificativa="Encerramento da turma.",
        agora=AGORA + dt.timedelta(minutes=5),
        request_id="req-test-6",
    )

    with sessionmaker(bind=db)() as session:
        vinculo_origem = session.get(models.AlunoTurma, (7, 11))
        vinculo_destino = session.get(models.AlunoTurma, (8, 11))
        turma = session.get(models.Turma, 7)
    assert vinculo_origem is not None and not vinculo_origem.ativo
    assert vinculo_destino is not None and vinculo_destino.ativo
    assert turma is not None and turma.excluida_em is not None


def test_exclusao_global_exige_admin_confirmacao_e_audita_sem_dados_biometricos(
    db: Any,
) -> None:
    repository = PostgresGestaoWebRepository(db)
    argumentos = {
        "aluno_id": 11,
        "confirmacao": "EXCLUIR-ALUNO-11",
        "justificativa": "Solicitação administrativa autorizada.",
        "agora": AGORA,
        "request_id": "req-exclusao-sintetica",
        "armazenamento_referencias_disponivel": True,
        "armazenamento_legado_disponivel": True,
        "armazenamento_capturas_disponivel": True,
    }
    with pytest.raises(PermissionError):
        repository.excluir_aluno_global(ator=ATOR, **argumentos)
    with pytest.raises(ValueError, match="confirmação"):
        repository.excluir_aluno_global(
            ator=ADMIN, **{**argumentos, "confirmacao": "NAO"}
        )

    resultado = repository.excluir_aluno_global(ator=ADMIN, **argumentos)
    assert resultado["caminhos_referencias"] == ()
    assert resultado["caminho_legado"] is None
    assert resultado["jobs_temporarios"] == ()

    with sessionmaker(bind=db)() as session:
        assert session.get(models.Aluno, 11) is None
        auditoria = session.scalar(
            select(models.EventoAuditoriaWeb).where(
                models.EventoAuditoriaWeb.acao == "aluno_excluido_globalmente"
            )
        )
    assert auditoria is not None
    assert auditoria.antes == {
        "vinculos": 2,
        "presencas": 0,
        "conjuntos_referencia": 0,
    }
    assert auditoria.depois == {"excluido": True}
    assert "embedding" not in str(auditoria.antes)
    assert "matricula" not in str(auditoria.antes)


def test_exclusao_global_apaga_solicitacao_de_cadastro_aprovada_e_seus_jobs(
    db: Any,
) -> None:
    # Cadastro aprovado: aluno_id fica nulo na solicitação (CHECK
    # identificacao_coerente); o vínculo com o aluno é o conjunto.
    repository = PostgresGestaoWebRepository(db)
    recusado, aceito = uuid4(), uuid4()
    with sessionmaker(bind=db)() as session, session.begin():
        solicitacao = models.SolicitacaoCadastroWeb(
            tipo="cadastro",
            estado="aprovada",
            convite_ref="convite-sintetico",
            turma_id=7,
            aluno_id=None,
            matricula="SINT-11",
            nome="Pessoa Sintética",
            consentimento_em=AGORA,
            consentimento_versao="aviso-v1",
            expira_em=AGORA + dt.timedelta(days=1),
            criada_em=AGORA,
        )
        session.add(solicitacao)
        session.flush()
        for job_id in (recusado, aceito):
            session.add(
                models.JobFacialWeb(
                    id=job_id,
                    dono_id=str(solicitacao.id),
                    tipo="cadastro",
                    estado="recebida",
                    idempotencia_hash=job_id.hex * 2,
                    credencial_hash="a" * 64,
                    manifesto=None,
                    bytes_reservados=1,
                    prazo_reserva=AGORA + dt.timedelta(minutes=5),
                    prazo_execucao=AGORA + dt.timedelta(minutes=15),
                    criada_em=AGORA,
                    atualizada_em=AGORA,
                )
            )
        session.flush()
        solicitacao.job_id = aceito
        session.add(
            models.ConjuntoReferenciasWeb(
                solicitacao_id=solicitacao.id,
                aluno_id=11,
                versao=1,
                estado="ativo",
                job_id=str(aceito),
                embedding_modelo="Facenet512",
                embedding_dim=512,
                criado_em=AGORA,
                ativado_em=AGORA,
            )
        )
        solicitacao_id = solicitacao.id

    resultado = repository.excluir_aluno_global(
        ator=ADMIN,
        aluno_id=11,
        confirmacao="EXCLUIR-ALUNO-11",
        justificativa="Limpeza de cadastros de teste.",
        agora=AGORA,
        request_id=None,
        armazenamento_referencias_disponivel=True,
        armazenamento_legado_disponivel=True,
        armazenamento_capturas_disponivel=True,
    )

    # O job recusado (coleta reaberta) também sai, embora a solicitação não o aponte.
    assert set(resultado["jobs_temporarios"]) == {str(recusado), str(aceito)}
    with sessionmaker(bind=db)() as session:
        assert session.get(models.SolicitacaoCadastroWeb, solicitacao_id) is None
        assert session.get(models.JobFacialWeb, recusado) is None
        assert session.get(models.JobFacialWeb, aceito) is None


def test_reativacao_de_quota_exige_admin_e_registra_evento_auditavel(db: Any) -> None:
    link_id = uuid4()
    set_id = 31
    with sessionmaker(bind=db)() as session, session.begin():
        session.add(
            models.SolicitacaoCadastroWeb(
                id=71,
                tipo="atualizacao",
                estado="aprovada",
                convite_ref=None,
                turma_id=7,
                aluno_id=11,
                matricula=None,
                nome=None,
                expira_em=AGORA + dt.timedelta(days=1),
                criada_em=AGORA - dt.timedelta(days=1),
            )
        )
        session.flush()
        session.add(
            models.ConjuntoReferenciasWeb(
                id=set_id,
                solicitacao_id=71,
                aluno_id=11,
                versao=1,
                estado="ativo",
                job_id=str(uuid4()),
                embedding_modelo="Facenet512",
                embedding_dim=512,
                criado_em=AGORA - dt.timedelta(days=1),
                ativado_em=AGORA - dt.timedelta(days=1),
            )
        )
        session.add(
            models.LinkCadastroWeb(
                id=link_id,
                turma_id=7,
                emitido_por_conta_id=1,
                token_hash="b" * 64,
                finalidade="presenca",
                sessao_id=21,
                criado_em=AGORA - dt.timedelta(hours=1),
                expira_em=AGORA + dt.timedelta(hours=1),
                finalidade_ate=AGORA + dt.timedelta(hours=2),
            )
        )
        session.flush()
        for ordinal in range(1, 4):
            job_id = uuid4()
            session.add(
                models.JobFacialWeb(
                    id=job_id,
                    dono_id="presenca:21:11",
                    tipo="presenca",
                    estado="rejeitada",
                    idempotencia_hash=f"{ordinal:064d}",
                    credencial_hash="c" * 64,
                    manifesto=None,
                    bytes_reservados=1,
                    prazo_reserva=AGORA + dt.timedelta(minutes=1),
                    prazo_execucao=AGORA + dt.timedelta(minutes=5),
                    criada_em=AGORA - dt.timedelta(minutes=1),
                    atualizada_em=AGORA,
                    finalizada_em=AGORA,
                )
            )
            session.add(
                models.TentativaPresencaWeb(
                    id=job_id,
                    sessao_id=21,
                    turma_id=7,
                    aluno_id=11,
                    ordinal=ordinal,
                    conjunto_id=set_id,
                    versao_referencia=1,
                    versao_sessao=1,
                    link_id=link_id,
                    idempotencia_hash=f"{ordinal:064d}",
                    estado="rejeitada",
                    iniciada_em=AGORA - dt.timedelta(minutes=1),
                    prazo_envio=AGORA + dt.timedelta(minutes=1),
                    concluida_em=AGORA,
                )
            )

    repository = PostgresGestaoWebRepository(db)
    argumentos = {
        "turma_id": 7,
        "sessao_id": 21,
        "aluno_id": 11,
        "confirmar": True,
        "justificativa": "Reativação administrativa de teste.",
        "agora": AGORA + dt.timedelta(minutes=2),
        "request_id": "req-quota-sintetica",
    }
    with pytest.raises(PermissionError):
        repository.reativar_quota(ator=ATOR, **argumentos)
    with pytest.raises(ValueError, match="Confirme"):
        repository.reativar_quota(ator=ADMIN, **{**argumentos, "confirmar": False})

    limite = repository.reativar_quota(ator=ADMIN, **argumentos)

    assert limite == 6
    with sessionmaker(bind=db)() as session:
        auditoria = session.scalar(
            select(models.EventoAuditoriaWeb).where(
                models.EventoAuditoriaWeb.acao == "quota_presenca_reativada"
            )
        )
    assert auditoria is not None
    assert auditoria.antes == {"tentativas_emitidas": 3, "limite": 3}
    assert auditoria.depois == {"limite": 6}


def test_falha_de_auditoria_reverte_decisao_de_presenca(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = PostgresGestaoWebRepository(db)
    with db.connect() as connection:
        link_id = connection.execute(select(models.LinkCadastroWeb.id)).scalar_one()
    solicitacao = repository.solicitar_revisao(
        sessao_id=21,
        turma_id=7,
        link_id=link_id,
        matricula="SINT-11",
        justificativa="Pedido sintético acessível.",
        via_acessivel=True,
        agora=AGORA,
    )

    def falhar_auditoria(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Falha sintética de auditoria.")

    monkeypatch.setattr(repository, "_auditar", falhar_auditoria)
    with pytest.raises(RuntimeError, match="Falha sintética"):
        repository.decidir_revisao(
            ator=ATOR,
            revisao_id=solicitacao.id,
            decisao=StatusPresenca.PRESENTE,
            justificativa="Verificação independente sintética.",
            versao_esperada=0,
            identidade_confirmada=True,
            agora=AGORA + dt.timedelta(minutes=1),
        )

    with sessionmaker(bind=db)() as session:
        presenca = session.scalar(
            select(models.Presenca).where(models.Presenca.sessao_id == 21)
        )
        revisao = session.get(models.RevisaoPresencaWeb, solicitacao.id)
    assert presenca is None
    assert revisao is not None and revisao.estado == "aberta"


def test_revisao_anula_registro_existente_com_versao_e_estado_anterior(db: Any) -> None:
    with sessionmaker(bind=db)() as session, session.begin():
        session.add(
            models.Presenca(
                id=50,
                aluno_id=11,
                turma_id=7,
                sessao_id=21,
                tentativa_id=None,
                registrado_em=AGORA - dt.timedelta(minutes=5),
                data_referencia=dt.date(2026, 10, 18),
                status="presente",
                origem="manual",
                versao=1,
                horario_evidencia=None,
                corrigida_em=AGORA - dt.timedelta(minutes=5),
                corrigida_por_conta_id=1,
            )
        )
    repository = PostgresGestaoWebRepository(db)
    with db.connect() as connection:
        link_id = connection.execute(select(models.LinkCadastroWeb.id)).scalar_one()
    revisao = repository.solicitar_revisao(
        sessao_id=21,
        turma_id=7,
        link_id=link_id,
        matricula="SINT-11",
        justificativa="Correção acessível.",
        via_acessivel=True,
        agora=AGORA,
    )

    resultado = repository.decidir_revisao(
        ator=ATOR,
        revisao_id=revisao.id,
        decisao=StatusPresenca.ANULADA,
        justificativa="Identidade não confirmada.",
        versao_esperada=1,
        identidade_confirmada=False,
        agora=AGORA + dt.timedelta(minutes=1),
    )

    assert resultado.id == 50
    assert resultado.status is StatusPresenca.ANULADA
    assert resultado.versao == 2
    with sessionmaker(bind=db)() as session:
        auditoria = session.scalar(
            select(models.EventoAuditoriaWeb).where(
                models.EventoAuditoriaWeb.acao == "presenca_corrigida_manual"
            )
        )
    assert auditoria is not None
    assert auditoria.antes == {
        "status": "presente",
        "origem": "manual",
        "versao": 1,
    }
    assert auditoria.depois == {
        "status": "anulada",
        "origem": "manual",
        "versao": 2,
        "identidade_confirmada": False,
    }


def test_painel_e_csv_limitam_se_a_presencas_registradas_e_ao_fuso_local(
    db: Any,
) -> None:
    comeco_dia_local = dt.datetime(2026, 10, 18, 2, 30, tzinfo=dt.UTC)
    with sessionmaker(bind=db)() as session, session.begin():
        session.add(
            models.Presenca(
                id=51,
                aluno_id=11,
                turma_id=7,
                sessao_id=21,
                tentativa_id=None,
                registrado_em=comeco_dia_local,
                data_referencia=dt.date(2026, 10, 17),
                status="presente",
                origem="manual",
                versao=1,
                horario_evidencia=None,
                corrigida_em=comeco_dia_local,
                corrigida_por_conta_id=1,
            )
        )
    repository = PostgresGestaoWebRepository(db)

    painel = repository.consultar_painel(ATOR, 7, atualizado_em=AGORA)
    assert painel["atualizado_em"] == AGORA.isoformat()
    assert painel["sessoes"][0]["presencas_presentes"] == 1
    assert painel["sessoes"][0]["presencas_anuladas"] == 0

    linhas = repository.listar_presencas_exportacao(
        ATOR,
        turma_id=7,
        inicio=dt.date(2026, 10, 17),
        fim=dt.date(2026, 10, 17),
    )
    conteudo = ExportarPresencas(repository, "America/Sao_Paulo").executar(
        ATOR,
        turma_id=7,
        inicio=dt.date(2026, 10, 17),
        fim=dt.date(2026, 10, 17),
    )
    assert len(linhas) == 1
    assert linhas[0]["status"] == "presente"
    assert conteudo.decode("utf-8").splitlines()[1].count("23:30:00") == 2
    assert "embedding" not in conteudo.decode("utf-8")
    assert "ausente" not in conteudo.decode("utf-8")


def test_csv_da_sessao_filtra_pela_sessao_da_turma(db: Any) -> None:
    with sessionmaker(bind=db)() as session, session.begin():
        session.add(
            models.SessaoPresencaWeb(
                id=22,
                turma_id=7,
                criada_por_conta_id=1,
                titulo="Sessão sintética sem presença",
                inicio_em=AGORA + dt.timedelta(days=1),
                fim_em=AGORA + dt.timedelta(days=1, hours=1),
                criada_em=AGORA,
            )
        )
        session.add(
            models.Presenca(
                id=52,
                aluno_id=11,
                turma_id=7,
                sessao_id=21,
                tentativa_id=None,
                registrado_em=AGORA,
                data_referencia=AGORA.date(),
                status="presente",
                origem="manual",
                versao=1,
                horario_evidencia=None,
                corrigida_em=AGORA,
                corrigida_por_conta_id=1,
            )
        )
    exportar = ExportarPresencas(PostgresGestaoWebRepository(db), "America/Sao_Paulo")

    com_presenca = exportar.executar_sessao(ATOR, turma_id=7, sessao_id=21)
    sem_presenca = exportar.executar_sessao(ATOR, turma_id=7, sessao_id=22)

    linhas = list(csv.DictReader(StringIO(com_presenca.decode("utf-8"))))
    assert [(linha["sessao_id"], linha["matricula"]) for linha in linhas] == [
        ("21", "SINT-11")
    ]
    assert sem_presenca.decode("utf-8").count("\r\n") == 1
    with pytest.raises(LookupError):
        exportar.executar_sessao(ATOR, turma_id=7, sessao_id=999)


def test_worker_tardio_nao_grava_presenca_com_revisao_aberta(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    utc_original = presenca_web._utc

    def utc_sqlite(instante: dt.datetime) -> dt.datetime:
        if instante.tzinfo is None or instante.utcoffset() is None:
            instante = instante.replace(tzinfo=dt.UTC)
        return utc_original(instante)

    monkeypatch.setattr(presenca_web, "_utc", utc_sqlite)
    job_id = uuid4()
    lease = "lease-sintetico-para-worker-tardio"
    with db.connect() as connection:
        link_id = connection.execute(select(models.LinkCadastroWeb.id)).scalar_one()
    with sessionmaker(bind=db)() as session, session.begin():
        session.add(
            models.SolicitacaoCadastroWeb(
                id=71,
                tipo="atualizacao",
                estado="aprovada",
                convite_ref=None,
                turma_id=7,
                aluno_id=11,
                matricula=None,
                nome=None,
                expira_em=AGORA + dt.timedelta(days=1),
                criada_em=AGORA - dt.timedelta(days=1),
            )
        )
        session.flush()
        session.add(
            models.ConjuntoReferenciasWeb(
                id=31,
                solicitacao_id=71,
                aluno_id=11,
                versao=1,
                estado="ativo",
                job_id=str(uuid4()),
                embedding_modelo="Facenet512",
                embedding_dim=512,
                criado_em=AGORA - dt.timedelta(days=1),
                ativado_em=AGORA - dt.timedelta(days=1),
            )
        )
        session.add(
            models.JobFacialWeb(
                id=job_id,
                dono_id="presenca:21:11",
                tipo="presenca",
                estado="processando",
                idempotencia_hash="i" * 64,
                credencial_hash="c" * 64,
                manifesto={"capturas": []},
                bytes_reservados=1,
                prazo_reserva=AGORA + dt.timedelta(minutes=1),
                prazo_execucao=AGORA + dt.timedelta(minutes=5),
                criada_em=AGORA - dt.timedelta(minutes=1),
                atualizada_em=AGORA,
                iniciada_em=AGORA - dt.timedelta(seconds=30),
                lease_hash=hashlib.sha256(lease.encode()).hexdigest(),
                lease_expira_em=AGORA + dt.timedelta(minutes=1),
            )
        )
        session.flush()
        session.add(
            models.TentativaPresencaWeb(
                id=job_id,
                sessao_id=21,
                turma_id=7,
                aluno_id=11,
                ordinal=1,
                conjunto_id=31,
                versao_referencia=1,
                versao_sessao=1,
                link_id=link_id,
                idempotencia_hash="t" * 64,
                estado="processando",
                iniciada_em=AGORA - dt.timedelta(minutes=1),
                prazo_envio=AGORA + dt.timedelta(minutes=1),
                recebida_em=AGORA - dt.timedelta(seconds=30),
            )
        )
        session.add(
            models.RevisaoPresencaWeb(
                id=uuid4(),
                turma_id=7,
                sessao_id=21,
                aluno_id=11,
                estado="aberta",
                justificativa_solicitacao="Revisão acessível sintética.",
                via_acessivel=True,
                solicitada_em=AGORA,
                versao_presenca_base=0,
            )
        )

    job = JobFacial(
        id=job_id,
        dono_id="presenca:21:11",
        tipo=TipoJobFacial.PRESENCA,
        estado=EstadoJobFacial.PROCESSANDO,
        criada_em=AGORA - dt.timedelta(minutes=1),
        prazo=AGORA + dt.timedelta(minutes=1),
        prazo_execucao=AGORA + dt.timedelta(minutes=5),
        atualizada_em=AGORA,
        manifesto=None,
        lease=lease,
        lease_expira_em=AGORA + dt.timedelta(minutes=1),
        resultado_codigo=None,
        credencial_hash="c" * 64,
    )
    decisao = ResultadoFacial(
        identidade_ok=True,
        desafio_ok=True,
        antispoofing_ok=True,
        qualidade_ok=True,
        motivo_tecnico=None,
        versao_referencia=1,
        politica="mediana-3",
    )
    repository = PostgresPresencaWebRepository(db)

    persistida = repository.concluir_presenca(job, decisao, agora=AGORA)

    assert persistida is None
    with sessionmaker(bind=db)() as session:
        assert (
            session.scalar(
                select(models.Presenca.id).where(
                    models.Presenca.sessao_id == 21,
                    models.Presenca.aluno_id == 11,
                )
            )
            is None
        )
