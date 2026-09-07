"""Fase 1 -- ETL do SQLite legado para o PostgreSQL.

Usa um SQLite sintetico que reproduz os defeitos do banco real (data em
dd/mm/aaaa, varias presencas no mesmo dia, foto_path absoluto quebrado),
sem colocar dado pessoal ou biometrico na suite.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, text

from scripts.import_legacy_sqlite import (
    DryRunConcluido,
    ErroDeMigracao,
    converter_data_hora,
    migrar,
    resolver_foto,
)

TZ = ZoneInfo("America/Sao_Paulo")


# --------------------------------------------------------------------------
# Conversao de data -- unitario, sem banco
# --------------------------------------------------------------------------


def test_converte_formato_legado_dd_mm_aaaa() -> None:
    momento = converter_data_hora("10/03/2026 08:00:00", TZ)
    assert momento.date() == dt.date(2026, 3, 10)
    assert (momento.hour, momento.minute) == (8, 0)
    assert momento.tzinfo is not None


def test_converte_formato_iso_da_versao_atual() -> None:
    momento = converter_data_hora("2026-03-10 08:00:00", TZ)
    assert momento.date() == dt.date(2026, 3, 10)


def test_recusa_formato_desconhecido_em_vez_de_adivinhar() -> None:
    """Data ambigua nao pode ser 'consertada' por chute."""
    with pytest.raises(ValueError, match="formato de data nao reconhecido"):
        converter_data_hora("2026/03/10T08:00", TZ)


def test_recusa_data_vazia() -> None:
    with pytest.raises(ValueError):
        converter_data_hora("", TZ)


# --------------------------------------------------------------------------
# Resolucao de foto
# --------------------------------------------------------------------------


def test_foto_inexistente_vira_nulo_com_motivo(tmp_path: Path) -> None:
    valor, motivo = resolver_foto(r"C:\Users\OUTRO\Temp\ausente.jpg", tmp_path)
    assert valor is None
    assert motivo is not None


def test_foto_presente_no_storage_vira_caminho_relativo(tmp_path: Path) -> None:
    (tmp_path / "aluno.jpg").write_bytes(b"conteudo-sintetico")
    valor, motivo = resolver_foto(r"C:\Users\OUTRO\Temp\aluno.jpg", tmp_path)
    assert valor == "aluno.jpg"
    assert motivo is None


# --------------------------------------------------------------------------
# ETL completo -- integracao com PostgreSQL
# --------------------------------------------------------------------------


def test_dry_run_nao_grava_nada(
    banco_limpo: Engine, database_url: str, sqlite_legado: Path, tmp_path: Path
) -> None:
    with pytest.raises(DryRunConcluido) as capturado:
        migrar(
            sqlite_legado,
            database_url,
            aplicar=False,
            tz=TZ,
            storage_dir=tmp_path,
        )

    relatorio = capturado.value.relatorio
    assert relatorio.dry_run is True
    assert relatorio.alunos_lidos == 2

    with banco_limpo.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM alunos")).scalar_one() == 0
        assert conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one() == 0


def test_migra_alunos_e_presencas(
    banco_limpo: Engine, database_url: str, sqlite_legado: Path, tmp_path: Path
) -> None:
    relatorio = migrar(
        sqlite_legado, database_url, aplicar=True, tz=TZ, storage_dir=tmp_path
    )

    assert relatorio.alunos_lidos == 2
    assert relatorio.alunos_inseridos == 2

    # 6 linhas legadas -> 4 dias distintos (aluno 1: 10/03 e 11/03;
    # aluno 2: 10/03 e 11/03). As 2 repeticoes do aluno 1 em 10/03 sao
    # colapsadas pela regra "uma presenca por dia".
    assert relatorio.presencas_lidas == 6
    assert relatorio.presencas_inseridas == 4
    assert relatorio.presencas_ja_existentes == 2
    assert relatorio.presencas_rejeitadas == 0

    with banco_limpo.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM alunos")).scalar_one() == 2
        assert conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one() == 4


def test_nenhum_registro_e_perdido_em_silencio(
    banco_limpo: Engine, database_url: str, sqlite_legado: Path, tmp_path: Path
) -> None:
    """Toda linha lida termina em uma das contagens, e nao apenas some."""
    relatorio = migrar(
        sqlite_legado, database_url, aplicar=True, tz=TZ, storage_dir=tmp_path
    )

    contabilizadas = (
        relatorio.presencas_inseridas
        + relatorio.presencas_ja_existentes
        + relatorio.presencas_rejeitadas
    )
    assert contabilizadas == relatorio.presencas_lidas

    # E cada linha nao inserida aparece no relatorio, com o conteudo original.
    nao_inseridas = [
        o
        for o in relatorio.ocorrencias
        if o["nivel"] in {"erro", "aviso"} and "legado" in o
    ]
    assert len(nao_inseridas) == relatorio.presencas_ja_existentes
    assert all("data_hora" in o["legado"] for o in nao_inseridas)


def test_relacionamento_aluno_presenca_e_preservado(
    banco_limpo: Engine, database_url: str, sqlite_legado: Path, tmp_path: Path
) -> None:
    migrar(sqlite_legado, database_url, aplicar=True, tz=TZ, storage_dir=tmp_path)

    with banco_limpo.connect() as conexao:
        por_matricula = dict(
            conexao.execute(
                text(
                    "SELECT a.matricula, count(p.id)"
                    " FROM alunos a LEFT JOIN presencas p ON p.aluno_id = a.id"
                    " GROUP BY a.matricula"
                )
            ).all()
        )

    assert por_matricula == {"1": 2, "2": 2}


def test_data_e_hora_sao_preservadas(
    banco_limpo: Engine, database_url: str, sqlite_legado: Path, tmp_path: Path
) -> None:
    """Entre as repeticoes do mesmo dia, sobrevive a marcacao mais antiga."""
    migrar(sqlite_legado, database_url, aplicar=True, tz=TZ, storage_dir=tmp_path)

    with banco_limpo.connect() as conexao:
        linha = conexao.execute(
            text(
                "SELECT p.data_referencia, p.registrado_em"
                " FROM presencas p JOIN alunos a ON a.id = p.aluno_id"
                " WHERE a.matricula = '1' AND p.data_referencia = DATE '2026-03-10'"
            )
        ).one()

    data_referencia, registrado_em = linha
    assert data_referencia == dt.date(2026, 3, 10)
    # Origem tinha 09:15:00, 08:00:00 e 08:00:30 nesse dia.
    assert registrado_em.astimezone(TZ).strftime("%H:%M:%S") == "08:00:00"


def test_foto_absoluta_do_legado_nao_e_copiada_as_cegas(
    banco_limpo: Engine, database_url: str, sqlite_legado: Path, tmp_path: Path
) -> None:
    migrar(sqlite_legado, database_url, aplicar=True, tz=TZ, storage_dir=tmp_path)

    with banco_limpo.connect() as conexao:
        fotos = conexao.execute(text("SELECT foto_arquivo FROM alunos")).scalars().all()

    assert all(valor is None for valor in fotos)


def test_reexecucao_nao_duplica(
    banco_limpo: Engine, database_url: str, sqlite_legado: Path, tmp_path: Path
) -> None:
    migrar(sqlite_legado, database_url, aplicar=True, tz=TZ, storage_dir=tmp_path)
    segunda = migrar(
        sqlite_legado, database_url, aplicar=True, tz=TZ, storage_dir=tmp_path
    )

    assert segunda.alunos_inseridos == 0
    assert segunda.alunos_ja_existentes == 2
    assert segunda.presencas_inseridas == 0
    assert segunda.presencas_ja_existentes == 6

    with banco_limpo.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM alunos")).scalar_one() == 2
        assert conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one() == 4


def test_sqlite_de_origem_nao_e_alterado(
    banco_limpo: Engine, database_url: str, sqlite_legado: Path, tmp_path: Path
) -> None:
    antes = sqlite_legado.read_bytes()
    migrar(sqlite_legado, database_url, aplicar=True, tz=TZ, storage_dir=tmp_path)
    assert sqlite_legado.read_bytes() == antes
    assert sqlite_legado.is_file()


def test_arquivo_sqlite_ausente_gera_erro_claro(
    database_url: str, tmp_path: Path
) -> None:
    with pytest.raises(ErroDeMigracao, match="nao encontrado"):
        migrar(
            tmp_path / "nao-existe.db",
            database_url,
            aplicar=False,
            tz=TZ,
            storage_dir=tmp_path,
        )
