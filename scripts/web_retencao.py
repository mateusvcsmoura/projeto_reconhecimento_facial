"""Planeja retenÃ§Ã£o (dry-run) ou aplica expurgo web com confirmaÃ§Ã£o exata."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import create_engine, text

from src.application.services.web_backup import ExpurgarWeb
from src.application.use_cases.limpar_referencias_provisorias import (
    LimparReferenciasProvisorias,
)
from src.config.web_settings import get_web_settings
from src.infrastructure.backup.postgres import CoordenacaoBackupPostgres
from src.infrastructure.backup.rclone import RcloneCommandRunner, RcloneCryptArchive
from src.infrastructure.backup.retention import CatalogoRetencaoWeb
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    PostgresSolicitacaoRepository,
)
from src.infrastructure.storage.private_reference_storage import (
    PrivateReferenceStorageLocal,
)
from src.infrastructure.storage.temporary_capture_storage import TemporaryCaptureStorage
from src.infrastructure.workers.maintenance_gate import ManutencaoWeb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Aplica o plano exibido pelo dry-run."
    )
    parser.add_argument("--confirm-environment")
    parser.add_argument("--confirm-target")
    args = parser.parse_args()

    settings = get_web_settings()
    if settings.purpose_end_at is None:
        raise SystemExit("WEB_PURPOSE_END_AT precisa estar definido para retenÃ§Ã£o.")
    root = Path(__file__).resolve().parents[1]
    engine = create_engine(
        settings.database_url.get_secret_value(), future=True, pool_pre_ping=True
    )
    db_name = urlsplit(settings.database_url.get_secret_value()).path.strip("/")
    environment = settings.environment
    target = f"database:{db_name};web+backup:local"
    maintenance_dir = _path("WEB_MAINTENANCE_DIR")
    staging_root = _path("WEB_BACKUP_STAGING_DIR")
    service_file = _path("WEB_BACKUP_PG_SERVICE_FILE")
    pg_service = _required("WEB_BACKUP_PG_SERVICE")
    crypt_remote = _required("WEB_BACKUP_LOCAL_CRYPT_REMOTE")
    external_remote = os.environ.get("WEB_BACKUP_EXTERNAL_RAW_REMOTE", "").strip()
    rclone_config = _path("WEB_BACKUP_RCLONE_CONFIG")
    state_dir = _path("WEB_BACKUP_STATE_DIR")
    reference_root = settings.reference_storage_dir
    if reference_root is None:
        raise SystemExit("WEB_REFERENCE_STORAGE_DIR e obrigatoria para retenÃ§Ã£o.")
    _ensure_disjoint(
        [
            maintenance_dir,
            staging_root,
            state_dir,
            reference_root,
            settings.capture_temp_dir,
        ]
    )

    runner = RcloneCommandRunner(rclone_config)
    archive = RcloneCryptArchive(
        runner,
        config_path=rclone_config,
        remote=crypt_remote,
        state_dir=state_dir,
        external_remote=external_remote or None,
        project_root=root,
    )
    archive.validar_configuracao()
    capture_storage = None
    if settings.capture_temp_dir is not None:
        capture_storage = _CaptureStorageRetencao(
            settings.capture_temp_dir,
            max_bytes=settings.capture_max_bytes_per_capture,
            quota_bytes=settings.capture_storage_quota_bytes,
            require_memory_fs=settings.environment == "production",
        )
    solicitacoes = PostgresSolicitacaoRepository(engine)

    def active_job_ids() -> set[UUID]:
        with engine.connect() as connection:
            return set(
                connection.scalars(
                    text(
                        "SELECT id FROM jobs_faciais_web "
                        "WHERE estado IN ('recebida','enfileirada','processando')"
                    )
                )
            )

    def clean_provisional() -> tuple[int, tuple[int, ...]]:
        reference_storage = PrivateReferenceStorageLocal(reference_root)
        cleanup = LimparReferenciasProvisorias(solicitacoes, reference_storage)
        total = 0
        pending: tuple[int, ...] = ()
        while total < 100_000:
            count, pending = cleanup.executar(limite=1000)
            total += count
            if pending:
                raise RuntimeError(
                    "Limpeza de referÃªncias provisÃ³rias permanece pendente."
                )
            if count == 0:
                break
        return total, pending

    logs = os.environ.get("WEB_LOG_DIR", "").strip()
    catalog = CatalogoRetencaoWeb(
        engine,
        archive,
        backup_remote=crypt_remote,
        logs_root=Path(logs) if logs else None,
        capture_storage=capture_storage,
        reference_root=reference_root,
        active_job_ids=active_job_ids,
        limpar_referencias_provisorias=clean_provisional,
        project_root=root,
    )
    service = ExpurgarWeb(
        catalog,
        ambiente=environment,
        alvo=target,
        finalidade_ate=settings.purpose_end_at.astimezone(UTC),
    )
    plan = service.planejar(datetime.now(UTC))

    if not args.apply:
        print(
            json.dumps(
                {
                    "modo": "dry-run",
                    "ambiente": plan.ambiente,
                    "alvo": plan.alvo,
                    "planejado_em": plan.planejado_em.isoformat(),
                    "finalidade_encerrada": plan.finalidade_encerrada,
                    "quantidade_alvos": plan.quantidade_alvos,
                    "alvos": list(plan.alvos),
                    "confirmacao_ambiente": environment,
                    "confirmacao_alvo": target,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        engine.dispose()
        return 0

    if args.confirm_environment != environment or args.confirm_target != target:
        raise SystemExit(
            "--apply exige --confirm-environment e --confirm-target exatos do dry-run."
        )
    maintenance = ManutencaoWeb(maintenance_dir)
    coordinator = CoordenacaoBackupPostgres(
        engine,
        maintenance,
        reference_root=reference_root,
        staging_root=staging_root,
        pg_service=pg_service,
        pg_service_file=service_file,
        project_root=root,
        app_version=os.environ.get("WEB_APP_VERSION", "workspace-unknown"),
    )
    try:
        with maintenance.lock_backup():
            maintenance.solicitar_manutencao()
            try:
                coordinator.aguardar_jobs_ociosos(settings.job_deadline_seconds + 60)
                with maintenance.lock_snapshot(timeout_seconds=60):
                    result = service.aplicar(
                        plan,
                        confirmacao=f"APLICAR-EXPURGO-{environment}-{target}",
                    )
            finally:
                maintenance.liberar_manutencao()
        print(
            json.dumps(
                {
                    "modo": "aplicado",
                    "ambiente": result.ambiente,
                    "alvo": result.alvo,
                    "finalidade_encerrada": result.finalidade_encerrada,
                    "quantidade_removida": len(result.removidos),
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


def _ensure_disjoint(paths: list[Path | None]) -> None:
    project = Path(__file__).resolve().parents[1]
    resolved = [path.expanduser().resolve() for path in paths if path is not None]
    for index, path in enumerate(resolved):
        if path.is_relative_to(project):
            raise SystemExit("Diretorio operacional nao pode ficar no repositorio.")
        if any(
            path == other or path.is_relative_to(other) or other.is_relative_to(path)
            for other in resolved[:index]
        ):
            raise SystemExit(
                "Diretorios de backup, manutencao e biometria devem ser separados."
            )


class _CaptureStorageRetencao:
    """Vista read-only da raiz; instancia o storage mutavel somente em apply."""

    def __init__(
        self,
        raiz: Path,
        *,
        max_bytes: int,
        quota_bytes: int,
        require_memory_fs: bool,
    ) -> None:
        self.raiz = raiz.expanduser()
        self._root_original = raiz.expanduser()
        self._max_bytes = max_bytes
        self._quota_bytes = quota_bytes
        self._require_memory_fs = require_memory_fs

    def _storage(self) -> TemporaryCaptureStorage:
        if self._root_original.is_symlink():
            raise ValueError("A raiz de capturas nÃ£o pode ser symlink.")
        return TemporaryCaptureStorage(
            self._root_original,
            max_bytes_per_capture=self._max_bytes,
            max_captures=3,
            quota_bytes=self._quota_bytes,
            require_memory_fs=self._require_memory_fs,
        )

    def remover_job(self, job_id: UUID) -> None:
        self._storage().remover_job(job_id)

    def limpar_orfaos(self, ids_ativos: set[UUID]) -> int:
        return self._storage().limpar_orfaos(ids_ativos)


if __name__ == "__main__":
    raise SystemExit(main())
