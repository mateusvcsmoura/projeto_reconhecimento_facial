"""Caso de uso: cadastrar um aluno a partir de uma imagem."""

from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from src.domain.entities.aluno import Aluno
from src.domain.errors import (
    AlunoJaCadastrado,
    ConsentimentoNaoRegistrado,
    DadosInvalidos,
)
from src.domain.repositories.aluno_repository import AlunoRepository
from src.domain.services.face_recognition import FacePreparada, FaceRecognition
from src.domain.services.image_storage import ImageStorage

MATRICULA_MAXIMA = 32
NOME_MAXIMO = 255


class CadastrarAluno:
    def __init__(
        self,
        alunos: AlunoRepository,
        reconhecimento: FaceRecognition,
        storage: ImageStorage,
        tz: ZoneInfo,
    ) -> None:
        self._alunos = alunos
        self._reconhecimento = reconhecimento
        self._storage = storage
        self._tz = tz

    def preaquecer(self) -> None:
        """Carrega o modelo agora, e nao no meio do fluxo de camera."""
        self._reconhecimento.preaquecer()

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
            raise DadosInvalidos(f"O nome pode ter no maximo {NOME_MAXIMO} caracteres.")
        if self._alunos.existe_matricula(matricula_limpa):
            raise AlunoJaCadastrado(matricula_limpa)

        return matricula_limpa, nome_limpo

    def validar_captura(self, imagem: Any) -> None:
        """Valida uma observacao sem calcular embedding nem gravar dados."""
        self._reconhecimento.extrair_face_unica(imagem)

    def preparar_captura(self, imagem: Any) -> FacePreparada:
        """Calcula uma preparacao unica, ainda sem gravar imagem ou aluno."""
        return self._reconhecimento.preparar_cadastro(imagem)

    def concluir_cadastro(
        self,
        matricula: str,
        nome: str,
        preparada: FacePreparada,
        consentiu: bool,
    ) -> Aluno:
        """Revalida consentimento e identificacao antes de persistir a face."""
        if not consentiu:
            raise ConsentimentoNaoRegistrado(
                "O titular precisa consentir com o tratamento do dado "
                "biometrico antes do cadastro."
            )

        matricula_limpa, nome_limpo = self.validar_identificacao(matricula, nome)
        nome_arquivo = self._storage.salvar(f"{matricula_limpa}.jpg", preparada.imagem)

        return self._alunos.cadastrar(
            matricula=matricula_limpa,
            nome=nome_limpo,
            foto_arquivo=nome_arquivo,
            embedding=preparada.embedding,
            consentimento_em=dt.datetime.now(self._tz),
        )

    def executar(
        self, matricula: str, nome: str, imagem: Any, consentiu: bool
    ) -> Aluno:
        """Extrai o rosto, calcula o embedding e persiste tudo de uma vez.

        O embedding e calculado UMA vez, aqui. Era o recalculo dele a cada
        comparacao que tornava o reconhecimento inviavel (problema A5).

        `consentiu` nao tem valor padrao de proposito: cadastrar biometria
        sem consentimento explicito do titular nao pode ser o caminho mais
        facil de escrever (LGPD art. 11, I).

        Levanta ConsentimentoNaoRegistrado, erros de deteccao e qualidade,
        PossivelFraude, ModeloIndisponivel ou AlunoJaCadastrado.
        """
        if not consentiu:
            raise ConsentimentoNaoRegistrado(
                "O titular precisa consentir com o tratamento do dado "
                "biometrico antes do cadastro."
            )

        matricula_limpa, nome_limpo = self.validar_identificacao(matricula, nome)

        # Guarda-se o recorte alinhado, nao o frame inteiro (problema A14):
        # menos dado biometrico armazenado, sem fundo nem terceiros no
        # enquadramento. A identificacao ja foi validada antes do custo de ML;
        # concluir_cadastro a revalida no limite de persistencia.
        preparada = self.preparar_captura(imagem)

        return self.concluir_cadastro(
            matricula_limpa, nome_limpo, preparada, consentiu=True
        )
