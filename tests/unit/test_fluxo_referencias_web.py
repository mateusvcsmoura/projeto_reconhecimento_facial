"""Fluxos de referencias faciais web com fakes e dados sinteticos."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import fields
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from src.application.use_cases.anexar_referencias_web import (
    AnexarReferencias,
    ContextoJobReferencias,
)
from src.application.use_cases.solicitar_cadastro_web import (
    ConsentimentoWeb,
    ContextoConvite,
    DadosCadastroWeb,
    SolicitarCadastroWeb,
)
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.referencia_facial import PreparacaoReferencia
from src.domain.entities.solicitacao_cadastro import SolicitacaoCadastro

UTC = ZoneInfo("UTC")
AGORA = dt.datetime(2026, 10, 18, 12, tzinfo=UTC)


class _StorageFake:
    def __init__(self) -> None:
        self.salvos: list[str] = []
        self.removidos: list[str] = []

    def salvar(self, solicitacao_id: int, ordinal: int, recorte: bytes) -> str:
        caminho = f"privado/{solicitacao_id}/{ordinal}-{len(self.salvos)}.bin"
        self.salvos.append(caminho)
        return caminho

    def remover(self, caminho: str) -> None:
        self.removidos.append(caminho)


class _RepositorioAnexoFake:
    def __init__(self, solicitacao: SolicitacaoCadastro) -> None:
        self.solicitacao = solicitacao
        self.referencias: list[object] = []
        self.erro: Exception | None = None
        self.anexos_por_job: dict[uuid.UUID, str] = {}

    def obter_solicitacao(self, solicitacao_id: int) -> SolicitacaoCadastro:
        assert solicitacao_id == self.solicitacao.id
        return self.solicitacao

    def estado_do_job(self, solicitacao_id: int, job_id: uuid.UUID) -> str | None:
        assert solicitacao_id == self.solicitacao.id
        return self.anexos_por_job.get(job_id)

    def anexar_referencias(self, solicitacao_id: int, **kwargs: object) -> str:
        assert solicitacao_id == self.solicitacao.id
        if self.erro is not None:
            raise self.erro
        self.referencias.extend(kwargs["referencias"])  # type: ignore[arg-type]
        job_id = kwargs["job_id"]
        assert isinstance(job_id, uuid.UUID)
        self.anexos_por_job[job_id] = "pendente_aprovacao"
        return "pendente_aprovacao"


def _solicitacao() -> SolicitacaoCadastro:
    return SolicitacaoCadastro(
        id=11,
        tipo="cadastro",
        estado="em_coleta",
        turma_id=7,
        aluno_id=None,
        matricula="000123",
        nome="Pessoa Sintetica",
        expira_em=AGORA + dt.timedelta(days=2),
        consentimento_em=AGORA,
        consentimento_versao="termos-2026-01",
    )


def _preparacoes(*, modelo: str = "FaceNet512", dimensao: int = 512):
    return tuple(
        PreparacaoReferencia(
            ordinal=ordinal,
            captura_id=f"captura-{ordinal}",
            recorte=f"\xff\xd8recorte-{ordinal}\xff\xd9".encode(),
            embedding=FaceEmbedding.de_valores(
                np.arange(1, dimensao + 1, dtype=np.float32) + ordinal,
                modelo,
            ),
        )
        for ordinal in (1, 2, 3)
    )


def test_solicitar_cadastro_exige_consentimento_e_nao_reserva_matricula() -> None:
    class Repositorio:
        def __init__(self) -> None:
            self.chamadas: list[dict[str, object]] = []

        def criar_cadastro(self, **kwargs: object) -> SolicitacaoCadastro:
            self.chamadas.append(kwargs)
            return _solicitacao()

    repo = Repositorio()
    caso = SolicitarCadastroWeb(repo, relogio=lambda: AGORA)
    convite = ContextoConvite(
        referencia="convite-opaco-7",
        turma_id=7,
        expira_em=AGORA + dt.timedelta(days=3),
    )

    with pytest.raises(ValueError, match="consentimento"):
        caso.criar(
            DadosCadastroWeb(matricula="000123", nome="Pessoa Sintetica"),
            convite,
            ConsentimentoWeb(aceito=False, versao="termos-2026-01"),
        )
    assert repo.chamadas == []

    retorno = caso.criar(
        DadosCadastroWeb(matricula="000123", nome="  Pessoa   Sintetica "),
        convite,
        ConsentimentoWeb(aceito=True, versao="termos-2026-01"),
    )

    assert retorno.estado == "em_coleta"
    assert repo.chamadas[0]["matricula"] == "000123"
    assert repo.chamadas[0]["nome"] == "Pessoa Sintetica"
    assert repo.chamadas[0]["expira_em"] <= convite.expira_em


@pytest.mark.parametrize(
    ("preparacoes", "mensagem"),
    [
        (_preparacoes()[:2], "três"),
        ((_preparacoes()[0], _preparacoes()[0], _preparacoes()[2]), "ordinais"),
        (
            (
                _preparacoes()[0],
                _preparacoes()[1],
                PreparacaoReferencia(
                    ordinal=3,
                    captura_id="captura-3",
                    recorte=b"recorte-terceiro",
                    embedding=FaceEmbedding.de_valores(np.ones(512), "OutroModelo"),
                ),
            ),
            "modelo",
        ),
        (_preparacoes(dimensao=128), "512"),
    ],
)
def test_anexar_recusa_conjunto_incompleto_ou_inconsistente(
    preparacoes: tuple[PreparacaoReferencia, ...], mensagem: str
) -> None:
    repo = _RepositorioAnexoFake(_solicitacao())
    storage = _StorageFake()
    caso = AnexarReferencias(repo, storage, relogio=lambda: AGORA)

    with pytest.raises(ValueError, match=mensagem):
        caso.executar(
            11,
            preparacoes,
            ContextoJobReferencias(
                job_id=uuid.uuid4(),
                consentimento_em=AGORA,
                consentimento_versao="termos-2026-01",
            ),
        )

    assert storage.salvos == []
    assert repo.referencias == []


def test_anexar_tres_referencias_e_idempotente_por_job() -> None:
    repo = _RepositorioAnexoFake(_solicitacao())
    storage = _StorageFake()
    caso = AnexarReferencias(repo, storage, relogio=lambda: AGORA)
    contexto = ContextoJobReferencias(
        job_id=uuid.uuid4(),
        consentimento_em=AGORA,
        consentimento_versao="termos-2026-01",
    )

    estado = caso.executar(11, _preparacoes(), contexto)
    repetido = caso.executar(11, _preparacoes(), contexto)

    assert estado == repetido == "pendente_aprovacao"
    assert len(repo.referencias) == 3
    assert len(storage.salvos) == 3


def test_falha_sql_remove_apenas_arquivos_da_tentativa() -> None:
    repo = _RepositorioAnexoFake(_solicitacao())
    repo.erro = RuntimeError("falha de persistência")
    storage = _StorageFake()
    caso = AnexarReferencias(repo, storage, relogio=lambda: AGORA)

    with pytest.raises(RuntimeError, match="persistência"):
        caso.executar(
            11,
            _preparacoes(),
            ContextoJobReferencias(
                job_id=uuid.uuid4(),
                consentimento_em=AGORA,
                consentimento_versao="termos-2026-01",
            ),
        )

    assert storage.removidos == storage.salvos


def test_dto_de_solicitacao_nao_expoe_biometria_caminhos_ou_urls() -> None:
    nomes = {campo.name for campo in fields(SolicitacaoCadastro)}

    assert not nomes.intersection(
        {
            "imagem",
            "recorte",
            "embedding",
            "caminho_privado_relativo",
            "url",
        }
    )
