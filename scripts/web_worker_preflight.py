"""Impede boot do worker se os modelos locais obrigatorios nao estiverem prontos."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def arquivos_de_modelo_ausentes() -> tuple[str, ...]:
    """Retorna somente nomes ausentes; nunca baixa nem registra caminhos locais."""
    raiz_deepface = Path(
        os.environ.get("DEEPFACE_HOME", "/var/lib/facediff/models/home")
    )
    pesos_deepface = raiz_deepface / ".deepface" / "weights"
    obrigatorios = [
        pesos_deepface / "facenet512_weights.h5",
        pesos_deepface / "2.7_80x80_MiniFASNetV2.pth",
        pesos_deepface / "4_0_0_80x80_MiniFASNetV1SE.pth",
    ]
    ausentes = [
        caminho.name
        for caminho in obrigatorios
        if not caminho.is_file() or not os.access(caminho, os.R_OK)
    ]
    modelo_landmarks = os.environ.get("WEB_MEDIAPIPE_MODEL_PATH")
    if not modelo_landmarks:
        ausentes.append("WEB_MEDIAPIPE_MODEL_PATH")
    else:
        caminho_modelo = Path(modelo_landmarks)
        if not caminho_modelo.is_file() or not os.access(caminho_modelo, os.R_OK):
            ausentes.append(caminho_modelo.name)
    return tuple(ausentes)


def main() -> int:
    ausentes = arquivos_de_modelo_ausentes()
    if ausentes:
        print(
            "Worker nao iniciado: modelos locais ausentes ou sem leitura ("
            + ", ".join(ausentes)
            + ").",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
