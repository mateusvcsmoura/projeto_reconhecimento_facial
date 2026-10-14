"""Framing binario privado entre a aplicacao e o worker local de landmarks."""

from __future__ import annotations

import json
import struct
from typing import Any

MAX_HEADER_BYTES = 1024 * 1024
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024


def escrever_mensagem(
    stream: Any, cabecalho: dict[str, Any], payload: bytes = b""
) -> None:
    """Escreve um cabeçalho JSON com comprimento e um payload binário opcional."""
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("Payload do worker excede o limite do protocolo")
    dados_cabecalho = dict(cabecalho)
    dados_cabecalho["payload_bytes"] = len(payload)
    serializado = json.dumps(dados_cabecalho, separators=(",", ":")).encode("utf-8")
    if len(serializado) > MAX_HEADER_BYTES:
        raise ValueError("Cabeçalho do worker excede o limite do protocolo")

    mensagem = struct.pack("<I", len(serializado)) + serializado + payload
    offset = 0
    while offset < len(mensagem):
        escritos = stream.write(mensagem[offset:])
        if escritos is None or escritos <= 0:
            raise BrokenPipeError("Pipe local do worker foi fechado")
        offset += escritos
    stream.flush()


def ler_mensagem(stream: Any) -> tuple[dict[str, Any], bytes] | None:
    """Lê uma mensagem enquadrada; retorna None somente no EOF entre mensagens."""
    prefixo = _ler_exatamente(stream, 4, aceitar_eof=True)
    if prefixo is None:
        return None
    tamanho_cabecalho = struct.unpack("<I", prefixo)[0]
    if not 0 < tamanho_cabecalho <= MAX_HEADER_BYTES:
        raise ValueError("Comprimento inválido no protocolo de landmarks")

    bytes_cabecalho = _ler_exatamente(stream, tamanho_cabecalho)
    assert bytes_cabecalho is not None
    cabecalho = json.loads(bytes_cabecalho.decode("utf-8"))
    if not isinstance(cabecalho, dict):
        raise ValueError("Cabeçalho inválido no protocolo de landmarks")

    tamanho_payload = cabecalho.get("payload_bytes", 0)
    if (
        isinstance(tamanho_payload, bool)
        or not isinstance(tamanho_payload, int)
        or not 0 <= tamanho_payload <= MAX_PAYLOAD_BYTES
    ):
        raise ValueError("Comprimento inválido no payload de landmarks")
    payload = _ler_exatamente(stream, tamanho_payload)
    assert payload is not None
    return cabecalho, payload


def _ler_exatamente(
    stream: Any, tamanho: int, *, aceitar_eof: bool = False
) -> bytes | None:
    partes = bytearray()
    while len(partes) < tamanho:
        parte = stream.read(tamanho - len(partes))
        if not parte:
            if aceitar_eof and not partes:
                return None
            raise EOFError("Pipe local terminou no meio de uma mensagem")
        partes.extend(parte)
    return bytes(partes)
