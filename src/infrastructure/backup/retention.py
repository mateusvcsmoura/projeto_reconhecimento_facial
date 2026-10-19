"""CatÃ¡logo de retenÃ§Ã£o com plano puro e exclusÃ£o confinada a raÃ­zes aprovadas."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, inspect, text

from src.infrastructure.backup.rclone import RcloneCryptArchive


class CaptureStorageRetencao(Protocol):
    raiz: Path

    def remover_job(self, job_id: UUID) -> None: ...

    def limpar_orfaos(self, ids_ativos: set[UUID]) -> int: ...


class CatalogoRetencaoWeb:
    """Planeja cÃ³pias, logs, capturas Ã³rfÃ£s e limpeza final dos dados web."""

    def __init__(
        self,
        engine: Engine,
        archive: RcloneCryptArchive,
        *,
        backup_remote: str,
        logs_root: Path | None,
        capture_storage: CaptureStorageRetencao | None,
        reference_root: Path,
        active_job_ids: Callable[[], set[UUID]],
        limpar_referencias_provisorias: Callable[[], tuple[int, tuple[int, ...]]],
        project_root: Path,
    ) -> None:
        self._engine = engine
        self._archive = archive
        self._remote = backup_remote
        self._logs_original = logs_root.expanduser() if logs_root is not None else None
        self._logs = self._logs_original.resolve() if self._logs_original else None
        self._captures = capture_storage
        self._references_original = reference_root.expanduser()
        self._references = self._references_original.resolve()
        self._active_job_ids = active_job_ids
        self._limpar_provisorias = limpar_referencias_provisorias
        self._project_root = project_root.resolve()
        self._targets: dict[str, tuple[str, object]] = {}
        roots = [self._references]
        if self._logs is not None:
            roots.append(self._logs)
        if self._captures is not None:
            roots.append(self._captures.raiz.resolve())
        for index, root in enumerate(roots):
            if root.is_relative_to(self._project_root):
                raise ValueError("Raiz de retenÃ§Ã£o nÃ£o pode ficar no repositÃ³rio.")
            if any(
                root == other
                or root.is_relative_to(other)
                or other.is_relative_to(root)
                for other in roots[:index]
            ):
                raise ValueError(
                    "Raizes de logs, capturas e referencias devem ser distintas."
                )

    def planejar(
        self,
        agora: datetime,
        finalidade_ate: datetime,
        max_geracoes: int,
        retencao_logs: timedelta,
    ) -> tuple[str, ...]:
        _utc(agora)
        _utc(finalidade_ate)
        if max_geracoes < 1 or retencao_logs <= timedelta(0):
            raise ValueError("RetenÃ§Ã£o invÃ¡lida.")
        self._targets.clear()
        encerrada = agora >= finalidade_ate
        targets: list[str] = []

        completas = sorted(
            self._archive.listar_geracoes_completas(),
            key=lambda item: str(item.get("criado_em", "")),
            reverse=True,
        )
        for index, entry in enumerate(completas):
            generation = str(entry.get("geracao", ""))
            if not generation:
                continue
            if encerrada or index >= max_geracoes:
                targets.append(
                    self._registrar(f"backup:{generation}", "backup", generation)
                )

        for generation in self._archive.listar_incompletas():
            targets.append(
                self._registrar(f"incompleto:{generation}", "incomplete", generation)
            )
        for generation in self._archive.listar_transportes_incompletos():
            targets.append(
                self._registrar(
                    f"transporte-incompleto:{generation}",
                    "external-incomplete",
                    generation,
                )
            )

        if self._logs is not None:
            self._validar_raiz(self._logs_original, self._logs)
            cutoff = agora - retencao_logs
            for path in sorted(self._logs.rglob("*")):
                if path.is_symlink():
                    raise ValueError("A raiz de logs contÃ©m symlink.")
                if path.is_file() and (
                    encerrada
                    or datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff
                ):
                    relative = path.relative_to(self._logs).as_posix()
                    token = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
                    targets.append(self._registrar(f"log:{token}", "log", path))

        if self._captures is not None:
            if self._captures.raiz.is_symlink():
                raise ValueError("A raiz de capturas nÃ£o pode ser symlink.")
            active = self._active_job_ids()
            for path in (
                self._captures.raiz.iterdir() if self._captures.raiz.exists() else ()
            ):
                if path.is_symlink() or not path.is_dir():
                    continue
                try:
                    job_id = UUID(path.name)
                except ValueError:
                    continue
                if job_id not in active:
                    token = hashlib.sha256(path.name.encode("ascii")).hexdigest()[:24]
                    targets.append(
                        self._registrar(f"captura:{token}", "capture", job_id)
                    )

        if self._tem_referencias_provisorias(agora) > 0:
            targets.append(
                self._registrar("referencias-provisorias", "provisional", None)
            )
        if encerrada:
            targets.append(
                self._registrar("dados-web-finalidade-encerrada", "final", None)
            )
        return tuple(targets)

    def aplicar(self, alvo: str) -> None:
        try:
            tipo, value = self._targets.pop(alvo)
        except KeyError as erro:
            raise ValueError(
                "Alvo nÃ£o pertence ao plano de retenÃ§Ã£o atual."
            ) from erro
        if tipo in {"backup", "incomplete"}:
            self._archive.remover_geracao(str(value), self._remote)
        elif tipo == "external-incomplete":
            self._archive.remover_transporte_incompleto(str(value))
        elif tipo == "log":
            if not isinstance(value, Path):
                raise ValueError("Alvo de log invÃ¡lido.")
            path = Path(value)
            self._validar_caminho(self._logs_original, self._logs, path)
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ValueError("Recusa de exclusÃ£o de log inseguro.")
            path.unlink(missing_ok=True)
        elif tipo == "capture":
            if self._captures is None or not isinstance(value, UUID):
                raise ValueError("Armazenamento temporÃ¡rio indisponÃ­vel.")
            if value in self._active_job_ids():
                raise RuntimeError("Captura voltou a pertencer a job ativo.")
            self._captures.remover_job(value)
        elif tipo == "provisional":
            self._limpar_provisorias()
        elif tipo == "final":
            self._expurgar_dados_web()
        else:
            raise ValueError("Tipo de expurgo invÃ¡lido.")

    def _registrar(self, key: str, kind: str, value: object) -> str:
        self._targets[key] = (kind, value)
        return key

    def _tem_referencias_provisorias(self, agora: datetime) -> int:
        with self._engine.connect() as connection:
            return int(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM solicitacoes_cadastro_web s "
                        "WHERE s.limpa_em IS NULL AND ("
                        "s.estado IN ('rejeitada','cancelada','expirada') OR "
                        "(s.estado IN ('em_coleta','em_validacao',"
                        "'pendente_aprovacao') "
                        "AND s.expira_em <= :agora) OR "
                        "(s.estado = 'aprovada' AND EXISTS ("
                        "SELECT 1 FROM conjuntos_referencias_web c "
                        "WHERE c.solicitacao_id=s.id AND c.estado='descartado')))"
                    ),
                    {"agora": agora},
                )
                or 0
            )

    def _expurgar_dados_web(self) -> None:
        """Remove tabelas web biomÃ©tricas e invalida acesso; preserva dados da CLI."""
        ordered = (
            "revisoes_presenca_web",
            "recebimentos_tentativa_presenca_web",
            "desafios_verificacao_web",
            "tentativas_presenca_web",
            "referencias_faciais_web",
            "conjuntos_referencias_web",
            "credenciais_link_cadastro_web",
            "solicitacoes_cadastro_web",
            "jobs_faciais_web",
            "links_cadastro_web",
            "sessoes_presenca_web",
            "sessoes_autenticacao_web",
            "limites_login_web",
            "limites_presenca_web",
        )
        existing = set(inspect(self._engine).get_table_names())
        with self._engine.begin() as connection:
            if "presencas" in existing:
                connection.execute(
                    text("DELETE FROM presencas WHERE tentativa_id IS NOT NULL")
                )
            for table in ordered:
                if table in existing:
                    connection.execute(text(f"DELETE FROM {table}"))
            if "contas_web" in existing:
                connection.execute(
                    text(
                        "UPDATE contas_web SET ativa = false, "
                        "troca_senha_obrigatoria = true, "
                        "versao_credencial = versao_credencial + 1"
                    )
                )
        self._limpar_raiz_privada(self._references_original, self._references)
        if self._logs_original is not None and self._logs is not None:
            self._limpar_raiz_privada(self._logs_original, self._logs)
        if self._captures is not None:
            self._captures.limpar_orfaos(set())

    def _validar_raiz(self, original: Path | None, resolved: Path) -> None:
        if (
            original is None
            or not original.is_absolute()
            or original.is_symlink()
            or resolved.is_relative_to(self._project_root)
        ):
            raise ValueError(
                "Raiz de expurgo deve ser privada e externa ao repositÃ³rio."
            )

    def _validar_caminho(
        self, original: Path | None, root: Path | None, target: Path
    ) -> None:
        if original is None or root is None:
            raise ValueError("Raiz do arquivo nÃ£o configurada.")
        self._validar_raiz(original, root)
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ValueError("Caminho de exclusÃ£o escapa da raiz autorizada.")

    def _limpar_raiz_privada(self, original: Path, root: Path) -> None:
        self._validar_raiz(original, root)
        if not root.exists():
            return
        for path in root.iterdir():
            if path.is_symlink():
                raise ValueError("Raiz privada de expurgo contÃ©m symlink.")
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError("Caminho de expurgo escapa da raiz.")
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
            else:
                raise ValueError("Raiz privada contÃ©m item especial.")


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("O horÃ¡rio deve ser datetime aware em UTC.")
