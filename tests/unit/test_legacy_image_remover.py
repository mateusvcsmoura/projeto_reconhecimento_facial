from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.storage.legacy_image_remover import LegacyImageRemover


def test_remocao_legada_apaga_somente_arquivo_na_raiz(tmp_path: Path) -> None:
    arquivo = tmp_path / "foto-sintetica.jpg"
    arquivo.write_bytes(b"imagem sintetica")
    remover = LegacyImageRemover(tmp_path)

    remover.remover(arquivo.name)
    remover.remover(arquivo.name)

    assert not arquivo.exists()


@pytest.mark.parametrize("nome", ["../fora.jpg", "C:/fora.jpg", "", ".", ".."])
def test_remocao_legada_recusa_caminho_absoluto_ou_travessia(
    tmp_path: Path, nome: str
) -> None:
    remover = LegacyImageRemover(tmp_path / "imagens")

    with pytest.raises(ValueError):
        remover.remover(nome)
