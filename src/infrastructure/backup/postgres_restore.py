"""Restore ensaio restrito a banco e volume explicitamente descartÃ¡veis."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.sql.elements import BindParameter

from src.application.services.web_backup import (
    ArquivoManifestoBackup,
    AutorizacaoRestore,
    ManifestoBackup,
)
from src.infrastructure.backup.exclusions import RegistroExclusoes
from src.infrastructure.storage.private_reference_storage import (
    PrivateReferenceStorageLocal,
)

_DISPOSABLE_COMMENT = (
    "projeto_reconhecimento_facial: task017 disposable restore database"
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ExecutorRestore(Protocol):
    def executar(self, argumentos: list[str], *, ambiente: dict[str, str]) -> str: ...


class FonteRestore(Protocol):
    def descriptografar(self, geracao: str) -> Path: ...


class PostgresRestoreAdapter:
    """Valida o alvo antes do restore destrutivo e verifica o resultado local."""

    def __init__(
        self,
        engine: Engine,
        runner: ExecutorRestore,
        fonte: FonteRestore,
        *,
        pg_service: str,
        pg_service_file: Path,
        references_root: Path,
        staging_root: Path,
        exclusions: RegistroExclusoes,
        project_root: Path,
    ) -> None:
        self._engine = engine
        self._runner = runner
        self._fonte = fonte
        self._service = pg_service
        self._service_file = pg_service_file.expanduser().resolve()
        self._references_original = references_root.expanduser()
        self._references_root = self._references_original.resolve()
        self._staging_original = staging_root.expanduser()
        self._staging_root = self._staging_original.resolve()
        self._exclusions = exclusions
        self._project_root = project_root.resolve()
        self._database = make_url(str(engine.url)).database or ""
        self._base_validada = False
        self._exclusoes_aplicadas = 0

    def validar_alvo_descartavel(
        self, banco: str, autorizacao: AutorizacaoRestore
    ) -> None:
        autorizacao.exigir_alvo(banco)
        url = make_url(str(self._engine.url))
        host = (url.host or "").lower().rstrip(".")
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise PermissionError("Restore de ensaio aceita apenas PostgreSQL local.")
        if "task017" not in banco.lower() or self._database != banco:
            raise PermissionError(
                "Banco de restore nÃ£o identificado como descartÃ¡vel."
            )
        if (
            self._service_file.is_symlink()
            or self._service_file.is_relative_to(self._project_root)
            or not self._service_file.is_file()
        ):
            raise ValueError("Arquivo externo pg_service ausente.")
        if (
            not self._references_original.is_absolute()
            or self._references_original.is_symlink()
            or self._references_root.is_relative_to(self._project_root)
            or self._references_root.is_relative_to(self._staging_root)
            or self._staging_root.is_relative_to(self._references_root)
        ):
            raise ValueError("Volume de referÃªncias deve ser descartÃ¡vel e externo.")
        if (
            not self._staging_original.is_absolute()
            or self._staging_original.is_symlink()
            or self._staging_root.is_relative_to(self._project_root)
        ):
            raise ValueError("Staging de restore deve ser absoluto e externo.")
        marcador_volume = self._references_root / ".task017-disposable"
        if (
            not marcador_volume.is_file()
            or marcador_volume.is_symlink()
            or marcador_volume.read_text(encoding="utf-8").strip() != banco
        ):
            raise PermissionError(
                "O volume de referÃªncias nÃ£o tem marcador descartÃ¡vel."
            )
        with self._engine.connect() as connection:
            nome, comentario = connection.execute(
                text(
                    "SELECT current_database(), "
                    "shobj_description(d.oid, 'pg_database') "
                    "FROM pg_database d WHERE d.datname = current_database()"
                )
            ).one()
        if nome != banco or comentario != _DISPOSABLE_COMMENT:
            raise PermissionError("O banco nÃ£o tem o marcador descartÃ¡vel requerido.")
        env = {"PGSERVICEFILE": str(self._service_file)}
        nome_servico = self._runner.executar(
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
        if nome_servico != banco:
            raise PermissionError("pg_service aponta para outro banco.")
        self._base_validada = True

    def descriptografar(self, geracao: str) -> Path:
        return self._fonte.descriptografar(geracao)

    def verificar_manifesto(self, staging: Path) -> ManifestoBackup:
        _exigir_dentro(staging, self._staging_root)
        if (
            staging.is_symlink()
            or staging.parent.resolve() != self._staging_root
            or self._staging_original.is_symlink()
        ):
            raise ValueError("Staging de restore nÃ£o pode ser symlink.")
        manifest_path = staging / "MANIFEST.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(data["criado_em"])
            files = tuple(
                ArquivoManifestoBackup(
                    caminho=str(item["caminho"]),
                    tamanho_bytes=int(item["tamanho_bytes"]),
                    sha256=str(item["sha256"]),
                    restaurar_em=(
                        str(item["restaurar_em"])
                        if item.get("restaurar_em") is not None
                        else None
                    ),
                )
                for item in data["arquivos"]
            )
            manifesto = ManifestoBackup(
                geracao=str(data["geracao"]),
                criado_em=created,
                modo=str(data["modo"]),
                versao_aplicacao=str(data["versao_aplicacao"]),
                revisao_schema=str(data["revisao_schema"]),
                arquivos=files,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as erro:
            raise ValueError("Manifesto do backup invÃ¡lido.") from erro
        esperados: set[str] = {"MANIFEST.json"}
        destinos_referencias: set[str] = set()
        for arquivo in manifesto.arquivos:
            relativo = _validar_caminho_manifesto(arquivo.caminho)
            if relativo.parts[0] == "references":
                if arquivo.restaurar_em is None:
                    raise ValueError("Arquivo de referência sem destino de restore.")
                destino = _validar_destino_referencia(arquivo.restaurar_em).as_posix()
                if destino in destinos_referencias:
                    raise ValueError("Manifesto repete destino de referência.")
                destinos_referencias.add(destino)
            elif arquivo.restaurar_em is not None:
                raise ValueError("O dump do banco não pode ter destino de referência.")
            if (
                arquivo.tamanho_bytes < 0
                or _SHA256_RE.fullmatch(arquivo.sha256) is None
            ):
                raise ValueError("Entrada do manifesto invÃ¡lida.")
            relative_name = relativo.as_posix()
            if relative_name in esperados:
                raise ValueError("Manifesto repete caminho de arquivo.")
            esperados.add(relative_name)
            candidate = staging.joinpath(*relativo.parts)
            _exigir_dentro(candidate, staging)
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError("Arquivo do manifesto estÃ¡ ausente ou inseguro.")
            size, digest = _digest(candidate)
            if size != arquivo.tamanho_bytes or digest != arquivo.sha256:
                raise ValueError("Hash ou tamanho de arquivo do backup diverge.")
        presentes: set[str] = set()
        for path in staging.rglob("*"):
            if path.is_symlink():
                raise ValueError("Staging de restore contÃ©m symlink.")
            if path.is_file():
                presentes.add(path.relative_to(staging).as_posix())
        if presentes != esperados:
            raise ValueError("Staging nÃ£o corresponde ao manifesto.")
        return manifesto

    def restaurar_banco(self, staging: Path, banco: str) -> None:
        self._exigir_validacao(banco)
        dump = staging / "database.dump"
        if not dump.is_file() or dump.is_symlink():
            raise ValueError("Dump de banco invÃ¡lido.")
        self._runner.executar(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "--dbname",
                f"service={self._service}",
                str(dump),
            ],
            ambiente={"PGSERVICEFILE": str(self._service_file)},
        )

    def restaurar_referencias(self, staging: Path, banco: str) -> None:
        self._exigir_validacao(banco)
        source = staging / "references"
        if not source.is_dir() or source.is_symlink():
            raise ValueError("DiretÃ³rio de referÃªncias do manifesto ausente.")
        manifesto = self.verificar_manifesto(staging)
        existentes = (
            tuple(self._references_root.iterdir())
            if self._references_root.exists()
            else ()
        )
        if any(item.name != ".task017-disposable" for item in existentes):
            raise ValueError("O volume de restore deve estar vazio.")
        self._references_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            self._references_root.chmod(0o700)
        for entry in manifesto.arquivos:
            if entry.restaurar_em is None:
                continue
            relative = _validar_caminho_manifesto(entry.caminho)
            item = staging.joinpath(*relative.parts)
            target_relative = _validar_destino_referencia(entry.restaurar_em)
            target = self._references_root.joinpath(*target_relative.parts)
            _exigir_dentro(target, self._references_root)
            if item.is_symlink() or not item.is_file():
                raise ValueError("Snapshot de refer?ncias cont?m arquivo inseguro.")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(item, target)
            if os.name == "posix":
                target.chmod(0o600)

    def reaplicar_exclusoes(self, banco: str) -> int:
        self._exigir_validacao(banco)
        excluidas = self._exclusions.exclusoes_a_reaplicar()
        storage = PrivateReferenceStorageLocal(self._references_root)
        ids_alunos = sorted({entry.identificador for entry in excluidas})
        for aluno_id in ids_alunos:
            with self._engine.begin() as connection:
                caminhos = tuple(
                    connection.scalars(
                        text(
                            "SELECT rf.caminho_privado_relativo "
                            "FROM referencias_faciais_web rf "
                            "JOIN conjuntos_referencias_web cr "
                            "ON cr.id = rf.conjunto_id "
                            "WHERE cr.aluno_id = :aluno_id"
                        ),
                        {"aluno_id": aluno_id},
                    )
                )
                solicitacoes = tuple(
                    connection.scalars(
                        text(
                            "SELECT id FROM solicitacoes_cadastro_web "
                            "WHERE aluno_id = :aluno_id"
                        ),
                        {"aluno_id": aluno_id},
                    )
                )
                jobs = set(
                    connection.scalars(
                        text(
                            "SELECT id FROM tentativas_presenca_web "
                            "WHERE aluno_id = :aluno_id"
                        ),
                        {"aluno_id": aluno_id},
                    )
                )
                if solicitacoes:
                    jobs.update(
                        connection.scalars(
                            text(
                                "SELECT job_id FROM solicitacoes_cadastro_web "
                                "WHERE id IN :ids AND job_id IS NOT NULL"
                            ).bindparams(_expanding("ids")),
                            {"ids": list(solicitacoes)},
                        )
                    )
                conjuntos = tuple(
                    connection.scalars(
                        text(
                            "SELECT id FROM conjuntos_referencias_web "
                            "WHERE aluno_id = :aluno_id"
                        ),
                        {"aluno_id": aluno_id},
                    )
                )
                connection.execute(
                    text(
                        "DELETE FROM revisoes_presenca_web WHERE aluno_id = :aluno_id"
                    ),
                    {"aluno_id": aluno_id},
                )
                connection.execute(
                    text("DELETE FROM presencas WHERE aluno_id = :aluno_id"),
                    {"aluno_id": aluno_id},
                )
                _delete_in(connection, "desafios_verificacao_web", "id", jobs)
                connection.execute(
                    text(
                        "DELETE FROM tentativas_presenca_web WHERE aluno_id = :aluno_id"
                    ),
                    {"aluno_id": aluno_id},
                )
                _delete_in(
                    connection, "referencias_faciais_web", "conjunto_id", conjuntos
                )
                _delete_in(connection, "conjuntos_referencias_web", "id", conjuntos)
                _delete_in(connection, "solicitacoes_cadastro_web", "id", solicitacoes)
                _delete_in(connection, "jobs_faciais_web", "id", jobs)
                connection.execute(
                    text("DELETE FROM alunos WHERE id = :aluno_id"),
                    {"aluno_id": aluno_id},
                )
            for caminho in caminhos:
                if caminho is not None:
                    storage.remover(str(caminho))
            self._exclusoes_aplicadas += 1
        return self._exclusoes_aplicadas

    def invalidar_sessoes_e_tokens(self, banco: str) -> int:
        self._exigir_validacao(banco)
        with self._engine.begin() as connection:
            sessoes = (
                connection.scalar(text("SELECT count(*) FROM sessoes_autenticacao_web"))
                or 0
            )
            contas = connection.scalar(text("SELECT count(*) FROM contas_web")) or 0
            connection.execute(text("DELETE FROM sessoes_autenticacao_web"))
            connection.execute(
                text("UPDATE contas_web SET versao_credencial = versao_credencial + 1")
            )
            connection.execute(
                text(
                    "UPDATE links_cadastro_web SET expira_em = CURRENT_TIMESTAMP "
                    "WHERE expira_em > CURRENT_TIMESTAMP"
                )
            )
            connection.execute(
                text(
                    "UPDATE credenciais_link_cadastro_web "
                    "SET expira_em = CURRENT_TIMESTAMP "
                    "WHERE expira_em > CURRENT_TIMESTAMP"
                )
            )
            connection.execute(
                text(
                    "UPDATE solicitacoes_cadastro_web SET "
                    "credencial_captura_hash = NULL, "
                    "credencial_captura_expira_em = NULL, "
                    "desafio_nonce_hash = NULL, desafio_direcao = NULL, "
                    "desafio_expira_em = NULL "
                    "WHERE credencial_captura_hash IS NOT NULL "
                    "OR desafio_nonce_hash IS NOT NULL"
                )
            )
        return int(sessoes) + int(contas)

    def validar_restore(self, banco: str, manifesto: ManifestoBackup) -> None:
        self._exigir_validacao(banco)
        exclusoes = self._exclusions.exclusoes_a_reaplicar()
        with self._engine.connect() as connection:
            revision = connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            alunos = connection.scalar(text("SELECT count(*) FROM alunos"))
            sessoes = connection.scalar(
                text("SELECT count(*) FROM sessoes_autenticacao_web")
            )
            links_vivos = connection.scalar(
                text(
                    "SELECT count(*) FROM links_cadastro_web "
                    "WHERE expira_em > CURRENT_TIMESTAMP"
                )
            )
            credenciais_vivas = connection.scalar(
                text(
                    "SELECT count(*) FROM credenciais_link_cadastro_web "
                    "WHERE expira_em > CURRENT_TIMESTAMP"
                )
            )
        if revision != manifesto.revisao_schema:
            raise RuntimeError("A revisÃ£o do schema restaurado diverge do manifesto.")
        if (
            alunos is None
            or int(sessoes or 0) != 0
            or int(links_vivos or 0) != 0
            or int(credenciais_vivas or 0) != 0
        ):
            raise RuntimeError(
                "A validaÃ§Ã£o de dados ou invalidaÃ§Ã£o de sessÃ£o falhou."
            )
        for exclusao in exclusoes:
            with self._engine.connect() as connection:
                ainda_presente = connection.scalar(
                    text("SELECT count(*) FROM alunos WHERE id = :aluno_id"),
                    {"aluno_id": exclusao.identificador},
                )
            if int(ainda_presente or 0) != 0:
                raise RuntimeError("Uma exclusÃ£o nÃ£o foi reaplicada no restore.")

    def limpar_staging(self, staging: Path) -> None:
        if staging.is_symlink() or staging.parent.resolve() != self._staging_root:
            raise ValueError("Staging de restore nÃ£o pode ser symlink.")
        shutil.rmtree(staging, ignore_errors=False)

    def _exigir_validacao(self, banco: str) -> None:
        if not self._base_validada or banco != self._database:
            raise PermissionError("O alvo de restore nÃ£o foi validado.")


def _validar_caminho_manifesto(value: str) -> PurePosixPath:
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (
        not value
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or "\\" in value
        or ".." in posix.parts
        or posix.parts[0] not in {"database.dump", "references"}
        or (posix.parts[0] == "database.dump" and len(posix.parts) != 1)
        or (
            posix.parts[0] == "references"
            and (
                len(posix.parts) != 2
                or re.fullmatch(r"[0-9a-f]{48}\.bin", posix.parts[1]) is None
            )
        )
    ):
        raise ValueError("Caminho do manifesto fora do snapshot esperado.")
    return posix


def _validar_destino_referencia(value: str) -> PurePosixPath:
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (
        not value
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or windows.root
        or "\\" in value
        or len(posix.parts) != 2
        or re.fullmatch(r"[1-9][0-9]*", posix.parts[0]) is None
        or re.fullmatch(r"[1-3]-[0-9a-f]{48}\.bin", posix.parts[1]) is None
    ):
        raise ValueError("Destino de referência do manifesto inválido.")
    return posix


def _exigir_dentro(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as erro:
        raise ValueError("Caminho do restore escapa do staging.") from erro


def _digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _expanding(name: str) -> BindParameter[object]:
    from sqlalchemy import bindparam

    return bindparam(name, expanding=True)


def _delete_in(
    connection: Connection,
    table: str,
    column: str,
    values: set[object] | tuple[object, ...],
) -> None:
    if not values:
        return
    allowed = {
        ("desafios_verificacao_web", "id"),
        ("referencias_faciais_web", "conjunto_id"),
        ("conjuntos_referencias_web", "id"),
        ("solicitacoes_cadastro_web", "id"),
        ("jobs_faciais_web", "id"),
    }
    if (table, column) not in allowed:
        raise ValueError("Destino SQL nÃ£o permitido.")
    query = text(f"DELETE FROM {table} WHERE {column} IN :ids").bindparams(
        _expanding("ids")
    )
    connection.execute(query, {"ids": list(values)})
