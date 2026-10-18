"""Cria a primeira conta administrativa por prompt local explicito.

Executar manualmente com ``python -m scripts.criar_admin_web``. O comando nao
aceita usuario/senha como argumentos e nunca registra a senha.
"""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.web_settings import get_web_settings
from src.infrastructure.repositories.postgres_conta_repository import (
    BootstrapJaConfigurado,
    PostgresContaRepository,
)


def main(argv: list[str] | None = None) -> int:
    argumentos = sys.argv[1:] if argv is None else argv
    if argumentos:
        print(
            "Este comando nao aceita argumentos; informe os dados nos prompts locais.",
            file=sys.stderr,
        )
        return 2

    usuario = input("Usuario do administrador inicial: ").strip()
    senha = getpass.getpass("Senha (nao sera exibida): ")
    confirmacao = getpass.getpass("Confirme a senha: ")
    if senha != confirmacao:
        print("As senhas nao conferem.", file=sys.stderr)
        return 2

    engine = None
    try:
        settings = get_web_settings()
        engine = create_engine(
            settings.database_url.get_secret_value(), future=True, pool_pre_ping=True
        )
        factory: sessionmaker[Session] = sessionmaker(
            bind=engine, expire_on_commit=False, future=True
        )
        repository = PostgresContaRepository(
            factory,
            segredo=settings.secret_key.get_secret_value(),
        )
        conta_id = repository.criar_admin_bootstrap(usuario, senha)
    except BootstrapJaConfigurado:
        print("Bootstrap ja realizado; nenhuma conta ou senha foi alterada.")
        return 0
    except Exception:
        print(
            "Bootstrap nao concluido; confira configuracao, banco e politica de senha.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    print(f"Conta administrativa inicial configurada (id {conta_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
