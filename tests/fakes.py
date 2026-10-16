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
from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import (
    AlunoJaCadastrado,
    AlunoNaoEncontrado,
    AlunoSemConsentimento,
    TurmaInativa,
    TurmaNaoEncontrada,
    VinculoNaoEncontrado,
)
from src.domain.services.face_recognition import FacePreparada


class FakeAlunoRepository:
    def __init__(
        self,
        alunos: list[Aluno] | None = None,
        embeddings: dict[int, FaceEmbedding] | None = None,
    ) -> None:
        self.alunos = list(alunos or [])
        self.embeddings = dict(embeddings or {})
        self._proximo_id = max((a.id for a in self.alunos), default=0) + 1
        self.turmas_ativas: set[int] = {1}
        self.turmas_excluidas: set[int] = set()
        self.vinculos: set[tuple[int, int]] = {(1, aluno.id) for aluno in self.alunos}

    def validar_turma_ativa(self, turma_id: int) -> None:
        if turma_id in self.turmas_excluidas:
            raise TurmaInativa(turma_id)
        if turma_id not in self.turmas_ativas:
            raise TurmaNaoEncontrada(turma_id)

    def existe_matricula(self, matricula: str) -> bool:
        return any(a.matricula == matricula for a in self.alunos)

    def existe_matricula_global(self, matricula: str) -> bool:
        return self.existe_matricula(matricula)

    def listar(self) -> list[Aluno]:
        return sorted(self.alunos, key=lambda a: a.nome)

    def listar_por_turma(self, turma_id: int) -> list[Aluno]:
        self.validar_turma_ativa(turma_id)
        return sorted(
            (aluno for aluno in self.alunos if (turma_id, aluno.id) in self.vinculos),
            key=lambda aluno: aluno.nome,
        )

    def listar_referencias(
        self, modelo: str, *, turma_id: int = 1
    ) -> list[tuple[Aluno, FaceEmbedding]]:
        self.validar_turma_ativa(turma_id)
        return [
            (aluno, self.embeddings[aluno.id])
            for aluno in self.alunos
            if (turma_id, aluno.id) in self.vinculos
            if aluno.id in self.embeddings
            and self.embeddings[aluno.id].modelo == modelo
        ]

    def obter_por_matricula(self, matricula: str) -> Aluno | None:
        for aluno in self.alunos:
            if aluno.matricula == matricula:
                return aluno
        return None

    def obter_global_por_matricula(self, matricula: str) -> Aluno | None:
        return self.obter_por_matricula(matricula)

    def excluir_global(self, aluno_id: int) -> None:
        self.alunos = [a for a in self.alunos if a.id != aluno_id]
        self.embeddings.pop(aluno_id, None)
        self.vinculos = {
            (turma, aluno) for turma, aluno in self.vinculos if aluno != aluno_id
        }

    def excluir(self, aluno_id: int) -> None:
        self.excluir_global(aluno_id)

    def cadastrar_em_turma(
        self,
        turma_id: int,
        matricula: str,
        nome: str,
        foto_arquivo: str | None,
        embedding: FaceEmbedding | None,
        consentimento_em: dt.datetime,
    ) -> Aluno:
        self.validar_turma_ativa(turma_id)
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
        self.vinculos.add((turma_id, aluno.id))
        if embedding is not None:
            self.embeddings[aluno.id] = embedding
        return aluno

    def cadastrar(
        self,
        matricula: str,
        nome: str,
        foto_arquivo: str | None,
        embedding: FaceEmbedding | None,
        consentimento_em: dt.datetime,
    ) -> Aluno:
        """Atalho de fixture para semear o contexto sintético padrão 1."""
        return self.cadastrar_em_turma(
            1, matricula, nome, foto_arquivo, embedding, consentimento_em
        )


class FakeGerenciarTurmas:
    """Fake transacional pequeno para exercitar a navegação da CLI."""

    def __init__(self, alunos: FakeAlunoRepository, turma_id: int = 1) -> None:
        self.alunos = alunos
        self.turmas = {
            turma_id: Turma(id=turma_id, materia="IA", periodo=Periodo.DIURNO)
        }
        self.alunos.turmas_ativas.add(turma_id)
        self._proximo_id = turma_id + 1

    def criar(self, materia: str, periodo: str) -> Turma:
        validada = Turma.nova(materia, periodo)
        turma = Turma(
            id=self._proximo_id,
            materia=validada.materia,
            periodo=validada.periodo,
        )
        self._proximo_id += 1
        self.turmas[turma.id] = turma  # type: ignore[index]
        self.alunos.turmas_ativas.add(turma.id)  # type: ignore[arg-type]
        return turma

    def listar_ativas(self) -> list[Turma]:
        return [turma for turma in self.turmas.values() if turma.ativa]

    def listar_excluidas(self) -> list[Turma]:
        return [turma for turma in self.turmas.values() if not turma.ativa]

    def obter(self, turma_id: int) -> Turma | None:
        return self.turmas.get(turma_id)

    def obter_ativa(self, turma_id: int) -> Turma:
        self.alunos.validar_turma_ativa(turma_id)
        turma = self.turmas.get(turma_id)
        if turma is None:
            raise TurmaNaoEncontrada(turma_id)
        return turma

    def atualizar(self, turma_id: int, materia: str, periodo: str) -> Turma:
        self.obter_ativa(turma_id)
        nova = Turma.nova(materia, periodo)
        atualizada = Turma(id=turma_id, materia=nova.materia, periodo=nova.periodo)
        self.turmas[turma_id] = atualizada
        return atualizada

    def excluir(self, turma_id: int) -> None:
        turma = self.obter_ativa(turma_id)
        self.turmas[turma_id] = Turma(
            id=turma_id,
            materia=turma.materia,
            periodo=turma.periodo,
            excluida_em=dt.datetime.now(dt.UTC),
        )
        self.alunos.turmas_ativas.discard(turma_id)
        self.alunos.turmas_excluidas.add(turma_id)

    def vincular(self, turma_id: int, matricula: str) -> tuple[Aluno, bool]:
        self.obter_ativa(turma_id)
        aluno = self.alunos.obter_global_por_matricula(matricula)
        if aluno is None:
            raise AlunoNaoEncontrado(matricula)
        if aluno.consentimento_em is None:
            raise AlunoSemConsentimento(matricula)
        chave = (turma_id, aluno.id)
        if chave in self.alunos.vinculos:
            return aluno, False
        self.alunos.vinculos.add(chave)
        return aluno, True

    def desvincular(self, turma_id: int, matricula: str) -> Aluno:
        self.obter_ativa(turma_id)
        aluno = self.alunos.obter_global_por_matricula(matricula)
        if aluno is None:
            raise AlunoNaoEncontrado(matricula)
        chave = (turma_id, aluno.id)
        if chave not in self.alunos.vinculos:
            raise VinculoNaoEncontrado(turma_id, matricula)
        self.alunos.vinculos.remove(chave)
        return aluno


class FakePresencaRepository:
    def __init__(self) -> None:
        self.registros: set[tuple[int, dt.date] | tuple[int, int, dt.date]] = set()
        self.chamadas: list[tuple[int, dt.date, dt.datetime]] = []
        self.contextos: list[tuple[int, int]] = []
        self.registros_legado: set[tuple[int, dt.date]] = set()

    @staticmethod
    def _partes(
        registro: tuple[int, dt.date] | tuple[int, int, dt.date],
    ) -> tuple[int | None, int, dt.date]:
        if len(registro) == 2:
            aluno_id, dia = registro
            return 1, aluno_id, dia
        turma_id, aluno_id, dia = registro
        return turma_id, aluno_id, dia

    def listar_da_turma(self, turma_id: int, dia: dt.date) -> list[Any]:
        from src.domain.repositories.presenca_repository import (
            PresencaRegistrada,
        )

        return [
            PresencaRegistrada(
                aluno_id=aluno_id,
                matricula=str(aluno_id),
                nome=f"Aluno {aluno_id}",
                registrado_em=dt.datetime.combine(d, dt.time(8, 0), tzinfo=dt.UTC),
                turma_id=tid,
            )
            for registro in sorted(self.registros, key=repr)
            for tid, aluno_id, d in [self._partes(registro)]
            if tid == turma_id and d == dia
        ]

    def listar_historico_da_turma(self, turma_id: int, dia: dt.date) -> list[Any]:
        return self.listar_da_turma(turma_id, dia)

    def listar_legado(self, dia: dt.date) -> list[Any]:
        from src.domain.repositories.presenca_repository import PresencaRegistrada

        return [
            PresencaRegistrada(
                aluno_id=aluno_id,
                matricula=str(aluno_id),
                nome=f"Aluno {aluno_id}",
                registrado_em=dt.datetime.combine(d, dt.time(8, 0), tzinfo=dt.UTC),
            )
            for aluno_id, d in sorted(self.registros_legado)
            if d == dia
        ]

    def listar_do_dia(self, dia: dt.date) -> list[Any]:
        return [
            registro
            for turma_id in {self._partes(r)[0] for r in self.registros}
            if turma_id is not None
            for registro in self.listar_da_turma(turma_id, dia)
        ] + self.listar_legado(dia)

    def expurgar_anteriores_a(self, dia: dt.date) -> int:
        antes = len(self.registros) + len(self.registros_legado)
        self.registros = {
            registro for registro in self.registros if self._partes(registro)[2] >= dia
        }
        self.registros_legado = {
            registro for registro in self.registros_legado if registro[1] >= dia
        }
        return antes - len(self.registros) - len(self.registros_legado)

    def registrar_se_ausente(
        self,
        aluno_id: int,
        dia: dt.date,
        momento: dt.datetime,
        *,
        turma_id: int = 1,
    ) -> bool:
        self.chamadas.append((aluno_id, dia, momento))
        self.contextos.append((aluno_id, turma_id))
        chave = (aluno_id, dia) if turma_id == 1 else (turma_id, aluno_id, dia)
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
        erro_ao_preparar: Exception | None = None,
    ) -> None:
        self.embedding = embedding
        self.face = face if face is not None else object()
        self.erro_ao_extrair = erro_ao_extrair
        self.erro_ao_gerar = erro_ao_gerar
        self.erro_ao_preparar = erro_ao_preparar
        self.preparacoes = 0
        self.extracoes = 0
        self.erros_ao_gerar: list[Exception | None] = []
        self.erros_ao_preparar: list[Exception | None] = []
        self.inferencias = 0
        self.preaquecido = False

    def preaquecer(self) -> None:
        self.preaquecido = True

    def extrair_face_unica(self, imagem: Any) -> Any:
        self.extracoes += 1
        if self.erro_ao_extrair is not None:
            raise self.erro_ao_extrair
        return self.face

    def gerar_embedding(self, imagem: Any) -> FaceEmbedding:
        self.inferencias += 1
        if self.erros_ao_gerar:
            erro = self.erros_ao_gerar.pop(0)
            if erro is not None:
                raise erro
        if self.erro_ao_gerar is not None:
            raise self.erro_ao_gerar
        if self.embedding is None:
            return FaceEmbedding.de_valores([1.0, 0.0, 0.0], "Facenet512")
        return self.embedding

    def preparar_cadastro(self, imagem: Any) -> FacePreparada:
        self.preparacoes += 1
        if self.erros_ao_preparar:
            erro = self.erros_ao_preparar.pop(0)
            if erro is not None:
                raise erro
        if self.erro_ao_preparar is not None:
            raise self.erro_ao_preparar
        face = self.extrair_face_unica(imagem)
        embedding = self.gerar_embedding(face)
        return FacePreparada(imagem=face, embedding=embedding)


class FakeImageStorage:
    def __init__(self, existentes: set[str] | None = None) -> None:
        self.arquivos: set[str] = set(existentes or set())
        self.gravacoes: list[str] = []
        self.imagens_salvas: list[tuple[str, Any]] = []
        self.remocoes: list[str] = []

    def salvar(self, nome_arquivo: str, imagem: Any) -> str:
        self.arquivos.add(nome_arquivo)
        self.gravacoes.append(nome_arquivo)
        self.imagens_salvas.append((nome_arquivo, imagem))
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
