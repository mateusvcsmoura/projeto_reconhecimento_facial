"""Proteções locais do armazenamento privado de recortes web."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.storage.private_reference_storage import (
    PrivateReferenceStorageLocal,
)


def test_storage_usa_caminho_relativo_opaco_e_remove_idempotentemente(
    tmp_path: Path,
) -> None:
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")

    caminho = storage.salvar(12, 2, b"recorte sintetico")
    arquivo = tmp_path / "privado" / caminho

    assert not Path(caminho).is_absolute()
    assert caminho.startswith("12/2-")
    assert arquivo.read_bytes() == b"recorte sintetico"
    storage.remover(caminho)
    storage.remover(caminho)
    assert not arquivo.exists()


@pytest.mark.parametrize("caminho", ["../fora.bin", "C:/fora.bin", ""])
def test_storage_nao_remove_fora_da_raiz_privada(tmp_path: Path, caminho: str) -> None:
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")

    with pytest.raises(ValueError):
        storage.remover(caminho)


def test_storage_recusa_ordinal_ou_tamanho_invalido(tmp_path: Path) -> None:
    storage = PrivateReferenceStorageLocal(tmp_path / "privado")

    with pytest.raises(ValueError):
        storage.salvar(12, 4, b"recorte")
    with pytest.raises(ValueError):
        storage.salvar(12, 1, b"")
