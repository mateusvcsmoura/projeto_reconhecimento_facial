"""Chaves HMAC e origem do cliente para limites HTTP persistidos."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Protocol

from fastapi import Request

JANELA_RATE_LIMIT = timedelta(minutes=1)


class RepositorioRateLimit(Protocol):
    def limitar_requisicao(
        self,
        chave_hash: str,
        *,
        agora: datetime,
        limite: int,
        janela: timedelta,
    ) -> int | None: ...


@lru_cache(maxsize=32)
def _redes_confiaveis(
    cidr_texto: str,
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    redes = []
    for item in cidr_texto.split(","):
        if item.strip():
            redes.append(ipaddress.ip_network(item.strip(), strict=False))
    return tuple(redes)


def endereco_cliente(request: Request, trusted_proxy_cidrs: str | None) -> str:
    """Resolve IP por X-Forwarded-For somente quando o peer é proxy confiável."""

    peer = request.client.host if request.client is not None else None
    if peer is None:
        return "desconhecido"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return "desconhecido"

    if not trusted_proxy_cidrs:
        return str(peer_ip)
    redes = _redes_confiaveis(trusted_proxy_cidrs)
    if not any(peer_ip in rede for rede in redes):
        return str(peer_ip)

    encaminhados = request.headers.get("x-forwarded-for", "")
    if not encaminhados:
        return str(peer_ip)
    partes = encaminhados.split(",")
    if len(partes) > 32:
        return str(peer_ip)
    try:
        cadeia = [ipaddress.ip_address(item.strip()) for item in partes]
    except ValueError:
        return str(peer_ip)

    for endereco in reversed((*cadeia, peer_ip)):
        if not any(endereco in rede for rede in redes):
            return str(endereco)
    return str(peer_ip)


def bearer_token(request: Request) -> str | None:
    esquema, separador, valor = request.headers.get("authorization", "").partition(" ")
    if esquema.lower() != "bearer" or not separador or not valor.strip():
        return None
    token = valor.strip()
    return token if len(token) <= 256 else None


def aplicar_limite(
    repository: RepositorioRateLimit,
    secret: bytes,
    *,
    namespace: str,
    origin: str,
    context: str,
    now: datetime,
    limit: int,
) -> int | None:
    """Persiste contador somente com HMAC; token e endereço nunca são gravados."""

    if len(secret) < 32 or limit < 1 or not namespace:
        raise ValueError("A configuração do rate limit é inválida.")
    payload = json.dumps(
        ["facediff-web-rate-v1", namespace, origin, context],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return repository.limitar_requisicao(
        digest,
        agora=now,
        limite=limit,
        janela=JANELA_RATE_LIMIT,
    )
