"""Roundtrip local opcional; nunca usa DATABASE_URL/.env nem banco operacional."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_OPT_IN = os.environ.get("FACE_WEB_BACKUP_INTEGRATION") == "task017-disposable-local"
pytestmark = pytest.mark.skipif(
    not _OPT_IN,
    reason="exige opt-in de banco descartavel local exclusivo da task017",
)


def test_restore_local_em_banco_e_volume_marcados_como_descartaveis() -> None:
    assert shutil.which("pg_restore") is not None
    assert shutil.which("rclone") is not None
    root = Path(__file__).resolve().parents[2]
    target = os.environ.get("FACE_WEB_BACKUP_INTEGRATION_TARGET", "").strip()
    generation = os.environ.get("FACE_WEB_BACKUP_TEST_GENERATION", "").strip()
    if not target or not generation:
        pytest.skip("informe target task017 e geracao completa local para o roundtrip")
    database_url = os.environ.get("FACE_WEB_RESTORE_DATABASE_URL", "")
    if not database_url.endswith(f"/{target}"):
        pytest.skip("target informado nao corresponde ao banco de restore")
    confirmation = f"RESTAURAR-TASK017-{target}"
    environment = dict(os.environ)
    environment["FACE_WEB_RESTORE_DATABASE_URL"] = database_url
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "web_restore_check.py"),
            "--geracao",
            generation,
            "--confirmacao",
            confirmation,
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )

    assert result.returncode == 0, (
        "ensaio de restore local falhou; detalhes foram ocultados"
    )
