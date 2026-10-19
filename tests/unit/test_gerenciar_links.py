from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.application.use_cases.gerenciar_links import GerenciarLinks
from src.domain.services.autorizacao import AtorWeb

AGORA = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)
ATOR = AtorWeb(
    conta_id=9,
    papel="professor",
    ativa=True,
    troca_senha_obrigatoria=False,
    professor_id=3,
)


class LinksFake:
    def __init__(self) -> None:
        self.link_id = UUID("8fc0c272-c303-4e7f-83f5-302aee20c591")
        self.link: dict[str, object] | None = None
        self.access_hash: str | None = None
        self.revoked = False

    def criar_link(self, **kwargs: object) -> UUID:
        self.link = kwargs
        return self.link_id

    def trocar_token(self, **kwargs: object) -> dict[str, object] | None:
        assert self.link is not None
        if kwargs["token_hash"] != self.link["token_hash"] or self.revoked:
            return None
        self.access_hash = str(kwargs["credencial_hash"])
        return {
            "link_id": self.link_id,
            "turma_id": 14,
            "finalidade": "cadastro",
            "finalidade_ate": self.link["finalidade_ate"],
            "credencial_expira_em": kwargs["credencial_expira_em"],
        }

    def revogar(
        self, ator: AtorWeb, link_id: UUID, **_kwargs: object
    ) -> tuple[int, tuple[int, ...]]:
        assert ator == ATOR
        assert link_id == self.link_id
        self.revoked = True
        return 2, (31, 32)


def test_link_tem_256_bits_hash_persistido_e_expira_em_sete_dias() -> None:
    repositorio = LinksFake()
    gerenciador = GerenciarLinks(repositorio, relogio=lambda: AGORA)

    link = gerenciador.criar(ATOR, 14, finalidade_ate=AGORA + timedelta(days=10))

    assert link.id == repositorio.link_id
    assert len(link.token) >= 43
    assert repositorio.link is not None
    assert (
        repositorio.link["token_hash"]
        == hashlib.sha256(link.token.encode()).hexdigest()
    )
    assert repositorio.link["token_hash"] != link.token
    assert link.expira_em == AGORA + timedelta(days=7)
    assert repositorio.link["finalidade"] == "cadastro"


def test_troca_link_emite_credencial_efemera_de_256_bits() -> None:
    repositorio = LinksFake()
    gerenciador = GerenciarLinks(repositorio, relogio=lambda: AGORA)
    link = gerenciador.criar(ATOR, 14, finalidade_ate=AGORA + timedelta(days=10))

    acesso = gerenciador.trocar(link.token)

    assert acesso is not None
    assert len(acesso.credencial) >= 43
    assert (
        repositorio.access_hash
        == hashlib.sha256(acesso.credencial.encode()).hexdigest()
    )
    assert acesso.finalidade == "cadastro"
    assert acesso.turma_id == 14


def test_link_revogado_nao_emite_credencial_e_revogacao_retorna_efeito() -> None:
    repositorio = LinksFake()
    gerenciador = GerenciarLinks(repositorio, relogio=lambda: AGORA)
    link = gerenciador.criar(ATOR, 14, finalidade_ate=AGORA + timedelta(days=10))

    resultado = gerenciador.revogar(ATOR, link.id)

    assert resultado.solicitacoes_canceladas == 2
    assert resultado.solicitacao_ids == (31, 32)
    assert gerenciador.trocar(link.token) is None
