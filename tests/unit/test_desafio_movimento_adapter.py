from __future__ import annotations

import importlib.util
from types import SimpleNamespace
from typing import Any

import pytest

MODULO = "src.infrastructure.face_recognition.desafio_movimento_adapter"


class DetectorFake:
    def __init__(self, rostos: tuple[tuple[Any, ...], ...]) -> None:
        self.rostos = rostos
        self.timestamps: list[int] = []
        self.fechado = False

    def detectar(self, _frame: Any, timestamp_ms: int) -> Any:
        self.timestamps.append(timestamp_ms)
        return SimpleNamespace(rostos=self.rostos)

    def fechar(self) -> None:
        self.fechado = True


def _pontos(yaw: float = 0.0) -> tuple[Any, ...]:
    from src.domain.services.facial_landmarks import PontoFacial

    pontos = [PontoFacial(0.5, 0.5, 0.0) for _ in range(468)]
    pontos[33] = PontoFacial(0.35, 0.4, 0.0)
    pontos[263] = PontoFacial(0.65, 0.4, 0.0)
    pontos[1] = PontoFacial(0.5 + yaw * 0.3, 0.5, 0.0)
    return tuple(pontos)


def _adapter(detector: DetectorFake) -> Any:
    import importlib

    modulo = importlib.import_module(MODULO)
    return modulo.DesafioMovimentoAdapter(detector)


def test_pose_admite_frente_e_movimentos_leves_nas_duas_direcoes() -> None:
    assert importlib.util.find_spec(MODULO) is not None, "Adapter ainda ausente."
    modulo = importlib.import_module(MODULO)
    esquerda = _adapter(DetectorFake((_pontos(-0.18),)))
    direita = _adapter(DetectorFake((_pontos(0.18),)))
    frente = _adapter(DetectorFake((_pontos(0.0),)))

    assert esquerda.analisar(object()).orientacao is modulo.OrientacaoPose.ESQUERDA
    assert direita.analisar(object()).orientacao is modulo.OrientacaoPose.DIREITA
    assert frente.analisar(object()).orientacao is modulo.OrientacaoPose.FRENTE


@pytest.mark.parametrize("quantidade", [0, 2])
def test_pose_recusa_ausencia_ou_multiplos_rostos(quantidade: int) -> None:
    assert importlib.util.find_spec(MODULO) is not None, "Adapter ainda ausente."
    modulo = importlib.import_module(MODULO)
    rostos = tuple(_pontos(0.0) for _ in range(quantidade))

    resultado = _adapter(DetectorFake(rostos)).analisar(object())

    esperado = (
        modulo.OrientacaoPose.AUSENTE
        if quantidade == 0
        else modulo.OrientacaoPose.MULTIPLOS
    )
    assert resultado.orientacao is esperado


def test_landmarks_incompletos_nao_confirmam_movimento() -> None:
    assert importlib.util.find_spec(MODULO) is not None, "Adapter ainda ausente."
    modulo = importlib.import_module(MODULO)

    resultado = _adapter(DetectorFake((tuple(_pontos()[:3]),))).analisar(object())

    assert resultado.orientacao is modulo.OrientacaoPose.INDETERMINADA


def test_timestamp_monotonico_e_liberacao_de_processo() -> None:
    assert importlib.util.find_spec(MODULO) is not None, "Adapter ainda ausente."
    detector = DetectorFake((_pontos(),))
    adapter = _adapter(detector)
    adapter.analisar(object())
    adapter.analisar(object())

    adapter.fechar()

    assert detector.timestamps[0] < detector.timestamps[1]
    assert detector.fechado is True
