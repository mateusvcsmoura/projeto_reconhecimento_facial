"""Preparacoes biometricas internas para cadastro web.

Estes objetos sao contratos entre worker/application e persistencia. Nunca
devem ser retornados por consultas destinadas a professores ou clientes HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.face_embedding import FaceEmbedding


@dataclass(frozen=True, slots=True)
class PreparacaoReferencia:
    ordinal: int
    captura_id: str
    recorte: bytes
    embedding: FaceEmbedding


@dataclass(frozen=True, slots=True)
class ReferenciaParaPersistir:
    ordinal: int
    caminho_privado_relativo: str
    embedding: FaceEmbedding


def validar_tres_referencias(
    preparacoes: tuple[PreparacaoReferencia, ...] | list[PreparacaoReferencia],
) -> tuple[PreparacaoReferencia, ...]:
    if len(preparacoes) != 3:
        raise ValueError("São necessárias exatamente três referências.")
    if {item.ordinal for item in preparacoes} != {1, 2, 3}:
        raise ValueError("Os ordinais das referências devem ser 1, 2 e 3.")
    capturas = {item.captura_id.strip() for item in preparacoes}
    if len(capturas) != 3 or "" in capturas:
        raise ValueError("Cada referência deve vir de uma captura distinta.")
    if len({item.recorte for item in preparacoes}) != 3:
        raise ValueError("Cada referência deve conter um recorte distinto.")

    modelos = {item.embedding.modelo.strip() for item in preparacoes}
    if len(modelos) != 1 or not next(iter(modelos)):
        raise ValueError("As referências devem usar o mesmo modelo de embedding.")

    canonicas: list[PreparacaoReferencia] = []
    for item in sorted(preparacoes, key=lambda referencia: referencia.ordinal):
        if not item.recorte:
            raise ValueError("O recorte facial não pode ser vazio.")
        if item.embedding.dimensao != 512:
            raise ValueError("Cada embedding facial deve possuir dimensão 512.")
        embedding = FaceEmbedding.de_valores(
            item.embedding.vetor, item.embedding.modelo.strip()
        )
        canonicas.append(
            PreparacaoReferencia(
                ordinal=item.ordinal,
                captura_id=item.captura_id.strip(),
                recorte=bytes(item.recorte),
                embedding=embedding,
            )
        )
    return tuple(canonicas)
