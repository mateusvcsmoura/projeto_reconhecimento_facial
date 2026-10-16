"""Composicao das politicas optativas temporal e de qualidade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.config.settings import Settings
from src.domain.entities.turma import Periodo, Turma
from src.domain.services.consistencia_temporal import ParametrosTemporais
from src.domain.services.matcher import PoliticaAmbiguidade
from src.domain.services.qualidade_captura import ParametrosQualidade
from tests.unit.test_main_qualidade import _carregar_main_com_deepface_falso

URL_VALIDA = "postgresql+psycopg://u:p@h:5432/d"


@pytest.mark.parametrize(
    ("qualidade_habilitada", "temporal_habilitada", "ambiguidade_habilitada"),
    [
        (qualidade, temporal, ambiguidade)
        for qualidade in (False, True)
        for temporal in (False, True)
        for ambiguidade in (False, True)
    ],
)
def test_montar_menu_compõe_politicas_sem_conectar_ao_banco(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    qualidade_habilitada: bool,
    temporal_habilitada: bool,
    ambiguidade_habilitada: bool,
) -> None:
    main = _carregar_main_com_deepface_falso()
    recebido_adapter: dict[str, Any] = {}
    recebido_menu: dict[str, Any] = {}
    recebido_reconhecedor: dict[str, Any] = {}

    class AdaptadorEspiao:
        def __init__(self, **kwargs: Any) -> None:
            recebido_adapter.update(kwargs)

    class MenuEspiao:
        def __init__(self, **kwargs: Any) -> None:
            recebido_menu.update(kwargs)

        def executar(self) -> None:
            pass

    class ReconhecedorEspiao:
        def __init__(self, *_args: object, **kwargs: Any) -> None:
            recebido_reconhecedor.update(kwargs)

    monkeypatch.setattr(main, "criar_engine", lambda _url: object())
    monkeypatch.setattr(main, "PostgresAlunoRepository", lambda _engine: object())
    monkeypatch.setattr(main, "PostgresPresencaRepository", lambda _engine: object())
    monkeypatch.setattr(main, "PostgresTurmaRepository", lambda _engine: object())
    monkeypatch.setattr(main, "LocalImageStorage", lambda _raiz: object())
    monkeypatch.setattr(main, "DeepFaceAdapter", AdaptadorEspiao)
    monkeypatch.setattr(main, "MenuCLI", MenuEspiao)
    monkeypatch.setattr(main, "ReconhecerAluno", ReconhecedorEspiao)
    monkeypatch.setattr(main, "JanelaDeVideo", lambda _titulo: object())

    valores: dict[str, Any] = {
        "_env_file": None,
        "database_url": URL_VALIDA,
        "storage_dir": tmp_path,
        "face_quality_enabled": qualidade_habilitada,
        "face_temporal_enabled": temporal_habilitada,
        "face_anti_spoofing": True,
    }
    if qualidade_habilitada:
        valores.update(
            face_quality_min_face_px=96,
            face_quality_min_brightness=35.0,
            face_quality_max_brightness=225.0,
            face_quality_min_sharpness=125.0,
        )
    if temporal_habilitada:
        valores.update(
            face_temporal_min_observations=4,
            face_temporal_window_seconds=8.0,
            face_temporal_max_age_seconds=1.5,
        )
    if ambiguidade_habilitada:
        valores.update(
            face_ambiguity_enabled=True,
            face_ambiguity_min_margin=0.04,
        )

    menu = main.montar_menu(Settings(**valores))
    menu._abrir_turma(Turma(id=1, materia="IA", periodo=Periodo.DIURNO))

    esperado_qualidade = (
        ParametrosQualidade(
            min_face_px=96,
            min_brightness=35.0,
            max_brightness=225.0,
            min_sharpness=125.0,
        )
        if qualidade_habilitada
        else None
    )
    esperado_temporal = (
        ParametrosTemporais(
            min_observacoes=4,
            janela_segundos=8.0,
            validade_segundos=1.5,
        )
        if temporal_habilitada
        else None
    )

    assert recebido_adapter["qualidade"] == esperado_qualidade
    assert recebido_adapter["anti_spoofing"] is True
    assert recebido_menu["temporal"] == esperado_temporal
    assert recebido_reconhecedor["limiar"] == 0.30
    assert recebido_reconhecedor["ambiguidade"] == (
        PoliticaAmbiguidade(0.04) if ambiguidade_habilitada else None
    )
