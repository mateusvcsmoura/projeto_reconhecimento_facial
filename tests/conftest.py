"""Fixtures dos testes de integracao da Fase 1.

Os testes rodam contra um PostgreSQL real (TEST_DATABASE_URL), que precisa
ser diferente do banco de desenvolvimento: o schema e criado e destruido
pelas migrations a cada sessao.

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

from src.config.settings import get_settings  # noqa: E402
from src.infrastructure.database.engine import criar_engine  # noqa: E402


def _test_database_url() -> str:
    url = get_settings().test_database_url
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL nao definida. Suba o banco com "
            "'docker compose up -d' e configure o .env."
        )
    return url


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
    return _test_database_url()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """Aplica as migrations na entrada e desfaz na saida."""
    _alembic("downgrade", "base", url=database_url)  # limpa resíduo de execucao anterior
    _alembic("upgrade", "head", url=database_url)

    motor = criar_engine(database_url)
    try:
        yield motor
    finally:
        motor.dispose()
        _alembic("downgrade", "base", url=database_url)


@pytest.fixture
def banco_limpo(engine: Engine) -> Iterator[Engine]:
    """Zera as tabelas entre testes, preservando o schema."""
    with engine.begin() as conexao:
        conexao.execute(text("TRUNCATE presencas, alunos RESTART IDENTITY CASCADE"))
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
