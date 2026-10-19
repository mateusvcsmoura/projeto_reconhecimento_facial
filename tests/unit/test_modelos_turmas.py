from __future__ import annotations

from src.infrastructure.database import models


def test_turma_metadata_expressa_regras_de_materia_e_periodo() -> None:
    tabela = models.Turma.__table__

    assert tabela.c.materia.type.length == 120
    assert tabela.c.periodo.type.length == 10
    checks = {
        str(constraint.sqltext)
        for constraint in tabela.constraints
        if hasattr(constraint, "sqltext")
    }
    assert any("btrim(materia)" in check for check in checks)
    assert any(
        "periodo" in check and "matutino" in check and "noturno" in check
        for check in checks
    )
    assert tabela.c.excluida_em.nullable


def test_vinculo_tem_pk_composta_estado_coerente_e_indices_reversos() -> None:
    tabela = models.AlunoTurma.__table__

    assert [col.name for col in tabela.primary_key.columns] == ["turma_id", "aluno_id"]
    assert tabela.c.ativo.server_default is not None
    checks = {
        str(constraint.sqltext)
        for constraint in tabela.constraints
        if hasattr(constraint, "sqltext")
    }
    assert any("desvinculado_em" in check and "ativo" in check for check in checks)
    assert any(
        index.name == "ix_aluno_turma_aluno_id"
        and [col.name for col in index.columns] == ["aluno_id"]
        for index in tabela.indexes
    )


def test_presenca_permita_legado_e_separe_unicidade_por_turma() -> None:
    tabela = models.Presenca.__table__

    assert tabela.c.turma_id.nullable
    assert "uq_presencas_aluno_dia" not in {
        constraint.name for constraint in tabela.constraints
    }
    assert "uq_presencas_turma_aluno_dia" in {index.name for index in tabela.indexes}
    assert "uq_presencas_turma_aluno_dia" not in {
        constraint.name for constraint in tabela.constraints
    }
    indice_legado = next(
        index
        for index in tabela.indexes
        if index.name == "uq_presencas_legado_aluno_dia"
    )
    assert indice_legado.unique
    assert "sessao_id IS NULL" in str(
        indice_legado.dialect_options["postgresql"]["where"]
    )
    assert "turma_id IS NULL" in str(
        indice_legado.dialect_options["postgresql"]["where"]
    )
    assert "uq_presencas_sessao_aluno" in {index.name for index in tabela.indexes}
    fks = {constraint.name: constraint for constraint in tabela.foreign_key_constraints}
    assert fks["fk_presencas_turma_id_turmas"].ondelete == "RESTRICT"
    assert fks["fk_presencas_turma_aluno_aluno_turma"].ondelete == "CASCADE"
