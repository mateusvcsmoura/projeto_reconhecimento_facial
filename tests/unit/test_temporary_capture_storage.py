from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from src.infrastructure.storage.temporary_capture_storage import (
    TemporaryCaptureStorage,
)


def test_grava_capturas_com_limite_e_remove_o_diretorio_do_job(
    tmp_path: Path,
) -> None:
    storage = TemporaryCaptureStorage(
        tmp_path / "capturas",
        max_bytes_per_capture=16,
        max_captures=3,
    )
    job_id = uuid.uuid4()

    storage.salvar_captura(job_id, 1, b"synthetic")

    manifesto = storage.manifesto(job_id)
    assert len(manifesto.capturas) == 1
    assert manifesto.capturas[0].tamanho_bytes == 9


def test_rejeita_payload_acima_do_limite_antes_de_criar_arquivo(
    tmp_path: Path,
) -> None:
    storage = TemporaryCaptureStorage(
        tmp_path / "capturas",
        max_bytes_per_capture=8,
        max_captures=3,
    )
    job_id = uuid.uuid4()

    with pytest.raises(ValueError, match="limite"):
        storage.salvar_captura(job_id, 1, b"x" * 9)

    assert not (tmp_path / "capturas" / str(job_id)).exists()


def test_manifesto_ausente_e_orfaos_sao_limpos(tmp_path: Path) -> None:
    storage = TemporaryCaptureStorage(
        tmp_path / "capturas",
        max_bytes_per_capture=16,
        max_captures=3,
    )
    ativo = uuid.uuid4()
    orfao = uuid.uuid4()
    storage.salvar_captura(ativo, 1, b"active")
    storage.salvar_captura(orfao, 1, b"orphan")

    removidos = storage.limpar_orfaos({ativo})

    assert removidos == 1
    assert (tmp_path / "capturas" / str(ativo)).is_dir()
    assert not (tmp_path / "capturas" / str(orfao)).exists()


def test_manifesto_nao_pode_sair_da_raiz_temporaria(tmp_path: Path) -> None:
    storage = TemporaryCaptureStorage(
        tmp_path / "capturas",
        max_bytes_per_capture=16,
        max_captures=3,
    )
    job_id = uuid.uuid4()

    with pytest.raises(ValueError, match="manifesto"):
        storage.ler_captura(job_id, "..\\fora.bin")
