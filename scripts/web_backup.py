"""Cria ou transporta um backup web; segredos chegam apenas por ambiente externo."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from src.application.services.web_backup import GerarBackup, TransportarBackup
from src.config.web_settings import get_web_settings
from src.infrastructure.backup.postgres import CoordenacaoBackupPostgres
from src.infrastructure.backup.rclone import (
    RcloneCiphertextTransport,
    RcloneCommandRunner,
    RcloneCryptArchive,
)
from src.infrastructure.workers.maintenance_gate import ManutencaoWeb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--mode",
        choices=("diario", "manual_pre_apresentacao"),
        help="Gera um backup local cifrado.",
    )
    action.add_argument(
        "--transportar", metavar="GERACAO", help="Transfere uma geraÃ§Ã£o completa."
    )
    args = parser.parse_args()

    settings = get_web_settings()
    root = Path(__file__).resolve().parents[1]
    engine = create_engine(
        settings.database_url.get_secret_value(), future=True, pool_pre_ping=True
    )
    maintenance_dir = _required_path("WEB_MAINTENANCE_DIR")
    staging_root = _required_path("WEB_BACKUP_STAGING_DIR")
    service_file = _required_path("WEB_BACKUP_PG_SERVICE_FILE")
    config_path = _required_path("WEB_BACKUP_RCLONE_CONFIG")
    reference_root = settings.reference_storage_dir
    if reference_root is None:
        raise SystemExit("WEB_REFERENCE_STORAGE_DIR e obrigatoria para backup.")
    pg_service = _required("WEB_BACKUP_PG_SERVICE")
    crypt_remote = _required("WEB_BACKUP_LOCAL_CRYPT_REMOTE")
    external_remote = os.environ.get("WEB_BACKUP_EXTERNAL_RAW_REMOTE", "").strip()
    state_dir = _required_path("WEB_BACKUP_STATE_DIR")
    _ensure_disjoint(
        [
            maintenance_dir,
            staging_root,
            state_dir,
            reference_root,
            settings.capture_temp_dir,
        ]
    )
    if settings.backup_exclusions_file is not None:
        exclusion_file = settings.backup_exclusions_file.resolve()
        if any(
            exclusion_file.is_relative_to(path.resolve())
            for path in [
                maintenance_dir,
                staging_root,
                state_dir,
                reference_root,
                settings.capture_temp_dir,
            ]
            if path is not None
        ):
            raise SystemExit(
                "WEB_BACKUP_EXCLUSIONS_FILE nao pode entrar em roots de backup "
                "ou biometria."
            )
    app_version = os.environ.get("WEB_APP_VERSION", "workspace-unknown")

    runner = RcloneCommandRunner(config_path)
    archive = RcloneCryptArchive(
        runner,
        config_path=config_path,
        remote=crypt_remote,
        state_dir=state_dir,
        external_remote=external_remote or None,
        project_root=root,
    )
    archive.validar_configuracao()
    coordinator = CoordenacaoBackupPostgres(
        engine,
        ManutencaoWeb(maintenance_dir),
        reference_root=reference_root,
        staging_root=staging_root,
        pg_service=pg_service,
        pg_service_file=service_file,
        project_root=root,
        app_version=app_version,
    )
    try:
        if settings.purpose_end_at is not None and datetime.now(
            UTC
        ) >= settings.purpose_end_at.astimezone(UTC):
            raise SystemExit(
                "A finalidade web terminou; backup/transporte estao encerrados."
            )
        if args.transportar:
            if not external_remote:
                raise SystemExit(
                    "WEB_BACKUP_EXTERNAL_RAW_REMOTE e obrigatorio para transporte."
                )
            transport = RcloneCiphertextTransport(
                runner,
                config_path=config_path,
                encrypted_remote=crypt_remote,
                external_remote=external_remote,
                scratch_dir=_required_path("WEB_BACKUP_TRANSPORT_STAGING_DIR"),
            )
            result = TransportarBackup(archive).executar(
                args.transportar, transport, destino=external_remote
            )
            print(
                json.dumps(
                    {
                        "geracao": result.geracao,
                        "destino": result.destino,
                        "tamanho_bytes": result.tamanho_bytes,
                        "sha256_indice": result.sha256,
                        "verificado_em": result.verificado_em.isoformat(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        manifesto = GerarBackup(coordinator, archive).executar(
            crypt_remote,
            datetime.now(UTC),
            args.mode or "diario",
        )
        transporte_completo = False
        if external_remote:
            transport = RcloneCiphertextTransport(
                runner,
                config_path=config_path,
                encrypted_remote=crypt_remote,
                external_remote=external_remote,
                scratch_dir=_required_path("WEB_BACKUP_TRANSPORT_STAGING_DIR"),
            )
            TransportarBackup(archive).executar(
                manifesto.geracao,
                transport,
                destino=external_remote,
            )
            transporte_completo = True
        print(
            json.dumps(
                {
                    "geracao": manifesto.geracao,
                    "modo": manifesto.modo,
                    "revisao_schema": manifesto.revisao_schema,
                    "arquivos": len(manifesto.arquivos),
                    "tamanho_bytes": manifesto.tamanho_total_bytes,
                    "completo": True,
                    "externo_completo": transporte_completo,
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


def _required_path(name: str) -> Path:
    path = Path(_required(name)).expanduser()
    if not path.is_absolute():
        raise SystemExit(f"{name} precisa ser caminho absoluto.")
    return path


def _ensure_disjoint(paths: list[Path | None]) -> None:
    resolved = [path.expanduser().resolve() for path in paths if path is not None]
    for index, path in enumerate(resolved):
        if path.is_relative_to(Path(__file__).resolve().parents[1]):
            raise SystemExit("Diretorio operacional nao pode ficar no repositorio.")
        if any(
            path == other or path.is_relative_to(other) or other.is_relative_to(path)
            for other in resolved[:index]
        ):
            raise SystemExit(
                "Diretorios de backup, manutencao e biometria devem ser separados."
            )


if __name__ == "__main__":
    raise SystemExit(main())
