from __future__ import annotations

import csv
import datetime as dt
from io import StringIO
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.config.web_settings import WebSettings
from src.domain.entities.presenca_web import (
    OrigemPresenca,
    Presenca,
    RevisaoPresenca,
    StatusPresenca,
)
from src.infrastructure.repositories.postgres_conta_repository import ContaAutenticada
from src.presentation.web.app import WebServices, create_app

AGORA = dt.datetime(2026, 10, 18, 12, tzinfo=dt.UTC)


class _RepositorioAuth:
    def autenticar_sessao(self, token: str | None) -> ContaAutenticada | None:
        if token == "sessao-professor":
            return ContaAutenticada(
                10, "professor", True, False, 3, 20, "h" * 64, "csrf"
            )
        if token == "sessao-admin":
            return ContaAutenticada(
                11, "admin", True, False, None, 20, "a" * 64, "csrf-admin"
            )
        return None

    def validar_csrf(self, _conta: ContaAutenticada, token: str | None) -> bool:
        return token in {"csrf", "csrf-admin"}


class _RepositorioGestao:
    def obter_turma(self, _ator: Any, turma_id: int) -> dict[str, object]:
        return {"id": turma_id, "materia": "IA", "periodo": "diurno"}

    def criar_turma(self, **kwargs: Any) -> dict[str, object]:
        return {"id": 8, "materia": kwargs["materia"], "periodo": kwargs["periodo"]}

    def atualizar_turma(self, **kwargs: Any) -> dict[str, object]:
        return {"id": kwargs["turma_id"], "materia": kwargs["materia"]}

    def excluir_turma(self, **_kwargs: Any) -> None:
        return None

    def listar_alunos_turma(
        self, _ator: Any, _turma_id: int
    ) -> list[dict[str, object]]:
        return [{"aluno_id": 11, "matricula": "SINT-11", "nome": "Pessoa sintética"}]

    def vincular_aluno(self, **kwargs: Any) -> dict[str, object]:
        return {"aluno_id": 11, "matricula": kwargs["matricula"], "vinculado": True}

    def desvincular_aluno(self, **_kwargs: Any) -> None:
        return None

    def excluir_aluno_global(self, **_kwargs: Any) -> dict[str, object]:
        return {
            "caminhos_referencias": (),
            "caminho_legado": "foto-legada-sintetica.jpg",
            "jobs_temporarios": (),
        }

    def listar_revisoes(
        self, _ator: Any, _turma_id: int, **_kwargs: Any
    ) -> list[dict[str, object]]:
        return [{"id": "revisao-sintetica", "estado": "aberta"}]

    def decidir_revisao(self, **kwargs: Any) -> Presenca:
        instante = kwargs["agora"]
        return Presenca(
            id=51,
            aluno_id=11,
            turma_id=7,
            sessao_id=4,
            status=StatusPresenca(kwargs["decisao"]),
            origem=OrigemPresenca.MANUAL,
            registrado_em=instante,
            data_referencia=instante.date(),
            horario_evidencia=None,
            corrigida_em=instante,
            corrigida_por_conta_id=10,
            versao=1,
        )

    def consultar_painel(
        self, _ator: Any, turma_id: int, **_kwargs: Any
    ) -> dict[str, object]:
        return {"turma_id": turma_id, "atualizado_em": AGORA.isoformat(), "sessoes": []}

    def listar_presencas_sessao(
        self, _ator: Any, turma_id: int, sessao_id: int
    ) -> list[dict[str, object]]:
        assert (turma_id, sessao_id) == (7, 21)
        return [
            {
                "nome": "Pessoa de teste",
                "matricula": "SINT-11",
                "status": "presente",
                "origem": "biometrica",
                "registrado_em": AGORA.isoformat(),
            }
        ]

    def reativar_quota(self, **_kwargs: Any) -> int:
        return 6

    def solicitar_revisao(self, **kwargs: Any) -> RevisaoPresenca:
        assert kwargs["matricula"] == "SINT-11"
        assert kwargs["via_acessivel"] is True
        return RevisaoPresenca(
            id=UUID("00000000-0000-0000-0000-000000000016"),
            turma_id=7,
            sessao_id=4,
            aluno_id=11,
            matricula=None,
            nome=None,
            estado="aberta",
            justificativa_solicitacao="Pedido sintético.",
            via_acessivel=True,
            solicitada_em=AGORA,
            versao_presenca_base=0,
        )

    def listar_turmas(self, _ator: Any) -> list[dict[str, object]]:
        return [
            {
                "id": 7,
                "materia": "Inteligência Artificial",
                "periodo": "diurno",
                "responsavel_professor_id": 3,
                "ativa": True,
            }
        ]

    def listar_presencas_exportacao(
        self,
        _ator: Any,
        *,
        turma_id: int,
        inicio: dt.date | None = None,
        fim: dt.date | None = None,
        sessao_id: int | None = None,
    ) -> list[dict[str, object]]:
        assert turma_id == 7
        if sessao_id is None:
            assert inicio is not None and fim is not None
            assert inicio <= dt.date(2026, 10, 18) <= fim
        else:
            assert (inicio, fim, sessao_id) == (None, None, 4)
        return [
            {
                "turma_id": 7,
                "materia": "Ciência, IA",
                "periodo": "diurno",
                "sessao_id": 4,
                "data_referencia": dt.date(2026, 10, 18),
                "horario_evidencia": AGORA,
                "horario_correcao": None,
                "matricula": "00042",
                "nome": '=HYPERLINK("https://example.invalid","João, aluno")',
                "status": "presente",
                "origem": "biometrica",
                "corrigida_em": None,
            }
        ]


class _RepositorioLinks:
    def __init__(self) -> None:
        self.hash_token: str | None = None

    def contexto_credencial(
        self, hash_token: str, *, agora: dt.datetime, exigir_link_ativo: bool
    ) -> dict[str, object]:
        assert agora == AGORA
        assert exigir_link_ativo is True
        self.hash_token = hash_token
        return {
            "finalidade": "presenca",
            "sessao_id": 4,
            "turma_id": 7,
            "link_id": UUID("00000000-0000-0000-0000-000000000014"),
        }


class _Limitador:
    def limitar_requisicao(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _RemovedorLegado:
    def __init__(self) -> None:
        self.removidos: list[str] = []

    def remover(self, caminho: str) -> None:
        self.removidos.append(caminho)


@pytest.mark.parametrize(
    "caminho",
    [
        "/api/v1/turmas",
        "/api/v1/turmas/7/painel",
        "/api/v1/turmas/7/sessoes/21/presencas",
        "/api/v1/turmas/7/revisoes",
        "/api/v1/turmas/7/presencas.csv?inicio=2026-10-01&fim=2026-10-31",
        "/api/v1/turmas/7/sessoes/4/presencas.csv",
    ],
)
def test_rotas_de_gestao_exigem_sessao_autenticada(caminho: str) -> None:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@test-db:5432/face_task016_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
    )
    app = create_app(settings, WebServices(auth_repository=_RepositorioAuth()))

    with TestClient(app) as client:
        response = client.get(caminho)

    assert response.status_code == 401


def test_listagem_de_turmas_usa_sessao_e_retorna_somente_campos_de_gestao() -> None:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@test-db:5432/face_task016_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
    )
    services = WebServices(auth_repository=_RepositorioAuth())
    object.__setattr__(services, "gestao_repository", _RepositorioGestao())
    app = create_app(settings, services)

    with TestClient(app, base_url="https://facediff.test") as client:
        client.cookies.set("facediff_session", "sessao-professor")
        response = client.get("/api/v1/turmas")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 7,
            "materia": "Inteligência Artificial",
            "periodo": "diurno",
            "responsavel_professor_id": 3,
            "ativa": True,
        }
    ]
    assert "embedding" not in response.text


def test_csv_escapa_formulas_e_preserva_unicode_e_virgulas() -> None:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@test-db:5432/face_task016_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
    )
    services = WebServices(auth_repository=_RepositorioAuth())
    object.__setattr__(services, "gestao_repository", _RepositorioGestao())
    app = create_app(settings, services)

    with TestClient(app, base_url="https://facediff.test") as client:
        client.cookies.set("facediff_session", "sessao-professor")
        response = client.get(
            "/api/v1/turmas/7/presencas.csv?inicio=2026-10-18&fim=2026-10-18"
        )

    rows = list(csv.DictReader(StringIO(response.content.decode("utf-8"))))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv; charset=utf-8")
    assert rows[0]["nome"] == '\'=HYPERLINK("https://example.invalid","João, aluno")'
    assert rows[0]["materia"] == "Ciência, IA"
    assert rows[0]["matricula"] == "00042"


def test_csv_da_sessao_baixa_so_a_sessao_escolhida() -> None:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@test-db:5432/face_task016_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
    )
    services = WebServices(auth_repository=_RepositorioAuth())
    object.__setattr__(services, "gestao_repository", _RepositorioGestao())
    app = create_app(settings, services)

    with TestClient(app, base_url="https://facediff.test") as client:
        client.cookies.set("facediff_session", "sessao-professor")
        response = client.get("/api/v1/turmas/7/sessoes/4/presencas.csv")

    rows = list(csv.DictReader(StringIO(response.content.decode("utf-8"))))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv; charset=utf-8")
    assert response.headers["content-disposition"] == (
        'attachment; filename="presencas-turma-7-sessao-4.csv"'
    )
    assert [row["sessao_id"] for row in rows] == ["4"]


def test_pedido_publico_de_revisao_nao_revela_dados_do_aluno() -> None:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@test-db:5432/face_task016_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
    )
    links = _RepositorioLinks()
    services = WebServices(
        auth_repository=_RepositorioAuth(),
        link_repository=links,
        presenca_repository=_Limitador(),
        rate_limit_secret=b"segredo-sintetico",
        clock=lambda: AGORA,
    )
    object.__setattr__(services, "gestao_repository", _RepositorioGestao())
    app = create_app(settings, services)

    with TestClient(app, base_url="https://facediff.test") as client:
        response = client.post(
            "/api/v1/revisoes",
            headers={"Authorization": "Bearer token-sintetico"},
            json={
                "sessao_id": 4,
                "matricula": "SINT-11",
                "justificativa": "Pedido de acessibilidade.",
                "via_acessivel": True,
            },
        )

    assert response.status_code == 202
    assert response.json() == {
        "protocolo": "00000000-0000-0000-0000-000000000016",
        "estado": "aberta",
    }
    assert "SINT-11" not in response.text
    assert "Pessoa de teste" not in response.text
    assert links.hash_token is not None
    assert links.hash_token != "token-sintetico"


class _LimitadorRegistrando:
    def __init__(self) -> None:
        self.chaves: list[str] = []

    def limitar_requisicao(self, chave_hash: str, *_args: Any, **_kwargs: Any) -> None:
        self.chaves.append(chave_hash)


def test_pedido_de_revisao_limita_pelo_ip_real_atras_do_proxy() -> None:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@test-db:5432/face_task016_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
        trusted_proxy_cidrs="127.0.0.1/32",
    )
    limitador = _LimitadorRegistrando()
    services = WebServices(
        auth_repository=_RepositorioAuth(),
        link_repository=_RepositorioLinks(),
        presenca_repository=limitador,
        rate_limit_secret=b"segredo-sintetico",
        clock=lambda: AGORA,
    )
    object.__setattr__(services, "gestao_repository", _RepositorioGestao())
    corpo = {
        "sessao_id": 4,
        "matricula": "SINT-11",
        "justificativa": "Pedido de acessibilidade.",
        "via_acessivel": True,
    }

    # Atrás do Caddy o peer é sempre o proxy; o limite precisa usar o IP do aluno.
    with TestClient(
        create_app(settings, services),
        base_url="https://facediff.test",
        client=("127.0.0.1", 43000),
    ) as client:
        for ip_aluno in ("203.0.113.1", "203.0.113.2"):
            resposta = client.post(
                "/api/v1/revisoes",
                headers={
                    "Authorization": "Bearer token-sintetico",
                    "X-Forwarded-For": ip_aluno,
                },
                json=corpo,
            )
            assert resposta.status_code == 202

    assert len(limitador.chaves) == 2
    assert limitador.chaves[0] != limitador.chaves[1]


def test_decisao_manual_exige_confirmacao_explicita_de_identidade() -> None:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@test-db:5432/face_task016_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
    )
    services = WebServices(auth_repository=_RepositorioAuth())
    object.__setattr__(services, "gestao_repository", _RepositorioGestao())
    app = create_app(settings, services)

    with TestClient(app, base_url="https://facediff.test") as client:
        client.cookies.set("facediff_session", "sessao-professor")
        response = client.post(
            "/api/v1/revisoes/00000000-0000-0000-0000-000000000016/decidir",
            headers={
                "Origin": "https://facediff.test",
                "X-CSRF-Token": "csrf",
            },
            json={
                "decisao": "presente",
                "justificativa": "Verificação independente.",
                "versao_esperada": 0,
            },
        )

    assert response.status_code == 422


def test_rotas_de_gestao_executam_crud_revisao_painel_csv_e_acoes_admin() -> None:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@test-db:5432/face_task016_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
    )
    services = WebServices(auth_repository=_RepositorioAuth())
    object.__setattr__(services, "gestao_repository", _RepositorioGestao())
    removedor = _RemovedorLegado()
    object.__setattr__(services, "legacy_image_storage", removedor)
    app = create_app(settings, services)
    headers = {"Origin": "https://facediff.test", "X-CSRF-Token": "csrf"}

    with TestClient(app, base_url="https://facediff.test") as client:
        client.cookies.set("facediff_session", "sessao-professor")
        response_turma = client.get("/api/v1/turmas/7")
        assert response_turma.status_code == 200, response_turma.text
        criada = client.post(
            "/api/v1/turmas",
            headers=headers,
            json={"materia": "IA", "periodo": "diurno"},
        )
        assert criada.status_code == 201
        assert (
            client.patch(
                "/api/v1/turmas/7",
                headers=headers,
                json={"materia": "Visão computacional"},
            ).status_code
            == 200
        )
        assert (
            client.patch(
                "/api/v1/turmas/7",
                headers=headers,
                json={"responsavel_professor_id": None},
            ).status_code
            == 422
        )
        assert client.get("/api/v1/turmas/7/alunos").status_code == 200
        assert (
            client.post(
                "/api/v1/turmas/7/alunos",
                headers=headers,
                json={"matricula": "SINT-11"},
            ).status_code
            == 201
        )
        assert (
            client.request(
                "DELETE",
                "/api/v1/turmas/7/alunos/11",
                headers=headers,
                json={"justificativa": "Desvínculo sintético."},
            ).status_code
            == 204
        )
        assert (
            client.request(
                "DELETE",
                "/api/v1/turmas/7",
                headers=headers,
                json={"justificativa": "Encerramento sintético."},
            ).status_code
            == 204
        )
        assert client.get("/api/v1/turmas/7/painel").status_code == 200
        presentes = client.get("/api/v1/turmas/7/sessoes/21/presencas")
        assert presentes.status_code == 200
        assert presentes.json() == {
            "sessao_id": 21,
            "presencas": [
                {
                    "nome": "Pessoa de teste",
                    "matricula": "SINT-11",
                    "status": "presente",
                    "origem": "biometrica",
                    "registrado_em": AGORA.isoformat(),
                }
            ],
        }
        assert presentes.headers["cache-control"] == "no-store"
        assert client.get("/api/v1/turmas/7/revisoes").status_code == 200
        decidir = client.post(
            "/api/v1/revisoes/00000000-0000-0000-0000-000000000016/decidir",
            headers=headers,
            json={
                "decisao": "presente",
                "justificativa": "Conferência física independente.",
                "versao_esperada": 0,
                "identidade_confirmada": True,
            },
        )
        assert decidir.status_code == 200
        csv_response = client.get("/api/v1/turmas/7/presencas.csv?mes=2026-10")
        assert csv_response.status_code == 200

        client.cookies.set("facediff_session", "sessao-admin")
        headers_admin = {
            "Origin": "https://facediff.test",
            "X-CSRF-Token": "csrf-admin",
        }
        exclusao = client.request(
            "DELETE",
            "/api/v1/alunos/11",
            headers=headers_admin,
            json={
                "confirmacao": "EXCLUIR-ALUNO-11",
                "justificativa": "Exclusão autorizada sintética.",
            },
        )
        assert exclusao.status_code == 202
        assert exclusao.json() == {"excluido": True, "limpeza_pendente": False}
        assert removedor.removidos == ["foto-legada-sintetica.jpg"]
        quota = client.post(
            "/api/v1/turmas/7/sessoes/4/alunos/11/reativar-quota",
            headers=headers_admin,
            json={"confirmar": True, "justificativa": "Quota autorizada."},
        )
        assert quota.status_code == 200
        assert quota.json()["limite_tentativas"] == 6
