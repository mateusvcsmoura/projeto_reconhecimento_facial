"""Aplica a politica de retencao: apaga presencas alem do prazo.

Dado pessoal nao deve ser guardado por mais tempo do que a finalidade que o
justificou (LGPD art. 15 e 16). O prazo vem de RETENCAO_PRESENCAS_DIAS.

Uso:
    python -m scripts.expurgar_presencas            # simula
    python -m scripts.expurgar_presencas --apply    # efetiva

Feito para rodar agendado (cron, Agendador de Tarefas). Nao requer camera
nem DeepFace.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.use_cases.expurgar_presencas import (  # noqa: E402
    ExpurgarPresencas,
)
from src.config.logging import configurar_logging  # noqa: E402
from src.config.settings import get_settings  # noqa: E402
from src.infrastructure.database.engine import criar_engine  # noqa: E402
from src.infrastructure.repositories.postgres_presenca_repository import (  # noqa: E402
    PostgresPresencaRepository,
)


class _RepositorioSimulado:
    """Conta o que seria apagado, sem apagar. Usado no modo padrao."""

    def __init__(self, real: PostgresPresencaRepository) -> None:
        self._real = real
        self.contadas = 0

    def expurgar_anteriores_a(self, dia: object) -> int:
        from sqlalchemy import func, select

        from src.infrastructure.database import models
        from src.infrastructure.database.engine import sessao

        with sessao(self._real._engine) as session:  # noqa: SLF001
            self.contadas = int(
                session.scalar(
                    select(func.count())
                    .select_from(models.Presenca)
                    .where(models.Presenca.data_referencia < dia)
                )
                or 0
            )
        return self.contadas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expurgo de presencas antigas")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="efetiva a remocao (sem esta flag, apenas conta)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configurar_logging(settings.log_level)

    engine = criar_engine(settings.database_url)
    repositorio: object = PostgresPresencaRepository(engine)
    if not args.apply:
        repositorio = _RepositorioSimulado(repositorio)  # type: ignore[arg-type]

    caso = ExpurgarPresencas(
        repositorio,  # type: ignore[arg-type]
        tz=settings.timezone,
        retencao_dias=settings.retencao_presencas_dias,
    )

    modo = "APLICADO" if args.apply else "SIMULACAO (nada foi removido)"
    print(f"\n=== EXPURGO DE PRESENCAS -- {modo} ===")

    if not caso.ativo:
        print("Retencao desligada (RETENCAO_PRESENCAS_DIAS = 0). Nada a fazer.\n")
        return 0

    limite = caso.limite()
    afetadas = caso.executar()

    print(f"Prazo de retencao: {settings.retencao_presencas_dias} dias")
    print(f"Corte: presencas anteriores a {limite}")
    print(f"Linhas {'removidas' if args.apply else 'que seriam removidas'}: {afetadas}")
    if not args.apply:
        print("Repita com --apply para efetivar.\n")
    else:
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
