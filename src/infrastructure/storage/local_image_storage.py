"""Armazenamento das imagens de referencia em disco local.

O banco guarda apenas o nome do arquivo; a raiz vem de STORAGE_DIR. Assim a
base volta a ser portavel entre maquinas -- o prototipo gravava caminho
absoluto e o unico registro existente apontava para o %TEMP% de outro
usuario (problema A11).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2

logger = logging.getLogger(__name__)


class LocalImageStorage:
    def __init__(self, raiz: Path) -> None:
        self._raiz = Path(raiz)

    def _caminho(self, nome_arquivo: str) -> Path:
        # Impede que um nome vindo do banco escape da raiz.
        seguro = Path(nome_arquivo).name
        return self._raiz / seguro

    def salvar(self, nome_arquivo: str, imagem: Any) -> str:
        self._raiz.mkdir(parents=True, exist_ok=True)
        destino = self._caminho(nome_arquivo)

        if not cv2.imwrite(str(destino), imagem):
            raise OSError(f"Nao foi possivel gravar a imagem em {destino}.")

        logger.info("Imagem de referencia gravada (%s bytes)", destino.stat().st_size)
        return destino.name

    def existe(self, nome_arquivo: str) -> bool:
        return self._caminho(nome_arquivo).is_file()

    def remover(self, nome_arquivo: str) -> None:
        self._caminho(nome_arquivo).unlink(missing_ok=True)
        # Sem o nome do arquivo no log: ele e a matricula do aluno.
        logger.info("Imagem de referencia removida do disco")

    def caminho_absoluto(self, nome_arquivo: str) -> str:
        return str(self._caminho(nome_arquivo).resolve())
