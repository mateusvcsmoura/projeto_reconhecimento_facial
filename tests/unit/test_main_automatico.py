"""Composicao dos parametros de captura automatica sem abrir infra real."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.config.settings import Settings
from src.domain.entities.turma import Periodo, Turma
from src.domain.services.captura_automatica import ParametrosCapturaAutomatica
from tests.unit.test_main_qualidade import _carregar_main_com_deepface_falso

URL_VALIDA = "postgresql+psycopg://u:p@h:5432/d"


@pytest.mark.parametrize("habilitada", [False, True])
def test_montar_menu_injeta_ou_desliga_captura_automatica(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    habilitada: bool,
) -> None:
    main = _carregar_main_com_deepface_falso()
    recebido: dict[str, Any] = {}

    class MenuEspiao:
        def __init__(self, **kwargs: Any) -> None:
            recebido.update(kwargs)

        def executar(self) -> None:
            pass

    class AdaptadorEspiao:
        def __init__(self, **_kwargs: Any) -> None:
            pass

    class ReconhecedorEspiao:
        def __init__(self, *_args: object, **_kwargs: Any) -> None:
            pass

    monkeypatch.setattr(main, "criar_engine", lambda _url: object())
    monkeypatch.setattr(main, "PostgresAlunoRepository", lambda _engine: object())
    monkeypatch.setattr(main, "PostgresPresencaRepository", lambda _engine: object())
    monkeypatch.setattr(main, "PostgresTurmaRepository", lambda _engine: object())
    monkeypatch.setattr(main, "LocalImageStorage", lambda _diretorio: object())
    monkeypatch.setattr(main, "DeepFaceAdapter", AdaptadorEspiao)
    monkeypatch.setattr(main, "MenuCLI", MenuEspiao)
    monkeypatch.setattr(main, "ReconhecerAluno", ReconhecedorEspiao)

    settings = Settings(
        _env_file=None,
        database_url=URL_VALIDA,
        storage_dir=tmp_path,
        face_auto_capture_enabled=habilitada,
        face_auto_capture_wait_seconds=7.0,
        face_auto_capture_sample_seconds=0.25,
        face_auto_capture_max_age_seconds=1.25,
    )

    menu = main.montar_menu(settings)
    menu._abrir_turma(Turma(id=1, materia="IA", periodo=Periodo.DIURNO))

    esperado = (
        ParametrosCapturaAutomatica(
            espera_segundos=7.0,
            intervalo_amostragem_segundos=0.25,
            idade_maxima_segundos=1.25,
        )
        if habilitada
        else None
    )
    assert recebido["captura_automatica"] == esperado
