"""Contratos de publicação da interface web na mesma origem."""

from __future__ import annotations

import asyncio
from typing import Any

from src.config.web_settings import WebSettings
from src.presentation.web.app import WebServices, create_app

SEGREDO_TESTE = "segredo-sintetico-com-mais-de-trinta-e-dois-caracteres"
DATABASE_TESTE = "postgresql+psycopg://u:p@localhost:5432/facediff_test_task020"


def _settings() -> WebSettings:
    return WebSettings(
        environment="test",
        database_url=DATABASE_TESTE,
        secret_key=SEGREDO_TESTE,
        retention_days=14,
        database_disposable=True,
    )


def _get(app: Any, path: str) -> tuple[int, dict[str, str], bytes]:
    async def executar() -> tuple[int, dict[str, str], bytes]:
        enviados: list[dict[str, Any]] = []
        corpo = bytearray()
        recebida = False
        raw_path = path.encode("ascii")

        async def receive() -> dict[str, Any]:
            nonlocal recebida
            if not recebida:
                recebida = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()
            raise AssertionError("A leitura da requisição foi cancelada.")

        async def send(mensagem: dict[str, Any]) -> None:
            enviados.append(mensagem)
            if mensagem["type"] == "http.response.body":
                corpo.extend(mensagem.get("body", b""))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": raw_path,
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 12345),
            "server": ("testserver", 80),
        }
        await app(scope, receive, send)
        inicio = next(
            item for item in enviados if item["type"] == "http.response.start"
        )
        headers = {
            chave.decode("latin-1").lower(): valor.decode("latin-1")
            for chave, valor in inicio["headers"]
        }
        return int(inicio["status"]), headers, bytes(corpo)

    return asyncio.run(executar())


def test_interface_entrega_shell_local_com_layout_responsivo_e_sem_cdn() -> None:
    app = create_app(_settings(), WebServices())

    status, headers, corpo = _get(app, "/")
    html = corpo.decode("utf-8")

    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in headers["content-security-policy"]
    assert 'name="viewport"' in html
    assert 'href="/assets/app.css"' in html
    assert 'src="/assets/app.mjs"' in html
    assert "FaceDiff" in html
    assert "https://" not in html


def test_paginas_de_link_e_auth_sao_diretas_e_nao_armazenaveis() -> None:
    app = create_app(_settings(), WebServices())
    paginas = (
        "/login",
        "/trocar-senha",
        "/professor",
        "/cadastro/credencial-sintetica",
        "/presenca/credencial-sintetica",
    )

    for caminho in paginas:
        status, headers, corpo = _get(app, caminho)
        assert status == 200, caminho
        assert b"FaceDiff" in corpo
        assert headers["cache-control"] == "no-store"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["x-robots-tag"] == "noindex, nofollow"


def test_assets_sao_servicos_locais_e_rotas_api_nao_caem_no_shell() -> None:
    app = create_app(_settings(), WebServices())

    css_status, css_headers, css = _get(app, "/assets/app.css")
    js_status, js_headers, js = _get(app, "/assets/app.mjs")
    api_status, api_headers, api = _get(app, "/api/v1/rota-inexistente")

    assert css_status == 200
    assert css_headers["content-type"].startswith("text/css")
    assert b"prefers-reduced-motion" in css
    assert js_status == 200
    assert js_headers["content-type"].startswith("text/javascript")
    assert b"localStorage" not in js
    assert b"/api/v1" in js
    assert b"Authorization" in js
    camera_status, _camera_headers, camera = _get(app, "/assets/camera.mjs")
    assert camera_status == 200
    assert b"getUserMedia" in camera
    assert b"sessionStorage" not in camera
    assert api_status == 404
    assert api_headers["content-type"].startswith("application/json")
    assert b"FaceDiff" not in api
