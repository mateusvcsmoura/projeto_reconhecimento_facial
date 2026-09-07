"""Fase 2 -- regra "uma presenca por dia", sem banco."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from src.application.use_cases.registrar_presenca import RegistrarPresenca
from tests.fakes import FakePresencaRepository

TZ = ZoneInfo("America/Sao_Paulo")


def test_primeira_presenca_do_dia_e_registrada() -> None:
    caso = RegistrarPresenca(FakePresencaRepository(), TZ)
    assert caso.executar(aluno_id=1) is True


def test_segunda_presenca_no_mesmo_dia_nao_registra() -> None:
    caso = RegistrarPresenca(FakePresencaRepository(), TZ)
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)

    assert caso.executar(1, momento) is True
    assert caso.executar(1, momento.replace(hour=17)) is False


def test_mesmo_aluno_em_dias_diferentes_registra_duas_vezes() -> None:
    caso = RegistrarPresenca(FakePresencaRepository(), TZ)

    assert caso.executar(1, dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)) is True
    assert caso.executar(1, dt.datetime(2026, 3, 11, 8, 0, tzinfo=TZ)) is True


def test_alunos_diferentes_no_mesmo_dia_nao_se_bloqueiam() -> None:
    caso = RegistrarPresenca(FakePresencaRepository(), TZ)
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)

    assert caso.executar(1, momento) is True
    assert caso.executar(2, momento) is True


def test_o_dia_e_calculado_no_fuso_da_aplicacao() -> None:
    """23h30 UTC ainda e o dia anterior em Sao Paulo -- vale o fuso da app."""
    presencas = FakePresencaRepository()
    caso = RegistrarPresenca(presencas, TZ)

    caso.executar(1, dt.datetime(2026, 3, 10, 23, 30, tzinfo=dt.timezone.utc))

    _, dia, _ = presencas.chamadas[0]
    assert dia == dt.date(2026, 3, 10)
