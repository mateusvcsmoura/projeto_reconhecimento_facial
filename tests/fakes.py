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
from src.domain.errors import AlunoJaCadastrado


class FakeAlunoRepository:
    def __init__(self, alunos: list[Aluno] | None = None) -> None:
        self.alunos = list(alunos or [])
        self._proximo_id = max((a.id for a in self.alunos), default=0) + 1

    def existe_matricula(self, matricula: str) -> bool:
        return any(a.matricula == matricula for a in self.alunos)

    def listar(self) -> list[Aluno]:
        return sorted(self.alunos, key=lambda a: a.nome)

    def cadastrar(self, matricula: str, nome: str, foto_arquivo: str | None) -> Aluno:
        if self.existe_matricula(matricula):
            raise AlunoJaCadastrado(matricula)
        aluno = Aluno(
            id=self._proximo_id,
            matricula=matricula,
            nome=nome,
            foto_arquivo=foto_arquivo,
        )
        self._proximo_id += 1
        self.alunos.append(aluno)
        return aluno


class FakePresencaRepository:
    def __init__(self) -> None:
        self.registros: set[tuple[int, dt.date]] = set()
        self.chamadas: list[tuple[int, dt.date, dt.datetime]] = []

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

    `erro_ao_validar` e `erro_ao_comparar` permitem exercitar cada falha
    traduzida pelo adaptador real, sem ter o DeepFace instalado.
    """

    def __init__(
        self,
        *,
        casa_com: str | None = None,
        erro_ao_validar: Exception | None = None,
        erro_ao_comparar: Exception | None = None,
    ) -> None:
        self.casa_com = casa_com
        self.erro_ao_validar = erro_ao_validar
        self.erro_ao_comparar = erro_ao_comparar
        self.comparacoes: list[str] = []

    def validar_rosto_unico(self, imagem: Any) -> None:
        if self.erro_ao_validar is not None:
            raise self.erro_ao_validar

    def sao_a_mesma_pessoa(self, imagem: Any, caminho_referencia: str) -> bool:
        self.comparacoes.append(caminho_referencia)
        if self.erro_ao_comparar is not None:
            raise self.erro_ao_comparar
        return self.casa_com is not None and self.casa_com in caminho_referencia


class FakeImageStorage:
    def __init__(self, existentes: set[str] | None = None) -> None:
        self.arquivos: set[str] = set(existentes or set())
        self.gravacoes: list[str] = []

    def salvar(self, nome_arquivo: str, imagem: Any) -> str:
        self.arquivos.add(nome_arquivo)
        self.gravacoes.append(nome_arquivo)
        return nome_arquivo

    def existe(self, nome_arquivo: str) -> bool:
        return nome_arquivo in self.arquivos

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

    def mostrar(self, frame: Any, linhas: list[tuple[str, tuple[int, int, int]]]) -> int:
        self.exibicoes.append(linhas)
        if not self._teclas:
            raise AssertionError("O teste consumiu mais teclas do que forneceu.")
        return self._teclas.pop(0)
