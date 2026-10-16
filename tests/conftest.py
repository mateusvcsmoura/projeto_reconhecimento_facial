"""Fixtures dos testes de integracao da Fase 1.

Os testes rodam contra um PostgreSQL explicitamente descartavel. Antes de
qualquer migration/limpeza exigem opt-in e comentario identificador no banco.

Nenhum teste usa o escola.db real. Os dados legados de teste sao sinteticos,
para que dado biometrico/pessoal nunca entre na suite nem no Git.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.database.engine import criar_engine  # noqa: E402

VAR_URL = "FACE_TURMAS_TEST_DATABASE_URL"
VAR_AUTORIZACAO = "FACE_TURMAS_TEST_DB_AUTORIZACAO"
TOKEN_AUTORIZACAO = "AUTORIZO_DESTRUIR_BANCO_DESCARTAVEL_TASK_008"
COMENTARIO_BANCO = "projeto_reconhecimento_facial: task 008 disposable test database"


def _test_database_url() -> str:
    if os.environ.get(VAR_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip(
            "Integracao PostgreSQL desabilitada: exige opt-in explicito para "
            "banco descartavel da tarefa 008."
        )
    url = os.environ.get(VAR_URL)
    if not url:
        pytest.skip(f"{VAR_URL} nao definida; nenhum .env e consultado.")
    return url


def _validar_banco_descartavel(url: str) -> None:
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            comentario = conexao.execute(
                text(
                    "SELECT shobj_description(oid, 'pg_database') "
                    "FROM pg_database WHERE datname = current_database()"
                )
            ).scalar_one_or_none()
        if comentario != COMENTARIO_BANCO:
            raise RuntimeError(
                "Banco recusado antes de DDL: o comentario nao confirma "
                "o marcador descartavel esperado."
            )
    finally:
        motor.dispose()


def _identidade_banco(url: str) -> tuple[str, str | None, int | None]:
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            nome, endereco, porta = conexao.execute(
                text(
                    "SELECT current_database(), inet_server_addr()::text, "
                    "inet_server_port()"
                )
            ).one()
        return str(nome), endereco, porta
    finally:
        motor.dispose()


def _alembic(*args: str, url: str) -> None:
    ambiente = {**os.environ, "ALEMBIC_DATABASE_URL": url}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=ambiente,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            f"alembic {' '.join(args)} falhou:\n{resultado.stdout}\n{resultado.stderr}"
        )


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_database_url()
    _validar_banco_descartavel(url)
    return url


@pytest.fixture(scope="session")
def migration_database_url() -> str:
    if os.environ.get(VAR_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip("Teste de migration exige opt-in explicito task 008.")
    url = os.environ.get("FACE_TURMAS_MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("FACE_TURMAS_MIGRATION_DATABASE_URL nao definida.")
    if url == os.environ.get(VAR_URL):
        raise RuntimeError(
            "O banco dedicado de migration nao pode ser o banco "
            "compartilhado de integracao."
        )
    _validar_banco_descartavel(url)
    banco_compartilhado = os.environ.get(VAR_URL)
    if banco_compartilhado and _identidade_banco(url) == _identidade_banco(
        banco_compartilhado
    ):
        raise RuntimeError(
            "A migration exige um banco fisicamente separado do banco "
            "compartilhado de integracao."
        )
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """Aplica as migrations na entrada e desfaz na saida."""
    motor = criar_engine(database_url)
    migrations_started = False
    try:
        _validar_banco_descartavel(database_url)

        # O opt-in e o marcador foram validados antes de qualquer DDL.
        migrations_started = True
        _alembic("downgrade", "base", url=database_url)
        _alembic("upgrade", "head", url=database_url)
        yield motor
    finally:
        try:
            if migrations_started:
                _alembic("downgrade", "base", url=database_url)
        finally:
            motor.dispose()


@pytest.fixture
def banco_limpo(engine: Engine) -> Iterator[Engine]:
    """Zera as tabelas entre testes, preservando o schema."""
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "TRUNCATE presencas, aluno_turma, turmas, alunos "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield engine


@pytest.fixture
def sqlite_legado(tmp_path: Path) -> Path:
    """SQLite sintetico com o MESMO formato do banco legado real.

    Reproduz de proposito os defeitos encontrados no escola.db original:
      * schema sem NOT NULL e sem FOREIGN KEY;
      * data_hora como TEXT em dd/mm/aaaa;
      * varias presencas do mesmo aluno no mesmo dia;
      * foto_path absoluto apontando para arquivo inexistente.
    """
    caminho = tmp_path / "legado.db"
    conexao = sqlite3.connect(caminho)
    conexao.executescript(
        """
        CREATE TABLE alunos
            (id INTEGER PRIMARY KEY, nome TEXT, foto_path TEXT, biometria_id INTEGER);
        CREATE TABLE presencas
            (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, data_hora TEXT);
        """
    )
    conexao.executemany(
        "INSERT INTO alunos (id, nome, foto_path, biometria_id) VALUES (?, ?, ?, ?)",
        [
            (1, "Aluno Um", r"C:\Users\OUTRO\AppData\Local\Temp\um.jpg", 1),
            (2, "Aluno Dois", r"C:\Users\OUTRO\AppData\Local\Temp\dois.jpg", 2),
        ],
    )
    conexao.executemany(
        "INSERT INTO presencas (aluno_id, data_hora) VALUES (?, ?)",
        [
            # Aluno 1: tres marcacoes no MESMO dia (fora de ordem cronologica,
            # para provar que sobrevive a mais antiga).
            (1, "10/03/2026 09:15:00"),
            (1, "10/03/2026 08:00:00"),
            (1, "10/03/2026 08:00:30"),
            # Aluno 1: outro dia -> deve virar uma segunda presenca.
            (1, "11/03/2026 08:05:00"),
            # Aluno 2: um dia.
            (2, "10/03/2026 07:50:00"),
            # Formato ISO, gravado pela versao atual do cadastro.py.
            (2, "2026-03-11 07:55:00"),
        ],
    )
    conexao.commit()
    conexao.close()
    return caminho
