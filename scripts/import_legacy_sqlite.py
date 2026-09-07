"""ETL pontual: SQLite legado -> PostgreSQL.

    SQLite  ->  leitura  ->  validacao/transformacao  ->  PostgreSQL

Executado sob demanda, nunca pela aplicacao. O arquivo SQLite de origem e
aberto em modo somente leitura e jamais alterado ou removido.

Uso:
    # simulacao (padrao) -- nao escreve nada no PostgreSQL
    python -m scripts.import_legacy_sqlite --sqlite escola.db

    # execucao real
    python -m scripts.import_legacy_sqlite --sqlite escola.db --apply

Garantias:
  * transacao unica: ou tudo entra, ou nada entra;
  * idempotente: reexecutar nao duplica (alunos por matricula, presencas
    pela UNIQUE(aluno_id, data_referencia));
  * nada e descartado em silencio: toda linha nao migrada aparece no
    relatorio JSON, com o motivo e o conteudo original.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import get_settings
from src.infrastructure.database.engine import criar_engine, sessao
from src.infrastructure.database.models import Aluno, Presenca

# Formatos aceitos em presencas.data_hora. Sao os dois que o projeto
# comprovadamente gravou ao longo da sua historia. Qualquer outro e
# rejeitado: adivinhar dia/mes em data ambigua corromperia o registro.
FORMATOS_DATA = (
    "%d/%m/%Y %H:%M:%S",  # versao antiga (dados legados em escola.db)
    "%Y-%m-%d %H:%M:%S",  # versao atual do cadastro.py
)


@dataclass
class Relatorio:
    sqlite_path: str
    dry_run: bool
    alunos_lidos: int = 0
    alunos_inseridos: int = 0
    alunos_ja_existentes: int = 0
    alunos_rejeitados: int = 0
    presencas_lidas: int = 0
    presencas_inseridas: int = 0
    presencas_ja_existentes: int = 0
    presencas_rejeitadas: int = 0
    ocorrencias: list[dict[str, Any]] = field(default_factory=list)

    def registrar(self, nivel: str, motivo: str, **contexto: Any) -> None:
        self.ocorrencias.append({"nivel": nivel, "motivo": motivo, **contexto})

    def to_dict(self) -> dict[str, Any]:
        return {
            "gerado_em": dt.datetime.now(dt.UTC).isoformat(),
            "sqlite_path": self.sqlite_path,
            "dry_run": self.dry_run,
            "alunos": {
                "lidos": self.alunos_lidos,
                "inseridos": self.alunos_inseridos,
                "ja_existentes": self.alunos_ja_existentes,
                "rejeitados": self.alunos_rejeitados,
            },
            "presencas": {
                "lidas": self.presencas_lidas,
                "inseridas": self.presencas_inseridas,
                "ja_existentes": self.presencas_ja_existentes,
                "rejeitadas": self.presencas_rejeitadas,
            },
            "ocorrencias": self.ocorrencias,
        }


class ErroDeMigracao(RuntimeError):
    """Falha que impede a migracao de continuar."""


class DryRunConcluido(Exception):
    """Sinaliza fim do dry-run apos o rollback (uso interno)."""

    def __init__(self, relatorio: Relatorio) -> None:
        super().__init__("dry-run concluido")
        self.relatorio = relatorio


def abrir_sqlite(caminho: Path) -> sqlite3.Connection:
    """Abre a origem em modo somente leitura -- o legado nunca e tocado."""
    if not caminho.is_file():
        raise ErroDeMigracao(f"Arquivo SQLite nao encontrado: {caminho}")
    uri = f"file:{caminho.as_posix()}?mode=ro"
    conexao = sqlite3.connect(uri, uri=True)
    conexao.row_factory = sqlite3.Row
    return conexao


def converter_data_hora(bruto: str | None, tz: ZoneInfo) -> dt.datetime:
    """Converte o texto legado em datetime com fuso.

    O SQLite guardava texto livre. A funcao date() do SQLite nao interpreta
    o formato dd/mm/aaaa, e era essa a causa de a regra "uma presenca por
    dia" nunca ter valido para os dados antigos.
    """
    texto = (bruto or "").strip()
    for formato in FORMATOS_DATA:
        try:
            ingenuo = dt.datetime.strptime(texto, formato)
        except ValueError:
            continue
        return ingenuo.replace(tzinfo=tz)
    aceitos = ", ".join(FORMATOS_DATA)
    raise ValueError(f"formato de data nao reconhecido: {texto!r} (aceitos: {aceitos})")


def resolver_foto(
    foto_path: str | None, storage_dir: Path
) -> tuple[str | None, str | None]:
    """Decide o valor de foto_arquivo a partir do foto_path legado.

    Retorna (valor, motivo_de_descarte). O caminho absoluto do legado nao e
    copiado as cegas: so vira referencia se o arquivo existir de fato.
    """
    if not foto_path or not foto_path.strip():
        return None, "aluno sem foto_path no legado"

    origem = Path(foto_path)
    if origem.is_file():
        return origem.name, None

    if (storage_dir / origem.name).is_file():
        return origem.name, None

    return None, (
        "foto_path legado aponta para arquivo inexistente neste ambiente; "
        "foto_arquivo gravado como NULL"
    )


def _migrar_alunos(
    session: Session,
    alunos_legado: list[sqlite3.Row],
    relatorio: Relatorio,
    storage_dir: Path,
) -> dict[str, int]:
    """Insere os alunos e devolve o mapa matricula_legada -> id novo."""
    mapa: dict[str, int] = {}

    for linha in alunos_legado:
        matricula = str(linha["id"]).strip()
        nome = (linha["nome"] or "").strip()

        if not matricula:
            relatorio.alunos_rejeitados += 1
            relatorio.registrar(
                "erro", "aluno sem id/matricula no legado", legado=dict(linha)
            )
            continue

        if not nome:
            relatorio.alunos_rejeitados += 1
            relatorio.registrar(
                "erro",
                "aluno sem nome -- viola NOT NULL/CHECK do novo schema",
                legado=dict(linha),
            )
            continue

        existente = session.scalar(select(Aluno).where(Aluno.matricula == matricula))
        if existente is not None:
            mapa[matricula] = existente.id
            relatorio.alunos_ja_existentes += 1
            relatorio.registrar(
                "info",
                "aluno ja presente no PostgreSQL -- nada a fazer",
                matricula=matricula,
            )
            continue

        foto_arquivo, motivo_foto = resolver_foto(linha["foto_path"], storage_dir)
        if motivo_foto:
            relatorio.registrar(
                "aviso",
                motivo_foto,
                matricula=matricula,
                foto_path_legado=linha["foto_path"],
            )

        aluno = Aluno(matricula=matricula, nome=nome, foto_arquivo=foto_arquivo)
        session.add(aluno)
        session.flush()  # obtem o id gerado pelo IDENTITY

        mapa[matricula] = aluno.id
        relatorio.alunos_inseridos += 1

    return mapa


def _migrar_presencas(
    session: Session,
    presencas_legado: list[sqlite3.Row],
    mapa_matricula: dict[str, int],
    relatorio: Relatorio,
    tz: ZoneInfo,
) -> None:
    # Valida tudo antes de inserir e ordena por instante. Assim, quando o
    # legado tem varias marcacoes no mesmo dia, a que sobrevive a constraint
    # e a MAIS ANTIGA (a hora de chegada), independentemente da ordem dos
    # ids na origem.
    validas: list[tuple[dt.datetime, int, sqlite3.Row]] = []

    for linha in presencas_legado:
        matricula = str(linha["aluno_id"]).strip()
        aluno_id = mapa_matricula.get(matricula)

        if aluno_id is None:
            relatorio.presencas_rejeitadas += 1
            relatorio.registrar(
                "erro",
                "presenca orfa: aluno correspondente nao existe/nao migrou",
                legado=dict(linha),
            )
            continue

        try:
            registrado_em = converter_data_hora(linha["data_hora"], tz)
        except ValueError as exc:
            relatorio.presencas_rejeitadas += 1
            relatorio.registrar("erro", f"data invalida: {exc}", legado=dict(linha))
            continue

        validas.append((registrado_em, aluno_id, linha))

    validas.sort(key=lambda item: item[0])

    for registrado_em, aluno_id, linha in validas:
        data_referencia = registrado_em.date()

        # ON CONFLICT DO NOTHING sobre UNIQUE(aluno_id, data_referencia): e a
        # mesma constraint que passa a garantir a regra de negocio. Torna a
        # reexecucao segura e colapsa as repeticoes do legado.
        comando = (
            pg_insert(Presenca)
            .values(
                aluno_id=aluno_id,
                registrado_em=registrado_em,
                data_referencia=data_referencia,
            )
            .on_conflict_do_nothing(constraint="uq_presencas_aluno_dia")
            .returning(Presenca.id)
        )
        inserido = session.execute(comando).scalar()

        if inserido is None:
            relatorio.presencas_ja_existentes += 1
            relatorio.registrar(
                "aviso",
                "presenca nao inserida: ja existe registro para este aluno neste "
                "dia (regra de uma presenca por dia)",
                legado=dict(linha),
                data_referencia=data_referencia.isoformat(),
            )
        else:
            relatorio.presencas_inseridas += 1


def migrar(
    sqlite_path: Path,
    database_url: str,
    *,
    aplicar: bool,
    tz: ZoneInfo,
    storage_dir: Path,
) -> Relatorio:
    relatorio = Relatorio(sqlite_path=str(sqlite_path), dry_run=not aplicar)
    origem = abrir_sqlite(sqlite_path)

    try:
        alunos_legado = origem.execute(
            "SELECT id, nome, foto_path FROM alunos ORDER BY id"
        ).fetchall()
        presencas_legado = origem.execute(
            "SELECT id, aluno_id, data_hora FROM presencas ORDER BY id"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise ErroDeMigracao(f"Falha ao ler o SQLite legado: {exc}") from exc
    finally:
        origem.close()

    relatorio.alunos_lidos = len(alunos_legado)
    relatorio.presencas_lidas = len(presencas_legado)

    engine = criar_engine(database_url)

    # Transacao unica: qualquer erro desfaz tudo. No dry-run o rollback e
    # forcado no final, entao o PostgreSQL nunca chega a ser alterado.
    with sessao(engine) as session:
        mapa = _migrar_alunos(session, alunos_legado, relatorio, storage_dir)
        _migrar_presencas(session, presencas_legado, mapa, relatorio, tz)

        if not aplicar:
            session.rollback()
            raise DryRunConcluido(relatorio)

    return relatorio


def salvar_relatorio(relatorio: Relatorio, destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    carimbo = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    sufixo = "dry-run" if relatorio.dry_run else "aplicado"
    arquivo = destino / f"import-legacy-{carimbo}-{sufixo}.json"
    arquivo.write_text(
        json.dumps(relatorio.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return arquivo


def imprimir_resumo(relatorio: Relatorio, arquivo: Path) -> None:
    modo = "SIMULACAO (nada foi gravado)" if relatorio.dry_run else "APLICADO"
    print(f"\n=== IMPORTACAO DO LEGADO -- {modo} ===")
    print(f"Origem: {relatorio.sqlite_path}")
    print(
        f"Alunos    | lidos={relatorio.alunos_lidos} "
        f"inseridos={relatorio.alunos_inseridos} "
        f"ja_existentes={relatorio.alunos_ja_existentes} "
        f"rejeitados={relatorio.alunos_rejeitados}"
    )
    print(
        f"Presencas | lidas={relatorio.presencas_lidas} "
        f"inseridas={relatorio.presencas_inseridas} "
        f"ja_existentes={relatorio.presencas_ja_existentes} "
        f"rejeitadas={relatorio.presencas_rejeitadas}"
    )

    erros = [o for o in relatorio.ocorrencias if o["nivel"] == "erro"]
    avisos = [o for o in relatorio.ocorrencias if o["nivel"] == "aviso"]
    print(f"Ocorrencias: {len(erros)} erro(s), {len(avisos)} aviso(s)")

    destaque = erros + avisos
    for ocorrencia in destaque[:5]:
        print(f"  [{ocorrencia['nivel']}] {ocorrencia['motivo']}")
    if len(destaque) > 5:
        print(f"  ... e mais {len(destaque) - 5}. Detalhe completo no relatorio.")

    print(f"Relatorio completo: {arquivo}")
    if relatorio.dry_run:
        print("Nada foi gravado. Repita com --apply para efetivar.\n")
    else:
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ETL SQLite legado -> PostgreSQL")
    parser.add_argument(
        "--sqlite", type=Path, default=Path("escola.db"), help="SQLite de origem"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="efetiva a gravacao (sem esta flag, apenas simula)",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("storage") / "etl",
        help="diretorio do relatorio JSON",
    )
    parser.add_argument(
        "--database-url", default=None, help="sobrepoe DATABASE_URL do ambiente"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    database_url = args.database_url or settings.database_url

    try:
        relatorio = migrar(
            args.sqlite,
            database_url,
            aplicar=args.apply,
            tz=settings.timezone,
            storage_dir=settings.storage_dir,
        )
    except DryRunConcluido as fim:
        relatorio = fim.relatorio
    except ErroDeMigracao as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    arquivo = salvar_relatorio(relatorio, args.report_dir)
    imprimir_resumo(relatorio, arquivo)

    houve_erro = any(o["nivel"] == "erro" for o in relatorio.ocorrencias)
    return 1 if houve_erro else 0


if __name__ == "__main__":
    raise SystemExit(main())
