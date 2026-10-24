"""Download conferido por hash e ajuste do .env, sem acesso a rede."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from scripts import baixar_modelos

CONTEUDO = b"modelo sintetico"
MODELO = baixar_modelos.Modelo(
    "https://exemplo.invalid/modelo.bin",
    "modelo.bin",
    hashlib.sha256(CONTEUDO).hexdigest(),
)


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    chamadas: list[str] = []

    def urlopen(url: str, timeout: float) -> io.BytesIO:
        chamadas.append(url)
        return io.BytesIO(CONTEUDO)

    monkeypatch.setattr(baixar_modelos.urllib.request, "urlopen", urlopen)
    return chamadas


def test_baixa_e_grava_quando_hash_confere(
    tmp_path: Path, downloads: list[str]
) -> None:
    assert baixar_modelos.garantir(MODELO, tmp_path / "pasta") is True
    assert (tmp_path / "pasta" / "modelo.bin").read_bytes() == CONTEUDO
    assert downloads == [MODELO.url]


def test_nao_baixa_de_novo_arquivo_valido(tmp_path: Path, downloads: list[str]) -> None:
    (tmp_path / "modelo.bin").write_bytes(CONTEUDO)
    assert baixar_modelos.garantir(MODELO, tmp_path) is False
    assert downloads == []


def test_rejeita_hash_divergente_sem_deixar_arquivo(
    tmp_path: Path, downloads: list[str]
) -> None:
    errado = baixar_modelos.Modelo(MODELO.url, MODELO.nome, "0" * 64)
    with pytest.raises(baixar_modelos.HashDivergente):
        baixar_modelos.garantir(errado, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_substitui_arquivo_corrompido(tmp_path: Path, downloads: list[str]) -> None:
    (tmp_path / "modelo.bin").write_bytes(b"truncado")
    assert baixar_modelos.garantir(MODELO, tmp_path) is True
    assert (tmp_path / "modelo.bin").read_bytes() == CONTEUDO


def test_apontar_env_troca_so_a_linha_dos_pesos(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_bytes(
        b"DATABASE_URL=x\r\nWEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR=C:/Users/Outro\r\nA=1\r\n"
    )
    linha = baixar_modelos.apontar_env(env, Path("/home/aluno/.deepface/weights"))
    assert linha == "WEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR=/home/aluno/.deepface/weights"
    assert env.read_bytes() == (
        b"DATABASE_URL=x\r\n"
        b"WEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR=/home/aluno/.deepface/weights\r\n"
        b"A=1\r\n"
    )


def test_apontar_env_acrescenta_linha_ausente(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=x", encoding="utf-8")
    baixar_modelos.apontar_env(env, Path("/pesos"))
    assert env.read_text(encoding="utf-8") == (
        "DATABASE_URL=x\nWEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR=/pesos\n"
    )
