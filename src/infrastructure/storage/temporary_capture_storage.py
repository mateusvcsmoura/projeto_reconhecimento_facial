"""Armazenamento transitório privado para capturas compartilhadas com worker."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from uuid import UUID

from src.application.services.fila_facial import (
    ArquivoTemporario,
    ManifestoTemporario,
)


class TemporaryCaptureStorage:
    """Armazena bytes limitados em diretórios exclusivos por UUID de job."""

    def __init__(
        self,
        raiz: Path,
        *,
        max_bytes_per_capture: int,
        max_captures: int = 3,
        quota_bytes: int = 300 * 1024 * 1024,
        require_memory_fs: bool = False,
    ) -> None:
        if max_bytes_per_capture < 1 or max_captures != 3 or quota_bytes < 1:
            raise ValueError("Os limites do armazenamento temporário são inválidos.")
        self._raiz = raiz.expanduser().resolve()
        self._max_bytes = max_bytes_per_capture
        self._max_captures = max_captures
        self._quota_bytes = quota_bytes
        self._require_memory_fs = require_memory_fs
        self._raiz.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            self._raiz.chmod(0o700)
        if require_memory_fs:
            self._exigir_memoria_compartilhada()

    @property
    def raiz(self) -> Path:
        return self._raiz

    def salvar_captura(self, job_id: UUID, ordinal: int, conteudo: bytes) -> None:
        if ordinal not in range(1, self._max_captures + 1):
            raise ValueError("Ordinal de captura inválido.")
        if not isinstance(conteudo, bytes) or not conteudo:
            raise ValueError("A captura está vazia ou não contém bytes.")
        if len(conteudo) > self._max_bytes:
            raise ValueError("A captura excede o limite de bytes.")

        diretorio = self._diretorio_job(job_id)
        if diretorio.exists() and len(tuple(diretorio.iterdir())) >= self._max_captures:
            raise ValueError("O job excede o limite de capturas.")
        diretorio.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            diretorio.chmod(0o700)
        destino = diretorio / f"captura-{ordinal}.bin"
        criado = False
        try:
            with destino.open("xb") as arquivo:
                criado = True
                arquivo.write(conteudo)
            if os.name == "posix":
                destino.chmod(0o600)
        except OSError:
            if criado:
                destino.unlink(missing_ok=True)
            raise

    def manifesto(self, job_id: UUID) -> ManifestoTemporario:
        diretorio = self._diretorio_job(job_id)
        if not diretorio.is_dir():
            raise FileNotFoundError("Capturas temporárias indisponíveis.")
        capturas: list[ArquivoTemporario] = []
        for caminho in sorted(diretorio.iterdir()):
            correspondencia = re.fullmatch(r"captura-([1-3])\.bin", caminho.name)
            if correspondencia is None or not caminho.is_file():
                raise ValueError("O diretório temporário contém arquivo inesperado.")
            tamanho = caminho.stat().st_size
            if tamanho < 1 or tamanho > self._max_bytes:
                raise ValueError("Captura temporária inválida.")
            capturas.append(
                ArquivoTemporario(
                    ordinal=int(correspondencia.group(1)),
                    nome=caminho.name,
                    tamanho_bytes=tamanho,
                )
            )
        if len(capturas) > self._max_captures:
            raise ValueError("O job excede o limite de capturas.")
        return ManifestoTemporario(job_id=job_id, capturas=tuple(capturas))

    def ler_captura(self, job_id: UUID, nome: str) -> bytes:
        if re.fullmatch(r"captura-[1-3]\.bin", nome) is None:
            raise ValueError("Nome fora do manifesto temporário.")
        caminho = self._diretorio_job(job_id) / nome
        self._exigir_dentro_da_raiz(caminho.resolve())
        tamanho = caminho.stat().st_size
        if tamanho < 1 or tamanho > self._max_bytes:
            raise ValueError("A captura temporária está inválida.")
        conteudo = caminho.read_bytes()
        return conteudo

    def remover_captura(self, job_id: UUID, ordinal: int) -> None:
        """Descarta a captura recusada de uma etapa devolvida ao aluno."""
        if ordinal not in range(1, self._max_captures + 1):
            raise ValueError("Ordinal de captura inválido.")
        caminho = self._diretorio_job(job_id) / f"captura-{ordinal}.bin"
        self._exigir_dentro_da_raiz(caminho.resolve())
        caminho.unlink(missing_ok=True)

    def remover_job(self, job_id: UUID) -> None:
        diretorio = self._diretorio_job(job_id)
        self._exigir_dentro_da_raiz(diretorio.resolve())
        if diretorio.is_dir():
            shutil.rmtree(diretorio)

    def limpar_orfaos(self, ids_ativos: set[UUID]) -> int:
        removidos = 0
        for caminho in self._raiz.iterdir():
            if not caminho.is_dir():
                continue
            try:
                job_id = UUID(caminho.name)
            except ValueError:
                continue
            if job_id not in ids_ativos:
                self.remover_job(job_id)
                removidos += 1
        return removidos

    def validar_quota_disponivel(self) -> None:
        if (
            self._require_memory_fs
            and shutil.disk_usage(self._raiz).free < self._quota_bytes
        ):
            raise RuntimeError("O tmpfs não comporta a quota configurada.")

    def _diretorio_job(self, job_id: UUID) -> Path:
        if not isinstance(job_id, UUID):
            raise ValueError("O identificador do job deve ser UUID.")
        diretorio = self._raiz / str(job_id)
        self._exigir_dentro_da_raiz(diretorio.resolve())
        return diretorio

    def _exigir_dentro_da_raiz(self, caminho: Path) -> None:
        try:
            caminho.relative_to(self._raiz)
        except ValueError as exc:
            raise ValueError("Caminho fora da raiz temporária.") from exc

    def _exigir_memoria_compartilhada(self) -> None:
        if os.name != "posix" or not Path("/proc/self/mountinfo").is_file():
            raise RuntimeError("O worker exige armazenamento em memória no Linux.")
        caminho = str(self._raiz)
        mounts: list[tuple[int, str, str]] = []
        for linha in Path("/proc/self/mountinfo").read_text().splitlines():
            partes = linha.split()
            try:
                separador = partes.index("-")
                ponto = partes[4].replace("\\040", " ")
                tipo = partes[separador + 1]
            except (IndexError, ValueError):
                continue
            if caminho == ponto or caminho.startswith(ponto.rstrip("/") + "/"):
                mounts.append((len(ponto), ponto, tipo))
        if not mounts or max(mounts, key=lambda item: item[0])[2] != "tmpfs":
            raise RuntimeError("WEB_CAPTURE_TEMP_DIR precisa estar em um tmpfs.")
