from __future__ import annotations

import importlib
import importlib.util
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

MODULO = "src.domain.services.desafio_captura"
AGORA = datetime(2026, 10, 18, 12, tzinfo=UTC)


class RepositorioDesafioFake:
    def __init__(self) -> None:
        self.registros: dict[UUID, Any] = {}

    def criar(self, registro: Any) -> Any:
        existente = self.registros.get(registro.id)
        if existente is not None:
            return existente
        self.registros[registro.id] = registro
        return registro

    def obter(self, desafio_id: UUID) -> Any | None:
        return self.registros.get(desafio_id)

    def registrar_recebimento(
        self, desafio_id: UUID, sequencia: int, nonce_hash: str, agora: datetime
    ) -> Any | None:
        api = importlib.import_module(MODULO)
        registro = self.registros.get(desafio_id)
        if (
            registro is None
            or registro.estado is not api.EstadoDesafio.AGUARDANDO_ETAPA
            or registro.etapa_recebida != registro.etapa_validada
            or sequencia != registro.etapa_validada + 1
            or nonce_hash != registro.nonce_hash
            or agora > registro.expira_em
        ):
            return None
        atualizado = replace(
            registro,
            etapa_recebida=sequencia,
            estado=api.EstadoDesafio.ETAPA_RECEBIDA,
            atualizada_em=agora,
        )
        self.registros[desafio_id] = atualizado
        return atualizado

    def validar_etapa(
        self,
        desafio_id: UUID,
        sequencia: int,
        *,
        aprovada: bool,
        motivo: str | None,
        agora: datetime,
        repetir: bool = False,
    ) -> Any | None:
        api = importlib.import_module(MODULO)
        registro = self.registros.get(desafio_id)
        if (
            registro is None
            or registro.estado is not api.EstadoDesafio.ETAPA_RECEBIDA
            or registro.etapa_recebida != sequencia
            or registro.etapa_validada + 1 != sequencia
        ):
            return None
        novo_estado = (
            api.EstadoDesafio.AGUARDANDO_ETAPA
            if not aprovada and repetir
            else api.EstadoDesafio.REJEITADO
            if not aprovada
            else api.EstadoDesafio.CONCLUIDO
            if sequencia == 3
            else api.EstadoDesafio.AGUARDANDO_ETAPA
        )
        atualizado = replace(
            registro,
            etapa_validada=sequencia if aprovada else registro.etapa_validada,
            etapa_recebida=(
                registro.etapa_validada if repetir else registro.etapa_recebida
            ),
            estado=novo_estado,
            motivo=motivo,
            atualizada_em=agora,
        )
        self.registros[desafio_id] = atualizado
        return atualizado

    def encerrar(
        self,
        desafio_id: UUID,
        estado: Any,
        *,
        motivo: str,
        agora: datetime,
    ) -> Any | None:
        api = importlib.import_module(MODULO)
        registro = self.registros.get(desafio_id)
        if registro is None or registro.estado in {
            api.EstadoDesafio.CONCLUIDO,
            api.EstadoDesafio.REJEITADO,
            api.EstadoDesafio.EXPIRADO,
        }:
            return None
        atualizado = replace(
            registro, estado=estado, motivo=motivo, atualizada_em=agora
        )
        self.registros[desafio_id] = atualizado
        return atualizado


def _api() -> tuple[Any, RepositorioDesafioFake] | None:
    if importlib.util.find_spec(MODULO) is None:
        return None
    return importlib.import_module(MODULO), RepositorioDesafioFake()


def _emitir(api: Any, repositorio: RepositorioDesafioFake, *, agora: datetime = AGORA):
    contexto = api.ContextoDesafio(
        job_id=uuid4(),
        aluno_id=12,
        conjunto_id=34,
        versao_referencia=2,
        prazo_recebimento=agora + timedelta(seconds=90),
    )
    servico = api.DesafioCaptura(repositorio, segredo=b"s" * 32)
    return servico, servico.emitir(contexto, agora)


def _evidencia(api: Any, pose: str, **ajustes: object):
    dados: dict[str, object] = {
        "quantidade_rostos": 1,
        "orientacao": api.OrientacaoPose(pose),
        "identidade_ok": True,
        "qualidade_ok": True,
        "antispoofing_ok": True,
        "versao_referencia": 2,
    }
    dados.update(ajustes)
    return api.EvidenciaEtapa(**dados)


def _receber(servico: Any, desafio: Any, sequencia: int, agora: datetime = AGORA):
    return servico.registrar_etapa_recebida(desafio.id, desafio.nonce, sequencia, agora)


def test_desafio_requer_frente_movimento_sorteado_e_retorno() -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)
    movimento = (
        modulo.OrientacaoPose.DIREITA
        if desafio.direcao is modulo.DirecaoMovimento.DIREITA
        else modulo.OrientacaoPose.ESQUERDA
    )

    assert desafio.primeira_orientacao is modulo.OrientacaoPose.FRENTE
    assert _receber(servico, desafio, 1).estado is modulo.EstadoDesafio.ETAPA_RECEBIDA
    frente = servico.validar_etapa(desafio.id, 1, _evidencia(modulo, "frente"), AGORA)
    assert frente.estado is modulo.EstadoDesafio.AGUARDANDO_ETAPA
    assert frente.proxima_orientacao is movimento

    assert _receber(servico, desafio, 2).estado is modulo.EstadoDesafio.ETAPA_RECEBIDA
    virada = servico.validar_etapa(
        desafio.id, 2, _evidencia(modulo, movimento.value), AGORA
    )
    assert virada.proxima_orientacao is modulo.OrientacaoPose.FRENTE

    assert _receber(servico, desafio, 3).estado is modulo.EstadoDesafio.ETAPA_RECEBIDA
    retorno = servico.validar_etapa(desafio.id, 3, _evidencia(modulo, "frente"), AGORA)
    assert retorno.estado is modulo.EstadoDesafio.CONCLUIDO
    assert retorno.desafio_ok is True


def test_nonce_incorreto_rejeita_o_desafio() -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)

    estado = servico.registrar_etapa_recebida(desafio.id, "nonce-incorreto", 1, AGORA)

    assert estado.estado is modulo.EstadoDesafio.REJEITADO
    assert estado.desafio_ok is False


def test_reenvio_da_mesma_etapa_nao_rejeita_desafio_ativo() -> None:
    api = _api()
    assert api is not None
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)

    inicial = servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 1, AGORA)
    repetida = servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 1, AGORA)

    assert inicial.estado is modulo.EstadoDesafio.ETAPA_RECEBIDA
    assert repetida.estado is modulo.EstadoDesafio.ETAPA_RECEBIDA
    assert repetida.recebimento_repetido is True
    assert repositorio.obter(desafio.id).estado is modulo.EstadoDesafio.ETAPA_RECEBIDA

    servico.validar_etapa(desafio.id, 1, _evidencia(modulo, "frente"), AGORA)
    repetida_apos_validacao = servico.registrar_etapa_recebida(
        desafio.id, desafio.nonce, 1, AGORA
    )
    assert repetida_apos_validacao.estado is modulo.EstadoDesafio.AGUARDANDO_ETAPA
    assert repetida_apos_validacao.recebimento_repetido is True


def test_etapa_antiga_ou_invertida_nao_aprova() -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)

    estado = servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 3, AGORA)

    assert estado.estado is modulo.EstadoDesafio.REJEITADO
    assert estado.desafio_ok is False


def test_frame_estatico_na_etapa_de_movimento_devolve_a_etapa_ate_passar() -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)
    servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 1, AGORA)
    servico.validar_etapa(desafio.id, 1, _evidencia(modulo, "frente"), AGORA)
    servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 2, AGORA)

    estado = servico.validar_etapa(desafio.id, 2, _evidencia(modulo, "frente"), AGORA)

    # Pose errada não encerra: a etapa 2 volta, com o motivo para orientar o aluno.
    assert estado.estado is modulo.EstadoDesafio.AGUARDANDO_ETAPA
    assert estado.proxima_etapa == 2
    assert estado.motivo_tecnico == "movimento_nao_confirmado"
    assert estado.desafio_ok is False
    direcao = repositorio.registros[desafio.id].direcao.value
    reenvio = servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 2, AGORA)
    assert reenvio.estado is modulo.EstadoDesafio.ETAPA_RECEBIDA
    assert reenvio.recebimento_repetido is False
    aprovada = servico.validar_etapa(desafio.id, 2, _evidencia(modulo, direcao), AGORA)
    assert aprovada.estado is modulo.EstadoDesafio.AGUARDANDO_ETAPA
    assert aprovada.proxima_etapa == 3
    assert aprovada.motivo_tecnico is None


@pytest.mark.parametrize(
    ("ajustes", "motivo"),
    [
        ({"qualidade_ok": False}, "qualidade_insuficiente"),
        ({"orientacao": "indeterminada"}, "movimento_nao_confirmado"),
    ],
)
def test_recusa_corrigivel_devolve_a_etapa(
    ajustes: dict[str, object], motivo: str
) -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)
    servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 1, AGORA)

    estado = servico.validar_etapa(
        desafio.id, 1, _evidencia(modulo, "frente", **ajustes), AGORA
    )

    assert estado.estado is modulo.EstadoDesafio.AGUARDANDO_ETAPA
    assert estado.proxima_etapa == 1
    assert estado.motivo_tecnico == motivo


def test_repetir_etapa_so_aceita_motivo_corrigivel() -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)
    servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 1, AGORA)

    with pytest.raises(ValueError):
        servico.repetir_etapa(desafio.id, 1, "identidade_nao_confirmada", AGORA)
    estado = servico.repetir_etapa(desafio.id, 1, "face_unica_nao_confirmada", AGORA)

    assert estado.estado is modulo.EstadoDesafio.AGUARDANDO_ETAPA
    assert estado.motivo_tecnico == "face_unica_nao_confirmada"


@pytest.mark.parametrize(
    "ajustes",
    [
        {"quantidade_rostos": 0},
        {"quantidade_rostos": 2},
        {"quantidade_rostos": 1.0},
        {"identidade_ok": False},
        {"antispoofing_ok": False},
        {"versao_referencia": 3},
        {"versao_referencia": True},
    ],
)
def test_evidencia_incompleta_ou_insegura_rejeita(ajustes: dict[str, object]) -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)
    servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 1, AGORA)

    estado = servico.validar_etapa(
        desafio.id, 1, _evidencia(modulo, "frente", **ajustes), AGORA
    )

    assert estado.estado is modulo.EstadoDesafio.REJEITADO
    assert estado.desafio_ok is False


def test_expiracao_e_limite_do_contexto_nao_sao_ampliados() -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)

    expirado = servico.registrar_etapa_recebida(
        desafio.id, desafio.nonce, 1, desafio.expira_em + timedelta(microseconds=1)
    )

    assert desafio.expira_em == AGORA + timedelta(seconds=90)
    assert expirado.estado is modulo.EstadoDesafio.EXPIRADO
    assert expirado.desafio_ok is False


def test_etapa_recebida_nao_pode_ser_validada_depois_da_expiracao() -> None:
    api = _api()
    assert api is not None
    modulo, repositorio = api
    servico, desafio = _emitir(modulo, repositorio)
    servico.registrar_etapa_recebida(desafio.id, desafio.nonce, 1, AGORA)

    resultado = servico.validar_etapa(
        desafio.id,
        1,
        _evidencia(modulo, "frente"),
        desafio.expira_em + timedelta(seconds=1),
    )

    assert resultado.estado is modulo.EstadoDesafio.EXPIRADO


def test_evidencia_nao_aceita_booleano_de_sucesso_do_cliente() -> None:
    api = _api()
    assert api is not None, "O serviço de desafio ainda não está implementado."
    modulo, _ = api

    assert "desafio_ok" not in modulo.EvidenciaEtapa.__dataclass_fields__
