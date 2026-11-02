"""Persistência transacional da gestão, revisão manual e relatório web."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.entities.presenca_web import (
    OrigemPresenca,
    Presenca,
    RevisaoPresenca,
    StatusPresenca,
)
from src.domain.entities.turma import Turma
from src.domain.services.autorizacao import AtorWeb, AutorizarTurma
from src.infrastructure.database import models

ESTADOS_TENTATIVA_ATIVA = ("iniciada", "recebida", "enfileirada", "processando")


class VersaoPresencaDesatualizada(RuntimeError):
    """A presença mudou desde a versão exibida ao revisor."""


def _utc(instante: dt.datetime) -> dt.datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("O instante deve incluir fuso horário.")
    return instante.astimezone(dt.UTC)


def _utc_armazenado(instante: dt.datetime) -> dt.datetime:
    """Normaliza valores lidos; SQLite devolve naive para colunas timestamptz."""
    if instante.tzinfo is None or instante.utcoffset() is None:
        instante = instante.replace(tzinfo=dt.UTC)
    return instante.astimezone(dt.UTC)


def _justificativa(valor: str | None) -> str:
    if not isinstance(valor, str):
        raise ValueError("Informe uma justificativa.")
    limpa = " ".join(valor.split())
    if not limpa or len(limpa) > 500:
        raise ValueError("A justificativa deve conter entre 1 e 500 caracteres.")
    return limpa


def _para_presenca(linha: models.Presenca) -> Presenca:
    return Presenca(
        id=linha.id,
        aluno_id=linha.aluno_id,
        turma_id=linha.turma_id or 0,
        sessao_id=linha.sessao_id,
        status=StatusPresenca(linha.status),
        origem=OrigemPresenca(linha.origem),
        registrado_em=_utc_armazenado(linha.registrado_em),
        data_referencia=linha.data_referencia,
        horario_evidencia=(
            _utc_armazenado(linha.horario_evidencia)
            if linha.horario_evidencia
            else None
        ),
        corrigida_em=(
            _utc_armazenado(linha.corrigida_em) if linha.corrigida_em else None
        ),
        corrigida_por_conta_id=linha.corrigida_por_conta_id,
        versao=linha.versao,
    )


def _para_revisao(linha: models.RevisaoPresencaWeb) -> RevisaoPresenca:
    return RevisaoPresenca(
        id=linha.id,
        turma_id=linha.turma_id,
        sessao_id=linha.sessao_id,
        aluno_id=linha.aluno_id,
        matricula=None,
        nome=None,
        estado=linha.estado,
        justificativa_solicitacao=linha.justificativa_solicitacao,
        via_acessivel=linha.via_acessivel,
        solicitada_em=_utc_armazenado(linha.solicitada_em),
        versao_presenca_base=linha.versao_presenca_base,
        decisao=StatusPresenca(linha.decisao) if linha.decisao else None,
        justificativa_decisao=linha.justificativa_decisao,
        decidida_em=(_utc_armazenado(linha.decidida_em) if linha.decidida_em else None),
        decidida_por_conta_id=linha.decidida_por_conta_id,
    )


class PostgresGestaoWebRepository:
    """Usa locks e uma transação para autorização, mutação e respectiva auditoria."""

    def __init__(
        self,
        engine_or_factory: Engine | sessionmaker[Session],
        *,
        timezone_name: str = "America/Sao_Paulo",
    ) -> None:
        self._factory = (
            sessionmaker(bind=engine_or_factory, expire_on_commit=False, future=True)
            if isinstance(engine_or_factory, Engine)
            else engine_or_factory
        )
        self._timezone = ZoneInfo(timezone_name)

    def listar_turmas(self, ator: AtorWeb) -> list[dict[str, object]]:
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            consulta = select(models.Turma).where(models.Turma.excluida_em.is_(None))
            if atual.papel != "admin":
                if atual.professor_id is None:
                    raise PermissionError("Conta sem perfil de professor.")
                consulta = consulta.where(
                    models.Turma.responsavel_professor_id == atual.professor_id
                )
            return [self._turma_payload(linha) for linha in session.scalars(consulta)]

    def obter_turma(self, ator: AtorWeb, turma_id: int) -> dict[str, object]:
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            turma = self._turma_autorizada(session, atual, turma_id)
            return self._turma_payload(turma)

    def criar_turma(
        self,
        *,
        ator: AtorWeb,
        materia: str,
        periodo: str,
        responsavel_professor_id: int | None,
        agora: dt.datetime,
        confirmar: bool,
        justificativa: str | None,
        request_id: str | None,
    ) -> dict[str, object]:
        instante = _utc(agora)
        materia_valida = Turma.nova(materia, periodo)
        motivo = _justificativa(justificativa) if ator.papel == "admin" else None
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            if atual.papel == "professor" and atual.professor_id is not None:
                if (
                    responsavel_professor_id is not None
                    and responsavel_professor_id != atual.professor_id
                ):
                    raise PermissionError("Professor só pode criar turma própria.")
                responsavel_id = atual.professor_id
            elif atual.papel == "admin":
                if not confirmar or motivo is None:
                    raise ValueError(
                        "Criação administrativa exige confirmação e justificativa."
                    )
                if responsavel_professor_id is None:
                    raise ValueError("Informe um professor responsável pela turma.")
                self._professor_ativo(session, responsavel_professor_id)
                responsavel_id = responsavel_professor_id
            else:
                raise PermissionError("Conta sem permissão para criar turma.")
            linha = models.Turma(
                materia=materia_valida.materia,
                periodo=materia_valida.periodo.value,
                responsavel_professor_id=responsavel_id,
                criado_em=instante,
                atualizado_em=instante,
            )
            session.add(linha)
            session.flush()
            payload = self._turma_payload(linha)
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="turma_criada",
                alvo_tipo="turma",
                alvo_id=str(linha.id),
                instante=instante,
                justificativa=motivo,
                depois={
                    "materia": linha.materia,
                    "periodo": linha.periodo,
                    "responsavel_professor_id": responsavel_id,
                },
                request_id=request_id,
            )
            return payload

    def atualizar_turma(
        self,
        *,
        ator: AtorWeb,
        turma_id: int,
        materia: str | None,
        periodo: str | None,
        responsavel_professor_id: int | None,
        confirmar_transferencia: bool,
        justificativa: str | None,
        agora: dt.datetime,
        request_id: str | None,
    ) -> dict[str, object]:
        instante = _utc(agora)
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            turma = self._turma_autorizada(session, atual, turma_id, bloquear=True)
            transferencia = responsavel_professor_id is not None
            motivo = _justificativa(justificativa) if transferencia else None
            if transferencia:
                if atual.papel != "admin" or not confirmar_transferencia:
                    raise PermissionError(
                        "Transferência exige confirmação administrativa."
                    )
                if responsavel_professor_id is None:
                    raise ValueError("Informe o professor responsável.")
                self._professor_ativo(session, responsavel_professor_id)
            nova_materia = materia if materia is not None else turma.materia
            novo_periodo = periodo if periodo is not None else turma.periodo
            validada = Turma.nova(nova_materia, novo_periodo)
            antes: dict[str, object] = {
                "materia": turma.materia,
                "periodo": turma.periodo,
                "responsavel_professor_id": turma.responsavel_professor_id,
            }
            turma.materia = validada.materia
            turma.periodo = validada.periodo.value
            if responsavel_professor_id is not None:
                turma.responsavel_professor_id = responsavel_professor_id
            turma.atualizado_em = instante
            session.flush()
            depois: dict[str, object] = {
                "materia": turma.materia,
                "periodo": turma.periodo,
                "responsavel_professor_id": turma.responsavel_professor_id,
            }
            if antes != depois:
                self._auditar(
                    session,
                    ator_id=atual.conta_id,
                    acao="turma_atualizada"
                    if not transferencia
                    else "turma_transferida",
                    alvo_tipo="turma",
                    alvo_id=str(turma.id),
                    instante=instante,
                    justificativa=motivo,
                    antes=antes,
                    depois=depois,
                    request_id=request_id,
                )
            return self._turma_payload(turma)

    def excluir_turma(
        self,
        *,
        ator: AtorWeb,
        turma_id: int,
        justificativa: str,
        agora: dt.datetime,
        request_id: str | None,
    ) -> None:
        instante = _utc(agora)
        motivo = _justificativa(justificativa)
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            turma = self._turma_autorizada(
                session, atual, turma_id, bloquear=True, exigir_ativa=True
            )
            session.scalars(
                select(models.AlunoTurma.aluno_id)
                .where(models.AlunoTurma.turma_id == turma_id)
                .order_by(models.AlunoTurma.aluno_id)
                .with_for_update()
            ).all()
            turma.excluida_em = instante
            turma.atualizado_em = instante
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="turma_excluida_logicamente",
                alvo_tipo="turma",
                alvo_id=str(turma.id),
                instante=instante,
                justificativa=motivo,
                antes={"ativa": True},
                depois={"ativa": False},
                request_id=request_id,
            )

    def listar_alunos_turma(
        self, ator: AtorWeb, turma_id: int
    ) -> list[dict[str, object]]:
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            self._turma_autorizada(session, atual, turma_id)
            linhas = session.execute(
                select(models.Aluno.id, models.Aluno.matricula, models.Aluno.nome)
                .join(models.AlunoTurma, models.AlunoTurma.aluno_id == models.Aluno.id)
                .where(
                    models.AlunoTurma.turma_id == turma_id,
                    models.AlunoTurma.ativo.is_(True),
                )
                .order_by(models.Aluno.nome, models.Aluno.id)
            )
            return [
                {"aluno_id": item.id, "matricula": item.matricula, "nome": item.nome}
                for item in linhas
            ]

    def vincular_aluno(
        self,
        *,
        ator: AtorWeb,
        turma_id: int,
        matricula: str,
        agora: dt.datetime,
        request_id: str | None,
    ) -> dict[str, object]:
        instante = _utc(agora)
        limpa = matricula.strip()
        if not limpa or len(limpa) > 32:
            raise ValueError("A matrícula é inválida.")
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            self._turma_autorizada(
                session, atual, turma_id, bloquear=True, exigir_ativa=True
            )
            aluno = session.scalar(
                select(models.Aluno)
                .where(models.Aluno.matricula == limpa)
                .with_for_update()
            )
            if aluno is None or aluno.consentimento_em is None:
                raise LookupError("Aluno não disponível para vínculo.")
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(
                    models.AlunoTurma.turma_id == turma_id,
                    models.AlunoTurma.aluno_id == aluno.id,
                )
                .with_for_update()
            )
            ja_ativo = vinculo is not None and vinculo.ativo
            if not ja_ativo:
                if vinculo is None:
                    vinculo = models.AlunoTurma(
                        turma_id=turma_id,
                        aluno_id=aluno.id,
                        ativo=True,
                        vinculado_em=instante,
                    )
                    session.add(vinculo)
                else:
                    vinculo.ativo = True
                    vinculo.vinculado_em = instante
                    vinculo.desvinculado_em = None
                session.flush()
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="vinculo_turma_existente" if ja_ativo else "aluno_vinculado_turma",
                alvo_tipo="vinculo_turma",
                alvo_id=f"{turma_id}:{aluno.id}",
                instante=instante,
                depois={"ativo": True},
                request_id=request_id,
            )
            return {
                "aluno_id": aluno.id,
                "matricula": aluno.matricula,
                "nome": aluno.nome,
                "vinculado": not ja_ativo,
            }

    def desvincular_aluno(
        self,
        *,
        ator: AtorWeb,
        turma_id: int,
        aluno_id: int,
        justificativa: str,
        agora: dt.datetime,
        request_id: str | None,
    ) -> None:
        instante = _utc(agora)
        motivo = _justificativa(justificativa)
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            self._turma_autorizada(
                session, atual, turma_id, bloquear=True, exigir_ativa=True
            )
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(
                    models.AlunoTurma.turma_id == turma_id,
                    models.AlunoTurma.aluno_id == aluno_id,
                )
                .with_for_update()
            )
            if vinculo is None or not vinculo.ativo:
                raise LookupError("Vínculo não encontrado.")
            vinculo.ativo = False
            vinculo.desvinculado_em = instante
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="aluno_desvinculado_turma",
                alvo_tipo="vinculo_turma",
                alvo_id=f"{turma_id}:{aluno_id}",
                instante=instante,
                justificativa=motivo,
                antes={"ativo": True},
                depois={"ativo": False},
                request_id=request_id,
            )

    def solicitar_revisao(
        self,
        *,
        sessao_id: int,
        turma_id: int,
        link_id: UUID,
        matricula: str,
        justificativa: str,
        via_acessivel: bool,
        agora: dt.datetime,
        request_id: str | None = None,
    ) -> RevisaoPresenca:
        instante = _utc(agora)
        motivo = _justificativa(justificativa)
        with self._factory() as session, session.begin():
            sessao = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(
                    models.SessaoPresencaWeb.id == sessao_id,
                    models.SessaoPresencaWeb.turma_id == turma_id,
                )
                .with_for_update()
            )
            link = session.scalar(
                select(models.LinkCadastroWeb)
                .where(
                    models.LinkCadastroWeb.id == link_id,
                    models.LinkCadastroWeb.turma_id == turma_id,
                    models.LinkCadastroWeb.sessao_id == sessao_id,
                    models.LinkCadastroWeb.finalidade == "presenca",
                    models.LinkCadastroWeb.revogado_em.is_(None),
                )
                .with_for_update()
            )
            if sessao is None or sessao.revogada_em is not None or link is None:
                raise LookupError("Revisão indisponível.")
            turma = session.get(models.Turma, turma_id)
            if turma is None or turma.excluida_em is not None:
                raise LookupError("Revisão indisponível.")
            aluno = session.scalar(
                select(models.Aluno)
                .where(models.Aluno.matricula == matricula)
                .with_for_update()
            )
            if aluno is None:
                raise LookupError("Revisão indisponível.")
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(
                    models.AlunoTurma.turma_id == turma_id,
                    models.AlunoTurma.aluno_id == aluno.id,
                    models.AlunoTurma.ativo.is_(True),
                )
                .with_for_update()
            )
            if vinculo is None:
                raise LookupError("Revisão indisponível.")
            existente = session.scalar(
                select(models.RevisaoPresencaWeb)
                .where(
                    models.RevisaoPresencaWeb.sessao_id == sessao_id,
                    models.RevisaoPresencaWeb.aluno_id == aluno.id,
                    models.RevisaoPresencaWeb.estado == "aberta",
                )
                .with_for_update()
            )
            if existente is not None:
                return _para_revisao(existente)
            tentativas = int(
                session.scalar(
                    select(func.count())
                    .select_from(models.TentativaPresencaWeb)
                    .where(
                        models.TentativaPresencaWeb.sessao_id == sessao_id,
                        models.TentativaPresencaWeb.aluno_id == aluno.id,
                    )
                )
                or 0
            )
            limite = self._limite_tentativas(session, sessao_id, aluno.id)
            ativa = session.scalar(
                select(models.TentativaPresencaWeb.id).where(
                    models.TentativaPresencaWeb.sessao_id == sessao_id,
                    models.TentativaPresencaWeb.aluno_id == aluno.id,
                    models.TentativaPresencaWeb.estado.in_(ESTADOS_TENTATIVA_ATIVA),
                )
            )
            if ativa is not None or (not via_acessivel and tentativas < limite):
                raise LookupError("Revisão indisponível.")
            presenca = session.scalar(
                select(models.Presenca)
                .where(
                    models.Presenca.sessao_id == sessao_id,
                    models.Presenca.aluno_id == aluno.id,
                )
                .with_for_update()
            )
            revisao = models.RevisaoPresencaWeb(
                id=uuid4(),
                turma_id=turma_id,
                sessao_id=sessao_id,
                aluno_id=aluno.id,
                estado="aberta",
                justificativa_solicitacao=motivo,
                via_acessivel=via_acessivel,
                solicitada_em=instante,
                versao_presenca_base=presenca.versao if presenca is not None else 0,
            )
            session.add(revisao)
            session.flush()
            self._auditar(
                session,
                ator_id=None,
                acao="revisao_presenca_solicitada",
                alvo_tipo="revisao_presenca",
                alvo_id=str(revisao.id),
                instante=instante,
                depois={"estado": "aberta", "via_acessivel": via_acessivel},
                request_id=request_id,
            )
            return _para_revisao(revisao)

    def listar_revisoes(
        self,
        ator: AtorWeb,
        turma_id: int,
        *,
        estado: str = "aberta",
        limite: int = 100,
    ) -> list[dict[str, object]]:
        if estado not in {"aberta", "decidida", "todas"} or not 1 <= limite <= 100:
            raise ValueError("Os filtros de revisão são inválidos.")
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            self._turma_autorizada(session, atual, turma_id)
            consulta = (
                select(
                    models.RevisaoPresencaWeb,
                    models.Aluno.matricula,
                    models.Aluno.nome,
                    models.Presenca.versao.label("versao_presenca"),
                )
                .join(
                    models.Aluno, models.Aluno.id == models.RevisaoPresencaWeb.aluno_id
                )
                .outerjoin(
                    models.Presenca,
                    (models.Presenca.sessao_id == models.RevisaoPresencaWeb.sessao_id)
                    & (models.Presenca.aluno_id == models.RevisaoPresencaWeb.aluno_id),
                )
                .where(models.RevisaoPresencaWeb.turma_id == turma_id)
                .order_by(
                    models.RevisaoPresencaWeb.solicitada_em,
                    models.RevisaoPresencaWeb.id,
                )
                .limit(limite)
            )
            if estado != "todas":
                consulta = consulta.where(models.RevisaoPresencaWeb.estado == estado)
            return [
                {
                    "id": str(row.id),
                    "sessao_id": row.sessao_id,
                    "aluno_id": row.aluno_id,
                    "matricula": matricula,
                    "nome": nome,
                    "estado": row.estado,
                    "justificativa_solicitacao": row.justificativa_solicitacao,
                    "via_acessivel": row.via_acessivel,
                    "solicitada_em": _utc_armazenado(row.solicitada_em).isoformat(),
                    "versao_presenca": int(versao or 0),
                    "decisao": row.decisao,
                    "justificativa_decisao": row.justificativa_decisao,
                    "decidida_em": (
                        _utc_armazenado(row.decidida_em).isoformat()
                        if row.decidida_em
                        else None
                    ),
                }
                for row, matricula, nome, versao in session.execute(consulta)
            ]

    def decidir_revisao(
        self,
        *,
        ator: AtorWeb,
        revisao_id: UUID,
        decisao: StatusPresenca,
        justificativa: str,
        versao_esperada: int,
        identidade_confirmada: bool = False,
        agora: dt.datetime,
        request_id: str | None = None,
    ) -> Presenca:
        instante = _utc(agora)
        motivo = _justificativa(justificativa)
        if not isinstance(identidade_confirmada, bool):
            raise ValueError("A confirmação de identidade é inválida.")
        if decisao is StatusPresenca.PRESENTE and not identidade_confirmada:
            raise ValueError(
                "Presença manual exige verificação independente da identidade."
            )
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            base = session.get(models.RevisaoPresencaWeb, revisao_id)
            if base is None:
                raise LookupError("Revisão não encontrada.")
            sessao = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(models.SessaoPresencaWeb.id == base.sessao_id)
                .with_for_update()
            )
            if sessao is None or sessao.turma_id != base.turma_id:
                raise LookupError("Revisão não encontrada.")
            self._turma_autorizada(session, atual, base.turma_id, bloquear=True)
            revisao = session.scalar(
                select(models.RevisaoPresencaWeb)
                .where(models.RevisaoPresencaWeb.id == revisao_id)
                .with_for_update()
            )
            if revisao is None or revisao.estado != "aberta":
                raise LookupError("Revisão não disponível.")
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(
                    models.AlunoTurma.turma_id == base.turma_id,
                    models.AlunoTurma.aluno_id == base.aluno_id,
                )
                .with_for_update()
            )
            if vinculo is None:
                raise LookupError("Revisão não disponível.")
            presenca = session.scalar(
                select(models.Presenca)
                .where(
                    models.Presenca.sessao_id == base.sessao_id,
                    models.Presenca.aluno_id == base.aluno_id,
                )
                .with_for_update()
            )
            versao_atual = presenca.versao if presenca is not None else 0
            if (
                versao_esperada != versao_atual
                or revisao.versao_presenca_base != versao_atual
            ):
                raise VersaoPresencaDesatualizada()
            antes: dict[str, object] | None = None
            if presenca is None:
                sessao_referencia = _utc_armazenado(sessao.inicio_em).astimezone(
                    self._timezone
                )
                presenca = models.Presenca(
                    aluno_id=base.aluno_id,
                    turma_id=base.turma_id,
                    sessao_id=base.sessao_id,
                    tentativa_id=None,
                    registrado_em=instante,
                    data_referencia=sessao_referencia.date(),
                    status=decisao.value,
                    origem=OrigemPresenca.MANUAL.value,
                    versao=1,
                    horario_evidencia=None,
                    corrigida_em=instante,
                    corrigida_por_conta_id=atual.conta_id,
                )
                session.add(presenca)
            else:
                antes = {
                    "status": presenca.status,
                    "origem": presenca.origem,
                    "versao": presenca.versao,
                }
                presenca.status = decisao.value
                presenca.versao += 1
                presenca.corrigida_em = instante
                presenca.corrigida_por_conta_id = atual.conta_id
            revisao.estado = "decidida"
            revisao.decisao = decisao.value
            revisao.justificativa_decisao = motivo
            revisao.decidida_em = instante
            revisao.decidida_por_conta_id = atual.conta_id
            session.flush()
            depois = {
                "status": presenca.status,
                "origem": presenca.origem,
                "versao": presenca.versao,
                "identidade_confirmada": identidade_confirmada,
            }
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="presenca_corrigida_manual",
                alvo_tipo="presenca",
                alvo_id=str(presenca.id),
                instante=instante,
                justificativa=motivo,
                antes=antes,
                depois=depois,
                request_id=request_id,
            )
            return _para_presenca(presenca)

    def consultar_painel(
        self, ator: AtorWeb, turma_id: int, *, atualizado_em: dt.datetime
    ) -> dict[str, object]:
        instante = _utc(atualizado_em)
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            turma = self._turma_autorizada(session, atual, turma_id)
            sessoes = session.scalars(
                select(models.SessaoPresencaWeb)
                .where(models.SessaoPresencaWeb.turma_id == turma_id)
                .order_by(models.SessaoPresencaWeb.inicio_em.desc())
                .limit(100)
            ).all()
            ids = [sessao.id for sessao in sessoes]
            if not ids:
                return {
                    "turma_id": turma.id,
                    "atualizado_em": instante.isoformat(),
                    "sessoes": [],
                }
            presencas = session.execute(
                select(
                    models.Presenca.sessao_id,
                    models.Presenca.status,
                    func.count(models.Presenca.id),
                )
                .where(models.Presenca.sessao_id.in_(ids))
                .group_by(models.Presenca.sessao_id, models.Presenca.status)
            )
            contagem_presencas: dict[int, dict[str, int]] = defaultdict(dict)
            for sessao_id, estado, quantidade in presencas:
                contagem_presencas[int(sessao_id)][str(estado)] = int(quantidade)
            revisoes = session.execute(
                select(
                    models.RevisaoPresencaWeb.sessao_id,
                    models.RevisaoPresencaWeb.estado,
                    func.count(models.RevisaoPresencaWeb.id),
                )
                .where(models.RevisaoPresencaWeb.sessao_id.in_(ids))
                .group_by(
                    models.RevisaoPresencaWeb.sessao_id,
                    models.RevisaoPresencaWeb.estado,
                )
            )
            contagem_revisoes: dict[int, dict[str, int]] = defaultdict(dict)
            for sessao_id, estado, quantidade in revisoes:
                contagem_revisoes[int(sessao_id)][str(estado)] = int(quantidade)
            tentativas = session.execute(
                select(
                    models.TentativaPresencaWeb.sessao_id,
                    models.TentativaPresencaWeb.estado,
                    func.count(models.TentativaPresencaWeb.id),
                )
                .where(models.TentativaPresencaWeb.sessao_id.in_(ids))
                .group_by(
                    models.TentativaPresencaWeb.sessao_id,
                    models.TentativaPresencaWeb.estado,
                )
            )
            contagem_tentativas: dict[int, dict[str, int]] = defaultdict(dict)
            for sessao_id, estado, quantidade in tentativas:
                contagem_tentativas[int(sessao_id)][str(estado)] = int(quantidade)
            return {
                "turma_id": turma.id,
                "atualizado_em": instante.isoformat(),
                "sessoes": [
                    {
                        "id": sessao.id,
                        "titulo": sessao.titulo,
                        "inicio_em": _utc_armazenado(sessao.inicio_em).isoformat(),
                        "fim_em": _utc_armazenado(sessao.fim_em).isoformat(),
                        "revogada": sessao.revogada_em is not None,
                        "versao": sessao.versao,
                        "presencas_presentes": contagem_presencas[sessao.id].get(
                            "presente", 0
                        ),
                        "presencas_anuladas": contagem_presencas[sessao.id].get(
                            "anulada", 0
                        ),
                        "revisoes_abertas": contagem_revisoes[sessao.id].get(
                            "aberta", 0
                        ),
                        "tentativas_por_estado": dict(contagem_tentativas[sessao.id]),
                    }
                    for sessao in sessoes
                ],
            }

    def listar_presencas_sessao(
        self, ator: AtorWeb, turma_id: int, sessao_id: int
    ) -> list[dict[str, object]]:
        """Quem tem presença registrada na sessão; só identificação, sem biometria."""
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            self._turma_autorizada(session, atual, turma_id)
            self._exigir_sessao_da_turma(session, turma_id, sessao_id)
            linhas = session.execute(
                select(
                    models.Aluno.nome,
                    models.Aluno.matricula,
                    models.Presenca.status,
                    models.Presenca.origem,
                    models.Presenca.registrado_em,
                )
                .join(models.Aluno, models.Aluno.id == models.Presenca.aluno_id)
                .where(
                    models.Presenca.sessao_id == sessao_id,
                    models.Presenca.turma_id == turma_id,
                )
                .order_by(models.Aluno.nome, models.Aluno.matricula)
            )
            return [
                {
                    "nome": linha.nome,
                    "matricula": linha.matricula,
                    "status": linha.status,
                    "origem": linha.origem,
                    "registrado_em": _utc_armazenado(linha.registrado_em).isoformat(),
                }
                for linha in linhas
            ]

    def listar_presencas_exportacao(
        self,
        ator: AtorWeb,
        *,
        turma_id: int,
        inicio: dt.date | None = None,
        fim: dt.date | None = None,
        sessao_id: int | None = None,
    ) -> list[dict[str, object]]:
        filtros = [models.Presenca.turma_id == turma_id]
        if inicio is not None:
            filtros.append(models.Presenca.data_referencia >= inicio)
        if fim is not None:
            filtros.append(models.Presenca.data_referencia <= fim)
        if sessao_id is not None:
            filtros.append(models.Presenca.sessao_id == sessao_id)
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            self._turma_autorizada(session, atual, turma_id)
            if sessao_id is not None:
                self._exigir_sessao_da_turma(session, turma_id, sessao_id)
            linhas = session.execute(
                select(
                    models.Presenca.id,
                    models.Presenca.turma_id,
                    models.Turma.materia,
                    models.Turma.periodo,
                    models.Presenca.sessao_id,
                    models.Presenca.data_referencia,
                    models.Presenca.registrado_em,
                    models.Presenca.horario_evidencia,
                    models.Presenca.corrigida_em,
                    models.Aluno.matricula,
                    models.Aluno.nome,
                    models.Presenca.status,
                    models.Presenca.origem,
                )
                .join(models.Aluno, models.Aluno.id == models.Presenca.aluno_id)
                .join(models.Turma, models.Turma.id == models.Presenca.turma_id)
                .where(*filtros)
                .order_by(
                    models.Presenca.data_referencia,
                    models.Presenca.registrado_em,
                    models.Presenca.id,
                )
            )
            return [
                {
                    "turma_id": turma_id,
                    "materia": row.materia,
                    "periodo": row.periodo,
                    "sessao_id": row.sessao_id,
                    "data_referencia": row.data_referencia,
                    "registrado_em": _utc_armazenado(row.registrado_em),
                    "horario_evidencia": (
                        _utc_armazenado(row.horario_evidencia)
                        if row.horario_evidencia is not None
                        else None
                    ),
                    "horario_correcao": (
                        _utc_armazenado(row.corrigida_em)
                        if row.corrigida_em is not None
                        else None
                    ),
                    "corrigida_em": row.corrigida_em,
                    "matricula": row.matricula,
                    "nome": row.nome,
                    "status": row.status,
                    "origem": row.origem,
                }
                for row in linhas
            ]

    def reativar_quota(
        self,
        *,
        ator: AtorWeb,
        turma_id: int,
        sessao_id: int,
        aluno_id: int,
        confirmar: bool,
        justificativa: str,
        agora: dt.datetime,
        request_id: str | None = None,
    ) -> int:
        instante = _utc(agora)
        motivo = _justificativa(justificativa)
        if not confirmar:
            raise ValueError("Confirme explicitamente a reativação da quota.")
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            if atual.papel != "admin":
                raise PermissionError("Somente admin pode reativar quota.")
            self._turma_autorizada(session, atual, turma_id, bloquear=True)
            sessao = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(
                    models.SessaoPresencaWeb.id == sessao_id,
                    models.SessaoPresencaWeb.turma_id == turma_id,
                )
                .with_for_update()
            )
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(
                    models.AlunoTurma.turma_id == turma_id,
                    models.AlunoTurma.aluno_id == aluno_id,
                    models.AlunoTurma.ativo.is_(True),
                )
                .with_for_update()
            )
            if sessao is None or vinculo is None:
                raise LookupError("Quota indisponível.")
            alvo = f"{sessao_id}:{aluno_id}"
            quantidade = int(
                session.scalar(
                    select(func.count())
                    .select_from(models.TentativaPresencaWeb)
                    .where(
                        models.TentativaPresencaWeb.sessao_id == sessao_id,
                        models.TentativaPresencaWeb.aluno_id == aluno_id,
                    )
                )
                or 0
            )
            limite = self._limite_tentativas(session, sessao_id, aluno_id)
            presenca = session.scalar(
                select(models.Presenca.id).where(
                    models.Presenca.sessao_id == sessao_id,
                    models.Presenca.aluno_id == aluno_id,
                )
            )
            revisao_aberta = session.scalar(
                select(models.RevisaoPresencaWeb.id).where(
                    models.RevisaoPresencaWeb.sessao_id == sessao_id,
                    models.RevisaoPresencaWeb.aluno_id == aluno_id,
                    models.RevisaoPresencaWeb.estado == "aberta",
                )
            )
            if (
                quantidade < limite
                or presenca is not None
                or revisao_aberta is not None
            ):
                raise LookupError("Quota indisponível.")
            novo_limite = limite + 3
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="quota_presenca_reativada",
                alvo_tipo="sessao_aluno",
                alvo_id=alvo,
                instante=instante,
                justificativa=motivo,
                antes={"tentativas_emitidas": quantidade, "limite": limite},
                depois={"limite": novo_limite},
                request_id=request_id,
            )
            return novo_limite

    def excluir_aluno_global(
        self,
        *,
        ator: AtorWeb,
        aluno_id: int,
        confirmacao: str,
        justificativa: str,
        agora: dt.datetime,
        request_id: str | None,
        armazenamento_referencias_disponivel: bool,
        armazenamento_legado_disponivel: bool,
        armazenamento_capturas_disponivel: bool,
    ) -> dict[str, object]:
        if isinstance(aluno_id, bool) or aluno_id <= 0:
            raise LookupError("Aluno não encontrado.")
        if confirmacao != f"EXCLUIR-ALUNO-{aluno_id}":
            raise ValueError("A confirmação não corresponde ao aluno selecionado.")
        motivo = _justificativa(justificativa)
        instante = _utc(agora)
        with self._factory() as session, session.begin():
            atual = self._ator_atual(session, ator)
            if atual.papel != "admin":
                raise PermissionError("Exclusão global exige perfil administrativo.")

            sessoes_ids = tuple(
                session.scalars(
                    select(models.TentativaPresencaWeb.sessao_id)
                    .where(models.TentativaPresencaWeb.aluno_id == aluno_id)
                    .distinct()
                    .order_by(models.TentativaPresencaWeb.sessao_id)
                )
            )
            if sessoes_ids:
                session.scalars(
                    select(models.SessaoPresencaWeb)
                    .where(models.SessaoPresencaWeb.id.in_(sessoes_ids))
                    .order_by(models.SessaoPresencaWeb.id)
                    .with_for_update()
                ).all()

            # O cadastro aprovado deixa a solicitação sem aluno_id (com nome e
            # matrícula); o vínculo com o aluno fica no conjunto de referências.
            solicitacao_ids = tuple(
                session.scalars(
                    select(models.SolicitacaoCadastroWeb.id)
                    .where(
                        or_(
                            models.SolicitacaoCadastroWeb.aluno_id == aluno_id,
                            models.SolicitacaoCadastroWeb.id.in_(
                                select(
                                    models.ConjuntoReferenciasWeb.solicitacao_id
                                ).where(
                                    models.ConjuntoReferenciasWeb.aluno_id == aluno_id
                                )
                            ),
                        )
                    )
                    .order_by(models.SolicitacaoCadastroWeb.id)
                )
            )
            # Jobs de cadastro das solicitações, inclusive envios recusados que
            # reabriram a coleta (a solicitação já não aponta para eles).
            solicitacoes_jobs = (
                tuple(
                    session.scalars(
                        select(models.JobFacialWeb.id).where(
                            models.JobFacialWeb.tipo == "cadastro",
                            models.JobFacialWeb.dono_id.in_(
                                [str(item) for item in solicitacao_ids]
                            ),
                        )
                    )
                )
                if solicitacao_ids
                else ()
            )
            tentativa_ids = tuple(
                session.scalars(
                    select(models.TentativaPresencaWeb.id).where(
                        models.TentativaPresencaWeb.aluno_id == aluno_id
                    )
                )
            )
            job_ids = set(tentativa_ids)
            job_ids.update(job_id for job_id in solicitacoes_jobs if job_id is not None)
            jobs = (
                session.scalars(
                    select(models.JobFacialWeb)
                    .where(models.JobFacialWeb.id.in_(job_ids))
                    .order_by(models.JobFacialWeb.id)
                    .with_for_update()
                ).all()
                if job_ids
                else []
            )
            if any(job.estado == "processando" for job in jobs):
                raise RuntimeError(
                    "Exclusão global aguarda a conclusão do processamento facial."
                )
            if tentativa_ids:
                session.scalars(
                    select(models.TentativaPresencaWeb)
                    .where(models.TentativaPresencaWeb.id.in_(tentativa_ids))
                    .order_by(models.TentativaPresencaWeb.id)
                    .with_for_update()
                ).all()
            if solicitacao_ids:
                session.scalars(
                    select(models.SolicitacaoCadastroWeb)
                    .where(models.SolicitacaoCadastroWeb.id.in_(solicitacao_ids))
                    .order_by(models.SolicitacaoCadastroWeb.id)
                    .with_for_update()
                ).all()

            aluno = session.scalar(
                select(models.Aluno)
                .where(models.Aluno.id == aluno_id)
                .with_for_update()
            )
            if aluno is None:
                raise LookupError("Aluno não encontrado.")
            caminhos_referencias = tuple(
                caminho
                for caminho in session.scalars(
                    select(models.ReferenciaFacialWeb.caminho_privado_relativo)
                    .join(
                        models.ConjuntoReferenciasWeb,
                        models.ConjuntoReferenciasWeb.id
                        == models.ReferenciaFacialWeb.conjunto_id,
                    )
                    .where(models.ConjuntoReferenciasWeb.aluno_id == aluno_id)
                )
                if caminho is not None
            )
            caminho_legado = aluno.foto_arquivo
            if caminhos_referencias and not armazenamento_referencias_disponivel:
                raise RuntimeError(
                    "O armazenamento privado de referências não está configurado."
                )
            if caminho_legado and not armazenamento_legado_disponivel:
                raise RuntimeError(
                    "O armazenamento legado de imagens não está configurado."
                )
            if job_ids and not armazenamento_capturas_disponivel:
                raise RuntimeError(
                    "O armazenamento temporário de capturas não está configurado."
                )

            quantidades = {
                "vinculos": int(
                    session.scalar(
                        select(func.count())
                        .select_from(models.AlunoTurma)
                        .where(models.AlunoTurma.aluno_id == aluno_id)
                    )
                    or 0
                ),
                "presencas": int(
                    session.scalar(
                        select(func.count())
                        .select_from(models.Presenca)
                        .where(models.Presenca.aluno_id == aluno_id)
                    )
                    or 0
                ),
                "conjuntos_referencia": int(
                    session.scalar(
                        select(func.count())
                        .select_from(models.ConjuntoReferenciasWeb)
                        .where(models.ConjuntoReferenciasWeb.aluno_id == aluno_id)
                    )
                    or 0
                ),
            }
            session.execute(
                delete(models.RevisaoPresencaWeb).where(
                    models.RevisaoPresencaWeb.aluno_id == aluno_id
                )
            )
            session.execute(
                delete(models.Presenca).where(models.Presenca.aluno_id == aluno_id)
            )
            if job_ids:
                session.execute(
                    delete(models.DesafioVerificacaoWeb).where(
                        models.DesafioVerificacaoWeb.id.in_(job_ids)
                    )
                )
            session.execute(
                delete(models.TentativaPresencaWeb).where(
                    models.TentativaPresencaWeb.aluno_id == aluno_id
                )
            )
            session.execute(
                delete(models.ConjuntoReferenciasWeb).where(
                    models.ConjuntoReferenciasWeb.aluno_id == aluno_id
                )
            )
            session.execute(
                delete(models.SolicitacaoCadastroWeb).where(
                    models.SolicitacaoCadastroWeb.id.in_(solicitacao_ids)
                )
            )
            if job_ids:
                session.execute(
                    delete(models.JobFacialWeb).where(
                        models.JobFacialWeb.id.in_(job_ids)
                    )
                )
            session.delete(aluno)
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="aluno_excluido_globalmente",
                alvo_tipo="aluno",
                alvo_id=str(aluno_id),
                instante=instante,
                justificativa=motivo,
                antes=quantidades,
                depois={"excluido": True},
                request_id=request_id,
            )
            return {
                "caminhos_referencias": caminhos_referencias,
                "caminho_legado": caminho_legado,
                "jobs_temporarios": tuple(str(job_id) for job_id in job_ids),
            }

    @staticmethod
    def _turma_payload(turma: models.Turma) -> dict[str, object]:
        return {
            "id": turma.id,
            "materia": turma.materia,
            "periodo": turma.periodo,
            "responsavel_professor_id": turma.responsavel_professor_id,
            "ativa": turma.excluida_em is None,
            "criado_em": _utc_armazenado(turma.criado_em).isoformat(),
            "atualizado_em": _utc_armazenado(turma.atualizado_em).isoformat(),
        }

    @staticmethod
    def _professor_ativo(session: Session, professor_id: int) -> models.ProfessorWeb:
        professor = session.scalar(
            select(models.ProfessorWeb)
            .join(models.ContaWeb, models.ContaWeb.id == models.ProfessorWeb.conta_id)
            .where(
                models.ProfessorWeb.id == professor_id,
                models.ContaWeb.papel == "professor",
                models.ContaWeb.ativa.is_(True),
                models.ContaWeb.troca_senha_obrigatoria.is_(False),
            )
        )
        if professor is None:
            raise LookupError("Professor responsável não encontrado.")
        return professor

    @staticmethod
    def _turma_autorizada(
        session: Session,
        ator: AtorWeb,
        turma_id: int,
        *,
        bloquear: bool = False,
        exigir_ativa: bool = False,
    ) -> models.Turma:
        consulta = select(models.Turma).where(models.Turma.id == turma_id)
        if bloquear:
            consulta = consulta.with_for_update()
        turma = session.scalar(consulta)
        if turma is None or (exigir_ativa and turma.excluida_em is not None):
            raise LookupError("Turma não encontrada.")
        AutorizarTurma.exigir(ator, turma, "gerenciar turma web")
        return turma

    @staticmethod
    def _exigir_sessao_da_turma(
        session: Session, turma_id: int, sessao_id: int
    ) -> None:
        existe = session.scalar(
            select(models.SessaoPresencaWeb.id).where(
                models.SessaoPresencaWeb.id == sessao_id,
                models.SessaoPresencaWeb.turma_id == turma_id,
            )
        )
        if existe is None:
            raise LookupError("Sessão não encontrada.")

    @staticmethod
    def _ator_atual(session: Session, ator: AtorWeb) -> AtorWeb:
        conta = session.scalar(
            select(models.ContaWeb)
            .where(models.ContaWeb.id == ator.conta_id)
            .with_for_update()
        )
        if conta is None or not conta.ativa or conta.troca_senha_obrigatoria:
            raise PermissionError("Conta não autorizada.")
        professor = session.scalar(
            select(models.ProfessorWeb)
            .where(models.ProfessorWeb.conta_id == conta.id)
            .with_for_update()
        )
        return AtorWeb(
            conta_id=conta.id,
            papel=conta.papel,
            ativa=conta.ativa,
            troca_senha_obrigatoria=conta.troca_senha_obrigatoria,
            professor_id=professor.id if professor else None,
        )

    @staticmethod
    def _limite_tentativas(session: Session, sessao_id: int, aluno_id: int) -> int:
        eventos = int(
            session.scalar(
                select(func.count())
                .select_from(models.EventoAuditoriaWeb)
                .where(
                    models.EventoAuditoriaWeb.acao == "quota_presenca_reativada",
                    models.EventoAuditoriaWeb.alvo_tipo == "sessao_aluno",
                    models.EventoAuditoriaWeb.alvo_id == f"{sessao_id}:{aluno_id}",
                )
            )
            or 0
        )
        return 3 * (eventos + 1)

    @staticmethod
    def _auditar(
        session: Session,
        *,
        ator_id: int | None,
        acao: str,
        alvo_tipo: str,
        alvo_id: str,
        instante: dt.datetime,
        justificativa: str | None = None,
        antes: Mapping[str, object] | None = None,
        depois: Mapping[str, object] | None = None,
        request_id: str | None = None,
    ) -> None:
        session.add(
            models.EventoAuditoriaWeb(
                ator_conta_id=ator_id,
                acao=acao,
                alvo_tipo=alvo_tipo,
                alvo_id=alvo_id,
                instante=_utc(instante),
                justificativa=justificativa,
                antes=dict(antes) if antes is not None else None,
                depois=dict(depois) if depois is not None else None,
                request_id=request_id,
            )
        )
