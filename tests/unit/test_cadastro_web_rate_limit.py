from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from src.config.web_settings import WebSettings
from src.presentation.web.app import WebServices, create_app

ORIGEM = "https://cadastro.test"
SEGREDO = "segredo-sintetico-rate-limit-com-mais-de-trinta-e-dois-bytes"
AGORA = dt.datetime(2026, 10, 19, 12, tzinfo=dt.UTC)


class RateLimitFake:
    def __init__(self, clock: Callable[[], dt.datetime]) -> None:
        self.clock = clock
        self.buckets: dict[str, tuple[dt.datetime, int, dt.datetime | None]] = {}

    def limitar_requisicao(
        self,
        chave_hash: str,
        *,
        agora: dt.datetime,
        limite: int,
        janela: dt.timedelta,
    ) -> int | None:
        assert re.fullmatch(r"[0-9a-f]{64}", chave_hash)
        inicio, quantidade, bloqueado_ate = self.buckets.get(
            chave_hash, (agora, 0, None)
        )
        if bloqueado_ate is not None and bloqueado_ate > agora:
            return max(1, math.ceil((bloqueado_ate - agora).total_seconds()))
        if inicio + janela <= agora:
            inicio, quantidade, bloqueado_ate = agora, 0, None
        if quantidade >= limite:
            bloqueado_ate = agora + janela
            self.buckets[chave_hash] = (inicio, quantidade, bloqueado_ate)
            return max(1, math.ceil(janela.total_seconds()))
        self.buckets[chave_hash] = (inicio, quantidade + 1, bloqueado_ate)
        return None


class LinkFake:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def trocar_token(self, **kwargs: Any) -> None:
        self.calls.append(str(kwargs["token_hash"]))
        return None


def _settings(**overrides: object) -> WebSettings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": "postgresql+psycopg://user:password@test-db:5432/face_test_task019a",
        "secret_key": SEGREDO,
        "retention_days": 10,
        "database_disposable": True,
        "public_origin": ORIGEM,
        "public_registration_context_limit_per_minute": 1,
        "public_registration_query_limit_per_minute": 1,
        "public_registration_origin_limit_per_minute": 10,
    }
    values.update(overrides)
    return WebSettings(**values)  # type: ignore[arg-type]


@contextmanager
def _client(
    *,
    settings: WebSettings | None = None,
    peer: tuple[str, int] = ("198.51.100.20", 43000),
    clock: Callable[[], dt.datetime] = lambda: AGORA,
    links: LinkFake | None = None,
) -> Iterator[tuple[TestClient, RateLimitFake, LinkFake | None]]:
    limiter = RateLimitFake(clock)
    services = WebServices(
        link_repository=links,
        presenca_repository=limiter,  # type: ignore[arg-type]
        rate_limit_secret=SEGREDO.encode(),
        clock=clock,
    )
    app = create_app(settings or _settings(), services)
    with TestClient(app, base_url=ORIGEM, client=peer) as client:
        yield client, limiter, links


def _cadastro_invalido(client: TestClient, token: str, **headers: str):
    return client.post(
        "/api/v1/cadastros",
        headers={"Authorization": f"Bearer {token}", **headers},
        json={"campo": "inválido"},
    )


def test_limitacao_cobre_corpo_invalido_e_retorna_retry_after() -> None:
    with _client() as (client, limiter, _links):
        primeiro = _cadastro_invalido(client, "credencial-sintetica-019a")
        segundo = _cadastro_invalido(client, "credencial-sintetica-019a")

    assert primeiro.status_code == 422
    assert segundo.status_code == 429
    assert segundo.headers["Retry-After"] == "60"
    assert segundo.json()["codigo"] == "limite_requisicoes"
    assert all(len(chave) == 64 for chave in limiter.buckets)
    assert "credencial-sintetica-019a" not in repr(limiter.buckets)
    assert "198.51.100.20" not in repr(limiter.buckets)


def test_limite_de_consulta_por_credencial_tem_namespace_e_janela_proprios() -> None:
    agora = [AGORA]
    with _client(clock=lambda: agora[0]) as (client, limiter, _links):
        assert (
            _cadastro_invalido(client, "credencial-sintetica-019a").status_code == 422
        )
        consulta = client.get(
            "/api/v1/cadastros/71",
            headers={"Authorization": "Bearer credencial-sintetica-019a"},
        )
        repetida = client.get(
            "/api/v1/cadastros/71",
            headers={"Authorization": "Bearer credencial-sintetica-019a"},
        )
        agora[0] += dt.timedelta(minutes=1, seconds=1)
        apos_janela = _cadastro_invalido(client, "credencial-sintetica-019a")

    assert consulta.status_code == 503
    assert repetida.status_code == 429
    assert apos_janela.status_code == 422
    assert len(limiter.buckets) == 3


def test_teto_agregado_por_origem_impede_rotacao_de_credenciais() -> None:
    settings = _settings(public_registration_origin_limit_per_minute=1)
    with _client(settings=settings) as (client, _limiter, _links):
        primeiro = _cadastro_invalido(client, "credencial-primeira")
        rotacionada = _cadastro_invalido(client, "credencial-rotacionada")

    assert primeiro.status_code == 422
    assert rotacionada.status_code == 429


def test_captura_e_consentimento_tem_limites_separados_antes_da_validacao() -> None:
    with _client() as (client, _limiter, _links):
        captura_1 = client.post("/api/v1/cadastros/71/capturas", json={})
        consentimento_1 = client.post("/api/v1/cadastros/71/consentimento", json={})
        captura_2 = client.post("/api/v1/cadastros/71/capturas", json={})
        consentimento_2 = client.post("/api/v1/cadastros/71/consentimento", json={})

    assert captura_1.status_code != 429
    assert consentimento_1.status_code != 429
    assert captura_2.status_code == 429
    assert consentimento_2.status_code == 429


def test_renovacao_de_desafio_tem_limite_proprio() -> None:
    with _client() as (client, _limiter, _links):
        primeira = client.post("/api/v1/cadastros/71/desafio")
        segunda = client.post("/api/v1/cadastros/71/desafio")

    assert primeira.status_code != 429
    assert segunda.status_code == 429


def test_producao_sem_repositorio_de_rate_limit_falha_fechado(
    tmp_path: Path,
) -> None:
    settings = _settings(
        environment="production",
        database_url="postgresql+psycopg://user:password@db:5432/face_prod",
        database_disposable=False,
        purpose_end_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
        capture_temp_dir=tmp_path / "captures",
        reference_storage_dir=tmp_path / "references",
        maintenance_dir=tmp_path / "maintenance",
        backup_exclusions_file=tmp_path / "private" / "exclusions.jsonl",
        mediapipe_model_path=tmp_path / "model.task",
        mediapipe_python_executable=tmp_path / "python.exe",
    )
    app = create_app(settings, WebServices())

    with TestClient(app, base_url=ORIGEM) as client:
        response = client.get("/api/v1/cadastros/71")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"
    assert response.json()["codigo"] == "limite_indisponivel"


def test_x_forwarded_for_forjado_por_acesso_direto_nao_altera_a_origem() -> None:
    settings = _settings(public_registration_origin_limit_per_minute=1)
    with _client(settings=settings) as (client, _limiter, _links):
        primeiro = _cadastro_invalido(
            client, "credencial-direta", **{"X-Forwarded-For": "203.0.113.1"}
        )
        forjado = _cadastro_invalido(
            client, "credencial-direta", **{"X-Forwarded-For": "203.0.113.2"}
        )

    assert primeiro.status_code == 422
    assert forjado.status_code == 429


def test_forwarded_for_so_separa_origens_quando_peer_e_proxy_confiavel() -> None:
    settings = _settings(
        trusted_proxy_cidrs="127.0.0.1/32",
        public_registration_origin_limit_per_minute=1,
    )
    with _client(
        settings=settings,
        peer=("127.0.0.1", 43000),
    ) as (client, limiter, _links):
        primeira_origem = _cadastro_invalido(
            client, "credencial-proxy", **{"X-Forwarded-For": "203.0.113.1"}
        )
        segunda_origem = _cadastro_invalido(
            client, "credencial-proxy", **{"X-Forwarded-For": "203.0.113.2"}
        )

    assert primeira_origem.status_code == 422
    assert segunda_origem.status_code == 422
    assert len(limiter.buckets) == 4


def test_troca_de_link_publica_credencial_com_limite_por_token_e_origem() -> None:
    links = LinkFake()
    with _client(links=links) as (client, _limiter, _links):
        body = {"token": "t" * 43}
        primeiro = client.post("/api/v1/acessos-link", json=body)
        segundo = client.post("/api/v1/acessos-link", json=body)

    assert primeiro.status_code == 404
    assert segundo.status_code == 429
    assert len(links.calls) == 1
