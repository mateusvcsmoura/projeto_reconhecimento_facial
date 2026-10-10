"""Divisao de um dataset biometrico em treino, validacao e teste.

A divisao e POR IDENTIDADE, e acontece ANTES de formar qualquer par. Se a
mesma pessoa aparecesse no treino e no teste, o limiar seria calibrado
sobre rostos que depois servem para medi-lo -- e o erro reportado sairia
otimista (lacuna G4 de docs/ML-LEARNING-AUDIT.md). Dividir por identidade
simula o caso real: o sistema precisa acertar alunos que nem existiam
quando o limiar foi escolhido.

O teste vem lacrado. Treino e validacao sao livres; as identidades de teste
so saem por `abrir_teste`, uma unica vez, e exigem os limiares ja congelados.
E protecao de API, nao de criptografia: ela torna o uso indevido explicito
em vez de acidental.

Funcoes puras, sem DeepFace e sem disco: testaveis em qualquer ambiente.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

PROPORCOES_PADRAO = (0.6, 0.2, 0.2)

# Par impostor exige duas pessoas diferentes DENTRO do mesmo conjunto.
MINIMO_DE_IDENTIDADES_POR_CONJUNTO = 2


class DadosInsuficientes(ValueError):
    """O dataset nao sustenta uma divisao que produza pares em cada conjunto."""


class VazamentoDeIdentidade(ValueError):
    """A mesma identidade apareceu em mais de um conjunto."""


class UsoIndevidoDoTeste(RuntimeError):
    """Uso do conjunto de teste fora do protocolo."""


@dataclass(frozen=True, slots=True)
class ResumoDoConjunto:
    nome: str
    identidades: int
    imagens: int
    pares_genuinos: int
    pares_impostores: int


def _pares(contagens: list[int]) -> tuple[int, int]:
    """Pares genuinos e impostores que `contagens` imagens por pessoa geram.

    Mesma contagem que `evaluate_model.montar_pares` produz -- sem precisar
    de nenhum embedding.
    """
    genuinos = sum(k * (k - 1) // 2 for k in contagens)
    total = sum(contagens)
    impostores = (total * total - sum(k * k for k in contagens)) // 2
    return genuinos, impostores


class Divisao:
    def __init__(
        self,
        seed: int,
        treino: tuple[str, ...],
        validacao: tuple[str, ...],
        teste: tuple[str, ...],
    ) -> None:
        conjuntos = {"treino": treino, "validacao": validacao, "teste": teste}
        nomes = list(conjuntos)
        for i, nome_a in enumerate(nomes):
            for nome_b in nomes[i + 1 :]:
                comuns = set(conjuntos[nome_a]) & set(conjuntos[nome_b])
                if comuns:
                    raise VazamentoDeIdentidade(
                        f"{len(comuns)} identidade(s) em {nome_a} e {nome_b}: "
                        f"{sorted(comuns)[:5]}"
                    )

        self._seed = seed
        self._treino = treino
        self._validacao = validacao
        self._teste = teste
        self._teste_aberto = False
        self.limiares_congelados: dict[str, float] | None = None

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def treino(self) -> tuple[str, ...]:
        return self._treino

    @property
    def validacao(self) -> tuple[str, ...]:
        return self._validacao

    @property
    def teste_utilizado(self) -> bool:
        return self._teste_aberto

    def abrir_teste(self, limiares_congelados: Mapping[str, float]) -> tuple[str, ...]:
        """Libera as identidades de teste, uma unica vez.

        Pedir os limiares aqui e o ponto: o teste so existe para medir
        decisoes ja tomadas no treino/validacao -- todas as que serao
        comparadas (o baseline e cada limiar calibrado), congeladas juntas.
        Um segundo acesso significaria escolher de novo olhando o teste.
        """
        if self._teste_aberto:
            raise UsoIndevidoDoTeste(
                "O conjunto de teste ja foi usado (limiares congelados: "
                f"{self.limiares_congelados}). Repetir a medicao com outra "
                "escolha transformaria o teste em validacao."
            )
        if not limiares_congelados:
            raise ValueError("Congele ao menos um limiar antes de abrir o teste.")
        self._teste_aberto = True
        self.limiares_congelados = dict(limiares_congelados)
        return self._teste

    def assinatura(self) -> str:
        """Impressao digital da divisao, para conferir reproducao.

        A mesma seed sobre o mesmo dataset deve gerar a mesma assinatura em
        qualquer maquina com a mesma versao do Python.
        """
        conteudo = json.dumps([self._treino, self._validacao, self._teste])
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]

    def resumir(
        self, imagens_por_identidade: Mapping[str, int]
    ) -> list[ResumoDoConjunto]:
        """Contagens por conjunto. Do teste saem numeros, nunca identidades.

        Identidade ausente do mapa conta como zero imagens -- e o caso de quem
        teve todas as imagens recusadas na extracao.
        """
        resumos = []
        for nome, conjunto in (
            ("treino", self._treino),
            ("validacao", self._validacao),
            ("teste", self._teste),
        ):
            contagens = [imagens_por_identidade.get(p, 0) for p in conjunto]
            contagens = [k for k in contagens if k > 0]
            genuinos, impostores = _pares(contagens)
            resumos.append(
                ResumoDoConjunto(
                    nome=nome,
                    identidades=len(contagens),
                    imagens=sum(contagens),
                    pares_genuinos=genuinos,
                    pares_impostores=impostores,
                )
            )
        return resumos


def _validar_proporcoes(proporcoes: tuple[float, float, float]) -> None:
    if len(proporcoes) != 3 or any(p <= 0 for p in proporcoes):
        raise ValueError(
            "Sao 3 proporcoes positivas (treino, validacao, teste); "
            f"recebido {proporcoes}."
        )
    if not math.isclose(sum(proporcoes), 1.0):
        raise ValueError(f"As proporcoes devem somar 1; somam {sum(proporcoes)}.")


def dividir_por_identidade(
    identidades: Iterable[str],
    seed: int,
    proporcoes: tuple[float, float, float] = PROPORCOES_PADRAO,
) -> Divisao:
    """Embaralha as identidades com `seed` e corta em tres conjuntos.

    A lista e ordenada antes do embaralhamento: a ordem em que o disco
    devolve as pastas nao pode mudar a divisao.
    """
    _validar_proporcoes(proporcoes)

    ordenadas = sorted(identidades)
    if len(set(ordenadas)) != len(ordenadas):
        raise ValueError("Ha identidades repetidas na entrada.")

    minimo = MINIMO_DE_IDENTIDADES_POR_CONJUNTO
    total = len(ordenadas)
    if total < 3 * minimo:
        raise DadosInsuficientes(
            f"Sao necessarias ao menos {3 * minimo} identidades "
            f"({minimo} por conjunto); o dataset tem {total}."
        )

    # ponytail: random.Random e reprodutivel na mesma versao do Python; a
    # assinatura() denuncia se outra versao embaralhar diferente.
    random.Random(seed).shuffle(ordenadas)

    _, p_validacao, p_teste = proporcoes
    n_validacao = max(minimo, round(total * p_validacao))
    n_teste = max(minimo, round(total * p_teste))
    n_treino = total - n_validacao - n_teste
    if n_treino < minimo:
        raise DadosInsuficientes(
            f"Com {total} identidades sobram {n_treino} para treino; "
            f"o minimo e {minimo}."
        )

    corte = n_treino + n_validacao
    return Divisao(
        seed=seed,
        treino=tuple(sorted(ordenadas[:n_treino])),
        validacao=tuple(sorted(ordenadas[n_treino:corte])),
        teste=tuple(sorted(ordenadas[corte:])),
    )


def verificar_suficiencia(resumos: list[ResumoDoConjunto]) -> None:
    """Cada conjunto precisa de pares genuinos E impostores.

    Sem isso, FAR ou FRR nao tem denominador -- e qualquer numero reportado
    seria inventado.
    """
    problemas = []
    for resumo in resumos:
        if resumo.pares_genuinos == 0:
            problemas.append(
                f"{resumo.nome}: nenhum par genuino "
                "(nenhuma identidade com 2+ imagens)"
            )
        if resumo.pares_impostores == 0:
            problemas.append(
                f"{resumo.nome}: nenhum par impostor (menos de 2 identidades)"
            )
    if problemas:
        raise DadosInsuficientes("; ".join(problemas))
