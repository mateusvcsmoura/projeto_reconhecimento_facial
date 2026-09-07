"""Caso de uso: cadastrar um aluno a partir de uma imagem."""

from __future__ import annotations

from typing import Any

from src.domain.entities.aluno import Aluno
from src.domain.errors import AlunoJaCadastrado, DadosInvalidos
from src.domain.repositories.aluno_repository import AlunoRepository
from src.domain.services.face_recognition import FaceRecognition
from src.domain.services.image_storage import ImageStorage

MATRICULA_MAXIMA = 32
NOME_MAXIMO = 255


class CadastrarAluno:
    def __init__(
        self,
        alunos: AlunoRepository,
        reconhecimento: FaceRecognition,
        storage: ImageStorage,
    ) -> None:
        self._alunos = alunos
        self._reconhecimento = reconhecimento
        self._storage = storage

    def validar_identificacao(self, matricula: str, nome: str) -> tuple[str, str]:
        """Valida antes de acender a camera.

        Separado de `executar` de proposito: nao faz sentido pedir o rosto
        do aluno para so entao descobrir que a matricula esta duplicada.
        """
        matricula_limpa = matricula.strip()
        nome_limpo = " ".join(nome.split())

        if not matricula_limpa:
            raise DadosInvalidos("Informe a matricula.")
        if len(matricula_limpa) > MATRICULA_MAXIMA:
            raise DadosInvalidos(
                f"A matricula pode ter no maximo {MATRICULA_MAXIMA} caracteres."
            )
        if not nome_limpo:
            raise DadosInvalidos("Informe o nome do aluno.")
        if len(nome_limpo) > NOME_MAXIMO:
            raise DadosInvalidos(
                f"O nome pode ter no maximo {NOME_MAXIMO} caracteres."
            )
        if self._alunos.existe_matricula(matricula_limpa):
            raise AlunoJaCadastrado(matricula_limpa)

        return matricula_limpa, nome_limpo

    def executar(self, matricula: str, nome: str, imagem: Any) -> Aluno:
        """Valida o rosto, grava a imagem e persiste o aluno.

        Levanta NenhumRostoDetectado, MultiplosRostosDetectados,
        ModeloIndisponivel ou AlunoJaCadastrado.
        """
        matricula_limpa, nome_limpo = self.validar_identificacao(matricula, nome)

        self._reconhecimento.validar_rosto_unico(imagem)

        nome_arquivo = self._storage.salvar(f"{matricula_limpa}.jpg", imagem)

        return self._alunos.cadastrar(
            matricula=matricula_limpa, nome=nome_limpo, foto_arquivo=nome_arquivo
        )
