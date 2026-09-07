"""Contrato do mecanismo de reconhecimento facial.

Nesta fase o contrato cobre exatamente o que o prototipo fazia: validar que
ha um unico rosto na imagem, e comparar uma imagem com uma foto de
referencia. A Fase 4 substitui a comparacao imagem-a-imagem por embeddings.

O ponto ja garantido aqui: a orquestracao nao importa `deepface`.
"""

from __future__ import annotations

from typing import Any, Protocol


class FaceRecognition(Protocol):
    def validar_rosto_unico(self, imagem: Any) -> None:
        """Levanta NenhumRostoDetectado ou MultiplosRostosDetectados."""
        ...

    def sao_a_mesma_pessoa(self, imagem: Any, caminho_referencia: str) -> bool:
        """Compara a imagem com a foto de referencia.

        Levanta NenhumRostoDetectado quando nao ha rosto na imagem, e
        ModeloIndisponivel quando a falha e de infraestrutura de ML.
        """
        ...
