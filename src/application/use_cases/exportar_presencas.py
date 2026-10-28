"""Exportação pontual de presenças sem dados biométricos ou de terceiros."""

from __future__ import annotations

import csv
import datetime as dt
from collections.abc import Iterable
from io import StringIO
from typing import Protocol
from zoneinfo import ZoneInfo

from src.domain.services.autorizacao import AtorWeb

CABECALHOS_CSV = (
    "turma_id",
    "materia",
    "periodo",
    "sessao_id",
    "data",
    "horario_exibido",
    "rotulo_horario",
    "horario_evidencia",
    "horario_correcao",
    "matricula",
    "nome",
    "status",
    "correcao_manual",
)


class RepositorioExportacaoPresencas(Protocol):
    def listar_presencas_exportacao(
        self,
        ator: AtorWeb,
        *,
        turma_id: int,
        inicio: dt.date | None = None,
        fim: dt.date | None = None,
        sessao_id: int | None = None,
    ) -> list[dict[str, object]]: ...


class ExportarPresencas:
    def __init__(
        self, repositorio: RepositorioExportacaoPresencas, timezone_name: str
    ) -> None:
        self._repositorio = repositorio
        self._timezone = ZoneInfo(timezone_name)

    def executar(
        self, ator: AtorWeb, *, turma_id: int, inicio: dt.date, fim: dt.date
    ) -> bytes:
        if turma_id <= 0 or inicio > fim or (fim - inicio).days > 366:
            raise ValueError("O intervalo do relatório é inválido.")
        return _csv(
            self._repositorio.listar_presencas_exportacao(
                ator, turma_id=turma_id, inicio=inicio, fim=fim
            ),
            self._timezone,
        )

    def executar_sessao(self, ator: AtorWeb, *, turma_id: int, sessao_id: int) -> bytes:
        if turma_id <= 0 or sessao_id <= 0:
            raise ValueError("A sessão do relatório é inválida.")
        return _csv(
            self._repositorio.listar_presencas_exportacao(
                ator, turma_id=turma_id, sessao_id=sessao_id
            ),
            self._timezone,
        )


def _csv(linhas: list[dict[str, object]], timezone: ZoneInfo) -> bytes:
    buffer = StringIO(newline="")
    escritor = csv.writer(buffer, lineterminator="\r\n")
    escritor.writerow(CABECALHOS_CSV)
    for linha in linhas:
        escritor.writerow(_linha_csv(linha, timezone))
    return buffer.getvalue().encode("utf-8")


def _linha_csv(linha: dict[str, object], timezone: ZoneInfo) -> tuple[str, ...]:
    evidencia = _data_hora(linha.get("horario_evidencia"), timezone)
    correcao = _data_hora(linha.get("horario_correcao"), timezone)
    registro = _data_hora(linha.get("registrado_em"), timezone)
    rotulo = "evidencia_biometrica" if evidencia else "registro_legado"
    exibido = evidencia or registro
    if evidencia is None and correcao is not None:
        rotulo = "correcao_manual"
        exibido = correcao
    data = linha.get("data_referencia")
    if not isinstance(data, dt.date):
        raise ValueError("O registro de presença não contém uma data válida.")
    manual = linha.get("origem") == "manual" or linha.get("corrigida_em") is not None
    valores: Iterable[object] = (
        linha.get("turma_id"),
        linha.get("materia"),
        linha.get("periodo"),
        linha.get("sessao_id"),
        data.isoformat(),
        exibido or "",
        rotulo,
        evidencia,
        correcao,
        linha.get("matricula"),
        linha.get("nome"),
        linha.get("status"),
        "sim" if manual else "não",
    )
    return tuple(_campo_seguro(_texto(valor)) for valor in valores)


def _data_hora(valor: object, timezone: ZoneInfo) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, dt.datetime):
        raise ValueError("O registro de presença contém um horário inválido.")
    instante = valor
    if instante.tzinfo is None or instante.utcoffset() is None:
        instante = instante.replace(tzinfo=dt.UTC)
    return instante.astimezone(timezone).strftime("%H:%M:%S")


def _texto(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, dt.date):
        return valor.isoformat()
    return str(valor)


def _campo_seguro(valor: str) -> str:
    primeiro = valor.lstrip(" \t\r\n")[:1]
    if primeiro in {"=", "+", "-", "@", "\t", "\r", "\n"}:
        return "'" + valor
    return valor
