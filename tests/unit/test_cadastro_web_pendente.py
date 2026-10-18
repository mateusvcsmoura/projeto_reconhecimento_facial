"""Contratos de integridade do cadastro web pendente."""

from sqlalchemy import UniqueConstraint

from src.infrastructure.database import models


def test_schema_declara_solicitacoes_e_referencias_versionadas() -> None:
    tabelas = models.Base.metadata.tables

    assert "solicitacoes_cadastro_web" in tabelas
    assert "conjuntos_referencias_web" in tabelas
    assert "referencias_faciais_web" in tabelas


def test_matricula_pendente_nao_fica_reservada_globalmente() -> None:
    tabela = models.Base.metadata.tables["solicitacoes_cadastro_web"]

    assert tabela.c.matricula.nullable is True
    assert not any(
        isinstance(constraint, UniqueConstraint)
        and tuple(constraint.columns.keys()) == ("matricula",)
        for constraint in tabela.constraints
    )


def test_conjunto_tem_no_maximo_uma_versao_ativa_por_aluno() -> None:
    tabela = models.Base.metadata.tables["conjuntos_referencias_web"]
    indice = next(
        index
        for index in tabela.indexes
        if index.name == "uq_conjuntos_referencias_web_aluno_ativo"
    )

    assert indice.unique is True
    assert tuple(column.name for column in indice.columns) == ("aluno_id",)
    assert str(indice.dialect_options["postgresql"]["where"]) == "estado = 'ativo'"


def test_referencia_tem_recorte_privado_embedding_e_consentimento() -> None:
    tabela = models.Base.metadata.tables["referencias_faciais_web"]

    assert tabela.c.caminho_privado_relativo.nullable is False
    assert tabela.c.embedding.nullable is False
    assert tabela.c.embedding_modelo.nullable is False
    assert tabela.c.embedding_dim.nullable is False
    assert tabela.c.consentimento_em.nullable is False
    assert tabela.c.consentimento_versao.nullable is False


def test_schema_preserva_colunas_biometricas_legadas_do_aluno() -> None:
    tabela = models.Base.metadata.tables["alunos"]

    assert {"foto_arquivo", "embedding", "embedding_modelo", "embedding_dim"} <= set(
        tabela.c.keys()
    )


def test_solicitacao_nao_contem_dados_biometricos() -> None:
    tabela = models.Base.metadata.tables["solicitacoes_cadastro_web"]

    assert not {
        "foto_arquivo",
        "caminho_privado_relativo",
        "embedding",
        "embedding_modelo",
        "embedding_dim",
        "url",
    } & set(tabela.c.keys())


def test_ordinais_de_referencia_sao_limitados_a_tres() -> None:
    tabela = models.Base.metadata.tables["referencias_faciais_web"]
    constraint = next(
        item
        for item in tabela.constraints
        if getattr(item, "name", None) == "ck_referencias_faciais_web_ordinal_valido"
    )

    assert "ordinal BETWEEN 1 AND 3" in str(constraint.sqltext)
