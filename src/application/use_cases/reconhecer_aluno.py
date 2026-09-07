"""Caso de uso: identificar o aluno presente no frame."""

from __future__ import annotations

import logging
from typing import Any

from src.domain.entities.aluno import Aluno
from src.domain.errors import NenhumRostoDetectado
from src.domain.repositories.aluno_repository import AlunoRepository
from src.domain.services.face_recognition import FaceRecognition
from src.domain.services.image_storage import ImageStorage

logger = logging.getLogger(__name__)


class ReconhecerAluno:
    """Compara o frame com as fotos de referencia dos alunos cadastrados.

    Comportamento preservado do prototipo: comparacao 1:1 contra cada
    aluno, aceitando o primeiro que casar. A Fase 4/5 substitui isso por
    embeddings pre-calculados e escolha do MELHOR candidato -- o que exige
    a distancia, informacao que `verify()` nao expoe de forma util aqui.
    """

    def __init__(
        self,
        alunos: AlunoRepository,
        reconhecimento: FaceRecognition,
        storage: ImageStorage,
    ) -> None:
        self._alunos = alunos
        self._reconhecimento = reconhecimento
        self._storage = storage

    def candidatos(self) -> list[Aluno]:
        """Alunos que tem foto de referencia disponivel no storage."""
        disponiveis = []
        for aluno in self._alunos.listar():
            if aluno.foto_arquivo and self._storage.existe(aluno.foto_arquivo):
                disponiveis.append(aluno)
            else:
                logger.warning(
                    "Aluno sem foto de referencia utilizavel (id=%s)", aluno.id
                )
        return disponiveis

    def identificar(self, imagem: Any, candidatos: list[Aluno]) -> Aluno | None:
        """Devolve o aluno reconhecido, ou None.

        None significa exatamente uma coisa: nenhum candidato casou, ou nao
        havia rosto no frame. Falha de modelo NAO vira None -- propaga como
        ModeloIndisponivel, para nao se disfarcar de "nao reconhecido"
        (problema A6).
        """
        for aluno in candidatos:
            assert aluno.foto_arquivo is not None  # garantido por candidatos()
            referencia = self._storage.caminho_absoluto(aluno.foto_arquivo)

            try:
                if self._reconhecimento.sao_a_mesma_pessoa(imagem, referencia):
                    return aluno
            except NenhumRostoDetectado:
                # Frame sem rosto: situacao normal no laco de video, e nao
                # ha o que comparar contra os demais candidatos.
                return None

        return None
