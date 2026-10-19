"""Coordenacao e snapshot PostgreSQL sem carregar segredos em argv/logs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from src.application.services.web_backup import (
    ArquivoManifestoBackup,
    ManifestoBackup,
    ModoBackup,
)
from src.infrastructure.workers.maintenance_gate import ManutencaoWeb

_SERVICE_RE = re.compile(r"[A-Za-z0-9_.-]{1,63}\Z")


class ExecutorPostgres(Protocol):
    def executar(self, argumentos: list[str], *, ambiente: dict[str, str]) -> str: ...


class PostgresCommandRunner:
    """Executa pg_dump/psql com shell desativado e mensagens sanitizadas."""

    def __init__(self, *, executable_dir: Path | None = None) -> None:
        self._executable_dir = executable_dir

    def executar(self, argumentos: list[str], *, ambiente: dict[str, str]) -> str:
        if not argumentos or any(not isinstance(item, str) for item in argumentos):
            raise ValueError("Comando PostgreSQL invÃ¡lido.")
        executavel = argumentos[0]
        if self._executable_dir is not None:
            executavel = str(self._executable_dir / executavel)
        env = {"PATH": os.environ.get("PATH", "")}
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            if value := os.environ.get(key):
                env[key] = value
        env.update(ambiente)
        resultado = subprocess.run(
            [executavel, *argumentos[1:]],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            shell=False,
        )
        if resultado.returncode:
            raise RuntimeError(
                f"Ferramenta PostgreSQL falhou (cÃ³digo {resultado.returncode}); "
                "saÃ­da omitida para proteger configuraÃ§Ãµes."
            )
        return resultado.stdout.strip()


class CoordenacaoBackupPostgres:
    """Fecha as escritas web, aguarda fila e cria dump e fotos no mesmo ponto."""

    def __init__(
        self,
        engine: Engine,
        maintenance: ManutencaoWeb,
        *,
        reference_root: Path,
        staging_root: Path,
        pg_service: str,
        pg_service_file: Path,
        project_root: Path,
        app_version: str,
        runner: ExecutorPostgres | None = None,
        database_size_bytes: Callable[[], int] | None = None,
        poll_seconds: float = 0.25,
    ) -> None:
        if _SERVICE_RE.fullmatch(pg_service) is None:
            raise ValueError("WEB_BACKUP_PG_SERVICE invÃ¡lido.")
        if poll_seconds <= 0 or not app_version.strip():
            raise ValueError("ConfiguraÃ§Ã£o de backup invÃ¡lida.")
        self._engine = engine
        self._maintenance = maintenance
        self._reference_root = reference_root.expanduser().resolve()
        self._staging_root_original = staging_root.expanduser()
        self._staging_root = self._staging_root_original.resolve()
        self._service_file = pg_service_file.expanduser().resolve()
        self._project_root = project_root.resolve()
        for root in (self._reference_root, self._maintenance.raiz, self._project_root):
            if (
                self._staging_root == root
                or self._staging_root.is_relative_to(root)
                or root.is_relative_to(self._staging_root)
            ):
                raise ValueError(
                    "Raiz de staging precisa ser isolada das demais raizes."
                )
        self._service = pg_service
        self._app_version = app_version.strip()[:128]
        self._runner = runner or PostgresCommandRunner()
        self._database_size_bytes = database_size_bytes
        self._poll_seconds = poll_seconds
        self._database = make_url(str(engine.url)).database

    def lock_backup(self) -> AbstractContextManager[None]:
        return self._maintenance.lock_backup()

    def solicitar_manutencao(self) -> None:
        self._maintenance.solicitar_manutencao()

    def liberar_manutencao(self) -> None:
        self._maintenance.liberar_manutencao()

    def lock_snapshot(self, timeout_seconds: float) -> AbstractContextManager[None]:
        return self._maintenance.lock_snapshot(timeout_seconds)

    def aguardar_jobs_ociosos(self, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        with self._engine.connect() as connection:
            while True:
                ativos = connection.scalar(
                    text(
                        "SELECT count(*) FROM jobs_faciais_web "
                        "WHERE estado IN ('recebida','enfileirada','processando')"
                    )
                )
                if int(ativos or 0) == 0:
                    return
                restante = deadline - time.monotonic()
                if restante <= 0:
                    raise TimeoutError("A fila facial nÃ£o ficou ociosa a tempo.")
                time.sleep(min(self._poll_seconds, restante))

    def criar_staging(self, generation_id: str) -> Path:
        if self._staging_root_original.is_symlink():
            raise ValueError("A raiz temporÃ¡ria de backup nÃ£o pode ser symlink.")
        self._staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            self._staging_root.chmod(0o700)
        staging = Path(
            tempfile.mkdtemp(prefix=f"{generation_id}-", dir=self._staging_root)
        )
        if os.name == "posix":
            staging.chmod(0o700)
        return staging

    def criar_snapshot(
        self,
        staging: Path,
        generation_id: str,
        agora: datetime,
        modo: ModoBackup,
    ) -> ManifestoBackup:
        if not staging.is_absolute() or not staging.is_relative_to(self._staging_root):
            raise ValueError("Staging do backup escapou da raiz privada.")
        if not self._service_file.is_file() or self._service_file.is_relative_to(
            self._project_root
        ):
            raise ValueError("Arquivo pg_service externo e privado ausente.")
        if self._reference_root.is_symlink() or not self._reference_root.is_dir():
            raise ValueError("Raiz privada de referÃªncias indisponÃ­vel.")

        reference_sources: list[Path] = []
        reference_size = 0
        for source in sorted(self._reference_root.rglob("*")):
            if source.is_symlink():
                raise ValueError("A raiz de referÃªncias contÃ©m symlink.")
            if source.is_file():
                reference_sources.append(source)
                reference_size += source.stat().st_size
            elif not source.is_dir():
                raise ValueError("A raiz de referÃªncias contÃ©m arquivo especial.")
        if self._database_size_bytes is None:
            with self._engine.connect() as connection:
                database_size = int(
                    connection.scalar(
                        text("SELECT pg_database_size(current_database())")
                    )
                    or 0
                )
        else:
            database_size = self._database_size_bytes()
        required_space = int(database_size * 1.1) + reference_size
        if database_size < 0 or shutil.disk_usage(staging).free < required_space:
            raise OSError("EspaÃ§o livre insuficiente para staging do backup.")

        env = {"PGSERVICEFILE": str(self._service_file)}
        database = self._runner.executar(
            [
                "psql",
                "--dbname",
                f"service={self._service}",
                "--tuples-only",
                "--no-align",
                "--command",
                "SELECT current_database()",
            ],
            ambiente=env,
        )
        if database != self._database:
            raise ValueError(
                "O serviÃ§o pg_service nÃ£o corresponde ao banco WEB configurado."
            )

        database_dump = staging / "database.dump"
        self._runner.executar(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file",
                str(database_dump),
                "--dbname",
                f"service={self._service}",
            ],
            ambiente=env,
        )
        if not database_dump.is_file() or database_dump.is_symlink():
            raise RuntimeError("pg_dump nÃ£o produziu o arquivo esperado.")
        if os.name == "posix":
            database_dump.chmod(0o600)

        reference_target = staging / "references"
        reference_target.mkdir(mode=0o700)
        arquivos = [self._manifestar(database_dump, "database.dump")]
        for source in reference_sources:
            relative = source.relative_to(self._reference_root)
            # Keep request IDs and storage paths only inside the encrypted
            # manifest. The raw backend exposes directory names when crypt
            # uses directory_name_encryption=false.
            opaque_name = f"{secrets.token_hex(24)}.bin"
            target = reference_target / opaque_name
            shutil.copyfile(source, target)
            if os.name == "posix":
                target.chmod(0o600)
            archived = self._manifestar(
                target, (Path("references") / opaque_name).as_posix()
            )
            arquivos.append(
                ArquivoManifestoBackup(
                    caminho=archived.caminho,
                    tamanho_bytes=archived.tamanho_bytes,
                    sha256=archived.sha256,
                    restaurar_em=relative.as_posix(),
                )
            )

        with self._engine.connect() as connection:
            revision = connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
        if not isinstance(revision, str) or not revision:
            raise RuntimeError("A revisÃ£o Alembic nÃ£o pÃ´de ser registrada.")
        manifesto = ManifestoBackup(
            geracao=generation_id,
            criado_em=agora.astimezone(UTC),
            modo=modo,
            versao_aplicacao=self._app_version,
            revisao_schema=revision,
            arquivos=tuple(arquivos),
        )
        payload = {
            "geracao": manifesto.geracao,
            "criado_em": manifesto.criado_em.isoformat(),
            "modo": manifesto.modo,
            "versao_aplicacao": manifesto.versao_aplicacao,
            "revisao_schema": manifesto.revisao_schema,
            "arquivos": [
                {
                    "caminho": item.caminho,
                    "tamanho_bytes": item.tamanho_bytes,
                    "sha256": item.sha256,
                    **(
                        {"restaurar_em": item.restaurar_em}
                        if item.restaurar_em is not None
                        else {}
                    ),
                }
                for item in manifesto.arquivos
            ],
        }
        manifest_path = staging / "MANIFEST.json"
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if os.name == "posix":
            manifest_path.chmod(0o600)
        return manifesto

    def limpar_staging(self, staging: Path) -> None:
        resolved = staging.resolve()
        if staging.is_symlink() or not resolved.is_relative_to(self._staging_root):
            raise ValueError("Recusa de limpeza fora da raiz temporÃ¡ria de backup.")
        shutil.rmtree(resolved, ignore_errors=False)

    @staticmethod
    def _manifestar(path: Path, relative: str) -> ArquivoManifestoBackup:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(block)
                digest.update(block)
        return ArquivoManifestoBackup(relative, size, digest.hexdigest())
