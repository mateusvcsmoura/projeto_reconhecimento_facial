from __future__ import annotations

import datetime as dt
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.application.services.fila_facial import (
    EstadoJobFacial,
    FilaCheia,
    ReservaFacial,
)
from src.config.web_settings import WebSettings
from src.domain.entities.sessao_presenca import SessaoPresenca
from src.domain.entities.tentativa_presenca import (
    EstadoTentativaPresenca,
    TentativaPresenca,
)
from src.domain.services.desafio_captura import (
    Desafio,
    DirecaoMovimento,
    EstadoDesafio,
    OrientacaoPose,
    ResultadoEtapaDesafio,
)
from src.infrastructure.repositories.postgres_conta_repository import ContaAutenticada
from src.infrastructure.repositories.postgres_presenca_web_repository import (
    CapturaRepetidaDiferente,
    TentativaAtiva,
)
from src.presentation.web.app import WebServices, create_app

AGORA = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.UTC)


def _app(services: WebServices | None = None, **ajustes: Any) -> TestClient:
    settings = WebSettings(
        environment="test",
        database_url="postgresql+psycopg://usuario:senha@localhost:5432/facediff_test",
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
        public_origin="https://facediff.test",
        **ajustes,
    )
    return TestClient(create_app(settings, services or WebServices()))


def _sessao() -> SessaoPresenca:
    return SessaoPresenca(
        id=7,
        turma_id=2,
        criada_por_conta_id=10,
        titulo="Aula de IA",
        inicio_em=AGORA - dt.timedelta(minutes=1),
        fim_em=AGORA + dt.timedelta(hours=1),
        criada_em=AGORA - dt.timedelta(minutes=2),
    )


def _conta() -> ContaAutenticada:
    return ContaAutenticada(10, "professor", True, False, 3, 20, "h" * 64, "csrf")


class _RepositorioPresenca:
    def __init__(self) -> None:
        self.tentativa: TentativaPresenca | None = None
        self.link_id = uuid4()
        self.limitadas: list[tuple[str, dt.datetime]] = []
        self.limites_usados: list[object] = []
        self.recebimentos: list[dict[str, object]] = []
        self.sessao_criada: SessaoPresenca | None = None
        self.erro_inicio: Exception | None = None
        self.erro_captura: Exception | None = None
        self.prazo_consulta: dt.datetime | None = None
        self.espera_rate_limit: int | None = None
        self.sessao_revogada = False
        self.arquivos_cancelados: tuple[UUID, ...] = ()

    def criar_sessao(self, _ator, sessao: SessaoPresenca) -> SessaoPresenca:
        self.sessao_criada = replace(sessao, id=7)
        return self.sessao_criada

    def obter_sessao_autorizada(self, _ator, _sessao_id: int) -> SessaoPresenca:
        sessao = self.sessao_criada or _sessao()
        return (
            replace(sessao, revogada_em=AGORA, revogada_por_conta_id=10)
            if self.sessao_revogada
            else sessao
        )

    def revogar_sessao(self, _ator, _sessao_id: int, *, agora):
        return len(self.arquivos_cancelados), self.arquivos_cancelados

    def editar_sessao(self, _ator, sessao_id: int, **kwargs):
        self.edicao = kwargs
        return replace(
            _sessao(),
            id=sessao_id,
            titulo=kwargs["titulo"],
            inicio_em=kwargs["inicio_em"],
            fim_em=kwargs["fim_em"],
            versao=2,
        )

    def excluir_sessao(self, _ator, _sessao_id: int, *, agora):
        return {
            "presencas": 1,
            "tentativas": 1,
            "revisoes": 0,
            "links": 1,
            "jobs_temporarios": self.arquivos_cancelados,
        }

    def limitar_requisicao(self, chave_hash: str, *, agora, **kwargs):
        self.limitadas.append((chave_hash, agora))
        self.limites_usados.append(kwargs.get("limite"))
        return self.espera_rate_limit

    def consultar_contexto_inicio(self, **_kwargs):
        return {
            "sessao": _sessao(),
            "aluno_id": 12,
            "conjunto_id": 14,
            "versao_referencia": 1,
        }

    def reservar_tentativa(self, **kwargs):
        if self.erro_inicio is not None:
            raise self.erro_inicio
        self.tentativa = TentativaPresenca(
            id=kwargs["job_id"],
            sessao_id=7,
            turma_id=2,
            aluno_id=12,
            ordinal=1,
            estado=EstadoTentativaPresenca.INICIADA,
            iniciada_em=kwargs["iniciada_em"],
            prazo_envio=kwargs["prazo_envio"],
            versao_sessao=1,
            conjunto_id=14,
            versao_referencia=1,
        )
        return self.tentativa, False

    def rejeitar_tentativa(self, *_args, **_kwargs) -> None:
        return None

    def consultar_tentativa(self, tentativa_id: UUID, _credencial_hash: str):
        if self.tentativa is None or self.tentativa.id != tentativa_id:
            return None
        if self.prazo_consulta is not None:
            self.tentativa = replace(self.tentativa, prazo_envio=self.prazo_consulta)
        return {
            "tentativa": self.tentativa,
            "link_id": self.link_id,
            "estado_job": EstadoJobFacial.RECEBIDA,
            "sessao": _sessao(),
            "recebimentos": len(self.recebimentos),
        }

    def registrar_captura(self, **kwargs) -> bool:
        if self.erro_captura is not None:
            raise self.erro_captura
        self.recebimentos.append(kwargs)
        if self.tentativa is not None:
            self.tentativa = replace(
                self.tentativa,
                estado=EstadoTentativaPresenca.RECEBIDA,
                recebida_em=kwargs["recebida_em"],
            )
        return True


class _RepositorioAuth:
    def autenticar_sessao(self, token):
        return _conta() if token == "sessao-sintetica" else None

    def validar_csrf(self, _conta, token):
        return token == "csrf-sintetico"


class _RepositorioLinks:
    def contexto_credencial(self, _hash, *, agora, exigir_link_ativo):
        return {
            "finalidade": "presenca",
            "sessao_id": 7,
            "link_id": uuid4(),
            "turma_id": 2,
            "expira_em": AGORA + dt.timedelta(hours=1),
            "finalidade_ate": AGORA + dt.timedelta(hours=1),
        }

    def criar_link(self, **_kwargs) -> UUID:
        return uuid4()


class _Fila:
    def __init__(self) -> None:
        self.reservas: list[tuple[object, ...]] = []
        self.submissoes: list[tuple[object, ...]] = []
        self.erro_reserva: Exception | None = None

    def reservar(self, tipo, dono, chave, prazo):
        if self.erro_reserva is not None:
            raise self.erro_reserva
        job_id = uuid4()
        self.reservas.append((tipo, dono, chave, prazo))
        return ReservaFacial(job_id, "credencial-captura-sintetica", prazo)

    def cancelar(self, *_args):
        return True

    def submeter(self, job_id, manifesto):
        self.submissoes.append((job_id, manifesto))


class _Desafios:
    def __init__(self) -> None:
        self.desafio = Desafio(
            id=uuid4(),
            nonce="n" * 64,
            direcao=DirecaoMovimento.DIREITA,
            primeira_orientacao=OrientacaoPose.FRENTE,
            expira_em=AGORA + dt.timedelta(minutes=2),
            proxima_etapa=1,
        )

    def emitir(self, contexto, _agora):
        self.desafio = replace(self.desafio, id=contexto.job_id)
        return self.desafio

    def registrar_etapa_recebida(self, job_id, _nonce, _etapa, _agora):
        return ResultadoEtapaDesafio(
            id=job_id,
            estado=EstadoDesafio.ETAPA_RECEBIDA,
            etapa_validada=0,
            proxima_etapa=None,
            proxima_orientacao=None,
            desafio_ok=False,
            motivo_tecnico=None,
        )

    def consultar(self, _contexto, _agora):
        return replace(self.desafio, proxima_etapa=2)


class _Capturas:
    def __init__(self) -> None:
        self.salvas: list[tuple[UUID, int, bytes]] = []

    def remover_captura(self, _job_id: UUID, _ordinal: int) -> None:
        return None

    def salvar_captura(self, job_id: UUID, ordinal: int, conteudo: bytes) -> None:
        self.salvas.append((job_id, ordinal, conteudo))

    def manifesto(self, job_id: UUID) -> tuple[UUID, str]:
        return job_id, "manifesto-sintetico"

    def remover_job(self, _job_id: UUID) -> None:
        return None


def test_openapi_publica_contratos_de_sessao_tentativa_e_status() -> None:
    with _app() as client:
        response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/turmas/{turma_id}/sessoes" in paths
    assert "/api/v1/sessoes/{sessao_id}/links" in paths
    assert "/api/v1/sessoes/{sessao_id}/revogar" in paths
    assert "/api/v1/sessoes/{sessao_id}/tentativas" in paths
    assert "/api/v1/tentativas/{tentativa_id}/capturas" in paths
    assert "/api/v1/tentativas/{tentativa_id}" in paths


def test_inicio_e_captura_recusam_horarios_fornecidos_pelo_cliente() -> None:
    with _app() as client:
        inicio = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={"Idempotency-Key": "chave-de-idempotencia-sintetica"},
            json={"matricula": "00042", "iniciada_em": "2026-10-18T12:00:00Z"},
        )
        captura = client.post(
            "/api/v1/tentativas/00000000-0000-0000-0000-000000000001/capturas",
            headers={"Authorization": "Bearer credencial-sintetica"},
            json={
                "etapa": 1,
                "nonce": "n" * 64,
                "captura_base64": "AA==",
                "recebida_em": "2026-10-18T12:00:00Z",
            },
        )

    assert inicio.status_code == 422
    assert captura.status_code == 422
    assert "requisicao_invalida" in inicio.json()["codigo"]
    assert "requisicao_invalida" in captura.json()["codigo"]


def test_rotas_autenticadas_criam_link_e_revogam_sessao() -> None:
    presencas = _RepositorioPresenca()
    services = WebServices(
        auth_repository=_RepositorioAuth(),
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        clock=lambda: AGORA,
        capture_storage=_Capturas(),
    )
    app = create_app(
        WebSettings(
            environment="test",
            database_url="postgresql+psycopg://usuario:senha@localhost:5432/facediff_test",
            secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
            retention_days=14,
            database_disposable=True,
            public_origin="https://facediff.test",
        ),
        services,
    )

    with TestClient(app) as client:
        client.cookies.set("facediff_session", "sessao-sintetica")
        criada = client.post(
            "/api/v1/turmas/2/sessoes",
            headers={
                "Origin": "https://facediff.test",
                "X-CSRF-Token": "csrf-sintetico",
            },
            json={
                "titulo": "Aula de IA",
                "inicio_em": (AGORA + dt.timedelta(minutes=1)).isoformat(),
                "fim_em": (AGORA + dt.timedelta(hours=1)).isoformat(),
            },
        )
        link = client.post(
            "/api/v1/sessoes/7/links",
            headers={
                "Origin": "https://facediff.test",
                "X-CSRF-Token": "csrf-sintetico",
            },
        )
        revogada = client.post(
            "/api/v1/sessoes/7/revogar",
            headers={
                "Origin": "https://facediff.test",
                "X-CSRF-Token": "csrf-sintetico",
            },
        )

    assert criada.status_code == 201, criada.text
    assert criada.json()["id"] == 7
    assert link.status_code == 201
    assert link.json()["finalidade"] == "presenca"
    assert link.json()["sessao_id"] == 7
    assert revogada.status_code == 200
    assert revogada.json()["revogada"] is True


def test_rotas_autenticadas_editam_e_excluem_sessao() -> None:
    presencas = _RepositorioPresenca()
    app = create_app(
        WebSettings(
            environment="test",
            database_url="postgresql+psycopg://usuario:senha@localhost:5432/facediff_test",
            secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
            retention_days=14,
            database_disposable=True,
            public_origin="https://facediff.test",
        ),
        WebServices(
            auth_repository=_RepositorioAuth(),
            presenca_repository=presencas,
            clock=lambda: AGORA,
            capture_storage=_Capturas(),
        ),
    )
    csrf = {"Origin": "https://facediff.test", "X-CSRF-Token": "csrf-sintetico"}
    fim = AGORA + dt.timedelta(hours=2)

    with TestClient(app) as client:
        client.cookies.set("facediff_session", "sessao-sintetica")
        editada = client.patch(
            "/api/v1/sessoes/7",
            headers=csrf,
            json={
                "titulo": "Aula revisada",
                "inicio_em": (AGORA + dt.timedelta(hours=1)).isoformat(),
                "fim_em": fim.isoformat(),
            },
        )
        confirmacao_errada = client.request(
            "DELETE",
            "/api/v1/sessoes/7",
            headers=csrf,
            json={"confirmacao": "EXCLUIR-SESSAO-8"},
        )
        excluida = client.request(
            "DELETE",
            "/api/v1/sessoes/7",
            headers=csrf,
            json={"confirmacao": "EXCLUIR-SESSAO-7"},
        )

    assert editada.status_code == 200, editada.text
    assert editada.json()["titulo"] == "Aula revisada"
    assert editada.json()["versao"] == 2
    assert presencas.edicao["fim_link"] == fim + dt.timedelta(seconds=120)
    assert confirmacao_errada.status_code == 422
    assert excluida.status_code == 200, excluida.text
    assert excluida.json() == {
        "id": 7,
        "excluida": True,
        "presencas_removidas": 1,
        "tentativas_removidas": 1,
        "limpeza_pendente": False,
    }


def test_limites_de_presenca_por_link_e_ip_vem_da_configuracao() -> None:
    presencas = _RepositorioPresenca()
    services = WebServices(
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        fila_facial=_Fila(),
        desafio_captura=_Desafios(),
        capture_storage=_Capturas(),
        rate_limit_secret=b"s" * 32,
        clock=lambda: AGORA,
    )

    with _app(
        services,
        presence_start_limit_per_window=42,
        presence_capture_limit_per_window=99,
    ) as client:
        inicio = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-042",
            },
            json={"matricula": "00042"},
        )
        client.post(
            f"/api/v1/tentativas/{inicio.json()['id']}/capturas",
            headers={"Authorization": "Bearer credencial-captura-sintetica"},
            json={"etapa": 1, "nonce": "n" * 64, "captura_base64": "YQ=="},
        )

    assert presencas.limites_usados == [42, 99]


def test_rotas_publicas_iniciam_tentativa_recebem_captura_e_exibem_status() -> None:
    presencas = _RepositorioPresenca()
    fila = _Fila()
    desafios = _Desafios()
    capturas = _Capturas()
    services = WebServices(
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        fila_facial=fila,
        desafio_captura=desafios,
        capture_storage=capturas,
        rate_limit_secret=b"s" * 32,
        clock=lambda: AGORA,
    )

    with _app(services) as client:
        inicio = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-001",
            },
            json={"matricula": "00042"},
        )
        tentativa_id = inicio.json()["id"]
        captura = client.post(
            f"/api/v1/tentativas/{tentativa_id}/capturas",
            headers={"Authorization": "Bearer credencial-captura-sintetica"},
            json={"etapa": 1, "nonce": "n" * 64, "captura_base64": "YQ=="},
        )
        status = client.get(
            f"/api/v1/tentativas/{tentativa_id}",
            headers={"Authorization": "Bearer credencial-captura-sintetica"},
        )

    assert inicio.status_code == 201
    assert inicio.json()["desafio"]["etapa"] == 1
    assert len(presencas.limitadas) == 2
    assert captura.status_code == 202
    assert captura.json()["recebida"] is True
    assert len(capturas.salvas) == 1
    assert len(fila.submissoes) == 1
    assert status.status_code == 200
    assert status.headers["cache-control"] == "no-store"
    assert status.json()["desafio"]["etapa"] == 2


def test_rotas_publicas_mapeiam_fila_cheia_e_tentativa_ativa() -> None:
    presencas = _RepositorioPresenca()
    fila = _Fila()
    fila.erro_reserva = FilaCheia(9)
    services = WebServices(
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        fila_facial=fila,
        desafio_captura=_Desafios(),
        capture_storage=_Capturas(),
        rate_limit_secret=b"s" * 32,
        clock=lambda: AGORA,
    )

    with _app(services) as client:
        indisponivel = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-002",
            },
            json={"matricula": "00042"},
        )
        fila.erro_reserva = None
        presencas.erro_inicio = TentativaAtiva()
        ativa = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-003",
            },
            json={"matricula": "00042"},
        )
        presencas.erro_inicio = LookupError()
        desconhecida = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-004",
            },
            json={"matricula": "99999"},
        )

    assert indisponivel.status_code == 503
    assert indisponivel.headers["retry-after"] == "9"
    assert ativa.status_code == 409
    # Matrícula fora da turma: explica o que conferir sem revelar o motivo exato.
    assert desconhecida.status_code == 404
    mensagem = desconhecida.json()["mensagem"]
    assert mensagem.startswith("Tentativa indisponível.")
    assert "vinculada a esta turma" in mensagem
    assert "cadastro facial aprovado" in mensagem


def test_rate_limit_retorna_retry_after_numerico() -> None:
    presencas = _RepositorioPresenca()
    presencas.espera_rate_limit = 17
    services = WebServices(
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        fila_facial=_Fila(),
        desafio_captura=_Desafios(),
        capture_storage=_Capturas(),
        rate_limit_secret=b"s" * 32,
        clock=lambda: AGORA,
    )

    with _app(services) as client:
        resposta = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-006",
            },
            json={"matricula": "00042"},
        )

    assert resposta.status_code == 429
    assert resposta.headers["retry-after"] == "17"


def test_upload_recusa_base64_invalido_prazo_expirado_e_etapa_diferente() -> None:
    presencas = _RepositorioPresenca()
    fila = _Fila()
    clock = {"now": AGORA}
    services = WebServices(
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        fila_facial=fila,
        desafio_captura=_Desafios(),
        capture_storage=_Capturas(),
        rate_limit_secret=b"s" * 32,
        clock=lambda: clock["now"],
    )

    with _app(services) as client:
        sem_credencial = client.get(
            f"/api/v1/tentativas/{uuid4()}",
        )
        inicio = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-004",
            },
            json={"matricula": "00042"},
        )
        tentativa_id = inicio.json()["id"]
        credencial = {"Authorization": "Bearer credencial-captura-sintetica"}
        invalida = client.post(
            f"/api/v1/tentativas/{tentativa_id}/capturas",
            headers=credencial,
            json={"etapa": 1, "nonce": "n" * 64, "captura_base64": "%%%"},
        )
        clock["now"] = AGORA + dt.timedelta(seconds=121)
        expirada = client.post(
            f"/api/v1/tentativas/{tentativa_id}/capturas",
            headers=credencial,
            json={"etapa": 1, "nonce": "n" * 64, "captura_base64": "YQ=="},
        )

    assert sem_credencial.status_code == 404
    assert invalida.status_code == 422
    assert expirada.status_code == 410


def test_upload_repetido_com_bytes_diferentes_retorna_conflito() -> None:
    presencas = _RepositorioPresenca()
    services = WebServices(
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        fila_facial=_Fila(),
        desafio_captura=_Desafios(),
        capture_storage=_Capturas(),
        rate_limit_secret=b"s" * 32,
        clock=lambda: AGORA,
    )

    with _app(services) as client:
        inicio = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-005",
            },
            json={"matricula": "00042"},
        )
        presencas.erro_captura = CapturaRepetidaDiferente()
        conflito = client.post(
            f"/api/v1/tentativas/{inicio.json()['id']}/capturas",
            headers={"Authorization": "Bearer credencial-captura-sintetica"},
            json={"etapa": 1, "nonce": "n" * 64, "captura_base64": "YQ=="},
        )

    assert conflito.status_code == 409


def test_rotas_sessoes_mapeiam_turma_intervalo_e_sessao_revogada() -> None:
    presencas = _RepositorioPresenca()
    services = WebServices(
        auth_repository=_RepositorioAuth(),
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        clock=lambda: AGORA,
    )
    cabecalhos = {
        "Origin": "https://facediff.test",
        "X-CSRF-Token": "csrf-sintetico",
    }

    with _app(services) as client:
        client.cookies.set("facediff_session", "sessao-sintetica")
        turma_inexistente = client.post(
            "/api/v1/turmas/0/sessoes",
            headers=cabecalhos,
            json={
                "titulo": "Aula",
                "inicio_em": AGORA.isoformat(),
                "fim_em": (AGORA + dt.timedelta(hours=1)).isoformat(),
            },
        )
        intervalo_invalido = client.post(
            "/api/v1/turmas/2/sessoes",
            headers=cabecalhos,
            json={
                "titulo": "Aula",
                "inicio_em": AGORA.isoformat(),
                "fim_em": AGORA.isoformat(),
            },
        )
        presencas.sessao_revogada = True
        sessao_revogada = client.post("/api/v1/sessoes/7/links", headers=cabecalhos)

    assert turma_inexistente.status_code == 404
    assert intervalo_invalido.status_code == 422
    assert sessao_revogada.status_code == 404


def test_revogacao_informa_limpeza_pendente_quando_arquivo_nao_pode_ser_removido() -> (
    None
):
    class CapturasComFalha(_Capturas):
        def remover_job(self, _job_id: UUID) -> None:
            raise OSError("falha sintetica")

    presencas = _RepositorioPresenca()
    presencas.arquivos_cancelados = (uuid4(),)
    services = WebServices(
        auth_repository=_RepositorioAuth(),
        presenca_repository=presencas,
        capture_storage=CapturasComFalha(),
        clock=lambda: AGORA,
    )

    with _app(services) as client:
        client.cookies.set("facediff_session", "sessao-sintetica")
        response = client.post(
            "/api/v1/sessoes/7/revogar",
            headers={
                "Origin": "https://facediff.test",
                "X-CSRF-Token": "csrf-sintetico",
            },
        )

    assert response.status_code == 200
    assert response.json()["tentativas_canceladas"] == 1
    assert response.json()["limpeza_pendente"] is True


def test_falha_ao_gravar_captura_retorna_indisponibilidade_tecnica() -> None:
    class CapturasComFalha(_Capturas):
        def salvar_captura(self, _job_id: UUID, _ordinal: int, _conteudo: bytes):
            raise OSError("erro local sintetico")

    presencas = _RepositorioPresenca()
    services = WebServices(
        link_repository=_RepositorioLinks(),
        presenca_repository=presencas,
        fila_facial=_Fila(),
        desafio_captura=_Desafios(),
        capture_storage=CapturasComFalha(),
        rate_limit_secret=b"s" * 32,
        clock=lambda: AGORA,
    )

    with _app(services) as client:
        inicio = client.post(
            "/api/v1/sessoes/7/tentativas",
            headers={
                "Authorization": "Bearer token-do-link-sintetico",
                "Idempotency-Key": "chave-idempotente-sintetica-007",
            },
            json={"matricula": "00042"},
        )
        captura = client.post(
            f"/api/v1/tentativas/{inicio.json()['id']}/capturas",
            headers={"Authorization": "Bearer credencial-captura-sintetica"},
            json={"etapa": 1, "nonce": "n" * 64, "captura_base64": "YQ=="},
        )

    assert inicio.status_code == 201
    assert captura.status_code == 503
