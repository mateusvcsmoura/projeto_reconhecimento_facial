from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_web_mede_worker_fake_e_nao_exporta_dados_sensiveis() -> None:
    resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.benchmark_web",
            "--atraso-frio-ms",
            "1",
            "--atraso-quente-ms",
            "0",
            "--falha-falsa-a-cada",
            "3",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert resultado.returncode == 0, resultado.stderr
    relatorio = json.loads(resultado.stdout)

    assert relatorio["carga"] == {"tipo": "fake", "inferencia_real": False}
    assert [item["rotulo"] for item in relatorio["resultados"]] == [
        "1",
        "2",
        "5",
        "10",
        "excesso",
    ]
    assert [item["aceitos"] for item in relatorio["resultados"]] == [1, 2, 5, 10, 10]
    assert [item["recusados"] for item in relatorio["resultados"]] == [0, 0, 0, 0, 1]
    assert relatorio["resultados"][-1]["falhas"] == 3
    assert relatorio["resultados"][0]["latencia_fria_ms"] >= 1
    assert relatorio["recursos"]["rss_inicio_bytes"] > 0
    assert "pss_inicio_bytes" in relatorio["recursos"]
    assert "matricula" not in resultado.stdout.lower()
    assert "embedding" not in resultado.stdout.lower()
    assert "token" not in resultado.stdout.lower()
