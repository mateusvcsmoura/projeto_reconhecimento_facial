"""Contrato do mecanismo de reconhecimento facial.

O dominio fala em preparar uma face e gerar um embedding. Nao fala em
DeepFace, em Facenet512 nem em backend de deteccao -- trocar o modelo nao
deve alcancar os casos de uso.

A comparacao NAO faz parte deste contrato: ela e aritmetica sobre vetores e
vive em `domain/services/matcher.py`, onde e testavel sem modelo de IA.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.domain.entities.face_embedding import FaceEmbedding


@dataclass(frozen=True, slots=True)
class FacePreparada:
    """Recorte aceito para armazenamento e embedding calculado desse recorte."""

    imagem: Any
    embedding: FaceEmbedding


@dataclass(frozen=True, slots=True)
class ResultadoFacial:
    """Decisão interna de verificação sem imagem, embedding ou landmarks."""

    identidade_ok: bool
    desafio_ok: bool
    antispoofing_ok: bool
    qualidade_ok: bool
    motivo_tecnico: str | None
    versao_referencia: int
    politica: str
    distancia_mediana: float | None = None


class FaceRecognition(Protocol):
    def preaquecer(self) -> None:
        """Carrega o modelo antes do primeiro uso.

        Na primeira execucao o DeepFace baixa os pesos, o que leva minutos.
        Sem isso, a espera acontece com a camera ja aberta e o aluno
        parado na frente dela, sem nenhuma explicacao na tela.
        """
        ...

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

    def preparar_cadastro(self, imagem: Any) -> FacePreparada:
        """Prepara a face alinhada e seu embedding em uma deteccao unica.

        A mesma imagem que originou o embedding e devolvida para persistencia.
        """
        ...
