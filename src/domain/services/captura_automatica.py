"""Contrato puro para exigir tempo e observacoes antes da captura."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real


def _validar_tempo(nome: str, valor: object, *, positivo: bool) -> float:
    if isinstance(valor, bool) or not isinstance(valor, Real):
        raise ValueError(f"{nome} deve ser um numero real finito")
    try:
        numero = float(valor)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{nome} deve ser um numero real finito") from exc
    if not isfinite(numero) or (numero <= 0 if positivo else numero < 0):
        requisito = "positivo" if positivo else "nao negativo"
        raise ValueError(f"{nome} deve ser finito e {requisito}")
    return numero


@dataclass(frozen=True, slots=True)
class ParametrosCapturaAutomatica:
    espera_segundos: float = 5.0
    intervalo_amostragem_segundos: float = 0.5
    idade_maxima_segundos: float = 2.0

    def __post_init__(self) -> None:
        for nome in (
            "espera_segundos",
            "intervalo_amostragem_segundos",
            "idade_maxima_segundos",
        ):
            object.__setattr__(
                self, nome, _validar_tempo(nome, getattr(self, nome), positivo=True)
            )
        if self.intervalo_amostragem_segundos >= self.idade_maxima_segundos:
            raise ValueError(
                "intervalo_amostragem_segundos deve ser menor que idade_maxima_segundos"
            )


@dataclass(frozen=True, slots=True)
class EstadoCapturaAutomatica:
    chave: str | None
    observacoes: int
    tempo_restante: float
    pronto: bool


class ConfirmadorCapturaAutomatica:
    def __init__(self, parametros: ParametrosCapturaAutomatica) -> None:
        self._parametros = parametros
        self._chave: str | None = None
        self._inicio: float | None = None
        self._ultima_captura: float | None = None
        self._observacoes = 0
        self._ultimo_timestamp_observado: float | None = None
        self._ultimo_agora: float | None = None

    def observar(
        self, chave: str | None, capturado_em: float, agora: float
    ) -> EstadoCapturaAutomatica:
        if chave is not None and (not isinstance(chave, str) or not chave):
            raise ValueError("chave deve ser texto nao vazio ou None")
        timestamp = _validar_tempo("capturado_em", capturado_em, positivo=False)
        instante_atual = _validar_tempo("agora", agora, positivo=False)
        if instante_atual < timestamp:
            raise ValueError("agora nao pode ser anterior a capturado_em")
        if (
            self._ultimo_timestamp_observado is not None
            and timestamp <= self._ultimo_timestamp_observado
        ):
            raise ValueError("capturado_em deve crescer estritamente")
        if self._ultimo_agora is not None and instante_atual < self._ultimo_agora:
            raise ValueError("agora nao pode regredir")
        self._ultimo_timestamp_observado = timestamp
        self._ultimo_agora = instante_atual

        if (
            chave is None
            or instante_atual - timestamp > self._parametros.idade_maxima_segundos
        ):
            self._limpar_sequencia()
            return self._estado(instante_atual)

        intervalo_excedido = (
            self._ultima_captura is not None
            and timestamp - self._ultima_captura
            > self._parametros.idade_maxima_segundos
        )
        if self._chave != chave or intervalo_excedido:
            self._iniciar_sequencia(chave, timestamp)
        else:
            self._observacoes += 1
            self._ultima_captura = timestamp
        return self._estado(instante_atual)

    def consultar(self, agora: float) -> EstadoCapturaAutomatica:
        instante_atual = _validar_tempo("agora", agora, positivo=False)
        if self._ultimo_agora is not None and instante_atual < self._ultimo_agora:
            raise ValueError("agora nao pode regredir")
        self._ultimo_agora = instante_atual
        if (
            self._ultima_captura is not None
            and instante_atual - self._ultima_captura
            > self._parametros.idade_maxima_segundos
        ):
            self._limpar_sequencia()
        return self._estado(instante_atual)

    def reiniciar(self) -> None:
        self._limpar_sequencia()
        self._ultimo_timestamp_observado = None
        self._ultimo_agora = None

    def _iniciar_sequencia(self, chave: str, timestamp: float) -> None:
        self._chave = chave
        self._inicio = timestamp
        self._ultima_captura = timestamp
        self._observacoes = 1

    def _limpar_sequencia(self) -> None:
        self._chave = None
        self._inicio = None
        self._ultima_captura = None
        self._observacoes = 0

    def _estado(self, agora: float) -> EstadoCapturaAutomatica:
        inicio = self._inicio
        ultima = self._ultima_captura
        if self._chave is None or inicio is None or ultima is None:
            return EstadoCapturaAutomatica(
                None,
                0,
                self._parametros.espera_segundos,
                False,
            )
        decorrido = max(0.0, agora - inicio)
        pronto = (
            self._observacoes >= 3
            and ultima - inicio >= self._parametros.espera_segundos
            and agora - ultima <= self._parametros.idade_maxima_segundos
        )
        return EstadoCapturaAutomatica(
            self._chave,
            self._observacoes,
            max(0.0, self._parametros.espera_segundos - decorrido),
            pronto,
        )
