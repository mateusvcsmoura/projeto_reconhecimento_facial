"""Caso de uso: aplicar a politica de retencao de presencas.

Dado pessoal nao deve ser guardado por mais tempo do que a finalidade que o
justificou (LGPD art. 15 e 16). O prazo e configuravel; zero desliga.
"""

from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from src.domain.repositories.presenca_repository import PresencaRepository

logger = logging.getLogger(__name__)


class ExpurgarPresencas:
    def __init__(
        self, presencas: PresencaRepository, tz: ZoneInfo, retencao_dias: int
    ) -> None:
        self._presencas = presencas
        self._tz = tz
        self._retencao_dias = retencao_dias

    @property
    def ativo(self) -> bool:
        return self._retencao_dias > 0

    def limite(self, hoje: dt.date | None = None) -> dt.date:
        referencia = hoje or dt.datetime.now(self._tz).date()
        return referencia - dt.timedelta(days=self._retencao_dias)

    def executar(self, hoje: dt.date | None = None) -> int:
        """Apaga o que excedeu o prazo. Devolve quantas linhas sairam."""
        if not self.ativo:
            logger.info("Expurgo desligado (retencao = 0 dias)")
            return 0

        return self._presencas.expurgar_anteriores_a(self.limite(hoje))
