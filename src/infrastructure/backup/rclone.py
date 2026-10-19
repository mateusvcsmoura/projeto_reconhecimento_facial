"""Adaptadores rclone com configuração externa e comandos sem shell."""

from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from src.application.services.web_backup import ChaveBackupAusente, ManifestoBackup

_ID_RE = re.compile(r"[0-9a-f]{32}")
_REMOTE_RE = re.compile(r"(?P<alias>[A-Za-z0-9_-]+):(?P<path>[^\r\n]*)\Z")


class RcloneRunner(Protocol):
    def executar(self, argumentos: list[str]) -> str: ...


class ErroComandoExterno(RuntimeError):
    def __init__(self, ferramenta: str, codigo_saida: int) -> None:
        super().__init__(
            f"A ferramenta {ferramenta} falhou (código {codigo_saida}); "
            "saída técnica omitida para proteger credenciais."
        )
        self.ferramenta = ferramenta
        self.codigo_saida = codigo_saida


class RcloneCommandRunner:
    """Executa rclone com argv e ambiente mínimo, sem registrar stdout/stderr."""

    def __init__(self, config_path: Path, *, executable: str = "rclone") -> None:
        self._config_path = config_path.expanduser().resolve()
        self._executable = executable

    def executar(self, argumentos: list[str]) -> str:
        if not argumentos or any(not isinstance(item, str) for item in argumentos):
            raise ValueError("Comando rclone inválido.")
        ambiente = {"PATH": os.environ.get("PATH", "")}
        for nome in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            if valor := os.environ.get(nome):
                ambiente[nome] = valor
        ambiente["RCLONE_CONFIG"] = str(self._config_path)
        if segredo_config := os.environ.get("RCLONE_CONFIG_PASS"):
            ambiente["RCLONE_CONFIG_PASS"] = segredo_config
        resultado = subprocess.run(
            [self._executable, *argumentos],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=ambiente,
            shell=False,
        )
        if resultado.returncode != 0:
            raise ErroComandoExterno("rclone", resultado.returncode)
        return resultado.stdout


class RcloneCryptArchive:
    """Armazena no crypt remoto; nomes internos e conteúdo são cifrados."""

    def __init__(
        self,
        runner: RcloneRunner,
        *,
        config_path: Path,
        remote: str,
        state_dir: Path,
        external_remote: str | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._runner = runner
        self._config_path = config_path.expanduser().resolve()
        self._remote = remote
        self._external_remote = external_remote
        self._state_dir_original = state_dir.expanduser()
        self._state_dir = self._state_dir_original.resolve()
        self._project_root = (
            project_root or Path(__file__).resolve().parents[3]
        ).resolve()
        self._verificados: set[str] = set()

    def validar_configuracao(self) -> None:
        if not self._config_path.is_file():
            raise ValueError("A configuração externa do rclone está ausente.")
        if self._config_path.is_relative_to(self._project_root):
            raise ValueError("A configuração do rclone deve ficar fora do repositório.")
        if self._state_dir_original.is_symlink():
            raise ValueError("A raiz de estado do backup nÃ£o pode ser symlink.")
        if self._state_dir.is_relative_to(self._project_root):
            raise ValueError("O estado do backup deve ficar fora do repositÃ³rio.")
        alias, _ = _separar_remote(self._remote)
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(self._config_path, encoding="utf-8")
        except (OSError, configparser.Error):
            raise ValueError("A configuração externa do rclone é inválida.") from None
        if not parser.has_section(alias):
            raise ValueError("O remote crypt configurado não existe.")
        remote = parser[alias]
        if remote.get("type", "").strip().lower() != "crypt":
            raise ValueError("O destino local precisa ser um remote crypt.")
        if not remote.get("password", "").strip():
            raise ChaveBackupAusente("Chave de criptografia do backup ausente.")
        if remote.get("filename_encryption", "standard").strip().lower() != "standard":
            raise ValueError("O remote crypt precisa usar cifra de nomes de arquivos.")
        if remote.get("directory_name_encryption", "true").strip().lower() != "false":
            raise ValueError(
                "O remote crypt deve manter somente o diretório opaco da geração "
                "visível para copiar bytes cifrados entre remotes."
            )

        if self._external_remote is not None:
            external_alias, _ = _separar_remote(self._external_remote)
            if (
                not parser.has_section(external_alias)
                or parser[external_alias].get("type", "").strip().lower() == "crypt"
            ):
                raise ValueError(
                    "O remote externo deve ser um destino raw configurado."
                )

    def cifrar(self, staging: Path, destino: str, geracao: str) -> None:
        self._validar_geracao(geracao)
        self.validar_configuracao()
        self._exigir_remote_configurado(destino)
        self._preparar_estado()
        progresso = self._progresso(geracao)
        _escrever_json_seguro(
            progresso,
            {"geracao": geracao, "iniciada_em": datetime.now(UTC).isoformat()},
            substituir=False,
        )
        self._runner.executar(
            ["copy", str(staging), self._caminho_geracao(destino, geracao)]
        )

    def verificar(self, staging: Path, destino: str, geracao: str) -> None:
        self._validar_geracao(geracao)
        self.validar_configuracao()
        self._exigir_remote_configurado(destino)
        self._runner.executar(
            ["cryptcheck", str(staging), self._caminho_geracao(destino, geracao)]
        )
        self._verificados.add(geracao)

    def marcar_completa(self, destino: str, manifesto: ManifestoBackup) -> None:
        self._validar_geracao(manifesto.geracao)
        self._exigir_remote_configurado(destino)
        if manifesto.geracao not in self._verificados:
            raise ValueError("A geração não passou por cryptcheck.")
        if not self._progresso(manifesto.geracao).is_file():
            raise ValueError("A geração não tem marca de execução iniciada.")
        dados = {
            "geracao": manifesto.geracao,
            "criado_em": manifesto.criado_em.astimezone(UTC).isoformat(),
            "modo": manifesto.modo,
            "versao_aplicacao": manifesto.versao_aplicacao,
            "revisao_schema": manifesto.revisao_schema,
            "tamanho_bytes": manifesto.tamanho_total_bytes,
            "manifesto_sha256": _sha256_json(asdict(manifesto)),
        }
        _escrever_json_seguro(self._completa(manifesto.geracao), dados)
        self._progresso(manifesto.geracao).unlink(missing_ok=True)
        self._verificados.discard(manifesto.geracao)

    def descartar_incompleta(self, destino: str, geracao: str) -> None:
        self._validar_geracao(geracao)
        self.validar_configuracao()
        self._exigir_remote_configurado(destino)
        progresso = self._progresso(geracao)
        completa = self._completa(geracao)
        externa = self._externa(geracao)
        if progresso.exists():
            self._runner.executar(["purge", self._caminho_geracao(destino, geracao)])
        progresso.unlink(missing_ok=True)
        completa.unlink(missing_ok=True)
        externa.unlink(missing_ok=True)
        self._verificados.discard(geracao)

    def exigir_geracao_completa(self, geracao: str) -> None:
        self._validar_geracao(geracao)
        marker = self._completa(geracao)
        try:
            dados = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as erro:
            raise ValueError("A geração local está incompleta.") from erro
        if dados.get("geracao") != geracao or not _marcador_completo_valido(dados):
            raise ValueError("A marca local pertence a outra geração.")

    def marcar_transporte_completo(
        self, geracao: str, destino: str, tamanho_bytes: int, sha256: str
    ) -> None:
        self.exigir_geracao_completa(geracao)
        self._exigir_remote_externo(destino)
        _escrever_json_seguro(
            self._externa(geracao),
            {
                "geracao": geracao,
                "destino": destino,
                "tamanho_bytes": tamanho_bytes,
                "sha256": sha256,
                "verificado_em": datetime.now(UTC).isoformat(),
            },
        )
        self._transporte_em_andamento(geracao).unlink(missing_ok=True)

    def iniciar_transporte(self, geracao: str, destino: str) -> None:
        self.exigir_geracao_completa(geracao)
        self._exigir_remote_externo(destino)
        if self._externa(geracao).exists():
            raise ValueError("A geração já foi transportada para o destino externo.")
        _escrever_json_seguro(
            self._transporte_em_andamento(geracao),
            {"geracao": geracao, "destino": destino},
            substituir=False,
        )

    def abortar_transporte(self, geracao: str, destino: str) -> None:
        self._validar_geracao(geracao)
        self._exigir_remote_externo(destino)
        marker = self._transporte_em_andamento(geracao)
        if not marker.exists():
            return
        if marker.is_symlink():
            raise ValueError("A marca de transporte externo é insegura.")
        try:
            dados = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError("A marca de transporte externo é inválida.") from None
        if dados.get("geracao") != geracao or dados.get("destino") != destino:
            raise ValueError("A marca de transporte aponta para outro destino.")
        self._runner.executar(["purge", _remote_generation(destino, geracao)])
        marker.unlink(missing_ok=True)

    def listar_transportes_incompletos(self) -> tuple[str, ...]:
        if self._state_dir_original.is_symlink():
            raise ValueError("Raiz de estado do backup insegura.")
        if not self._state_dir.exists():
            return ()
        if not self._state_dir.is_dir():
            raise ValueError("Raiz de estado do backup inválida.")
        return tuple(
            marker.name.removesuffix(".external-inprogress.json")
            for marker in sorted(self._state_dir.glob("*.external-inprogress.json"))
            if not marker.is_symlink()
            and _ID_RE.fullmatch(marker.name.removesuffix(".external-inprogress.json"))
        )

    def remover_transporte_incompleto(self, geracao: str) -> None:
        self._validar_geracao(geracao)
        marker = self._transporte_em_andamento(geracao)
        if marker.is_symlink():
            raise ValueError("A marca de transporte externo é insegura.")
        try:
            dados = json.loads(marker.read_text(encoding="utf-8"))
            destino = str(dados["destino"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            raise ValueError("A marca de transporte externo é inválida.") from None
        self._exigir_remote_externo(destino)
        if dados.get("geracao") != geracao:
            raise ValueError("A marca de transporte pertence a outra geração.")
        self._runner.executar(["purge", _remote_generation(destino, geracao)])
        marker.unlink(missing_ok=True)

    def listar_geracoes_completas(self) -> tuple[dict[str, object], ...]:
        if self._state_dir_original.is_symlink():
            raise ValueError("Raiz de estado do backup insegura.")
        if not self._state_dir.exists():
            return ()
        if not self._state_dir.is_dir():
            raise ValueError("Raiz de estado do backup invÃ¡lida.")
        geracoes: list[dict[str, object]] = []
        for marker in sorted(self._state_dir.glob("*.complete.json")):
            if marker.is_symlink():
                raise ValueError("A raiz de estado contÃ©m marca symlink.")
            try:
                dados = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            geracao = marker.name.removesuffix(".complete.json")
            if (
                _ID_RE.fullmatch(geracao)
                and dados.get("geracao") == geracao
                and _marcador_completo_valido(dados)
            ):
                geracoes.append(dados)
        return tuple(geracoes)

    def listar_incompletas(self) -> tuple[str, ...]:
        if self._state_dir_original.is_symlink():
            raise ValueError("Raiz de estado do backup insegura.")
        if not self._state_dir.exists():
            return ()
        if not self._state_dir.is_dir():
            raise ValueError("Raiz de estado do backup invÃ¡lida.")
        return tuple(
            marker.name.removesuffix(".inprogress.json")
            for marker in sorted(self._state_dir.glob("*.inprogress.json"))
            if not marker.is_symlink()
            and _ID_RE.fullmatch(marker.name.removesuffix(".inprogress.json"))
        )

    def remover_geracao(self, geracao: str, destino: str) -> None:
        self._validar_geracao(geracao)
        self.validar_configuracao()
        self._exigir_remote_configurado(destino)
        progresso = self._progresso(geracao)
        completa = self._completa(geracao)
        if not progresso.exists() and not completa.exists():
            raise ValueError("A geraÃ§Ã£o nÃ£o pertence ao catÃ¡logo local.")
        external_marker = self._externa(geracao)
        if external_marker.exists():
            if external_marker.is_symlink():
                raise ValueError("A marca externa do backup é insegura.")
            try:
                external = json.loads(external_marker.read_text(encoding="utf-8"))
                external_destination = str(external["destino"])
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                raise ValueError("A marca externa do backup é inválida.") from None
            self._exigir_remote_externo(external_destination)
            if external.get("geracao") != geracao:
                raise ValueError("A marca externa pertence a outra geração.")
            self._runner.executar(
                ["purge", _remote_generation(external_destination, geracao)]
            )
        self._runner.executar(["purge", self._caminho_geracao(destino, geracao)])
        progresso.unlink(missing_ok=True)
        completa.unlink(missing_ok=True)
        self._externa(geracao).unlink(missing_ok=True)
        self._verificados.discard(geracao)

    def _preparar_estado(self) -> None:
        if self._state_dir_original.is_symlink():
            raise ValueError("A raiz de estado do backup não pode ser symlink.")
        self._state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            self._state_dir.chmod(0o700)

    def _validar_geracao(self, geracao: str) -> None:
        if _ID_RE.fullmatch(geracao) is None:
            raise ValueError("O identificador da geração é inválido.")

    def _caminho_geracao(self, remoto: str, geracao: str) -> str:
        _separar_remote(remoto)
        return f"{remoto.rstrip('/')}/{geracao}"

    def _exigir_remote_configurado(self, destino: str) -> None:
        if not _same_remote(destino, self._remote):
            raise ValueError("Destino deve corresponder ao remote crypt configurado.")

    def _progresso(self, geracao: str) -> Path:
        return self._state_dir / f"{geracao}.inprogress.json"

    def _completa(self, geracao: str) -> Path:
        return self._state_dir / f"{geracao}.complete.json"

    def _externa(self, geracao: str) -> Path:
        return self._state_dir / f"{geracao}.external.json"

    def _transporte_em_andamento(self, geracao: str) -> Path:
        return self._state_dir / f"{geracao}.external-inprogress.json"

    def _exigir_remote_externo(self, destino: str) -> None:
        if self._external_remote is None or not _same_remote(
            destino, self._external_remote
        ):
            raise ValueError("Destino externo não corresponde ao remote configurado.")


class RcloneCiphertextTransport:
    """Replica bytes cifrados para outro remote e compara conteÃºdo antes do sucesso."""

    def __init__(
        self,
        runner: RcloneRunner,
        *,
        config_path: Path,
        encrypted_remote: str,
        external_remote: str,
        scratch_dir: Path,
    ) -> None:
        self._runner = runner
        self._config_path = config_path.expanduser().resolve()
        self._encrypted_remote = encrypted_remote
        self._external_remote = external_remote
        self._scratch_dir_original = scratch_dir.expanduser()
        self._scratch_dir = self._scratch_dir_original.resolve()
        self._source_raw = ""
        self._validated = False

    def copiar_e_verificar(self, geracao: str) -> tuple[int, str]:
        if _ID_RE.fullmatch(geracao) is None:
            raise ValueError("O identificador da geraÃ§Ã£o Ã© invÃ¡lido.")
        self._validar()
        source = _remote_generation(self._source_raw, geracao)
        target = _remote_generation(self._external_remote, geracao)
        self._runner.executar(["copy", source, target])
        self._runner.executar(["check", source, target, "--download"])
        try:
            listado = json.loads(
                self._runner.executar(
                    ["lsjson", source, "--recursive", "--files-only", "--hash"]
                )
            )
        except json.JSONDecodeError as erro:
            raise RuntimeError(
                "A listagem de verificaÃ§Ã£o do backup Ã© invÃ¡lida."
            ) from erro
        if not isinstance(listado, list) or not listado:
            raise RuntimeError("A cÃ³pia cifrada estÃ¡ vazia.")
        itens: list[dict[str, object]] = []
        total = 0
        for entrada in listado:
            if not isinstance(entrada, dict):
                raise RuntimeError("A listagem cifrada contÃ©m item invÃ¡lido.")
            nome, tamanho = entrada.get("Path"), entrada.get("Size")
            if (
                not isinstance(nome, str)
                or not nome
                or Path(nome).is_absolute()
                or ".." in Path(nome).parts
                or isinstance(tamanho, bool)
                or not isinstance(tamanho, int)
                or tamanho < 0
            ):
                raise RuntimeError(
                    "A listagem cifrada contÃ©m caminho/tamanho invÃ¡lido."
                )
            total += tamanho
            itens.append(
                {"path": nome, "size": tamanho, "hashes": entrada.get("Hashes", {})}
            )
        self._verificar_amostra(source, target, str(itens[0]["path"]))
        fingerprint = hashlib.sha256(
            json.dumps(itens, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return total, fingerprint

    def _validar(self) -> None:
        if self._validated:
            return
        if not self._config_path.is_file():
            raise ValueError("A configuraÃ§Ã£o externa do rclone estÃ¡ ausente.")
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(self._config_path, encoding="utf-8")
            encrypted_alias, encrypted_path = _separar_remote(self._encrypted_remote)
            external_alias, _ = _separar_remote(self._external_remote)
            if not parser.has_section(encrypted_alias) or not parser.has_section(
                external_alias
            ):
                raise ValueError("Remote rclone nÃ£o configurado.")
            crypt = parser[encrypted_alias]
            if crypt.get("type", "").strip().lower() != "crypt":
                raise ValueError("A origem precisa ser um remote crypt.")
            raw = crypt.get("remote", "").strip()
            raw_alias, raw_path = _separar_remote(raw)
            if (
                not parser.has_section(raw_alias)
                or parser[raw_alias].get("type", "").lower() == "crypt"
            ):
                raise ValueError(
                    "A origem cifrada precisa resolver para um remote raw."
                )
            if encrypted_path.rstrip("/") != raw_path.rstrip("/"):
                raise ValueError(
                    "O remote configurado nÃ£o corresponde ao arquivo cifrado."
                )
            if parser[external_alias].get("type", "").strip().lower() == "crypt":
                raise ValueError(
                    "O destino externo deve receber os bytes jÃ¡ cifrados."
                )
            if self._scratch_dir.is_relative_to(Path(__file__).resolve().parents[3]):
                raise ValueError(
                    "Staging de transporte deve ficar fora do repositorio."
                )
            if self._scratch_dir_original.is_symlink():
                raise ValueError(
                    "A raiz temporÃ¡ria de transporte nÃ£o pode ser symlink."
                )
            self._scratch_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            if os.name == "posix":
                self._scratch_dir.chmod(0o700)
            self._source_raw = f"{raw_alias}:{raw_path}"
            self._validated = True
        except (OSError, configparser.Error):
            raise ValueError(
                "A configuraÃ§Ã£o do transporte rclone Ã© invÃ¡lida."
            ) from None

    def _verificar_amostra(self, source: str, target: str, nome: str) -> None:
        self._scratch_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="task017-amostra-", dir=self._scratch_dir
        ) as temp:
            raiz = Path(temp)
            origem, copia = raiz / "origem.bin", raiz / "destino.bin"
            relative = nome.replace("\\", "/")
            if relative.startswith("/") or any(
                segment == ".." for segment in relative.split("/")
            ):
                raise RuntimeError("Caminho de amostra cifrada invÃ¡lido.")
            self._runner.executar(
                ["copyto", f"{source.rstrip('/')}/{relative}", str(origem)]
            )
            self._runner.executar(
                ["copyto", f"{target.rstrip('/')}/{relative}", str(copia)]
            )
            if (
                not origem.is_file()
                or not copia.is_file()
                or _sha256(origem) != _sha256(copia)
            ):
                raise RuntimeError("A amostra transferida diverge do backup local.")


class RcloneRestoreArchive:
    """Descriptografa apenas geraÃ§Ã£o completa para staging privado."""

    def __init__(
        self,
        runner: RcloneRunner,
        *,
        archive: RcloneCryptArchive,
        encrypted_remote: str,
        staging_root: Path,
        project_root: Path | None = None,
    ) -> None:
        self._runner = runner
        self._archive = archive
        self._remote = encrypted_remote
        self._root_original = staging_root.expanduser()
        self._root = self._root_original.resolve()
        self._project_root = (
            project_root or Path(__file__).resolve().parents[3]
        ).resolve()
        if (
            not self._root_original.is_absolute()
            or self._root_original.is_symlink()
            or self._root.is_relative_to(self._project_root)
        ):
            raise ValueError(
                "Staging de restore deve ser absoluto e externo ao repositorio."
            )

    def descriptografar(self, geracao: str) -> Path:
        if not _same_remote(self._remote, self._archive._remote):
            raise ValueError("Restore deve usar o remote crypt configurado.")
        self._archive.validar_configuracao()
        self._archive.exigir_geracao_completa(geracao)
        if self._root_original.is_symlink():
            raise ValueError("A raiz de restore nÃ£o pode ser symlink.")
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            self._root.chmod(0o700)
        staging = Path(tempfile.mkdtemp(prefix=f"{geracao}-", dir=self._root))
        if os.name == "posix":
            staging.chmod(0o700)
        try:
            self._runner.executar(
                ["copy", _remote_generation(self._remote, geracao), str(staging)]
            )
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return staging


def _remote_generation(remote: str, geracao: str) -> str:
    alias, path = _separar_remote(remote)
    base = f"{alias}:{path}".rstrip("/")
    return f"{base}/{geracao}" if geracao else base


def _same_remote(left: str, right: str) -> bool:
    try:
        left_alias, left_path = _separar_remote(left)
        right_alias, right_path = _separar_remote(right)
    except ValueError:
        return False
    return left_alias == right_alias and left_path.rstrip("/") == right_path.rstrip("/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _separar_remote(remoto: str) -> tuple[str, str]:
    correspondencia = _REMOTE_RE.fullmatch(remoto)
    if correspondencia is None or ".." in Path(correspondencia.group("path")).parts:
        raise ValueError("O remote rclone configurado é inválido.")
    return correspondencia.group("alias"), correspondencia.group("path")


def _escrever_json_seguro(
    destino: Path, valor: dict[str, object], *, substituir: bool = True
) -> None:
    destino.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        destino.parent.chmod(0o700)
    temporario = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporario, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as arquivo:
            json.dump(valor, arquivo, ensure_ascii=False, sort_keys=True)
            arquivo.write("\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        if not substituir and destino.exists():
            temporario.unlink(missing_ok=True)
            raise FileExistsError("Já existe uma marca de estado para a geração.")
        os.replace(temporario, destino)
    except Exception:
        temporario.unlink(missing_ok=True)
        raise


def _sha256_json(valor: object) -> str:
    import hashlib

    serializado = json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: (
            item.isoformat() if isinstance(item, datetime) else str(item)
        ),
    ).encode("utf-8")
    return hashlib.sha256(serializado).hexdigest()


def _marcador_completo_valido(dados: object) -> bool:
    if not isinstance(dados, dict):
        return False
    try:
        criado = datetime.fromisoformat(str(dados["criado_em"]))
        tamanho = dados["tamanho_bytes"]
        checksum = dados["manifesto_sha256"]
    except (KeyError, TypeError, ValueError):
        return False
    return bool(
        criado.tzinfo is not None
        and isinstance(dados.get("modo"), str)
        and isinstance(dados.get("versao_aplicacao"), str)
        and isinstance(dados.get("revisao_schema"), str)
        and isinstance(tamanho, int)
        and not isinstance(tamanho, bool)
        and tamanho >= 0
        and isinstance(checksum, str)
        and re.fullmatch(r"[0-9a-f]{64}", checksum) is not None
    )
