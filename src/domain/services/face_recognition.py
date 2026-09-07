"""Contrato do mecanismo de reconhecimento facial.

O dominio fala em "extrair um rosto" e "gerar um embedding". Nao fala em
DeepFace, em Facenet512 nem em backend de deteccao -- trocar o modelo nao
deve alcancar os casos de uso.

A comparacao NAO faz parte deste contrato: ela e aritmetica sobre vetores e
vive em `domain/services/matcher.py`, onde e testavel sem modelo de IA.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.domain.entities.face_embedding import FaceEmbedding


class FaceRecognition(Protocol):
    def extrair_face_unica(self, imagem: Any) -> Any:
        """Detecta, alinha e recorta o unico rosto da imagem.

        Devolve o recorte pronto para gravacao. Levanta
        NenhumRostoDetectado, MultiplosRostosDetectados ou
        ModeloIndisponivel.
        """
        ...

    def gerar_embedding(self, imagem: Any) -> FaceEmbedding:
        """Uma inferencia: detecta, alinha e devolve o vetor normalizado.

        Levanta NenhumRostoDetectado, MultiplosRostosDetectados ou
        ModeloIndisponivel.
        """
        ...
