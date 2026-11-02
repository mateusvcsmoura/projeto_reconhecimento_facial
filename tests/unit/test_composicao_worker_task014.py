from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine

from src.application.services.fila_facial import TipoJobFacial
from src.config.web_settings import WebSettings
from src.domain.services.qualidade_captura import ParametrosQualidade

_deepface_stub = ModuleType("deepface")
_deepface_stub.DeepFace = object()
with patch.dict(sys.modules, {"deepface": _deepface_stub}):
    from src import face_worker_main

SEGREDO = "segredo-sintetico-de-composicao-com-mais-de-trinta-e-dois-caracteres"
URL_TESTE = "postgresql+psycopg://usuario:senha@test-db:5432/face_test_task014"


class _Preparador:
    def __init__(self) -> None:
        self.aquecimentos = 0
        self.fechamentos = 0

    def preaquecer(self) -> None:
        self.aquecimentos += 1

    def fechar(self) -> None:
        self.fechamentos += 1


class _Adapter(_Preparador):
    def preaquecer_para_web(self) -> None:
        self.aquecimentos += 1


def _settings(tmp_path: Path, **overrides: object) -> WebSettings:
    valores: dict[str, object] = {
        "environment": "test",
        "database_url": URL_TESTE,
        "secret_key": SEGREDO,
        "retention_days": 14,
        "database_disposable": True,
        "capture_temp_dir": tmp_path / "capturas",
    }
    valores.update(overrides)
    return WebSettings(**valores)  # type: ignore[arg-type]


def test_composicao_worker_monta_processadores_cadastro_e_presenca(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    dispose = Mock(wraps=engine.dispose)
    engine.dispose = dispose  # type: ignore[method-assign]
    adapter = _Adapter()
    cadastro = _Preparador()
    presenca = _Preparador()
    pose = _Preparador()
    jobs_repository = object()
    solicitacoes_repository = object()
    desafio_repository = object()
    monkeypatch.setattr(face_worker_main, "create_engine", lambda *_a, **_k: engine)
    argumentos_adapter: dict[str, Any] = {}
    monkeypatch.setattr(
        face_worker_main,
        "DeepFaceAdapter",
        lambda **kwargs: (argumentos_adapter.update(kwargs), adapter)[1],
    )
    monkeypatch.setattr(
        face_worker_main, "PostgresJobRepository", lambda _factory: jobs_repository
    )
    monkeypatch.setattr(
        face_worker_main,
        "PostgresSolicitacaoRepository",
        lambda _engine: solicitacoes_repository,
    )
    monkeypatch.setattr(face_worker_main, "MediaPipeLandmarks", lambda *_args: object())
    monkeypatch.setattr(
        face_worker_main, "DesafioMovimentoAdapter", lambda _landmarks: object()
    )
    monkeypatch.setattr(
        face_worker_main,
        "AdaptadorPoseSobDemanda",
        lambda factory: (factory(), pose)[1],
    )
    monkeypatch.setattr(
        face_worker_main,
        "PrivateReferenceStorageLocal",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        face_worker_main,
        "ProcessadorCadastroWeb",
        lambda *_args, **_kwargs: cadastro,
    )
    monkeypatch.setattr(
        face_worker_main,
        "PostgresDesafioRepository",
        lambda _factory: desafio_repository,
    )
    monkeypatch.setattr(
        face_worker_main, "DesafioCaptura", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        face_worker_main,
        "ProcessadorDesafioVerificacao",
        lambda *_args, **_kwargs: presenca,
    )
    settings = _settings(
        tmp_path,
        reference_storage_dir=tmp_path / "referencias",
        mediapipe_model_path=tmp_path / "face_landmarker.task",
        mediapipe_python_executable=tmp_path / ".venv-landmarks" / "python.exe",
        face_quality_min_sharpness=60.0,
        face_quality_dim_brightness=70.0,
    )

    worker, adapter_result, engine_result, repository_result = (
        face_worker_main.construir_worker(settings)
    )
    worker.preaquecer()
    worker.fechar()

    # Os demais padrões do WebSettings precisam coincidir com os do domínio.
    assert argumentos_adapter["qualidade"] == ParametrosQualidade(
        min_sharpness=60.0, dim_brightness=70.0
    )
    assert adapter_result is adapter
    assert engine_result is engine
    assert repository_result is jobs_repository
    assert cadastro.aquecimentos == 1
    assert presenca.aquecimentos == 1
    assert cadastro.fechamentos == 1
    assert presenca.fechamentos == 1
    engine.dispose()
    dispose.assert_called_once_with()


def test_composicao_worker_rejeita_configuracao_incompleta(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="WEB_CAPTURE_TEMP_DIR"):
        face_worker_main.construir_worker(_settings(tmp_path, capture_temp_dir=None))

    settings = _settings(tmp_path, reference_storage_dir=tmp_path / "referencias")
    with pytest.raises(RuntimeError, match="WEB_MEDIAPIPE_MODEL_PATH"):
        face_worker_main.construir_worker(settings)


class _Worker:
    def __init__(self, *, stop: bool = False) -> None:
        self.aquecimentos = 0
        self.fechamentos = 0
        self.stop = stop

    def preaquecer(self) -> None:
        self.aquecimentos += 1

    def executar_um(self) -> bool:
        if self.stop:
            raise RuntimeError("parada sintetica")
        return False

    def reconciliar_temporarios(self) -> int:
        return 0

    def fechar(self) -> None:
        self.fechamentos += 1


class _Repository:
    def __init__(self, adquirido: bool = True) -> None:
        self.adquirido = adquirido

    @contextmanager
    def worker_unico(self):
        yield self.adquirido


class _Lock:
    def __init__(self, _path: Path, adquirido: bool = True) -> None:
        self.adquirido = adquirido

    def __enter__(self) -> _Lock:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


@pytest.mark.parametrize(
    ("lock_local", "lock_db", "mensagem"),
    [
        (False, True, "worker facial ativo nesta máquina"),
        (True, False, "worker facial ativo no PostgreSQL"),
    ],
)
def test_worker_libera_recursos_ao_nao_adquirir_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lock_local: bool,
    lock_db: bool,
    mensagem: str,
) -> None:
    worker = _Worker()
    adapter = _Adapter()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    dispose = Mock(wraps=engine.dispose)
    engine.dispose = dispose  # type: ignore[method-assign]
    repository = _Repository(lock_db)
    monkeypatch.setattr(
        face_worker_main,
        "construir_worker",
        lambda *_args, **_kwargs: (worker, adapter, engine, repository),
    )
    monkeypatch.setattr(
        face_worker_main,
        "SingletonProcessLock",
        lambda _path: _Lock(_path, lock_local),
    )

    with pytest.raises(RuntimeError, match=mensagem):
        face_worker_main.executar_worker(_settings(tmp_path))

    assert worker.fechamentos == 1
    dispose.assert_called_once_with()


def test_worker_aquece_antes_de_reivindicar_e_libera_no_encerramento(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker = _Worker(stop=True)
    adapter = _Adapter()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    dispose = Mock(wraps=engine.dispose)
    engine.dispose = dispose  # type: ignore[method-assign]
    repository = _Repository()
    monkeypatch.setattr(
        face_worker_main,
        "construir_worker",
        lambda *_args, **_kwargs: (worker, adapter, engine, repository),
    )
    monkeypatch.setattr(
        face_worker_main,
        "SingletonProcessLock",
        lambda path: _Lock(path),
    )
    monkeypatch.setattr(
        face_worker_main,
        "preparar_worker",
        lambda _worker, aquecer: aquecer(),
    )
    publicar_marcador = face_worker_main._marcar_worker_pronto
    marcadores_publicados: list[str] = []

    def registrar_marcador(caminho: Path) -> None:
        assert adapter.aquecimentos == 1
        assert worker.aquecimentos == 1
        publicar_marcador(caminho)
        marcadores_publicados.append(caminho.read_text(encoding="ascii"))

    monkeypatch.setattr(face_worker_main, "_marcar_worker_pronto", registrar_marcador)

    with pytest.raises(RuntimeError, match="parada sintetica"):
        face_worker_main.executar_worker(
            _settings(tmp_path, maintenance_dir=tmp_path / "maintenance")
        )

    assert adapter.aquecimentos == 1
    assert worker.aquecimentos == 1
    assert worker.fechamentos == 1
    assert marcadores_publicados == ["ready\n"]
    assert not (tmp_path / "maintenance" / ".worker-ready").exists()
    dispose.assert_called_once_with()


def test_worker_construido_com_processadores_injetados_nao_carrega_landmarks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    dispose = Mock(wraps=engine.dispose)
    engine.dispose = dispose  # type: ignore[method-assign]
    adapter = _Adapter()
    jobs_repository = object()
    monkeypatch.setattr(face_worker_main, "create_engine", lambda *_a, **_k: engine)
    monkeypatch.setattr(face_worker_main, "DeepFaceAdapter", lambda **_k: adapter)
    monkeypatch.setattr(
        face_worker_main, "PostgresJobRepository", lambda _factory: jobs_repository
    )
    processors: dict[TipoJobFacial, Any] = {}

    worker, _, _, repository = face_worker_main.construir_worker(
        _settings(tmp_path), processadores=processors
    )

    assert repository is jobs_repository
    worker.fechar()
    engine.dispose()
    dispose.assert_called_once_with()
