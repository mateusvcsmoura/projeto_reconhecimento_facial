"""Caso de uso: excluir um aluno e todo o seu rastro.

Direito do titular a eliminacao dos dados (LGPD art. 18, VI). Nao basta
apagar a linha: a imagem de referencia vive fora do banco, e um embedding
esquecido continua sendo dado biometrico.
"""

from __future__ import annotations

import logging

from src.domain.entities.aluno import Aluno
from src.domain.errors import AlunoNaoEncontrado
from src.domain.repositories.aluno_repository import AlunoRepository
from src.domain.services.image_storage import ImageStorage

logger = logging.getLogger(__name__)


class ExcluirAluno:
    def __init__(self, alunos: AlunoRepository, storage: ImageStorage) -> None:
        self._alunos = alunos
        self._storage = storage

    def localizar(self, matricula: str) -> Aluno:
        """Busca o aluno para a interface confirmar antes de apagar."""
        aluno = self._alunos.obter_por_matricula(matricula.strip())
        if aluno is None:
            raise AlunoNaoEncontrado(matricula.strip())
        return aluno

    def executar(self, aluno: Aluno) -> None:
        """Apaga a linha, o embedding e a imagem de referencia.

        O banco vem primeiro: se a transacao falhar, nada foi perdido. Se a
        remocao do arquivo falhar depois, sobra um arquivo orfao -- que e
        registrado em log para limpeza manual, e nao um dado ainda ligado a
        uma pessoa identificavel dentro do sistema.
        """
        # A linha carrega o embedding; as presencas caem por ON DELETE
        # CASCADE, garantido pela constraint e nao por codigo.
        self._alunos.excluir(aluno.id)

        if aluno.foto_arquivo and self._storage.existe(aluno.foto_arquivo):
            try:
                self._storage.remover(aluno.foto_arquivo)
            except OSError as erro:
                logger.error(
                    "Aluno %s removido do banco, mas a imagem de referencia "
                    "permaneceu no disco e exige limpeza manual: %s",
                    aluno.id,
                    erro,
                )
                raise

        logger.info("Aluno e dados associados removidos (id=%s)", aluno.id)
