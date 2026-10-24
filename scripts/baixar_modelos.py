"""Baixa os modelos usados pela interface web e aponta o .env para os pesos.

Os arquivos ficam fora do Git e o worker facial nao acessa a internet, entao
o download acontece aqui, uma vez, antes do primeiro build:

- ``models/face_landmarker.task``: copiado para a imagem no build;
- pesos do DeepFace em ``~/.deepface/weights``: montados no worker e usados
  tambem pela CLI.

Cada arquivo e conferido por SHA-256 antes de ser gravado; um arquivo ja
presente com o hash certo nao e baixado de novo. Se existir um ``.env`` na
raiz, a linha ``WEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR`` passa a apontar para a
pasta dos pesos deste computador.

Uso:
    python -m scripts.baixar_modelos
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA_PESOS = Path.home() / ".deepface" / "weights"
VARIAVEL_PESOS = "WEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR"
_BLOCO = 1024 * 1024


@dataclass(frozen=True, slots=True)
class Modelo:
    url: str
    nome: str
    sha256: str


LANDMARKER = Modelo(
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task",
    "face_landmarker.task",
    "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
)
_ANTI_SPOOFING = (
    "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/"
    "resources/anti_spoof_models/"
)
PESOS = (
    Modelo(
        "https://github.com/serengil/deepface_models/releases/download/v1.0/"
        "facenet512_weights.h5",
        "facenet512_weights.h5",
        "3f76b5117a9ca574d536af8199e6720089eb4ad3dc7e93534496d88265de864f",
    ),
    Modelo(
        _ANTI_SPOOFING + "2.7_80x80_MiniFASNetV2.pth",
        "2.7_80x80_MiniFASNetV2.pth",
        "a5eb02e1843f19b5386b953cc4c9f011c3f985d0ee2bb9819eea9a142099bec0",
    ),
    Modelo(
        _ANTI_SPOOFING + "4_0_0_80x80_MiniFASNetV1SE.pth",
        "4_0_0_80x80_MiniFASNetV1SE.pth",
        "84ee1d37d96894d5e82de5a57df044ef80a58be2b218b5ed7cdfd875ec2f5990",
    ),
)


class HashDivergente(RuntimeError):
    """O arquivo baixado nao corresponde ao SHA-256 fixado."""


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(_BLOCO):
            resumo.update(bloco)
    return resumo.hexdigest()


def garantir(modelo: Modelo, pasta: Path) -> bool:
    """Deixa o modelo em ``pasta``. Devolve True se precisou baixar."""
    destino = pasta / modelo.nome
    if destino.exists() and _sha256(destino) == modelo.sha256:
        return False
    pasta.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".part")
    try:
        with (
            urllib.request.urlopen(modelo.url, timeout=60) as resposta,
            parcial.open("wb") as arquivo,
        ):
            while bloco := resposta.read(_BLOCO):
                arquivo.write(bloco)
        obtido = _sha256(parcial)
        if obtido != modelo.sha256:
            raise HashDivergente(
                f"{modelo.nome}: SHA-256 {obtido} difere do esperado {modelo.sha256}."
            )
        parcial.replace(destino)
    finally:
        parcial.unlink(missing_ok=True)
    return True


def apontar_env(env: Path, pasta_pesos: Path) -> str:
    """Grava a pasta dos pesos no .env, preservando as demais linhas."""
    linha = f"{VARIAVEL_PESOS}={pasta_pesos.as_posix()}"
    texto = env.read_bytes().decode("utf-8")  # read_text normalizaria o \r\n
    quebra = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.splitlines()
    prefixo = f"{VARIAVEL_PESOS}="
    if any(atual.startswith(prefixo) for atual in linhas):
        linhas = [linha if atual.startswith(prefixo) else atual for atual in linhas]
    else:
        linhas.append(linha)
    env.write_text(quebra.join(linhas) + quebra, encoding="utf-8", newline="")
    return linha


def main() -> int:
    alvos = [(LANDMARKER, RAIZ / "models")] + [(peso, PASTA_PESOS) for peso in PESOS]
    for modelo, pasta in alvos:
        print(f"{modelo.nome}: ", end="", flush=True)
        try:
            baixou = garantir(modelo, pasta)
        except (OSError, HashDivergente) as erro:
            print("falhou")
            print(f"Erro: {erro}", file=sys.stderr)
            return 1
        print("baixado" if baixou else "ja presente")

    env = RAIZ / ".env"
    if env.exists():
        print(f".env: {apontar_env(env, PASTA_PESOS)}")
    else:
        print(f"Sem .env; ao cria-lo, use {VARIAVEL_PESOS}={PASTA_PESOS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
