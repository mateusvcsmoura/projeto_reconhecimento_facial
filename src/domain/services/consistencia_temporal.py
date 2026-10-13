"""Confirma observacoes consecutivas sem depender de relogio ou de IO."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real


def _numero_finito_positivo(nome: str, valor: object) -> float:
    if isinstance(valor, bool) or not isinstance(valor, Real):
        raise ValueError(f"{nome} deve ser um numero real finito e positivo.")
    try:
        convertido = float(valor)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{nome} deve ser um numero real finito e positivo.") from exc
    if not isfinite(convertido) or convertido <= 0.0:
        raise ValueError(f"{nome} deve ser um numero real finito e positivo.")
    return convertido


def _timestamp_valido(valor: object) -> float:
    if isinstance(valor, bool) or not isinstance(valor, Real):
        raise ValueError("O timestamp deve ser real, finito e nao negativo.")
    try:
        convertido = float(valor)
    except (OverflowError, ValueError) as exc:
        raise ValueError("O timestamp deve ser real, finito e nao negativo.") from exc
    if not isfinite(convertido) or convertido < 0.0:
        raise ValueError("O timestamp deve ser real, finito e nao negativo.")
    return convertido


def _aluno_id_valido(valor: object) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, Integral) or valor <= 0:
        raise ValueError("aluno_id deve ser inteiro positivo ou None.")
    return int(valor)


@dataclass(frozen=True, slots=True)
class ParametrosTemporais:
    """Limites iniciais de engenharia, sem calibracao biometrica."""

    min_observacoes: int = 3
    janela_segundos: float = 5.0
    validade_segundos: float = 2.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.min_observacoes, bool)
            or not isinstance(self.min_observacoes, Integral)
            or self.min_observacoes < 2
        ):
            raise ValueError("min_observacoes deve ser um inteiro >= 2.")

        janela = _numero_finito_positivo("janela_segundos", self.janela_segundos)
        validade = _numero_finito_positivo("validade_segundos", self.validade_segundos)
        if validade > janela:
            raise ValueError("validade_segundos nao pode exceder janela_segundos.")

        object.__setattr__(self, "min_observacoes", int(self.min_observacoes))
        object.__setattr__(self, "janela_segundos", janela)
        object.__setattr__(self, "validade_segundos", validade)


@dataclass(frozen=True, slots=True)
class EstadoTemporal:
    """Snapshot da contagem e da vigencia da sequencia atual."""

    aluno_id: int | None
    observacoes: int
    confirmado: bool


class ConfirmadorTemporal:
    """Mantem no maximo N timestamps da mesma identidade observada."""

    def __init__(self, parametros: ParametrosTemporais) -> None:
        if not isinstance(parametros, ParametrosTemporais):
            raise ValueError("parametros deve ser ParametrosTemporais.")
        self._parametros = parametros
        self._observacoes: deque[float] = deque(maxlen=parametros.min_observacoes)
        self._aluno_id: int | None = None
        self._ultimo_timestamp: float | None = None

    def observar(self, aluno_id: int | None, capturado_em: float) -> EstadoTemporal:
        """Adiciona uma decisao nova ou interrompe a sequencia com None."""
        id_validado = _aluno_id_valido(aluno_id)
        instante = _timestamp_valido(capturado_em)
        if self._ultimo_timestamp is not None and instante <= self._ultimo_timestamp:
            raise ValueError("Os timestamps das observacoes devem ser crescentes.")

        # Validacoes completas antes de alterar estado, inclusive para None.
        self._ultimo_timestamp = instante
        self._expirar(instante)
        if id_validado is None:
            self._limpar_sequencia()
            return self._snapshot()

        if id_validado != self._aluno_id:
            self._limpar_sequencia()
            self._aluno_id = id_validado

        self._observacoes.append(instante)
        self._remover_fora_da_janela(instante)
        return self._snapshot()

    def consultar(self, agora: float) -> EstadoTemporal:
        """Consulta validade sem acrescentar ou renovar uma observacao."""
        instante = _timestamp_valido(agora)
        if self._ultimo_timestamp is not None and instante < self._ultimo_timestamp:
            raise ValueError(
                "O instante consultado nao pode anteceder a ultima observacao."
            )
        self._expirar(instante)
        return self._snapshot()

    def reiniciar(self) -> None:
        """Limpa sequencia e marcador temporal ao encerrar uma sessao."""
        self._limpar_sequencia()
        self._ultimo_timestamp = None

    def _expirar(self, agora: float) -> None:
        if not self._observacoes:
            return
        idade_ultima = agora - self._observacoes[-1]
        if idade_ultima > self._parametros.validade_segundos:
            self._limpar_sequencia()
            return
        self._remover_fora_da_janela(agora)

    def _remover_fora_da_janela(self, agora: float) -> None:
        while (
            self._observacoes
            and agora - self._observacoes[0] > self._parametros.janela_segundos
        ):
            self._observacoes.popleft()
        if not self._observacoes:
            self._aluno_id = None

    def _limpar_sequencia(self) -> None:
        self._observacoes.clear()
        self._aluno_id = None

    def _snapshot(self) -> EstadoTemporal:
        quantidade = len(self._observacoes)
        return EstadoTemporal(
            aluno_id=self._aluno_id,
            observacoes=quantidade,
            confirmado=quantidade == self._parametros.min_observacoes,
        )
