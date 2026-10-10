"""Logica pura da avaliacao experimental de identificacao facial 1:N.

Este modulo nao importa webcam, DeepFace, banco ou configuracao operacional.
Os identificadores recebidos devem ser pseudonimos mantidos somente em memoria.
"""

from __future__ import annotations

import math
import random
import statistics
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from scripts.divisao_por_identidade import (
    Divisao,
    dividir_por_identidade,
)
from src.domain.entities.face_embedding import FaceEmbedding

LIMIAR_HISTORICO = 0.30
LIMIAR_ETAPA_1 = 0.42817932706540435
DISTANCIA_QUASE_DUPLICATA = 0.01
TOLERANCIA_EMPATE = 1e-12


class EstrategiaGaleria(StrEnum):
    """Forma de resumir varias referencias da mesma identidade."""

    MENOR_DISTANCIA = "menor_distancia"
    CENTROIDE = "centroide"


class FaseProtocolo(StrEnum):
    VALIDACAO = "validacao"
    TESTE = "teste"


class MotivoIdentificacao(StrEnum):
    IDENTIFICADA = "identificada"
    ACIMA_DO_LIMIAR = "acima_do_limiar"
    EMPATE = "empate"
    GALERIA_VAZIA = "galeria_vazia"
    REFERENCIA_INDISPONIVEL = "referencia_indisponivel"
    FALHA_EXTRACAO = "falha_extracao"


@dataclass(frozen=True, slots=True)
class Amostra:
    """Uma imagem representada por embedding ou por uma falha contabilizavel."""

    identidade_id: str
    imagem_id: str
    embedding: FaceEmbedding | None
    falha_extracao: str | None = None

    def __post_init__(self) -> None:
        if not self.identidade_id.strip() or not self.imagem_id.strip():
            raise ValueError("A amostra exige IDs opacos de identidade e imagem.")
        if (self.embedding is None) == (self.falha_extracao is None):
            raise ValueError(
                "A amostra exige exatamente um embedding valido ou motivo de falha."
            )
        if self.falha_extracao is not None and not self.falha_extracao.strip():
            raise ValueError("O motivo da falha de extracao nao pode estar vazio.")


@dataclass(frozen=True, slots=True)
class Predicao:
    candidato_id: str | None
    identidade_aceita: str | None
    distancia: float | None
    motivo: MotivoIdentificacao


@dataclass(frozen=True, slots=True)
class Protocolo:
    """Galeria planejada e consultas de uma particao externa de identidades."""

    identidades_conhecidas: tuple[str, ...]
    identidades_desconhecidas: tuple[str, ...]
    identidades_insuficientes: tuple[str, ...]
    referencias: tuple[Amostra, ...]
    consultas_conhecidas: tuple[Amostra, ...]
    consultas_desconhecidas: tuple[Amostra, ...]
    fase: FaseProtocolo = FaseProtocolo.VALIDACAO

    def __post_init__(self) -> None:
        conhecidas = set(self.identidades_conhecidas)
        desconhecidas = set(self.identidades_desconhecidas)
        if conhecidas & desconhecidas:
            raise ValueError("Uma identidade nao pode ser conhecida e desconhecida.")
        if not {a.identidade_id for a in self.referencias} <= conhecidas:
            raise ValueError("A galeria contem identidade fora do grupo conhecido.")
        if not {a.identidade_id for a in self.consultas_conhecidas} <= conhecidas:
            raise ValueError("Consulta conhecida fora do grupo conhecido.")
        if not {a.identidade_id for a in self.consultas_desconhecidas} <= desconhecidas:
            raise ValueError("Consulta desconhecida fora do grupo desconhecido.")
        imagens_referencia = {a.imagem_id for a in self.referencias}
        imagens_consulta = {
            a.imagem_id
            for a in (*self.consultas_conhecidas, *self.consultas_desconhecidas)
        }
        if imagens_referencia & imagens_consulta:
            raise ValueError("Uma imagem nao pode ser referencia e consulta.")


@dataclass(frozen=True, slots=True)
class ObservacaoConsulta:
    """Registro transitório por consulta; nunca serializar IDs individualmente."""

    identidade_id: str
    conhecida: bool
    extracao_valida: bool
    candidato_correto: bool
    identificacao_correta: bool
    identificacao_aceita: bool
    troca_identidade: bool
    motivo: MotivoIdentificacao
    distancia_candidata: float | None


@dataclass(frozen=True, slots=True)
class ContagensDeErro:
    identificacao_correta: int
    rejeicao_conhecido_limiar: int
    troca_identidade: int
    rejeicao_desconhecido: int
    falsa_identificacao_desconhecido: int
    falha_extracao_consulta: int
    falha_extracao_referencia: int
    galeria_vazia: int
    empate: int
    identidade_conhecida_sem_referencia: int
    referencia_indisponivel: int


@dataclass(frozen=True, slots=True)
class MetricasIdentificacao:
    consultas_conhecidas: int
    consultas_conhecidas_extraidas: int
    consultas_desconhecidas: int
    consultas_desconhecidas_extraidas: int
    fpir_end_to_end: float | None
    fpir_condicional_extracao: float | None
    fnir_end_to_end: float | None
    fnir_condicional_extracao: float | None
    identificacao_correta_end_to_end: float | None
    top1_accuracy_end_to_end: float | None
    top1_accuracy_condicional_extracao: float | None
    rejeicao_desconhecido_end_to_end: float | None
    rejeicao_desconhecido_condicional_extracao: float | None


@dataclass(frozen=True, slots=True)
class RelatorioIdentificacao:
    metricas: MetricasIdentificacao
    erros: ContagensDeErro
    tamanho_galeria: int
    referencias_validas: int
    tempo_comparacao_ms_por_consulta: float
    tempo_decisao_ms_por_consulta: float
    observacoes: tuple[ObservacaoConsulta, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class SelecaoLimiar:
    limiar: float | None
    fpir_validacao: float | None
    fnir_validacao: float | None
    consultas_desconhecidas: int
    identidades_desconhecidas: int
    suficiencia: str


@dataclass(frozen=True, slots=True)
class IntervaloConfianca:
    pontual: float
    inferior: float
    superior: float
    identidades: int
    consultas: int
    limite_superior_regra_tres: float | None


def _vetor_unitario(embedding: FaceEmbedding) -> np.ndarray:
    vetor = np.asarray(embedding.vetor, dtype=np.float64)
    if vetor.ndim != 1 or vetor.size == 0:
        raise ValueError("O embedding deve ser um vetor unidimensional nao vazio.")
    if not np.all(np.isfinite(vetor)):
        raise ValueError("O embedding deve conter somente valores finitos.")
    norma = float(np.linalg.norm(vetor))
    if not math.isfinite(norma) or norma == 0.0:
        raise ValueError("O embedding deve ter norma finita e positiva.")
    return vetor / norma


def _validar_limiar(limiar: float) -> None:
    if not math.isfinite(limiar) or not 0.0 <= limiar <= 2.0:
        raise ValueError(
            f"O limiar de distancia cosseno deve estar em [0, 2]: {limiar}."
        )


class Galeria:
    """Referencias vetorizadas por identidade para uma configuracao de modelo."""

    def __init__(
        self,
        identidades_configuradas: frozenset[str],
        vetores: Mapping[str, np.ndarray],
        modelo: str | None,
        dimensao: int | None,
        estrategia: EstrategiaGaleria,
        referencias_validas: int,
    ) -> None:
        self._identidades_configuradas = identidades_configuradas
        self._vetores = dict(vetores)
        self._modelo = modelo
        self._dimensao = dimensao
        self.estrategia = estrategia
        self.referencias_validas = referencias_validas

    @classmethod
    def criar(
        cls,
        referencias: Iterable[Amostra],
        estrategia: EstrategiaGaleria = EstrategiaGaleria.MENOR_DISTANCIA,
    ) -> Galeria:
        grupos: dict[str, list[np.ndarray]] = defaultdict(list)
        identidades_configuradas: set[str] = set()
        modelos: set[str] = set()
        dimensoes: set[int] = set()
        imagens: set[str] = set()

        for amostra in referencias:
            identidades_configuradas.add(amostra.identidade_id)
            if amostra.imagem_id in imagens:
                raise ValueError("Uma imagem nao pode aparecer duas vezes na galeria.")
            imagens.add(amostra.imagem_id)
            if amostra.embedding is None:
                continue
            vetor = _vetor_unitario(amostra.embedding)
            modelos.add(amostra.embedding.modelo)
            dimensoes.add(int(vetor.size))
            grupos[amostra.identidade_id].append(vetor)

        if len(modelos) > 1:
            raise ValueError("A galeria mistura modelos de embedding incompatíveis.")
        if len(dimensoes) > 1:
            raise ValueError("A galeria mistura dimensoes de embedding incompatíveis.")

        vetores: dict[str, np.ndarray] = {}
        for identidade, grupo in grupos.items():
            matriz = np.vstack(grupo)
            if estrategia is EstrategiaGaleria.CENTROIDE:
                centroide = np.mean(matriz, axis=0)
                norma = float(np.linalg.norm(centroide))
                if not math.isfinite(norma) or norma == 0.0:
                    raise ValueError(
                        "O centroide da identidade nao pode ser normalizado."
                    )
                matriz = (centroide / norma).reshape(1, -1)
            vetores[identidade] = matriz

        return cls(
            frozenset(identidades_configuradas),
            vetores,
            next(iter(modelos), None),
            next(iter(dimensoes), None),
            estrategia,
            sum(len(grupo) for grupo in grupos.values()),
        )

    @property
    def identidades(self) -> tuple[str, ...]:
        """Identidades que possuem ao menos uma referencia valida."""
        return tuple(sorted(self._vetores))

    @property
    def identidades_configuradas(self) -> tuple[str, ...]:
        return tuple(sorted(self._identidades_configuradas))

    def distancias(self, consulta: FaceEmbedding) -> dict[str, float]:
        """Calcula a menor distancia ou a distancia ao centroide por identidade."""
        vetor = _vetor_unitario(consulta)
        if not self._vetores:
            return {}
        if consulta.modelo != self._modelo:
            raise ValueError("O modelo da consulta e da galeria deve ser igual.")
        if vetor.size != self._dimensao:
            raise ValueError("A dimensao da consulta e da galeria deve ser igual.")

        distancias: dict[str, float] = {}
        for identidade, referencias in self._vetores.items():
            similaridades = np.clip(referencias @ vetor, -1.0, 1.0)
            valores = np.clip(1.0 - similaridades, 0.0, 2.0)
            distancias[identidade] = float(np.min(valores))
        return distancias

    def identificar(self, consulta: FaceEmbedding, limiar: float) -> Predicao:
        _validar_limiar(limiar)
        return _decidir_distancias(
            self.distancias(consulta),
            self._identidades_configuradas,
            limiar,
        )


def dividir_identidades(identidades: Iterable[str], seed: int = 42) -> Divisao:
    """Divide identidades antes de construir enrollment ou consultas."""
    return dividir_por_identidade(identidades, seed=seed)


def _amostrar_por_identidade(
    amostras: Sequence[Amostra],
    quantidade: int,
    seed: int,
    identidade: str,
    papel: str,
) -> tuple[Amostra, ...]:
    ordenadas = sorted(amostras, key=lambda amostra: amostra.imagem_id)
    if len(ordenadas) <= quantidade:
        return tuple(ordenadas)
    gerador = random.Random(f"{seed}:{papel}:{identidade}")
    escolhidas = gerador.sample(ordenadas, quantidade)
    return tuple(sorted(escolhidas, key=lambda amostra: amostra.imagem_id))


def construir_protocolo(
    amostras: Sequence[Amostra],
    identidades: Iterable[str],
    seed: int = 42,
    referencias_por_identidade: int = 1,
    fracao_desconhecidas: float = 0.2,
    max_consultas_por_identidade: int = 5,
    fase: FaseProtocolo = FaseProtocolo.VALIDACAO,
) -> Protocolo:
    """Particiona imagens em enrollment/consulta sem cruzar imagens ou papéis.

    Identidades com menos imagens do que ``referencias_por_identidade + 1``
    ficam no grupo desconhecido. Assim nenhuma imagem é reutilizada para
    construir uma consulta conhecida da própria referência.
    """
    if referencias_por_identidade < 1 or max_consultas_por_identidade < 1:
        raise ValueError("Referencias e consultas por identidade devem ser positivas.")
    if not math.isfinite(fracao_desconhecidas) or not 0.0 < fracao_desconhecidas < 1.0:
        raise ValueError("A fracao de identidades desconhecidas deve estar em (0, 1).")

    ids = sorted(identidades)
    if len(ids) != len(set(ids)):
        raise ValueError("Ha identidades repetidas no protocolo.")
    if len(ids) < 2:
        raise ValueError("Sao necessarias identidades conhecidas e desconhecidas.")
    if len({amostra.imagem_id for amostra in amostras}) != len(amostras):
        raise ValueError("Ha IDs de imagem repetidos no protocolo.")

    por_identidade: dict[str, list[Amostra]] = defaultdict(list)
    for amostra in amostras:
        if amostra.identidade_id not in set(ids):
            raise ValueError("A amostra contem identidade fora do conjunto recebido.")
        por_identidade[amostra.identidade_id].append(amostra)
    if set(por_identidade) != set(ids):
        raise ValueError(
            "Cada identidade do protocolo precisa ter ao menos uma imagem."
        )

    elegiveis_conhecidas = sorted(
        identidade
        for identidade, grupo in por_identidade.items()
        if len(grupo) >= referencias_por_identidade + 1
    )
    insuficientes = sorted(set(ids) - set(elegiveis_conhecidas))
    if not elegiveis_conhecidas:
        raise ValueError("Dados insuficientes para criar uma identidade conhecida.")

    quantidade_desconhecidas = max(1, math.ceil(len(ids) * fracao_desconhecidas))
    # Mantem ao menos uma identidade na galeria; identidades com poucas
    # imagens contam primeiro como consultas desconhecidas.
    quantidade_elegiveis_desconhecidas = max(
        0, quantidade_desconhecidas - len(insuficientes)
    )
    quantidade_elegiveis_desconhecidas = min(
        quantidade_elegiveis_desconhecidas, len(elegiveis_conhecidas) - 1
    )
    gerador = random.Random(seed)
    embaralhadas = list(elegiveis_conhecidas)
    gerador.shuffle(embaralhadas)
    ids_desconhecidos = set(insuficientes)
    ids_desconhecidos.update(embaralhadas[:quantidade_elegiveis_desconhecidas])
    ids_conhecidos = set(elegiveis_conhecidas) - ids_desconhecidos
    if not ids_desconhecidos or not ids_conhecidos:
        raise ValueError(
            "Dados insuficientes para consultas conhecidas e desconhecidas."
        )

    referencias: list[Amostra] = []
    consultas_conhecidas: list[Amostra] = []
    consultas_desconhecidas: list[Amostra] = []
    for identidade in sorted(ids_conhecidos):
        grupo = sorted(por_identidade[identidade], key=lambda a: a.imagem_id)
        refs = _amostrar_por_identidade(
            grupo, referencias_por_identidade, seed, identidade, "referencia"
        )
        ids_refs = {amostra.imagem_id for amostra in refs}
        consultas = [amostra for amostra in grupo if amostra.imagem_id not in ids_refs]
        referencias.extend(refs)
        consultas_conhecidas.extend(
            _amostrar_por_identidade(
                consultas,
                max_consultas_por_identidade,
                seed,
                identidade,
                "consulta-conhecida",
            )
        )

    for identidade in sorted(ids_desconhecidos):
        consultas_desconhecidas.extend(
            _amostrar_por_identidade(
                por_identidade[identidade],
                max_consultas_por_identidade,
                seed,
                identidade,
                "consulta-desconhecida",
            )
        )

    return Protocolo(
        identidades_conhecidas=tuple(sorted(ids_conhecidos)),
        identidades_desconhecidas=tuple(sorted(ids_desconhecidos)),
        identidades_insuficientes=tuple(insuficientes),
        referencias=tuple(referencias),
        consultas_conhecidas=tuple(consultas_conhecidas),
        consultas_desconhecidas=tuple(consultas_desconhecidas),
        fase=fase,
    )


def reduzir_referencias(protocolo: Protocolo, quantidade: int) -> Protocolo:
    """Projeta um protocolo para menos referências sem trocar consultas.

    Usado para comparar galerias de uma e várias referências com as mesmas
    identidades e consultas. Para cada identidade, prefere uma referência
    extraída válida; falhas permanecem representadas se nenhuma for válida.
    """
    if quantidade < 1:
        raise ValueError("A quantidade de referências deve ser positiva.")
    por_identidade: dict[str, list[Amostra]] = defaultdict(list)
    for referencia in protocolo.referencias:
        por_identidade[referencia.identidade_id].append(referencia)
    if set(por_identidade) != set(protocolo.identidades_conhecidas):
        raise ValueError("Cada identidade conhecida precisa ter referências.")
    if any(len(referencias) < quantidade for referencias in por_identidade.values()):
        raise ValueError(
            "O protocolo não possui referências suficientes por identidade."
        )

    selecionadas: list[Amostra] = []
    for identidade in protocolo.identidades_conhecidas:
        referencias = por_identidade[identidade]
        validas = [
            referencia for referencia in referencias if referencia.embedding is not None
        ]
        invalidas = [
            referencia for referencia in referencias if referencia.embedding is None
        ]
        elegiveis = sorted(validas, key=lambda amostra: amostra.imagem_id) + sorted(
            invalidas, key=lambda amostra: amostra.imagem_id
        )
        selecionadas.extend(elegiveis[:quantidade])
    return Protocolo(
        identidades_conhecidas=protocolo.identidades_conhecidas,
        identidades_desconhecidas=protocolo.identidades_desconhecidas,
        identidades_insuficientes=protocolo.identidades_insuficientes,
        referencias=tuple(selecionadas),
        consultas_conhecidas=protocolo.consultas_conhecidas,
        consultas_desconhecidas=protocolo.consultas_desconhecidas,
        fase=protocolo.fase,
    )


def _decidir_distancias(
    distancias: Mapping[str, float],
    identidades_configuradas: frozenset[str],
    limiar: float,
) -> Predicao:
    if not distancias:
        motivo = (
            MotivoIdentificacao.GALERIA_VAZIA
            if not identidades_configuradas
            else MotivoIdentificacao.REFERENCIA_INDISPONIVEL
        )
        return Predicao(None, None, None, motivo)

    menor = min(distancias.values())
    candidatos = sorted(
        identidade
        for identidade, distancia in distancias.items()
        if math.isclose(distancia, menor, rel_tol=0.0, abs_tol=TOLERANCIA_EMPATE)
    )
    if len(candidatos) != 1:
        return Predicao(None, None, menor, MotivoIdentificacao.EMPATE)

    candidato = candidatos[0]
    if menor > limiar:
        return Predicao(candidato, None, menor, MotivoIdentificacao.ACIMA_DO_LIMIAR)
    return Predicao(candidato, candidato, menor, MotivoIdentificacao.IDENTIFICADA)


def _razao(numerador: int, denominador: int) -> float | None:
    return float(numerador / denominador) if denominador else None


def avaliar_protocolo(
    protocolo: Protocolo,
    limiar: float,
    estrategia: EstrategiaGaleria = EstrategiaGaleria.MENOR_DISTANCIA,
    tamanho_galeria: int | None = None,
) -> RelatorioIdentificacao:
    """Avalia consultas do protocolo e mantém IDs individuais só em memória."""
    _validar_limiar(limiar)
    if tamanho_galeria is not None and tamanho_galeria < 1:
        raise ValueError("O tamanho da galeria deve ser positivo ou None.")

    identidades = protocolo.identidades_conhecidas
    if tamanho_galeria is not None:
        identidades = identidades[:tamanho_galeria]
    permitidas = set(identidades)
    excluidas_da_galeria = set(protocolo.identidades_conhecidas) - permitidas
    referencias = tuple(
        amostra
        for amostra in protocolo.referencias
        if amostra.identidade_id in permitidas
    )
    conhecidas = tuple(
        consulta
        for consulta in protocolo.consultas_conhecidas
        if consulta.identidade_id in permitidas
    )
    # Ao simular uma galeria menor, identidades removidas deixam de ser
    # cadastradas e suas consultas passam a representar pessoas desconhecidas.
    desconhecidas = tuple(protocolo.consultas_desconhecidas) + tuple(
        consulta
        for consulta in protocolo.consultas_conhecidas
        if consulta.identidade_id in excluidas_da_galeria
    )
    galeria = Galeria.criar(referencias, estrategia)
    observacoes: list[ObservacaoConsulta] = []
    motivos: list[MotivoIdentificacao] = []
    tempos_comparacao: list[float] = []
    tempos_decisao: list[float] = []

    for conhecida, consultas in ((True, conhecidas), (False, desconhecidas)):
        for consulta in consultas:
            inicio_decisao = time.perf_counter_ns()
            if consulta.embedding is None:
                predicao = Predicao(
                    None, None, None, MotivoIdentificacao.FALHA_EXTRACAO
                )
                tempo_comparacao_ns = 0
            else:
                inicio_comparacao = time.perf_counter_ns()
                distancias = galeria.distancias(consulta.embedding)
                tempo_comparacao_ns = time.perf_counter_ns() - inicio_comparacao
                predicao = _decidir_distancias(
                    distancias,
                    frozenset(galeria.identidades_configuradas),
                    limiar,
                )
            tempos_decisao.append(time.perf_counter_ns() - inicio_decisao)
            tempos_comparacao.append(float(tempo_comparacao_ns))
            motivo = predicao.motivo
            motivos.append(motivo)
            candidato_correto = (
                predicao.candidato_id == consulta.identidade_id
                if consulta.embedding is not None
                else False
            )
            correta = predicao.identidade_aceita == consulta.identidade_id
            aceita = predicao.identidade_aceita is not None
            troca = conhecida and aceita and not correta
            observacoes.append(
                ObservacaoConsulta(
                    identidade_id=consulta.identidade_id,
                    conhecida=conhecida,
                    extracao_valida=consulta.embedding is not None,
                    candidato_correto=candidato_correto,
                    identificacao_correta=correta,
                    identificacao_aceita=aceita,
                    troca_identidade=troca,
                    motivo=motivo,
                    distancia_candidata=predicao.distancia,
                )
            )

    conhecidas_obs = [obs for obs in observacoes if obs.conhecida]
    desconhecidas_obs = [obs for obs in observacoes if not obs.conhecida]
    conhecidas_extraidas = sum(obs.extracao_valida for obs in conhecidas_obs)
    desconhecidas_extraidas = sum(obs.extracao_valida for obs in desconhecidas_obs)
    corretas = sum(obs.identificacao_correta for obs in conhecidas_obs)
    top1_corretos = sum(obs.candidato_correto for obs in conhecidas_obs)
    falsas_identificacoes = sum(obs.identificacao_aceita for obs in desconhecidas_obs)
    rejeicoes_desconhecidas = sum(
        obs.extracao_valida and not obs.identificacao_aceita
        for obs in desconhecidas_obs
    )

    metricas = MetricasIdentificacao(
        consultas_conhecidas=len(conhecidas_obs),
        consultas_conhecidas_extraidas=conhecidas_extraidas,
        consultas_desconhecidas=len(desconhecidas_obs),
        consultas_desconhecidas_extraidas=desconhecidas_extraidas,
        fpir_end_to_end=_razao(falsas_identificacoes, len(desconhecidas_obs)),
        fpir_condicional_extracao=_razao(
            falsas_identificacoes, desconhecidas_extraidas
        ),
        fnir_end_to_end=_razao(len(conhecidas_obs) - corretas, len(conhecidas_obs)),
        fnir_condicional_extracao=_razao(
            conhecidas_extraidas - corretas, conhecidas_extraidas
        ),
        identificacao_correta_end_to_end=_razao(corretas, len(conhecidas_obs)),
        top1_accuracy_end_to_end=_razao(top1_corretos, len(conhecidas_obs)),
        top1_accuracy_condicional_extracao=_razao(top1_corretos, conhecidas_extraidas),
        rejeicao_desconhecido_end_to_end=_razao(
            rejeicoes_desconhecidas, len(desconhecidas_obs)
        ),
        rejeicao_desconhecido_condicional_extracao=_razao(
            rejeicoes_desconhecidas, desconhecidas_extraidas
        ),
    )
    contagens = ContagensDeErro(
        identificacao_correta=corretas,
        rejeicao_conhecido_limiar=sum(
            obs.conhecida and obs.motivo is MotivoIdentificacao.ACIMA_DO_LIMIAR
            for obs in observacoes
        ),
        troca_identidade=sum(obs.troca_identidade for obs in observacoes),
        rejeicao_desconhecido=rejeicoes_desconhecidas,
        falsa_identificacao_desconhecido=falsas_identificacoes,
        falha_extracao_consulta=sum(
            obs.motivo is MotivoIdentificacao.FALHA_EXTRACAO for obs in observacoes
        ),
        falha_extracao_referencia=sum(
            amostra.embedding is None for amostra in referencias
        ),
        galeria_vazia=sum(
            motivo is MotivoIdentificacao.GALERIA_VAZIA for motivo in motivos
        ),
        empate=sum(motivo is MotivoIdentificacao.EMPATE for motivo in motivos),
        identidade_conhecida_sem_referencia=sum(
            obs.conhecida and obs.identidade_id not in galeria.identidades
            for obs in observacoes
        ),
        referencia_indisponivel=sum(
            motivo is MotivoIdentificacao.REFERENCIA_INDISPONIVEL for motivo in motivos
        ),
    )
    divisor = len(observacoes)
    mediana_tempo_comparacao_ms = (
        statistics.median(tempos_comparacao) / 1_000_000 if divisor else 0.0
    )
    mediana_tempo_decisao_ms = (
        statistics.median(tempos_decisao) / 1_000_000 if divisor else 0.0
    )
    return RelatorioIdentificacao(
        metricas=metricas,
        erros=contagens,
        tamanho_galeria=len(galeria.identidades),
        referencias_validas=galeria.referencias_validas,
        tempo_comparacao_ms_por_consulta=mediana_tempo_comparacao_ms,
        tempo_decisao_ms_por_consulta=mediana_tempo_decisao_ms,
        observacoes=tuple(observacoes),
    )


def selecionar_limiar_fpir(
    validacao: Protocolo,
    far_maximo: float = 0.001,
    estrategia: EstrategiaGaleria = EstrategiaGaleria.MENOR_DISTANCIA,
    tamanho_galeria: int | None = None,
) -> SelecaoLimiar:
    """Seleciona T2 na validação; não aceita nem referencia um conjunto de teste."""
    if validacao.fase is not FaseProtocolo.VALIDACAO:
        raise ValueError("A seleção de limiar só aceita protocolos de validação.")
    if not math.isfinite(far_maximo) or not 0.0 <= far_maximo <= 1.0:
        raise ValueError("O teto de FPIR deve estar em [0, 1].")

    relatorio_base = avaliar_protocolo(
        validacao,
        limiar=2.0,
        estrategia=estrategia,
        tamanho_galeria=tamanho_galeria,
    )
    scores_desconhecidos = [
        obs
        for obs in relatorio_base.observacoes
        if not obs.conhecida and obs.extracao_valida
    ]
    ids_desconhecidos = {obs.identidade_id for obs in scores_desconhecidos}
    identidades_na_galeria = (
        set(validacao.identidades_conhecidas)
        if tamanho_galeria is None
        else set(validacao.identidades_conhecidas[:tamanho_galeria])
    )
    candidatos = [
        amostra
        for amostra in (
            *validacao.consultas_desconhecidas,
            *(
                consulta
                for consulta in validacao.consultas_conhecidas
                if consulta.identidade_id not in identidades_na_galeria
            ),
        )
        if amostra.embedding is not None
    ]
    conhecidas = [
        amostra
        for amostra in validacao.consultas_conhecidas
        if amostra.embedding is not None
        and amostra.identidade_id in identidades_na_galeria
    ]
    if not candidatos or not conhecidas:
        return SelecaoLimiar(
            None,
            None,
            None,
            len(candidatos),
            len(ids_desconhecidos),
            "threshold_indisponivel",
        )

    galeria = Galeria.criar(
        (
            amostra
            for amostra in validacao.referencias
            if tamanho_galeria is None
            or amostra.identidade_id
            in validacao.identidades_conhecidas[:tamanho_galeria]
        ),
        estrategia,
    )
    if not galeria.identidades:
        return SelecaoLimiar(
            None,
            None,
            None,
            len(candidatos),
            len(ids_desconhecidos),
            "threshold_indisponivel",
        )
    scores = []
    for consulta in candidatos:
        assert consulta.embedding is not None
        predicao = _decidir_distancias(
            galeria.distancias(consulta.embedding),
            frozenset(galeria.identidades_configuradas),
            2.0,
        )
        if (
            predicao.distancia is not None
            and predicao.motivo is not MotivoIdentificacao.EMPATE
        ):
            scores.append(predicao.distancia)
    # O denominador do teto inclui empates, que são rejeitados conservadoramente
    # e continuam no total de consultas desconhecidas extraídas da métrica.
    permitidos = math.floor(far_maximo * len(candidatos) + 1e-9)
    ordenados = np.sort(np.asarray(scores, dtype=np.float64))
    if not ordenados.size or permitidos >= ordenados.size:
        limiar = 2.0
    else:
        barreira = float(ordenados[permitidos])
        limiar = float(np.nextafter(barreira, -np.inf))
        if limiar < 0.0:
            return SelecaoLimiar(
                None,
                0.0,
                None,
                len(candidatos),
                len(ids_desconhecidos),
                "threshold_indisponivel",
            )

    avaliacao = avaliar_protocolo(
        validacao,
        limiar=limiar,
        estrategia=estrategia,
        tamanho_galeria=tamanho_galeria,
    )
    if far_maximo == 0.0:
        suficiencia = "sem_garantia"
    else:
        minimo_identidades = math.ceil(3.0 / far_maximo)
        suficiencia = (
            "minimo_atendido"
            if len(ids_desconhecidos) >= minimo_identidades
            else "amostra_insuficiente"
        )
    return SelecaoLimiar(
        limiar,
        avaliacao.metricas.fpir_condicional_extracao,
        avaliacao.metricas.fnir_condicional_extracao,
        len(candidatos),
        len(ids_desconhecidos),
        suficiencia,
    )


def contar_quase_duplicatas_por_identidade(
    protocolo: Protocolo, limite: float = DISTANCIA_QUASE_DUPLICATA
) -> int:
    """Conta pares de imagens distintas da mesma identidade com d < limite.

    É um alerta heurístico, não remove amostras nem compara IDs diferentes.
    Duplicatas exatas entre identidades são auditadas antes da divisão.
    """
    if not math.isfinite(limite) or not 0.0 <= limite <= 2.0:
        raise ValueError("O limite de quase duplicata deve estar em [0, 2].")
    por_identidade: dict[str, list[FaceEmbedding]] = defaultdict(list)
    for amostra in (
        *protocolo.referencias,
        *protocolo.consultas_conhecidas,
        *protocolo.consultas_desconhecidas,
    ):
        if amostra.embedding is not None:
            por_identidade[amostra.identidade_id].append(amostra.embedding)
    quase = 0
    for embeddings in por_identidade.values():
        for indice, esquerda in enumerate(embeddings):
            for direita in embeddings[indice + 1 :]:
                if esquerda.distancia_cosseno(direita) < limite:
                    quase += 1
    return quase


def bootstrap_por_identidade(
    relatorio: RelatorioIdentificacao,
    metrica: str,
    replicas: int = 1000,
    seed: int = 42,
) -> IntervaloConfianca | None:
    """IC percentil por identidade de consulta, condicional à galeria fixa."""
    if replicas < 1:
        raise ValueError("O numero de replicas deve ser positivo.")
    if metrica not in {"fpir", "fpir_condicional", "fnir", "fnir_condicional"}:
        raise ValueError(
            "Metrica deve ser fpir, fpir_condicional, fnir ou fnir_condicional."
        )

    grupos: dict[str, list[float]] = defaultdict(list)
    for obs in relatorio.observacoes:
        if metrica.startswith("fpir") and obs.conhecida:
            continue
        if metrica.startswith("fnir") and not obs.conhecida:
            continue
        if metrica.endswith("_condicional") and not obs.extracao_valida:
            continue
        erro = (
            obs.identificacao_aceita
            if metrica.startswith("fpir")
            else not obs.identificacao_correta
        )
        grupos[obs.identidade_id].append(float(erro))

    if len(grupos) < 2:
        return None
    ids = sorted(grupos)
    valores = np.concatenate([np.asarray(grupos[identidade]) for identidade in ids])
    pontual = float(np.mean(valores))
    rng = np.random.default_rng(seed)
    amostras = np.empty(replicas, dtype=np.float64)
    for indice in range(replicas):
        sorteados = rng.integers(0, len(ids), size=len(ids))
        valores_replica = np.concatenate(
            [np.asarray(grupos[ids[int(i)]], dtype=np.float64) for i in sorteados]
        )
        amostras[indice] = float(np.mean(valores_replica))
    inferior, superior = np.quantile(amostras, [0.025, 0.975])
    regra_tres = (
        min(1.0, 3.0 / len(ids))
        if metrica.startswith("fpir") and np.sum(valores) == 0.0
        else None
    )
    return IntervaloConfianca(
        pontual=pontual,
        inferior=float(inferior),
        superior=float(superior),
        identidades=len(ids),
        consultas=int(valores.size),
        limite_superior_regra_tres=regra_tres,
    )
