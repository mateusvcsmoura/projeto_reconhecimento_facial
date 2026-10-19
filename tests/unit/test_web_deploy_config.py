"""Contratos estaticos dos artefatos de deploy web."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "web"


@pytest.fixture(scope="module")
def compose_config(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose nao instalado; validacao estrutural pendente.")

    temp = tmp_path_factory.mktemp("compose-config")
    env = os.environ.copy()
    secret_names = (
        "WEB_DATABASE_URL_FILE",
        "WEB_SECRET_KEY_FILE",
        "POSTGRES_PASSWORD_FILE",
        "WEB_APP_DB_PASSWORD_FILE",
        "WEB_MIGRATOR_DB_PASSWORD_FILE",
        "ALEMBIC_DATABASE_URL_FILE",
        "WEB_BACKUP_PG_SERVICE_FILE",
        "WEB_BACKUP_RCLONE_CONFIG_FILE",
    )
    for name in secret_names:
        secret_path = temp / name.lower()
        secret_path.write_text("valor sintetico nao secreto\n", encoding="utf-8")
        env[name] = str(secret_path)

    result = subprocess.run(
        [
            docker,
            "compose",
            "--env-file",
            str(DEPLOY / ".env.example"),
            "--profile",
            "admin",
            "--profile",
            "ops",
            "--file",
            str(DEPLOY / "compose.yaml"),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def test_compose_expoe_somente_http_e_https_no_caddy(
    compose_config: dict[str, object],
) -> None:
    services = compose_config["services"]
    assert isinstance(services, dict)
    port_bindings = {
        service_name: [port["published"] for port in service.get("ports", [])]
        for service_name, service in services.items()
        if service.get("ports")
    }
    assert port_bindings == {"caddy": ["80", "443"]}


def test_proxy_nao_monta_arquivos_biometricos_e_so_encaminha_para_api(
    compose_config: dict[str, object],
) -> None:
    services = compose_config["services"]
    assert isinstance(services, dict)
    caddy = services["caddy"]
    assert isinstance(caddy, dict)
    mount_sources = {mount["source"] for mount in caddy["volumes"]}
    assert not any(
        token in source.lower()
        for source in mount_sources
        for token in ("reference", "private", "model", "capture")
    )
    caddyfile = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    assert "reverse_proxy app:8000" in caddyfile
    assert "request>uri delete" in caddyfile
    assert "request>headers>Cookie delete" in caddyfile
    assert "request>headers>Authorization delete" in caddyfile
    assert "resp_headers>Set-Cookie delete" in caddyfile


def test_referencias_e_modelos_sao_persistentes_e_privados(
    compose_config: dict[str, object],
) -> None:
    services = compose_config["services"]
    volumes = compose_config["volumes"]
    assert isinstance(services, dict)
    assert isinstance(volumes, dict)
    assert {
        "postgres-data",
        "references",
        "caddy-data",
        "caddy-config",
        "backup-encrypted",
        "backup-state",
        "exclusions",
    } <= set(volumes)
    assert "docker.sock" not in json.dumps(compose_config).lower()

    caddy_sources = {mount["source"] for mount in services["caddy"]["volumes"]}
    assert "references" not in caddy_sources
    assert "models" not in caddy_sources
    assert any(
        mount["type"] == "volume" and mount["source"] == "references"
        for mount in services["app"]["volumes"]
    )
    assert any(
        mount["type"] == "volume" and mount["source"] == "references"
        for mount in services["face-worker"]["volumes"]
    )
    model_mount = next(
        mount
        for mount in services["face-worker"]["volumes"]
        if mount["target"] == "/var/lib/facediff/models"
    )
    assert model_mount["type"] == "bind"
    assert model_mount["read_only"] is True


def test_app_worker_compartilham_o_mesmo_diretorio_temporario_de_captura(
    compose_config: dict[str, object],
) -> None:
    services = compose_config["services"]
    assert isinstance(services, dict)
    sources: list[str] = []
    for service_name in ("app", "face-worker"):
        mounts = services[service_name]["volumes"]
        capture_mount = next(
            mount for mount in mounts if mount["target"] == "/run/facediff/captures"
        )
        assert capture_mount["type"] == "bind"
        sources.append(capture_mount["source"])
    assert sources[0] == sources[1]


def test_worker_e_backup_nao_compartilham_acesso_de_rede_publica(
    compose_config: dict[str, object],
) -> None:
    services = compose_config["services"]
    networks = compose_config["networks"]
    assert isinstance(services, dict)
    assert isinstance(networks, dict)
    assert networks["data"]["internal"] is True
    assert networks["web"]["internal"] is True
    assert set(services["face-worker"]["networks"]) == {"data"}
    assert set(services["postgres"]["networks"]) == {"data"}
    assert set(services["backup"]["networks"]) == {"data", "backup-egress"}
    assert "edge-egress" not in services["app"]["networks"]
    assert "edge-egress" not in services["face-worker"]["networks"]


def test_segredos_sao_arquivos_e_migration_nao_roda_no_boot_da_api(
    compose_config: dict[str, object],
) -> None:
    services = compose_config["services"]
    secrets = compose_config["secrets"]
    assert isinstance(services, dict)
    assert isinstance(secrets, dict)
    assert all("file" in secret for secret in secrets.values())
    app = services["app"]
    assert "alembic" not in json.dumps(app["command"]).lower()
    assert "migrate" not in app["command"]
    assert services["migrate"]["profiles"] == ["admin"]
    assert "alembic" in json.dumps(services["migrate"]["command"]).lower()


def test_saude_da_api_verifica_readiness_sem_expor_porta_host(
    compose_config: dict[str, object],
) -> None:
    services = compose_config["services"]
    assert isinstance(services, dict)
    app = services["app"]
    healthcheck = app["healthcheck"]
    assert "/health/ready" in json.dumps(healthcheck)
    assert "--no-access-log" in json.dumps(app["command"])
    assert "ports" not in app


def test_imagens_e_limites_sao_explicitos_e_worker_reinicia_com_seguranca(
    compose_config: dict[str, object],
) -> None:
    services = compose_config["services"]
    assert isinstance(services, dict)
    for service in services.values():
        if "build" not in service:
            assert "@sha256:" in service["image"]
    worker = services["face-worker"]
    assert worker["restart"] == "unless-stopped"
    assert worker["stop_signal"] == "SIGINT"
    assert all("mem_limit" in service for service in services.values())
    assert all("cpus" in service for service in services.values())
    worker_healthcheck = json.dumps(worker["healthcheck"])
    assert "/opt/facediff/entrypoint.py" in worker_healthcheck
    assert "web_worker_healthcheck" in worker_healthcheck


def test_dockerfile_fixa_bases_e_isola_dependencias_biometricas() -> None:
    dockerfile = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.count("python -m pip check") >= 3
    assert "python:3.12-slim-bookworm@sha256:" in dockerfile
    assert "postgres:16.15-bookworm@sha256:" in dockerfile
    assert "caddy:2.11.4-alpine@sha256:" in dockerfile
    app_stage = dockerfile.split("FROM web-base AS app", maxsplit=1)[1].split(
        "FROM python-base AS worker", maxsplit=1
    )[0]
    assert "requirements.txt" not in app_stage
    assert "requirements-landmarks-linux.txt" not in app_stage


def test_worker_preflight_exige_modelos_locais_sem_download_automatico() -> None:
    preflight = (ROOT / "scripts" / "web_worker_preflight.py").read_text(
        encoding="utf-8"
    )
    assert "facenet512_weights.h5" in preflight
    assert "2.7_80x80_MiniFASNetV2.pth" in preflight
    assert "4_0_0_80x80_MiniFASNetV1SE.pth" in preflight
    assert "WEB_MEDIAPIPE_MODEL_PATH" in preflight
    assert "download" not in preflight.lower()
