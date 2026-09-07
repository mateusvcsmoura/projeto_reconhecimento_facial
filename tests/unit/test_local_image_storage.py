"""Fase 7 -- armazenamento local de imagens, com cv2 dublado."""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

CAMINHO = "src.infrastructure.storage.local_image_storage"


class Cv2Duble:
    def __init__(self) -> None:
        self.gravacoes: list[str] = []
        self.sucesso = True

    def imwrite(self, destino: str, imagem: Any) -> bool:
        self.gravacoes.append(destino)
        if not self.sucesso:
            return False
        Path(destino).write_bytes(b"jpeg-sintetico")
        return True


@pytest.fixture
def cv2_duble() -> Iterator[Cv2Duble]:
    falso = Cv2Duble()
    modulo = types.ModuleType("cv2")
    modulo.imwrite = falso.imwrite  # type: ignore[attr-defined]

    original = sys.modules.get("cv2")
    sys.modules["cv2"] = modulo
    sys.modules.pop(CAMINHO, None)
    try:
        yield falso
    finally:
        sys.modules.pop(CAMINHO, None)
        if original is None:
            sys.modules.pop("cv2", None)
        else:
            sys.modules["cv2"] = original


def montar(raiz: Path) -> Any:
    return importlib.import_module(CAMINHO).LocalImageStorage(raiz)


def test_salvar_cria_o_diretorio_e_devolve_o_nome(
    cv2_duble: Cv2Duble, tmp_path: Path
) -> None:
    storage = montar(tmp_path / "faces")

    nome = storage.salvar("42.jpg", object())

    assert nome == "42.jpg"
    assert (tmp_path / "faces" / "42.jpg").is_file()


def test_falha_de_gravacao_vira_erro_explicito(
    cv2_duble: Cv2Duble, tmp_path: Path
) -> None:
    """imwrite devolve False em vez de levantar -- nao pode passar batido."""
    cv2_duble.sucesso = False
    storage = montar(tmp_path)

    with pytest.raises(OSError, match="Nao foi possivel gravar"):
        storage.salvar("42.jpg", object())


def test_nome_com_diretorio_nao_escapa_da_raiz(
    cv2_duble: Cv2Duble, tmp_path: Path
) -> None:
    """Um nome vindo do banco nao pode gravar fora de STORAGE_DIR."""
    raiz = tmp_path / "faces"
    storage = montar(raiz)

    storage.salvar("../../fora.jpg", object())

    assert (raiz / "fora.jpg").is_file()
    assert not (tmp_path.parent / "fora.jpg").exists()


def test_existe_reflete_o_disco(cv2_duble: Cv2Duble, tmp_path: Path) -> None:
    storage = montar(tmp_path)

    assert storage.existe("42.jpg") is False
    storage.salvar("42.jpg", object())
    assert storage.existe("42.jpg") is True


def test_remover_apaga_o_arquivo(cv2_duble: Cv2Duble, tmp_path: Path) -> None:
    storage = montar(tmp_path)
    storage.salvar("42.jpg", object())

    storage.remover("42.jpg")

    assert storage.existe("42.jpg") is False


def test_remover_arquivo_inexistente_nao_quebra(
    cv2_duble: Cv2Duble, tmp_path: Path
) -> None:
    """A exclusao de um aluno nao pode falhar por causa de imagem ja ausente."""
    montar(tmp_path).remover("nao-existe.jpg")


def test_caminho_absoluto_aponta_para_dentro_da_raiz(
    cv2_duble: Cv2Duble, tmp_path: Path
) -> None:
    storage = montar(tmp_path)

    absoluto = Path(storage.caminho_absoluto("42.jpg"))

    assert absoluto.parent == tmp_path.resolve()


def test_caminho_absoluto_tambem_e_sanitizado(
    cv2_duble: Cv2Duble, tmp_path: Path
) -> None:
    storage = montar(tmp_path)

    absoluto = Path(storage.caminho_absoluto("../../etc/passwd"))

    assert absoluto.parent == tmp_path.resolve()
    assert absoluto.name == "passwd"
