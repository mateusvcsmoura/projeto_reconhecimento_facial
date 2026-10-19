from __future__ import annotations

import os
import runpy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "deploy" / "web" / "entrypoint.py"


def test_entrypoint_carrega_segredos_de_arquivos_e_substitui_processo(
    monkeypatch: Any, tmp_path: Path
) -> None:
    secret = tmp_path / "database-url"
    secret.write_text("postgresql://usuario:senha@postgres/db\n", encoding="utf-8")
    monkeypatch.setenv("WEB_DATABASE_URL_FILE", str(secret))
    monkeypatch.setenv("WEB_SECRET_KEY_FILE", str(secret))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL_FILE", str(secret))
    monkeypatch.setenv("WEB_DATABASE_URL", "valor-substituido-pelo-segredo")
    monkeypatch.setenv("WEB_SECRET_KEY", "valor-substituido-pelo-segredo")
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "valor-substituido-pelo-segredo")
    monkeypatch.setattr("sys.argv", ["entrypoint.py", "python", "-m", "worker"])
    chamadas: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        "os.execvp", lambda file, args: chamadas.append((file, list(args)))
    )
    namespace = runpy.run_path(str(ENTRYPOINT), run_name="entrypoint_test")

    namespace["main"]()

    assert chamadas == [("python", ["python", "-m", "worker"])]
    assert os.environ["WEB_DATABASE_URL"] == ("postgresql://usuario:senha@postgres/db")
    assert "WEB_DATABASE_URL_FILE" not in os.environ
    assert "WEB_SECRET_KEY_FILE" not in os.environ
    assert "ALEMBIC_DATABASE_URL_FILE" not in os.environ


@pytest.mark.parametrize("conteudo", [None, "\n"])
def test_entrypoint_falha_fechado_para_segredo_ausente_ou_vazio(
    monkeypatch: Any, tmp_path: Path, conteudo: str | None
) -> None:
    secret = tmp_path / "secret"
    if conteudo is not None:
        secret.write_text(conteudo, encoding="utf-8")
    monkeypatch.setenv("WEB_SECRET_KEY_FILE", str(secret))
    monkeypatch.setattr("sys.argv", ["entrypoint.py", "python"])
    namespace = runpy.run_path(str(ENTRYPOINT), run_name="entrypoint_test")

    with pytest.raises(SystemExit, match="WEB_SECRET_KEY"):
        namespace["main"]()
