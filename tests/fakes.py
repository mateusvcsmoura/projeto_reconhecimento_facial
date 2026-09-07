"""Dubles para os contratos do dominio.

Escritos a mao, e nao com mock: para uma banca academica, um fake explicito
mostra o contrato melhor do que uma cadeia de `Mock()`.

A existencia destes dubles e a prova de que a arquitetura da Fase 2
funciona -- a suite exercita cadastro, reconhecimento e presenca sem
webcam, sem OpenCV, sem DeepFace e sem PostgreSQL.
"""

from __future__ import annotations

import datetime as dt
from types import TracebackType
from typing import Any

from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import AlunoJaCadastrado


class FakeAlunoRepository:
    def __init__(
        self,
        alunos: list[Aluno] | None = None,
        embeddings: dict[int, FaceEmbedding] | None = None,
    ) -> None:
        self.alunos = list(alunos or [])
        self.embeddings = dict(embeddings or {})
        self._proximo_id = max((a.id for a in self.alunos), default=0) + 1

    def existe_matricula(self, matricula: str) -> bool:
        return any(a.matricula == matricula for a in self.alunos)

    def listar_referencias(self, modelo: str) -> list[tuple[Aluno, FaceEmbedding]]:
        return [
            (aluno, self.embeddings[aluno.id])
            for aluno in self.alunos
            if aluno.id in self.embeddings
            and self.embeddings[aluno.id].modelo == modelo
        ]

    def obter_por_matricula(self, matricula: str) -> Aluno | None:
        for aluno in self.alunos:
            if aluno.matricula == matricula:
                return aluno
        return None

    def excluir(self, aluno_id: int) -> None:
        self.alunos = [a for a in self.alunos if a.id != aluno_id]
        self.embeddings.pop(aluno_id, None)

    def cadastrar(
        self,
        matricula: str,
        nome: str,
        foto_arquivo: str | None,
        embedding: FaceEmbedding | None,
        consentimento_em: dt.datetime,
    ) -> Aluno:
        if self.existe_matricula(matricula):
            raise AlunoJaCadastrado(matricula)
        aluno = Aluno(
            id=self._proximo_id,
            matricula=matricula,
            nome=nome,
            foto_arquivo=foto_arquivo,
            consentimento_em=consentimento_em,
        )
        self._proximo_id += 1
        self.alunos.append(aluno)
        if embedding is not None:
            self.embeddings[aluno.id] = embedding
        return aluno


class FakePresencaRepository:
    def __init__(self) -> None:
        self.registros: set[tuple[int, dt.date]] = set()
        self.chamadas: list[tuple[int, dt.date, dt.datetime]] = []

    def expurgar_anteriores_a(self, dia: dt.date) -> int:
        antes = len(self.registros)
        self.registros = {(a, d) for a, d in self.registros if d >= dia}
        return antes - len(self.registros)

    def registrar_se_ausente(
        self, aluno_id: int, dia: dt.date, momento: dt.datetime
    ) -> bool:
        self.chamadas.append((aluno_id, dia, momento))
        chave = (aluno_id, dia)
        if chave in self.registros:
            return False
        self.registros.add(chave)
        return True


class FakeFaceRecognition:
    """Reconhecimento controlado pelo teste.

    `erro_ao_extrair` e `erro_ao_gerar` permitem exercitar cada falha
    traduzida pelo adaptador real, sem ter o DeepFace instalado.

    `inferencias` conta quantas vezes o modelo foi acionado -- e o numero
    que prova que o custo por ciclo deixou de crescer com N (problema A5).
    """

    def __init__(
        self,
        *,
        embedding: FaceEmbedding | None = None,
        face: Any = None,
        erro_ao_extrair: Exception | None = None,
        erro_ao_gerar: Exception | None = None,
    ) -> None:
        self.embedding = embedding
        self.face = face if face is not None else object()
        self.erro_ao_extrair = erro_ao_extrair
        self.erro_ao_gerar = erro_ao_gerar
        self.inferencias = 0

    def extrair_face_unica(self, imagem: Any) -> Any:
        if self.erro_ao_extrair is not None:
            raise self.erro_ao_extrair
        return self.face

    def gerar_embedding(self, imagem: Any) -> FaceEmbedding:
        self.inferencias += 1
        if self.erro_ao_gerar is not None:
            raise self.erro_ao_gerar
        if self.embedding is None:
            return FaceEmbedding.de_valores([1.0, 0.0, 0.0], "Facenet512")
        return self.embedding


class FakeImageStorage:
    def __init__(self, existentes: set[str] | None = None) -> None:
        self.arquivos: set[str] = set(existentes or set())
        self.gravacoes: list[str] = []
        self.remocoes: list[str] = []

    def salvar(self, nome_arquivo: str, imagem: Any) -> str:
        self.arquivos.add(nome_arquivo)
        self.gravacoes.append(nome_arquivo)
        return nome_arquivo

    def existe(self, nome_arquivo: str) -> bool:
        return nome_arquivo in self.arquivos

    def remover(self, nome_arquivo: str) -> None:
        self.arquivos.discard(nome_arquivo)
        self.remocoes.append(nome_arquivo)

    def caminho_absoluto(self, nome_arquivo: str) -> str:
        return f"/fake/storage/{nome_arquivo}"


class FakeCamera:
    """Entrega uma sequencia de frames e registra se foi liberada."""

    def __init__(self, frames: list[Any], erro_ao_ler: Exception | None = None) -> None:
        self._frames = list(frames)
        self._erro_ao_ler = erro_ao_ler
        self.aberta = False
        self.liberada = False

    def __enter__(self) -> FakeCamera:
        self.aberta = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.aberta = False
        self.liberada = True

    def ler_frame(self) -> Any:
        if self._erro_ao_ler is not None:
            raise self._erro_ao_ler
        if not self._frames:
            raise AssertionError("O teste consumiu mais frames do que forneceu.")
        return self._frames.pop(0)


class FakeJanela:
    """Devolve uma sequencia pre-programada de teclas."""

    def __init__(self, teclas: list[int]) -> None:
        self._teclas = list(teclas)
        self.fechada = False
        self.exibicoes: list[list[tuple[str, tuple[int, int, int]]]] = []

    def __enter__(self) -> FakeJanela:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.fechada = True

    def mostrar(
        self, frame: Any, linhas: list[tuple[str, tuple[int, int, int]]]
    ) -> int:
        self.exibicoes.append(linhas)
        if not self._teclas:
            raise AssertionError("O teste consumiu mais teclas do que forneceu.")
        return self._teclas.pop(0)
