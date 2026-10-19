"""Executa um ensaio destrutivo somente em banco e volume task017 descartaveis."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from src.application.services.web_backup import AutorizacaoRestore, RestaurarEnsaio
from src.infrastructure.backup.exclusions import RegistroExclusoes
from src.infrastructure.backup.postgres import PostgresCommandRunner
from src.infrastructure.backup.postgres_restore import PostgresRestoreAdapter
from src.infrastructure.backup.rclone import (
    RcloneCommandRunner,
    RcloneCryptArchive,
    RcloneRestoreArchive,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--geracao", required=True, help="UUID opaco da geracao completa local."
    )
    parser.add_argument(
        "--confirmacao", required=True, help="RESTAURAR-TASK017-<banco descartavel>"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    database_url = _required("FACE_WEB_RESTORE_DATABASE_URL")
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    database = make_url(database_url).database or ""
    config_path = _path("WEB_BACKUP_RCLONE_CONFIG")
    crypt_remote = _required("WEB_BACKUP_LOCAL_CRYPT_REMOTE")
    state_dir = _path("WEB_BACKUP_STATE_DIR")
    staging_root = _path("FACE_WEB_RESTORE_STAGING_DIR")
    service_file = _path("FACE_WEB_RESTORE_PG_SERVICE_FILE")
    service = _required("FACE_WEB_RESTORE_PG_SERVICE")
    reference_root = _path("FACE_WEB_RESTORE_REFERENCE_DIR")
    exclusion_path = _path("WEB_BACKUP_EXCLUSIONS_FILE")

    rclone = RcloneCommandRunner(config_path)
    archive = RcloneCryptArchive(
        rclone,
        config_path=config_path,
        remote=crypt_remote,
        state_dir=state_dir,
        project_root=root,
    )
    source = RcloneRestoreArchive(
        rclone,
        archive=archive,
        encrypted_remote=crypt_remote,
        staging_root=staging_root,
        project_root=root,
    )
    exclusions = RegistroExclusoes(exclusion_path, project_root=root)
    adapter = PostgresRestoreAdapter(
        engine,
        PostgresCommandRunner(),
        source,
        pg_service=service,
        pg_service_file=service_file,
        references_root=reference_root,
        staging_root=staging_root,
        exclusions=exclusions,
        project_root=root,
    )
    try:
        evidence = RestaurarEnsaio(adapter).executar(
            args.geracao,
            database,
            AutorizacaoRestore(banco=database, confirmacao=args.confirmacao),
        )
        print(
            json.dumps(
                {
                    "geracao": evidence.geracao,
                    "banco_descartavel": evidence.banco,
                    "revisao_schema": evidence.revisao_schema,
                    "arquivos_verificados": evidence.arquivos_verificados,
                    "exclusoes_reaplicadas": evidence.exclusoes_reaplicadas,
                    "sessoes_tokens_invalidos": evidence.sessoes_tokens_invalidos,
                    "validado_em": evidence.validado_em.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    finally:
        engine.dispose()


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Variavel externa obrigatoria ausente: {name}.")
    return value


def _path(name: str) -> Path:
    path = Path(_required(name)).expanduser()
    if not path.is_absolute():
        raise SystemExit(f"{name} precisa ser caminho absoluto.")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
