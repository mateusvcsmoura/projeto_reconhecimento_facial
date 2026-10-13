"""Caso de uso: identificar o aluno presente no frame."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.domain.entities.aluno import Aluno
from src.domain.errors import MultiplosRostosDetectados, NenhumRostoDetectado
from src.domain.repositories.aluno_repository import AlunoRepository
from src.domain.services.face_recognition import FaceRecognition
from src.domain.services.matcher import MatrizDeReferencia, PoliticaAmbiguidade

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Reconhecimento:
    aluno: Aluno
    distancia: float


class ReconhecerAluno:
    """Identifica o aluno comparando embeddings.

    O desenho anterior chamava DeepFace.verify() para cada aluno a cada
    ciclo, recalculando o embedding do frame E o da foto de referencia --
    ate 2N inferencias por ciclo (problema A5). Aqui e UMA inferencia por
    ciclo, independente de N, seguida de um produto matriz-vetor.
    """

    def __init__(
        self,
        alunos: AlunoRepository,
        reconhecimento: FaceRecognition,
        modelo: str,
        limiar: float,
        *,
        ambiguidade: PoliticaAmbiguidade | None = None,
    ) -> None:
        self._alunos = alunos
        self._reconhecimento = reconhecimento
        self._modelo = modelo
        self._limiar = limiar
        self._ambiguidade = ambiguidade
        self._referencias: dict[int, Aluno] = {}

    def carregar_referencias(self) -> MatrizDeReferencia:
        """Le os embeddings cadastrados uma vez, para o ciclo de video todo.

        Deve ser chamado ao (re)entrar no modo de reconhecimento. O
        prototipo materializava a lista na entrada e nunca mais a
        atualizava, entao cadastros novos ficavam invisiveis ate reiniciar
        o modo (problema A15).
        """
        pares = self._alunos.listar_referencias(self._modelo)
        self._referencias = {aluno.id: aluno for aluno, _ in pares}

        if not pares:
            logger.warning("Nenhum aluno com embedding para o modelo %s", self._modelo)

        return MatrizDeReferencia.de_embeddings(
            [(aluno.id, embedding) for aluno, embedding in pares]
        )

    def identificar(
        self, imagem: Any, referencias: MatrizDeReferencia
    ) -> Reconhecimento | None:
        """Devolve o aluno de MENOR distancia abaixo do limiar, ou None.

        None significa: sem rosto utilizavel no frame, ou ninguem abaixo do
        limiar. Falha de modelo NAO vira None -- propaga como
        ModeloIndisponivel, para nao se disfarcar de "nao reconhecido"
        (problema A6).
        """
        if len(referencias) == 0:
            return None

        try:
            consulta = self._reconhecimento.gerar_embedding(imagem)
        except NenhumRostoDetectado:
            return None
        except MultiplosRostosDetectados as erro:
            # Com mais de uma pessoa no enquadramento nao ha identidade
            # unica a registrar. Nao e falha: e ambiguidade.
            logger.info("Frame ambiguo: %s rostos", erro.quantidade)
            return None

        identificacao = referencias.melhor_candidato(
            consulta, self._limiar, ambiguidade=self._ambiguidade
        )
        if identificacao is None:
            return None

        aluno = self._referencias.get(identificacao.aluno_id)
        if aluno is None:
            logger.error(
                "Matriz de referencia dessincronizada (aluno_id=%s)",
                identificacao.aluno_id,
            )
            return None

        return Reconhecimento(aluno=aluno, distancia=identificacao.distancia)
