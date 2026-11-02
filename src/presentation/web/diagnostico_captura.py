"""Medida local que o navegador envia junto da captura; só vai para o log."""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class DiagnosticoCaptura(BaseModel):
    """Não participa de nenhuma decisão: diz se o flash acendeu e o que o guia mediu."""

    model_config = ConfigDict(extra="forbid")

    flash: bool = False
    # Brilho médio do rosto medido pelo guia; nulo quando o guia não rodou.
    luz: float | None = Field(default=None, ge=0, le=255)


def registrar_diagnostico(contexto: str, itens: list[DiagnosticoCaptura]) -> None:
    resumo = "; ".join(
        f"flash={'sim' if item.flash else 'não'} "
        f"luz={'sem medida' if item.luz is None else f'{item.luz:.1f}'}"
        for item in itens
    )
    logger.info("%s: %s.", contexto, resumo or "sem diagnóstico do navegador")
