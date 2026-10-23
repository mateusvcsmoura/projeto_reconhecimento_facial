from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from src.application.services.fila_facial import (
    ArquivoTemporario,
    ManifestoTemporario,
    ReservaFacial,
    TipoJobFacial,
)
from src.config.web_settings import WebSettings
from src.domain.entities.solicitacao_cadastro import (
    ResultadoAprovacao,
    SolicitacaoCadastro,
)
from src.infrastructure.repositories.postgres_conta_repository import (
    COOKIE_SESSAO,
    ContaAutenticada,
)
from src.presentation.web.app import WebServices, create_app

ORIGEM = "https://cadastro.example.test"
SEGREDO = "chave-sintetica-de-teste-com-mais-de-trinta-e-dois-bytes"
AGORA = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)
FIM = AGORA + timedelta(days=10)


class AuthFake:
    def autenticar_sessao(self, token: str | None) -> ContaAutenticada | None:
        if token != "sessao-professor":
            return None
        return ContaAutenticada(4, "professor", True, False, 3, 8, "", "csrf-fake")

    def validar_csrf(self, _conta: ContaAutenticada, token: str | None) -> bool:
        return token == "csrf-fake"

    def autorizar_turma(self, turma_id: int) -> Any:
        from src.infrastructure.repositories.postgres_conta_repository import TurmaWeb

        return TurmaWeb(turma_id, "IA", "noturno", 3)


class AuthProfessorAlheio(AuthFake):
    def autenticar_sessao(self, token: str | None) -> ContaAutenticada | None:
        if token != "sessao-professor-alheio":
            return None
        return ContaAutenticada(9, "professor", True, False, 99, 10, "", "csrf-fake")


class ReferenceStorageFake:
    def __init__(self) -> None:
        self.removidos: list[str] = []

    def remover(self, _caminho: str) -> None:
        self.removidos.append(_caminho)


class ApiFake:
    def __init__(self) -> None:
        self.link_id = UUID("8fc0c272-c303-4e7f-83f5-302aee20c591")
        self.token_hash: str | None = None
        self.access_hash: str | None = None
        self.update_hash: str | None = None
        self.link_expira = AGORA + timedelta(days=7)
        self.link_revogado = False
        self.requests: dict[int, SolicitacaoCadastro] = {}
        self.created: list[dict[str, object]] = []
        self.associated: list[UUID] = []
        self.challenge_hash: str | None = None
        self.approvals: list[tuple[int, str, str]] = []
        self.rejections: list[tuple[int, str]] = []
        self.list_calls = 0
        self.revogacoes: list[UUID] = []
        self.limpezas_confirmadas: list[int] = []

    def criar_link(self, **kwargs: object) -> UUID:
        self.token_hash = str(kwargs["token_hash"])
        self.link_expira = kwargs["expira_em"]  # type: ignore[assignment]
        return self.link_id

    def revogar(
        self, _ator: object, link_id: UUID, **_kwargs: object
    ) -> tuple[int, tuple[int, ...]]:
        self.revogacoes.append(link_id)
        self.link_revogado = True
        return 2, (71, 72)

    def trocar_token(self, **kwargs: object) -> dict[str, object] | None:
        if self.link_revogado or kwargs["token_hash"] != self.token_hash:
            return None
        self.access_hash = str(kwargs["credencial_hash"])
        return {
            "link_id": self.link_id,
            "turma_id": 14,
            "finalidade": "cadastro",
            "finalidade_ate": FIM,
            "credencial_expira_em": kwargs["credencial_expira_em"],
        }

    def contexto_credencial(
        self,
        credencial_hash: str,
        *,
        agora: datetime,
        solicitacao_id: int | None = None,
        exigir_link_ativo: bool = True,
    ) -> dict[str, object] | None:
        update = credencial_hash == self.update_hash
        if self.link_revogado or (credencial_hash != self.access_hash and not update):
            return None
        if update:
            if solicitacao_id != 72:
                return None
            return {
                "link_id": None,
                "turma_id": 14,
                "finalidade": "atualizacao",
                "finalidade_ate": FIM,
                "expira_em": FIM,
            }
        if solicitacao_id is not None and solicitacao_id not in self.requests:
            return None
        return {
            "link_id": self.link_id,
            "turma_id": 14,
            "finalidade": "cadastro",
            "finalidade_ate": FIM,
            "expira_em": self.link_expira,
        }

    def criar_cadastro(self, **kwargs: object) -> SolicitacaoCadastro:
        self.created.append(kwargs)
        self.challenge_hash = str(kwargs["desafio_nonce_hash"])
        solicitacao = SolicitacaoCadastro(
            id=71,
            tipo="cadastro",
            estado="em_coleta",
            turma_id=14,
            aluno_id=None,
            matricula=str(kwargs["matricula"]),
            nome=str(kwargs["nome"]),
            expira_em=kwargs["expira_em"],  # type: ignore[arg-type]
            consentimento_em=kwargs["consentimento_em"],  # type: ignore[arg-type]
            consentimento_versao=str(kwargs["consentimento_versao"]),
            desafio_nonce_hash=self.challenge_hash,
            desafio_direcao=str(kwargs["desafio_direcao"]),
            desafio_expira_em=kwargs["desafio_expira_em"],  # type: ignore[arg-type]
        )
        self.requests[71] = solicitacao
        return solicitacao

    def obter_solicitacao(self, solicitacao_id: int) -> SolicitacaoCadastro:
        return self.requests[solicitacao_id]

    def validar_credencial_solicitacao(
        self, credencial_hash: str, solicitacao_id: int, *, agora: datetime
    ) -> bool:
        return (
            credencial_hash == self.access_hash
            and solicitacao_id in self.requests
            and not self.link_revogado
        )

    def associar_job_cadastro(
        self,
        solicitacao_id: int,
        job_id: UUID,
        _credencial_hash: str,
        *,
        agora: datetime,
    ) -> None:
        self.associated.append(job_id)
        current = self.requests[solicitacao_id]
        self.requests[solicitacao_id] = replace(current, estado="em_validacao")

    def solicitar_atualizacao_biometrica(
        self, _ator: object, aluno_id: int, turma_id: int, **kwargs: object
    ) -> SolicitacaoCadastro:
        self.update_hash = str(kwargs["credencial_captura_hash"])
        solicitacao = SolicitacaoCadastro(
            id=72,
            tipo="atualizacao",
            estado="em_coleta",
            turma_id=turma_id,
            aluno_id=aluno_id,
            matricula=None,
            nome=None,
            expira_em=kwargs["expira_em"],  # type: ignore[arg-type]
            consentimento_em=None,
            consentimento_versao=None,
        )
        self.requests[72] = solicitacao
        return solicitacao

    def registrar_consentimento_atualizacao(
        self,
        solicitacao_id: int,
        credencial_hash: str,
        versao: str,
        **kwargs: object,
    ) -> SolicitacaoCadastro:
        assert credencial_hash == self.update_hash
        solicitacao = replace(
            self.requests[solicitacao_id],
            consentimento_em=kwargs["agora"],  # type: ignore[arg-type]
            consentimento_versao=versao,
            desafio_nonce_hash=str(kwargs["desafio_nonce_hash"]),
            desafio_direcao=str(kwargs["desafio_direcao"]),
            desafio_expira_em=kwargs["desafio_expira_em"],  # type: ignore[arg-type]
        )
        self.requests[solicitacao_id] = solicitacao
        return solicitacao

    def renovar_desafio_coleta(
        self, solicitacao_id: int, **kwargs: object
    ) -> SolicitacaoCadastro:
        atual = self.requests[solicitacao_id]
        if atual.estado != "em_coleta":
            raise ValueError("A coleta não está disponível.")
        solicitacao = replace(
            atual,
            desafio_nonce_hash=str(kwargs["desafio_nonce_hash"]),
            desafio_direcao=str(kwargs["desafio_direcao"]),
            desafio_expira_em=kwargs["desafio_expira_em"],  # type: ignore[arg-type]
        )
        self.requests[solicitacao_id] = solicitacao
        return solicitacao

    def listar_cadastros_turma(
        self, _ator: object, _turma_id: int, *, estado: str, limite: int
    ) -> tuple[SolicitacaoCadastro, ...]:
        self.list_calls += 1
        return tuple(item for item in self.requests.values() if item.estado == estado)[
            :limite
        ]

    def aprovar_cadastro(
        self,
        _ator: object,
        solicitacao_id: int,
        *,
        metodo_identidade: str,
        justificativa: str,
        agora: datetime,
    ) -> ResultadoAprovacao:
        assert self.requests[solicitacao_id].estado == "pendente_aprovacao"
        self.approvals.append((solicitacao_id, metodo_identidade, justificativa))
        return ResultadoAprovacao(29, 14, aluno_existente=True)

    def rejeitar_cadastro_web(
        self,
        _ator: object,
        solicitacao_id: int,
        *,
        justificativa: str,
        agora: datetime,
    ) -> None:
        self.rejections.append((solicitacao_id, justificativa))

    def limpar_arquivos_provisorios(self, solicitacao_id: int) -> tuple[str, ...]:
        return (f"{solicitacao_id}/recorte.bin",)

    def confirmar_limpeza_provisoria(
        self, _solicitacao_id: int, *, agora: datetime
    ) -> None:
        self.limpezas_confirmadas.append(_solicitacao_id)


class QueueFake:
    def __init__(self) -> None:
        self.reservation: ReservaFacial | None = None
        self.submitted: list[UUID] = []

    def reservar(
        self,
        tipo: TipoJobFacial,
        dono_id: str,
        idempotencia: str,
        prazo: datetime,
    ) -> ReservaFacial:
        assert tipo is TipoJobFacial.CADASTRO
        assert dono_id in {"71", "72"}
        self.reservation = ReservaFacial(
            UUID("4b86cd66-a65a-47d0-8ce7-cac105613726"), "job-secret", prazo
        )
        return self.reservation

    def submeter(self, job_id: UUID, manifesto: ManifestoTemporario) -> object:
        assert self.reservation is not None
        assert manifesto.job_id == job_id
        self.submitted.append(job_id)
        return object()

    def cancelar(self, _job_id: UUID, _credential: str) -> bool:
        return True


class CaptureStorageFake:
    def __init__(self) -> None:
        self.files: dict[int, bytes] = {}

    def salvar_captura(self, _job_id: UUID, ordinal: int, conteudo: bytes) -> None:
        self.files[ordinal] = conteudo

    def manifesto(self, job_id: UUID) -> ManifestoTemporario:
        return ManifestoTemporario(
            job_id,
            tuple(
                ArquivoTemporario(i, f"captura-{i}.bin", len(data))
                for i, data in sorted(self.files.items())
            ),
        )

    def remover_job(self, _job_id: UUID) -> None:
        self.files.clear()


def _settings() -> WebSettings:
    return WebSettings(
        environment="test",
        database_url="postgresql+psycopg://user:password@test-db:5432/face_test_task014",
        secret_key=SEGREDO,
        retention_days=14,
        public_origin=ORIGEM,
        database_disposable=True,
        purpose_end_at=FIM,
        consent_notice_version="v1-2026-10-18",
    )


def _client(
    repository: ApiFake,
    auth_repository: AuthFake | None = None,
    *,
    settings: WebSettings | None = None,
    include_reference_storage: bool = True,
) -> TestClient:
    queue = QueueFake()
    storage = CaptureStorageFake()
    reference_storage = ReferenceStorageFake() if include_reference_storage else None
    repository.queue_fake = queue  # type: ignore[attr-defined]
    repository.storage_fake = storage  # type: ignore[attr-defined]
    repository.reference_storage_fake = reference_storage  # type: ignore[attr-defined]
    services = WebServices(
        auth_repository=auth_repository or AuthFake(),  # type: ignore[arg-type]
        reference_storage=reference_storage,  # type: ignore[arg-type]
        link_repository=repository,
        solicitacao_repository=repository,
        fila_facial=queue,  # type: ignore[arg-type]
        capture_storage=storage,  # type: ignore[arg-type]
        clock=lambda: AGORA,
    )
    return TestClient(create_app(settings or _settings(), services), base_url=ORIGEM)


def test_fluxo_http_cria_link_credencial_e_solicitacao_com_consentimento() -> None:
    repository = ApiFake()
    headers = {
        "Origin": ORIGEM,
        "X-CSRF-Token": "csrf-fake",
    }
    with _client(repository) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor")
        aviso = client.get("/api/v1/avisos/biometria")
        link = client.post("/api/v1/turmas/14/links-cadastro", headers=headers)
        assert link.status_code == 201, link.text
        acesso = client.post(
            "/api/v1/acessos-link", json={"token": link.json()["token"]}
        )
        assert acesso.status_code == 200, acesso.text
        assert (
            repository.access_hash
            == hashlib.sha256(acesso.json()["credencial"].encode()).hexdigest()
        )
        cadastro = client.post(
            "/api/v1/cadastros",
            headers={"Authorization": f"Bearer {acesso.json()['credencial']}"},
            json={
                "nome": "Pessoa Sintética",
                "matricula": "000123",
                "aviso_versao": "v1-2026-10-18",
                "consentimento": True,
            },
        )
        status = client.get(
            "/api/v1/cadastros/71",
            headers={"Authorization": f"Bearer {acesso.json()['credencial']}"},
        )

    assert repository.created
    assert aviso.status_code == 200
    assert aviso.json()["versao"] == "v1-2026-10-18"
    assert link.status_code == 201
    assert acesso.status_code == 200
    assert acesso.json()["finalidade"] == "cadastro"
    assert acesso.json()["finalidade_ate"] == FIM.isoformat()
    assert cadastro.status_code == 201, cadastro.text
    assert cadastro.json()["estado"] == "em_coleta"
    assert cadastro.json()["desafio"]["primeira_orientacao"] == "frente"
    assert cadastro.json()["desafio"]["sequencia"][2] == "frente"
    assert len(cadastro.json()["desafio"]["nonce"]) >= 40
    assert status.status_code == 200
    assert "embedding" not in status.text
    assert "caminho_privado" not in status.text
    assert "aluno_existente" not in status.text
    assert repository.created[0]["consentimento_versao"] == "v1-2026-10-18"
    assert (
        repository.created[0]["credencial_acesso_hash"]
        == hashlib.sha256(acesso.json()["credencial"].encode()).hexdigest()
    )
    assert status.headers["cache-control"] == "no-store"


def test_recusa_de_consentimento_nao_cria_solicitacao() -> None:
    repository = ApiFake()
    with _client(repository) as client:
        link = client.post(
            "/api/v1/turmas/14/links-cadastro",
            headers={
                "Origin": ORIGEM,
                "X-CSRF-Token": "csrf-fake",
                "Cookie": f"{COOKIE_SESSAO}=sessao-professor",
            },
        )
        assert link.status_code == 201, link.text
        acesso = client.post(
            "/api/v1/acessos-link", json={"token": link.json()["token"]}
        )
        resposta = client.post(
            "/api/v1/cadastros",
            headers={"Authorization": f"Bearer {acesso.json()['credencial']}"},
            json={
                "nome": "Pessoa Sintética",
                "matricula": "000123",
                "aviso_versao": "v1-2026-10-18",
                "consentimento": False,
            },
        )

    assert resposta.status_code == 422
    assert not repository.created


def test_credencial_nao_consulta_outra_solicitacao() -> None:
    with _client(ApiFake()) as client:
        resposta = client.get(
            "/api/v1/cadastros/71",
            headers={"Authorization": "Bearer credencial-inexistente"},
        )

    assert resposta.status_code == 404
    assert resposta.json()["codigo"] == "recurso_nao_encontrado"
    assert resposta.headers["cache-control"] == "no-store"


def test_capturas_exigem_tres_arquivos_e_reservam_fila_so_apos_consentimento() -> None:
    repository = ApiFake()
    with _client(repository) as client:
        link = client.post(
            "/api/v1/turmas/14/links-cadastro",
            headers={
                "Origin": ORIGEM,
                "X-CSRF-Token": "csrf-fake",
                "Cookie": f"{COOKIE_SESSAO}=sessao-professor",
            },
        )
        access = client.post(
            "/api/v1/acessos-link", json={"token": link.json()["token"]}
        )
        credential = access.json()["credencial"]
        headers = {"Authorization": f"Bearer {credential}"}
        cadastro = client.post(
            "/api/v1/cadastros",
            headers=headers,
            json={
                "nome": "Pessoa Sintética",
                "matricula": "000123",
                "aviso_versao": "v1-2026-10-18",
                "consentimento": True,
            },
        )
        incompletas = client.post(
            "/api/v1/cadastros/71/capturas",
            headers=headers,
            json={
                "nonce": cadastro.json()["desafio"]["nonce"],
                "capturas": [base64.b64encode(b"um").decode()] * 2,
            },
        )
        completas = client.post(
            "/api/v1/cadastros/71/capturas",
            headers=headers,
            json={
                "nonce": cadastro.json()["desafio"]["nonce"],
                "capturas": [
                    base64.b64encode(conteudo).decode()
                    for conteudo in (b"um", b"dois", b"tres")
                ],
            },
        )

    assert incompletas.status_code == 422
    assert completas.status_code == 202
    assert len(repository.associated) == 1
    assert len(repository.queue_fake.submitted) == 1  # type: ignore[attr-defined]
    assert repository.storage_fake.files == {  # type: ignore[attr-defined]
        1: b"um",
        2: b"dois",
        3: b"tres",
    }


def test_nonce_incorreto_nao_reserva_fila_nem_grava_capturas() -> None:
    repository = ApiFake()
    with _client(repository) as client:
        link = client.post(
            "/api/v1/turmas/14/links-cadastro",
            headers={
                "Origin": ORIGEM,
                "X-CSRF-Token": "csrf-fake",
                "Cookie": f"{COOKIE_SESSAO}=sessao-professor",
            },
        )
        access = client.post(
            "/api/v1/acessos-link", json={"token": link.json()["token"]}
        )
        credential = access.json()["credencial"]
        headers = {"Authorization": f"Bearer {credential}"}
        client.post(
            "/api/v1/cadastros",
            headers=headers,
            json={
                "nome": "Pessoa Sintética",
                "matricula": "000123",
                "aviso_versao": "v1-2026-10-18",
                "consentimento": True,
            },
        )

        resposta = client.post(
            "/api/v1/cadastros/71/capturas",
            headers=headers,
            json={
                "nonce": "nonce-invalido-longo-para-validacao-do-protocolo",
                "capturas": [
                    base64.b64encode(conteudo).decode()
                    for conteudo in (b"um", b"dois", b"tres")
                ],
            },
        )

    assert resposta.status_code == 409
    assert not repository.associated
    assert not repository.queue_fake.submitted  # type: ignore[attr-defined]
    assert not repository.storage_fake.files  # type: ignore[attr-defined]


def _iniciar_coleta(client: TestClient) -> tuple[dict[str, str], dict[str, Any]]:
    link = client.post(
        "/api/v1/turmas/14/links-cadastro",
        headers={
            "Origin": ORIGEM,
            "X-CSRF-Token": "csrf-fake",
            "Cookie": f"{COOKIE_SESSAO}=sessao-professor",
        },
    )
    access = client.post("/api/v1/acessos-link", json={"token": link.json()["token"]})
    headers = {"Authorization": f"Bearer {access.json()['credencial']}"}
    cadastro = client.post(
        "/api/v1/cadastros",
        headers=headers,
        json={
            "nome": "Pessoa Sintética",
            "matricula": "000123",
            "aviso_versao": "v1-2026-10-18",
            "consentimento": True,
        },
    )
    return headers, cadastro.json()["desafio"]


def _capturas(nonce: str) -> dict[str, object]:
    return {
        "nonce": nonce,
        "capturas": [
            base64.b64encode(conteudo).decode()
            for conteudo in (b"um", b"dois", b"tres")
        ],
    }


def test_renovar_desafio_invalida_nonce_anterior_e_aceita_o_novo() -> None:
    repository = ApiFake()
    with _client(repository) as client:
        headers, anterior = _iniciar_coleta(client)
        renovado = client.post("/api/v1/cadastros/71/desafio", headers=headers)
        com_anterior = client.post(
            "/api/v1/cadastros/71/capturas",
            headers=headers,
            json=_capturas(anterior["nonce"]),
        )
        com_novo = client.post(
            "/api/v1/cadastros/71/capturas",
            headers=headers,
            json=_capturas(renovado.json()["desafio"]["nonce"]),
        )

    assert renovado.status_code == 200, renovado.text
    desafio = renovado.json()["desafio"]
    assert desafio["nonce"] != anterior["nonce"]
    assert desafio["sequencia"] == ["frente", desafio["direcao"], "frente"]
    assert desafio["expira_em"] == (AGORA + timedelta(seconds=120)).isoformat()
    assert com_anterior.status_code == 409
    assert com_novo.status_code == 202, com_novo.text


def test_renovar_desafio_recusa_coleta_ja_enviada_ou_credencial_alheia() -> None:
    repository = ApiFake()
    with _client(repository) as client:
        headers, desafio = _iniciar_coleta(client)
        alheia = client.post(
            "/api/v1/cadastros/71/desafio",
            headers={"Authorization": "Bearer credencial-inexistente"},
        )
        enviada = client.post(
            "/api/v1/cadastros/71/capturas",
            headers=headers,
            json=_capturas(desafio["nonce"]),
        )
        apos_envio = client.post("/api/v1/cadastros/71/desafio", headers=headers)

    assert alheia.status_code == 404
    assert enviada.status_code == 202, enviada.text
    assert apos_envio.status_code == 409


def test_atualizacao_so_emite_desafio_apos_consentimento() -> None:
    repository = ApiFake()
    csrf_headers = {
        "Origin": ORIGEM,
        "X-CSRF-Token": "csrf-fake",
        "Cookie": f"{COOKIE_SESSAO}=sessao-professor",
    }
    with _client(repository) as client:
        solicitacao = client.post(
            "/api/v1/solicitacoes-biometria",
            headers=csrf_headers,
            json={"turma_id": 14, "aluno_id": 29},
        )
        token = solicitacao.json()["credencial_captura"]
        headers = {"Authorization": f"Bearer {token}"}
        recusado = client.post(
            "/api/v1/cadastros/72/consentimento",
            headers=headers,
            json={"aviso_versao": "v1-2026-10-18", "consentimento": False},
        )
        assert solicitacao.status_code == 201, solicitacao.text
        assert recusado.status_code == 422
        assert repository.requests[72].consentimento_em is None
        assert repository.requests[72].desafio_nonce_hash is None

        aceite = client.post(
            "/api/v1/cadastros/72/consentimento",
            headers=headers,
            json={"aviso_versao": "v1-2026-10-18", "consentimento": True},
        )
        captura = client.post(
            "/api/v1/cadastros/72/capturas",
            headers=headers,
            json={
                "nonce": aceite.json()["desafio"]["nonce"],
                "capturas": [
                    base64.b64encode(conteudo).decode()
                    for conteudo in (b"um", b"dois", b"tres")
                ],
            },
        )

    assert aceite.status_code == 200, aceite.text
    assert aceite.json()["desafio"]["sequencia"][0] == "frente"
    assert aceite.json()["desafio"]["sequencia"][2] == "frente"
    assert repository.requests[72].consentimento_em == AGORA
    assert repository.requests[72].desafio_nonce_hash is not None
    assert captura.status_code == 202, captura.text


def test_professor_alheio_nao_consulta_solicitacoes_da_turma() -> None:
    repository = ApiFake()
    with _client(repository, AuthProfessorAlheio()) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor-alheio")
        response = client.get("/api/v1/turmas/14/cadastros")

    assert response.status_code == 404
    assert repository.list_calls == 0


def test_professor_responsavel_lista_solicitacoes_pendentes_sem_biometria() -> None:
    repository = ApiFake()
    repository.requests[71] = SolicitacaoCadastro(
        id=71,
        tipo="cadastro",
        estado="pendente_aprovacao",
        turma_id=14,
        aluno_id=None,
        matricula="000123",
        nome="Pessoa Sintetica",
        expira_em=FIM,
        consentimento_em=AGORA,
        consentimento_versao="v1",
    )
    with _client(repository) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor")
        response = client.get("/api/v1/turmas/14/cadastros")

    assert response.status_code == 200
    assert response.json()["itens"][0]["matricula"] == "000123"
    assert "embedding" not in response.text
    assert repository.list_calls == 1


def _pendente(repository: ApiFake) -> None:
    repository.requests[71] = SolicitacaoCadastro(
        id=71,
        tipo="cadastro",
        estado="pendente_aprovacao",
        turma_id=14,
        aluno_id=None,
        matricula="000123",
        nome="Pessoa Sintetica",
        expira_em=FIM,
        consentimento_em=AGORA,
        consentimento_versao="v1",
        criada_em=AGORA,
        link_criado_em=AGORA - timedelta(hours=2),
    )


def test_lista_de_cadastros_informa_quando_e_por_qual_link() -> None:
    repository = ApiFake()
    _pendente(repository)
    with _client(repository) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor")
        item = client.get("/api/v1/turmas/14/cadastros").json()["itens"][0]

    assert item["criada_em"] == AGORA.isoformat()
    assert item["link_criado_em"] == (AGORA - timedelta(hours=2)).isoformat()


def test_aprovar_e_recusar_sem_formulario_registram_conferencia_do_professor() -> None:
    repository = ApiFake()
    _pendente(repository)
    csrf = {"Origin": ORIGEM, "X-CSRF-Token": "csrf-fake"}
    with _client(repository) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor")
        aprovada = client.post("/api/v1/cadastros/71/aprovar", headers=csrf, json={})
        recusada = client.post("/api/v1/cadastros/71/rejeitar", headers=csrf, json={})

    assert aprovada.status_code == 200, aprovada.text
    assert repository.approvals == [
        (
            71,
            "conferencia_professor",
            "Nome e matrícula conferidos pelo professor responsável.",
        )
    ]
    assert recusada.status_code == 200, recusada.text
    assert repository.rejections == [
        (71, "Cadastro não aprovado pelo professor responsável.")
    ]


def test_revogacao_de_link_limpa_referencias_provisorias() -> None:
    repository = ApiFake()
    csrf = {"Origin": ORIGEM, "X-CSRF-Token": "csrf-fake"}
    with _client(repository) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor")
        response = client.post(
            f"/api/v1/links/{repository.link_id}/revogar", headers=csrf
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(repository.link_id),
        "revogado": True,
        "solicitacoes_canceladas": 2,
        "limpeza_pendente": False,
    }
    assert repository.revogacoes == [repository.link_id]
    assert repository.reference_storage_fake.removidos == [  # type: ignore[attr-defined]
        "71/recorte.bin",
        "72/recorte.bin",
    ]
    assert repository.limpezas_confirmadas == [71, 72]


def test_revogacao_informa_limpeza_pendente_sem_storage_privado() -> None:
    repository = ApiFake()
    with _client(repository, include_reference_storage=False) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor")
        response = client.post(
            f"/api/v1/links/{repository.link_id}/revogar",
            headers={"Origin": ORIGEM, "X-CSRF-Token": "csrf-fake"},
        )

    assert response.status_code == 200
    assert response.json()["limpeza_pendente"] is True


def test_link_nao_pode_ser_criado_sem_prazo_de_finalidade() -> None:
    settings = _settings().model_copy(update={"purpose_end_at": None})
    with _client(ApiFake(), settings=settings) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor")
        response = client.post(
            "/api/v1/turmas/14/links-cadastro",
            headers={"Origin": ORIGEM, "X-CSRF-Token": "csrf-fake"},
        )

    assert response.status_code == 503


def test_troca_de_link_com_token_invalido_e_recusada() -> None:
    with _client(ApiFake()) as client:
        response = client.post("/api/v1/acessos-link", json={"token": "x" * 43})

    assert response.status_code == 404


def test_api_de_link_informa_indisponibilidade_sem_repositorio() -> None:
    services = WebServices(link_repository=None)
    with TestClient(create_app(_settings(), services), base_url=ORIGEM) as client:
        response = client.post("/api/v1/acessos-link", json={"token": "t" * 43})

    assert response.status_code == 503


def test_aprovacao_http_delega_identidade_sem_revelar_biometria() -> None:
    repository = ApiFake()
    csrf_headers = {
        "Origin": ORIGEM,
        "X-CSRF-Token": "csrf-fake",
    }
    with _client(repository) as client:
        client.cookies.set(COOKIE_SESSAO, "sessao-professor")
        link = client.post("/api/v1/turmas/14/links-cadastro", headers=csrf_headers)
        access = client.post(
            "/api/v1/acessos-link", json={"token": link.json()["token"]}
        )
        cadastro = client.post(
            "/api/v1/cadastros",
            headers={"Authorization": f"Bearer {access.json()['credencial']}"},
            json={
                "nome": "Pessoa Sintética",
                "matricula": "000123",
                "aviso_versao": "v1-2026-10-18",
                "consentimento": True,
            },
        )
        repository.requests[71] = replace(
            repository.requests[71], estado="pendente_aprovacao"
        )
        resposta = client.post(
            "/api/v1/cadastros/71/aprovar",
            headers=csrf_headers,
            json={
                "metodo_identidade": "documento_presencial",
                "justificativa": "Documento conferido pelo professor responsável.",
            },
        )

    assert cadastro.status_code == 201
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"estado": "aprovada", "limpeza_pendente": False}
    assert repository.approvals == [
        (
            71,
            "documento_presencial",
            "Documento conferido pelo professor responsável.",
        )
    ]
