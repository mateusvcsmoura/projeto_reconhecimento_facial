"""Etapa 1 -- calibracao supervisionada do limiar de reconhecimento (S1).

A regra de decisao do sistema e um classificador binario de UM parametro
-- uma arvore de decisao de profundidade 1 sobre a distancia cosseno:

    y_hat = 1 (mesma pessoa)      se d(e1, e2) <= tau
    y_hat = 0 (pessoas distintas) caso contrario

Calibrar tau com pares rotulados e treinar esse classificador. Os pesos do
Facenet512 NAO sao tocados: o modelo so gera os vetores.

Protocolo:

  1. Selecao: identidades com 2+ imagens unicas (duplicatas exatas fora),
     no maximo N imagens por identidade, sorteadas com a seed.
  2. Divisao por identidade ANTES de qualquer par (60/20/20, seed).
  3. Extracao: um embedding por imagem, reaproveitado em todos os pares e
     guardado em avaliacao/cache/, amarrado a configuracao do modelo.
  4. Pares genuinos e impostores DENTRO de cada conjunto.
  5. Calibracao na VALIDACAO: para cada teto de FAR, o maior tau que o
     respeita. O treino so serve de analise -- o criterio de
     escolha e uma regra de negocio fixa, sem hiperparametro, entao nao ha
     "ajuste no treino + selecao na validacao" a fazer neste experimento.
  6. Teste, UMA vez: o baseline (FACE_THRESHOLD) e os limiares calibrados,
     congelados juntos, medidos no mesmo conjunto, com IC por bootstrap de
     identidades.

Verificacao 1:1, sem prova de vida (Avaliacao A). Nao mede a operacao 1:N
e nao altera FACE_THRESHOLD, .env, settings nem o matcher.

    python -m scripts.calibrar_limiar --dataset avaliacao/datasets/lfw

Exige Python 3.12/3.13 com DeepFace e requirements-experimentos.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.divisao_por_identidade import (
    DadosInsuficientes,
    Divisao,
    ResumoDoConjunto,
    dividir_por_identidade,
    verificar_suficiencia,
)
from scripts.evaluate_model import (
    SEED_PADRAO,
    Falha,
    ResumoDaExtracao,
    inventariar,
    ler_imagem,
    processar_imagem,
    relatar_extracao,
    relatar_inventario,
)
from scripts.metricas import (
    MatrizDeConfusao,
    PontoDaCurva,
    area_sob_a_curva,
    eer,
    limiar_para_far_maximo,
    matriz_de_confusao,
)
from src.config.logging import configurar_logging
from src.config.settings import PROJECT_ROOT, get_settings
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import ModeloIndisponivel
from src.domain.services.matcher import ModeloIncompativel

TETOS_DE_FAR = (0.0, 0.001, 0.01, 0.05)
# O teto de FAR e decisao de negocio. Dos tetos oferecidos,
# 0,1% e o mais frouxo que ainda mantem a FPIR estimada de uma turma de 40
# alunos em um digito (40 x 0,1% ~ 4%); 1%
# daria ~33%.
TETO_PRINCIPAL = 0.001
MIN_IMAGENS = 2
# Sem teto, uma identidade com centenas de fotos dominaria os genuinos.
MAX_IMAGENS = 10
MAX_IMPOSTORES = 1_000_000
REPLICAS = 1000
BASELINE = "baseline"
# Muda quando o pipeline de extracao muda: invalida o cache inteiro.
VERSAO_DA_EXTRACAO = "1"
SALVAR_CACHE_A_CADA = 500
# Genuinos quase identicos sugerem a mesma foto reenquadrada. Heuristica:
# so reportada, nada e removido por ela.
DISTANCIA_DE_QUASE_DUPLICATA = 0.01

SAIDA_PADRAO = PROJECT_ROOT / "avaliacao" / "resultados" / "etapa1"
CACHE_PADRAO = PROJECT_ROOT / "avaliacao" / "cache"


def nome_do_metodo(teto: float) -> str:
    # `:g`, e nao casas fixas: 0,04% e 0,05% virariam "0.0%" e "0.1%" e um
    # teto sobrescreveria o outro no dicionario de limiares congelados.
    return f"FAR<={teto * 100:g}%"


# -- selecao --------------------------------------------------------------


def hash_do_arquivo(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class Selecao:
    imagens_por_pessoa: dict[str, list[Path]]
    duplicatas_na_identidade: int
    duplicatas_entre_identidades: int
    identidades_com_poucas_imagens: int
    imagens_excedentes: int

    @property
    def total_de_imagens(self) -> int:
        return sum(len(imagens) for imagens in self.imagens_por_pessoa.values())


def selecionar(
    imagens_por_pessoa: Mapping[str, list[Path]],
    hashes: Mapping[Path, str],
    min_imagens: int,
    max_imagens: int,
    seed: int,
) -> Selecao:
    """Imagens que entram no experimento, em ordem estavel.

    Duplicata exata (mesmo conteudo) fica fora: dentro da identidade, ela
    geraria um par genuino de distancia zero; entre identidades, um rotulo
    contraditorio. Conta a primeira ocorrencia, em ordem alfabetica.
    """
    if min_imagens < 1 or max_imagens < max(min_imagens, 2):
        raise ValueError(
            f"Exige 1 <= min_imagens <= max_imagens e max_imagens >= 2; "
            f"recebido {min_imagens} e {max_imagens}."
        )

    dono_do_hash: dict[str, str] = {}
    na_identidade = entre_identidades = poucas = excedentes = 0
    selecionadas: dict[str, list[Path]] = {}

    for pessoa in sorted(imagens_por_pessoa):
        unicas = []
        for imagem in sorted(imagens_por_pessoa[pessoa]):
            dono = dono_do_hash.get(hashes[imagem])
            if dono is None:
                dono_do_hash[hashes[imagem]] = pessoa
                unicas.append(imagem)
            elif dono == pessoa:
                na_identidade += 1
            else:
                entre_identidades += 1

        if len(unicas) < min_imagens:
            poucas += 1
            continue
        if len(unicas) > max_imagens:
            excedentes += len(unicas) - max_imagens
            # Semente por identidade: o sorteio de uma pessoa nao depende
            # de quantas outras existem no dataset.
            sorteio = random.Random(f"{seed}:{pessoa}")
            unicas = sorted(sorteio.sample(unicas, max_imagens))
        selecionadas[pessoa] = unicas

    return Selecao(selecionadas, na_identidade, entre_identidades, poucas, excedentes)


# -- extracao com cache ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfiguracaoDaExtracao:
    """Tudo o que muda o vetor. O que nao da para ler daqui (a leitura e o
    pre-processamento deste script) e guardado por VERSAO_DA_EXTRACAO."""

    modelo: str
    detector: str
    deepface: str
    opencv: str
    tensorflow: str
    alinhamento: bool = True
    prova_de_vida: bool = False
    normalizacao: str = "L2"
    versao: str = VERSAO_DA_EXTRACAO

    def como_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    def chave(self) -> str:
        return hashlib.sha256(self.como_json().encode()).hexdigest()[:16]


class CacheIncompativel(ValueError):
    """O arquivo de cache foi gerado com outra configuracao de extracao."""


class CacheDeEmbeddings:
    """Embeddings ja extraidos, indexados pelo hash do conteudo da imagem.

    Um arquivo por configuracao: trocar modelo, detector ou versao muda o
    nome do arquivo, entao vetores de configuracoes diferentes nunca se
    encontram. Falhas nao sao guardadas -- sao recontadas a cada execucao.
    E dado biometrico derivado: fica sob avaliacao/, fora do Git.
    """

    def __init__(self, diretorio: Path, config: ConfiguracaoDaExtracao) -> None:
        self.caminho = diretorio / f"embeddings-{config.chave()}.npz"
        self._config = config
        self._vetores: dict[str, np.ndarray] = {}
        self._novos = 0
        if self.caminho.exists():
            with np.load(self.caminho) as dados:
                if str(dados["config"]) != config.como_json():
                    raise CacheIncompativel(
                        f"{self.caminho} foi gerado com outra configuracao."
                    )
                self._vetores = dict(
                    zip(dados["hashes"].tolist(), dados["vetores"], strict=True)
                )

    def __len__(self) -> int:
        return len(self._vetores)

    def matriz(self) -> np.ndarray:
        """Retorna cópia matricial dos embeddings, sem expor hashes de imagem."""
        if not self._vetores:
            return np.empty((0, 0), dtype=np.float64)
        return np.vstack(list(self._vetores.values())).astype(np.float64, copy=True)

    def obter(self, chave: str) -> FaceEmbedding | None:
        vetor = self._vetores.get(chave)
        if vetor is None:
            return None
        # O vetor saiu de um FaceEmbedding, ja normalizado. Renormalizar
        # mudaria a 8a casa decimal e a execucao com cache divergiria da
        # execucao sem cache.
        return FaceEmbedding(vetor=vetor, modelo=self._config.modelo)

    def guardar(self, chave: str, embedding: FaceEmbedding) -> None:
        if embedding.modelo != self._config.modelo:
            raise ModeloIncompativel(
                f"Embedding de {embedding.modelo!r} num cache de "
                f"{self._config.modelo!r}."
            )
        self._vetores[chave] = embedding.vetor
        self._novos += 1
        # Extracao longa: um defeito no meio nao joga fora o que ja foi feito.
        if self._novos % SALVAR_CACHE_A_CADA == 0:
            self.salvar()

    def salvar(self) -> None:
        if not self._vetores:
            return
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.with_suffix(".tmp")
        with temporario.open("wb") as arquivo:
            np.savez(
                arquivo,
                hashes=np.array(list(self._vetores)),
                vetores=np.vstack(list(self._vetores.values())),
                config=np.array(self._config.como_json()),
            )
        temporario.replace(self.caminho)


@dataclass(frozen=True, slots=True)
class Tabela:
    """Um embedding por imagem processada.

    Identidades viram indices; os nomes ficam so aqui, em memoria, e nunca
    saem nos resultados.
    """

    nomes: tuple[str, ...]
    identidade: np.ndarray  # (n,) indice em `nomes` de cada linha
    vetores: np.ndarray  # (n, d) L2-normalizados

    def linhas_por_identidade(self) -> dict[str, np.ndarray]:
        linhas = {
            nome: np.flatnonzero(self.identidade == i)
            for i, nome in enumerate(self.nomes)
        }
        return {nome: idx for nome, idx in linhas.items() if idx.size}

    def contagens(self) -> dict[str, int]:
        return {nome: idx.size for nome, idx in self.linhas_por_identidade().items()}


def extrair(
    selecao: Selecao,
    hashes: Mapping[Path, str],
    ler: Callable[[Path], Any],
    gerar: Callable[[Any], FaceEmbedding],
    cache: CacheDeEmbeddings,
) -> tuple[Tabela, ResumoDaExtracao]:
    """Um embedding por imagem -- do cache, ou do modelo uma unica vez."""
    resumo = ResumoDaExtracao()
    nomes = tuple(sorted(selecao.imagens_por_pessoa))
    identidades: list[int] = []
    embeddings: list[FaceEmbedding] = []
    total = selecao.total_de_imagens

    for indice, pessoa in enumerate(nomes):
        for imagem in selecao.imagens_por_pessoa[pessoa]:
            resumo.recebidas += 1
            embedding = cache.obter(hashes[imagem])
            if embedding is None:
                resultado = processar_imagem(imagem, ler, gerar)
                if isinstance(resultado, Falha):
                    resumo.falhas.append(resultado)
                    continue
                embedding = resultado
                cache.guardar(hashes[imagem], embedding)
            identidades.append(indice)
            embeddings.append(embedding)
            if resumo.recebidas % SALVAR_CACHE_A_CADA == 0:
                print(f"  {resumo.recebidas}/{total} imagens", file=sys.stderr)
    cache.salvar()
    resumo.processadas = len(embeddings)

    if len({(e.modelo, e.dimensao) for e in embeddings}) > 1:
        raise ModeloIncompativel("A extracao misturou modelos ou dimensoes.")
    vetores = (
        np.vstack([e.vetor for e in embeddings]) if embeddings else np.empty((0, 0))
    )
    return Tabela(nomes, np.array(identidades, dtype=np.int32), vetores), resumo


# -- pares rotulados ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Pares:
    """Pares rotulados de um conjunto.

    Identificadores tecnicos apenas: linha da imagem na Tabela e indice da
    identidade. Nenhum nome de pessoa.
    """

    conjunto: str
    imagem_a: np.ndarray
    imagem_b: np.ndarray
    identidade_a: np.ndarray
    identidade_b: np.ndarray
    distancia: np.ndarray
    rotulo: np.ndarray  # 1 = mesma pessoa, 0 = pessoas diferentes
    impostores_possiveis: int  # antes da amostragem

    @property
    def genuinas(self) -> np.ndarray:
        return self.distancia[self.rotulo == 1]

    @property
    def impostoras(self) -> np.ndarray:
        return self.distancia[self.rotulo == 0]

    def pares_de_identidades_impostores(self) -> int:
        """Quantos pares DISTINTOS de pessoas os impostores cobrem."""
        impostor = self.rotulo == 0
        a, b = self.identidade_a[impostor], self.identidade_b[impostor]
        par = np.stack([np.minimum(a, b), np.maximum(a, b)], axis=1)
        return int(np.unique(par, axis=0).shape[0]) if par.size else 0


def gerar_pares(
    tabela: Tabela,
    identidades: Iterable[str],
    conjunto: str,
    max_impostores: int | None,
    seed: int,
) -> Pares:
    """Todos os genuinos; impostores todos ou uma amostra uniforme com seed.

    Amostrar impostores preserva o FAR em valor esperado e so reduz a
    resolucao: com n impostores, o menor FAR distinguivel de zero e ~3/n.
    """
    indice = {nome: i for i, nome in enumerate(tabela.nomes)}
    alvo = [indice[nome] for nome in identidades if nome in indice]
    linhas = np.flatnonzero(np.isin(tabela.identidade, alvo))

    # ponytail: matriz n x n inteira (8 n^2 bytes, ~1 GB com 11 mil imagens
    # num conjunto). Acima disso, calcular em blocos.
    vetores = tabela.vetores[linhas].astype(np.float64)
    a, b = np.triu_indices(linhas.size, k=1)
    # Mesma conta do matcher: vetores normalizados, distancia = 1 - <a, b>.
    distancias = 1.0 - (vetores @ vetores.T)[a, b]
    ids = tabela.identidade[linhas]
    genuino = ids[a] == ids[b]

    impostores = np.flatnonzero(~genuino)
    possiveis = int(impostores.size)
    if max_impostores is not None and impostores.size > max_impostores:
        rng = np.random.default_rng(seed)
        impostores = np.sort(rng.choice(impostores, size=max_impostores, replace=False))
    manter = np.sort(np.concatenate([np.flatnonzero(genuino), impostores]))

    return Pares(
        conjunto=conjunto,
        imagem_a=linhas[a[manter]],
        imagem_b=linhas[b[manter]],
        identidade_a=ids[a[manter]],
        identidade_b=ids[b[manter]],
        distancia=distancias[manter],
        rotulo=genuino[manter].astype(np.int8),
        impostores_possiveis=possiveis,
    )


# -- calibracao -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Calibracao:
    teto: float
    validacao: PontoDaCurva | None
    # So analise: o mesmo criterio em identidades disjuntas mostra quanto o
    # limiar varia de um grupo de pessoas para outro. Nao entra na escolha.
    treino: PontoDaCurva | None
    suficiencia: str


def avaliar_suficiencia(teto: float, impostores: int, pares_de_identidades: int) -> str:
    """Minimo HEURISTICO para o teto ser informativo -- nao e demonstracao.

    Com n < 3/teto, o teto admite menos de 3 impostores aceitos: o limiar
    passa a ser decidido pelos 1 ou 2 impostores mais extremos, e nem um
    FAR observado zero sustentaria o teto (regra do tres: o limite de 95%
    seria 3/n > teto). Pares do mesmo par de pessoas sao correlacionados,
    entao exige-se o mesmo minimo tambem em pares de identidades -- um n
    efetivo conservador. Atender o minimo nao estima a variancia do tau:
    para isso, ver a coluna do treino e o IC do teste.
    """
    if teto == 0.0:
        return "sem garantia"  # FAR observado zero nao e FAR zero
    necessario = 3.0 / teto
    if impostores < necessario:
        return "insuficiente"
    if pares_de_identidades < necessario:
        return "limitrofe"
    return "minimo atendido"


def calibrar(
    validacao: Pares, treino: Pares, tetos: Iterable[float]
) -> list[Calibracao]:
    """Escolhe tau por teto de FAR na validacao.

    A assinatura e a garantia: so treino e validacao entram aqui.
    """
    pares_de_identidades = validacao.pares_de_identidades_impostores()
    return [
        Calibracao(
            teto=teto,
            validacao=limiar_para_far_maximo(
                validacao.genuinas, validacao.impostoras, teto
            ),
            treino=limiar_para_far_maximo(treino.genuinas, treino.impostoras, teto),
            suficiencia=avaliar_suficiencia(
                teto, validacao.impostoras.size, pares_de_identidades
            ),
        )
        for teto in tetos
    ]


# -- avaliacao no teste ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Intervalo:
    inferior: float
    superior: float

    def contem(self, valor: float) -> bool:
        return self.inferior <= valor <= self.superior


def intervalo_95(replicas: np.ndarray) -> Intervalo:
    """Percentis 2,5 e 97,5; replicas sem denominador ficam de fora."""
    validas = replicas[np.isfinite(replicas)]
    if validas.size == 0:
        return Intervalo(float("nan"), float("nan"))
    inferior, superior = np.percentile(validas, [2.5, 97.5])
    return Intervalo(float(inferior), float(superior))


def bootstrap_por_identidade(
    pares: Pares, limiares: Mapping[str, float], replicas: int, seed: int
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Replicas de (FAR, FRR) por limiar, reamostrando IDENTIDADES.

    Pares que compartilham uma pessoa nao sao independentes: reamostrar
    pares trataria 10^5 comparacoes como 10^5 observacoes e estreitaria o
    intervalo. Cada replica sorteia pessoas com reposicao; quem sai w vezes
    pesa w nos seus genuinos e w_a * w_b nos impostores com outra pessoa
    ("subsets bootstrap", Bolle et al., 2004). Mesmas replicas para todos
    os limiares: as diferencas entre metodos ficam pareadas.
    """
    n = pares.distancia.size
    _, inversa = np.unique(
        np.concatenate([pares.identidade_a, pares.identidade_b]), return_inverse=True
    )
    a, b = inversa[:n], inversa[n:]
    k = int(inversa.max()) + 1
    fora_da_diagonal = ~np.eye(k, dtype=bool)

    def por_par_de_identidades(valores: np.ndarray) -> np.ndarray:
        matriz = np.zeros((k, k))
        np.add.at(matriz, (a, b), valores)
        return matriz

    pesos = (
        np.random.default_rng(seed)
        .multinomial(k, np.full(k, 1.0 / k), size=replicas)
        .astype(np.float64)
    )

    def ponderar(matriz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        genuinos = pesos @ np.diag(matriz)
        impostores = ((pesos @ (matriz * fora_da_diagonal)) * pesos).sum(axis=1)
        return genuinos, impostores

    total_genuinos, total_impostores = ponderar(por_par_de_identidades(np.ones(n)))
    resultado = {}
    for nome, limiar in limiares.items():
        aceitos = por_par_de_identidades((pares.distancia <= limiar).astype(np.float64))
        genuinos_aceitos, impostores_aceitos = ponderar(aceitos)
        with np.errstate(divide="ignore", invalid="ignore"):
            far = impostores_aceitos / total_impostores
            frr = 1.0 - genuinos_aceitos / total_genuinos
        resultado[nome] = (far, frr)
    return resultado


@dataclass(frozen=True, slots=True)
class ResultadoNoTeste:
    metodo: str
    limiar: float
    matriz: MatrizDeConfusao
    ic_far: Intervalo
    ic_frr: Intervalo
    pares_de_identidades: int  # impostores, distintos por par de pessoas

    @property
    def far_maximo_regra_do_tres(self) -> float | None:
        """Sem impostor aceito: limite de ~95% para o FAR, 3/n.

        n = pares de IDENTIDADES, nao de imagens: as comparacoes de um mesmo
        par de pessoas sao correlacionadas, e usar todas elas prometeria um
        limite estreito demais.
        """
        if self.matriz.fp or not self.pares_de_identidades:
            return None
        return 3.0 / self.pares_de_identidades


@dataclass(frozen=True, slots=True)
class Experimento:
    resumos: list[ResumoDoConjunto]
    pares: dict[str, Pares]
    calibracoes: list[Calibracao]
    congelados: dict[str, float]
    principal: str
    resultados: list[ResultadoNoTeste]
    # metodo -> {"far": IC de (metodo - baseline), "frr": ...}
    diferencas: dict[str, dict[str, Intervalo]]
    # Replicas sem genuinos ou sem impostores (denominador zero), fora dos IC.
    replicas_descartadas: int
    auc: float
    eer: PontoDaCurva
    auc_rotulos_embaralhados: float
    quase_duplicatas: dict[str, int]


def executar(
    tabela: Tabela,
    divisao: Divisao,
    baseline: float,
    tetos: Iterable[float],
    teto_principal: float,
    max_impostores: int | None,
    replicas: int,
    seed: int,
) -> Experimento:
    """Calibra na validacao, congela, abre o teste uma vez e mede."""
    resumos = divisao.resumir(tabela.contagens())
    verificar_suficiencia(resumos)

    treino = gerar_pares(tabela, divisao.treino, "treino", max_impostores, seed)
    validacao = gerar_pares(
        tabela, divisao.validacao, "validacao", max_impostores, seed
    )
    calibracoes = calibrar(validacao, treino, tetos)

    congelados = {BASELINE: baseline}
    for calibracao in calibracoes:
        if calibracao.validacao is not None:
            congelados[nome_do_metodo(calibracao.teto)] = calibracao.validacao.limiar
    principal = nome_do_metodo(teto_principal)
    if principal not in congelados:
        raise DadosInsuficientes(
            f"Nenhum limiar respeita FAR <= {teto_principal:.1%} na validacao."
        )

    # Daqui em diante nada mais e escolhido: o teste so mede.
    teste = gerar_pares(
        tabela, divisao.abrir_teste(congelados), "teste", max_impostores, seed
    )
    replicas_por_metodo = bootstrap_por_identidade(teste, congelados, replicas, seed)
    pares_de_identidades = teste.pares_de_identidades_impostores()

    resultados = [
        ResultadoNoTeste(
            metodo=nome,
            limiar=limiar,
            matriz=matriz_de_confusao(teste.genuinas, teste.impostoras, limiar),
            ic_far=intervalo_95(replicas_por_metodo[nome][0]),
            ic_frr=intervalo_95(replicas_por_metodo[nome][1]),
            pares_de_identidades=pares_de_identidades,
        )
        for nome, limiar in congelados.items()
    ]
    far_base, frr_base = replicas_por_metodo[BASELINE]
    # O denominador so depende do sorteio, nao do limiar: mesma conta para todos.
    descartadas = int(np.sum(~np.isfinite(far_base) | ~np.isfinite(frr_base)))
    diferencas = {
        nome: {
            "far": intervalo_95(far - far_base),
            "frr": intervalo_95(frr - frr_base),
        }
        for nome, (far, frr) in replicas_por_metodo.items()
        if nome != BASELINE
    }

    # Sanidade: sem o rotulo verdadeiro,
    # a distancia nao deveria separar nada. AUC longe de 0,5 = vazamento.
    embaralhado = np.random.default_rng(seed).permutation(validacao.rotulo)
    auc_embaralhado = area_sob_a_curva(
        validacao.distancia[embaralhado == 1], validacao.distancia[embaralhado == 0]
    )

    pares = {"treino": treino, "validacao": validacao, "teste": teste}
    return Experimento(
        resumos=resumos,
        pares=pares,
        calibracoes=calibracoes,
        congelados=congelados,
        principal=principal,
        resultados=resultados,
        diferencas=diferencas,
        replicas_descartadas=descartadas,
        auc=area_sob_a_curva(teste.genuinas, teste.impostoras),
        eer=eer(teste.genuinas, teste.impostoras),
        auc_rotulos_embaralhados=auc_embaralhado,
        quase_duplicatas={
            nome: int(np.sum(p.genuinas < DISTANCIA_DE_QUASE_DUPLICATA))
            for nome, p in pares.items()
        },
    )


# -- relatorio ------------------------------------------------------------


def _pct(valor: float | None, casas: int = 3) -> str:
    return "indef." if valor is None else f"{valor:.{casas}%}"


def _ic(intervalo: Intervalo) -> str:
    # 3 casas: um FAR de 0,002% com IC em 2 casas apareceria como [0; 0].
    return f"[{_pct(intervalo.inferior)}; {_pct(intervalo.superior)}]"


def _veredito(diferenca: Intervalo) -> str:
    if not np.isfinite([diferenca.inferior, diferenca.superior]).all():
        return "IC indefinido"
    if diferenca.contem(0.0):
        return "IC inclui 0 (diferenca nao sustentada)"
    sentido = "diminuiu" if diferenca.superior < 0 else "aumentou"
    return f"{sentido} (IC exclui 0)"


def relatar_selecao(selecao: Selecao, min_imagens: int, max_imagens: int) -> None:
    print("\n=== Selecao ===")
    print(
        f"Identidades com {min_imagens}+ imagens unicas: "
        f"{len(selecao.imagens_por_pessoa)} "
        f"(fora por terem menos: {selecao.identidades_com_poucas_imagens})"
    )
    print(
        "Duplicatas exatas removidas: "
        f"na mesma identidade {selecao.duplicatas_na_identidade} | "
        f"entre identidades {selecao.duplicatas_entre_identidades}"
    )
    print(
        f"Imagens selecionadas: {selecao.total_de_imagens} "
        f"(teto {max_imagens}/identidade; excedentes fora: "
        f"{selecao.imagens_excedentes})"
    )


def relatar(experimento: Experimento, seed: int, assinatura: str) -> None:
    print(f"\n=== Divisao por identidade (seed {seed}, assinatura {assinatura}) ===")
    print(
        f"{'conjunto':>10} | {'ident.':>6} | {'imagens':>7} | {'genuinos':>8} | "
        f"{'impost. possiveis':>17} | {'impost. usados':>14}"
    )
    for resumo in experimento.resumos:
        usados = experimento.pares[resumo.nome].impostoras.size
        print(
            f"{resumo.nome:>10} | {resumo.identidades:>6} | {resumo.imagens:>7} | "
            f"{resumo.pares_genuinos:>8} | {resumo.pares_impostores:>17} | "
            f"{usados:>14}"
        )

    validacao = experimento.pares["validacao"]
    print("\n=== Calibracao na VALIDACAO (teste lacrado) ===")
    print(
        f"Impostores: {validacao.impostoras.size} | pares de identidades: "
        f"{validacao.pares_de_identidades_impostores()} | regra do tres: "
        "teto c exige >= 3/c"
    )
    print(
        f"{'teto FAR':>9} | {'tau':>7} | {'FAR val':>8} | {'FRR val':>8} | "
        f"{'tau treino*':>11} | dados"
    )
    for c in experimento.calibracoes:
        if c.validacao is None:
            print(f"{c.teto:>9.1%} | nenhum limiar respeita o teto | {c.suficiencia}")
            continue
        tau_treino = f"{c.treino.limiar:.4f}" if c.treino else "-"
        print(
            f"{c.teto:>9.1%} | {c.validacao.limiar:>7.4f} | "
            f"{_pct(c.validacao.far):>8} | {_pct(c.validacao.frr):>8} | "
            f"{tau_treino:>11} | {c.suficiencia}"
        )
    print("* treino: so analise de estabilidade; nao entra na escolha.")
    congelados = ", ".join(f"{k}={v:.4f}" for k, v in experimento.congelados.items())
    print(f"Congelados antes de abrir o teste: {congelados}")

    print("\n=== TESTE (aberto uma unica vez) ===")
    print(
        f"{'metodo':>13} | {'limiar':>6} | {'TP':>6} | {'FN':>6} | {'FP':>7} | "
        f"{'TN':>8} | {'FAR [IC95]':>27} | {'FRR [IC95]':>27} | "
        f"{'acur.':>7} | {'prec.':>7} | {'recall':>7} | {'F1':>7}"
    )
    for r in experimento.resultados:
        m = r.matriz
        print(
            f"{r.metodo:>13} | {r.limiar:>6.4f} | {m.tp:>6} | {m.fn:>6} | {m.fp:>7} | "
            f"{m.tn:>8} | {_pct(m.far):>8} {_ic(r.ic_far):>18} | "
            f"{_pct(m.frr):>8} {_ic(r.ic_frr):>18} | {_pct(m.acuracia, 2):>7} | "
            f"{_pct(m.precisao, 2):>7} | {_pct(m.recall, 2):>7} | {_pct(m.f1, 2):>7}"
        )
        if r.far_maximo_regra_do_tres is not None:
            print(
                f"{'':>13}   FP = 0: FAR < ~{r.far_maximo_regra_do_tres:.4%} (regra "
                "do tres com n = pares de identidades; o IC degenera em [0; 0])"
            )

    print(f"\nAUC (teste): {experimento.auc:.4f} -- a mesma para todo limiar.")
    ponto = experimento.eer
    print(
        f"EER (teste, so comparativo): {(ponto.far + ponto.frr) / 2:.4%} "
        f"no limiar {ponto.limiar:.4f}"
    )
    print(
        "\nDiferenca para o baseline (IC95, bootstrap pareado por identidade, "
        "condicional ao tau congelado; replicas sem denominador descartadas: "
        f"{experimento.replicas_descartadas}):"
    )
    for nome, ic in experimento.diferencas.items():
        papel = "principal" if nome == experimento.principal else "exploratorio"
        print(f"  {nome:>13} ({papel}): dFAR {_ic(ic['far'])} | dFRR {_ic(ic['frr'])}")
    # Um veredito so, para a comparacao definida antes de abrir o teste: os
    # demais tetos sao exploratorios (sem correcao para comparacoes multiplas).
    principal = experimento.diferencas[experimento.principal]
    print(
        f"Veredito ({experimento.principal} x baseline): FAR "
        f"{_veredito(principal['far'])}; FRR {_veredito(principal['frr'])}"
    )
    print(
        "\nSanidade -- AUC com rotulos embaralhados (validacao): "
        f"{experimento.auc_rotulos_embaralhados:.4f} (esperado ~0,5)"
    )
    quase = " | ".join(f"{k} {v}" for k, v in experimento.quase_duplicatas.items())
    print(f"Genuinos com d < {DISTANCIA_DE_QUASE_DUPLICATA}: {quase}")
    print(
        "\nVerificacao 1:1, sem prova de vida, em dataset publico: NAO e a taxa "
        "de erro da operacao 1:N na sala.\nFACE_THRESHOLD nao foi alterado."
    )


def _versao(pacote: str) -> str:
    try:
        return metadata.version(pacote)
    except metadata.PackageNotFoundError:
        return "ausente"


def _ponto(p: PontoDaCurva | None) -> dict[str, float] | None:
    return None if p is None else {"limiar": p.limiar, "far": p.far, "frr": p.frr}


def _metricas(m: MatrizDeConfusao) -> dict[str, Any]:
    return {
        **asdict(m),
        "far": m.far,
        "frr": m.frr,
        "acuracia": m.acuracia,
        "precisao": m.precisao,
        "recall": m.recall,
        "f1": m.f1,
    }


def salvar(
    experimento: Experimento,
    destino: Path,
    metadados: dict[str, Any],
    selecao: Selecao,
    resumo: ResumoDaExtracao,
) -> list[Path]:
    """resultado.json (agregados, sem nomes) e pares.npz (pares rotulados)."""
    destino.mkdir(parents=True, exist_ok=True)
    resultado = {
        "metadados": metadados,
        "selecao": {
            "identidades": len(selecao.imagens_por_pessoa),
            "imagens": selecao.total_de_imagens,
            "identidades_com_poucas_imagens": selecao.identidades_com_poucas_imagens,
            "duplicatas_na_identidade": selecao.duplicatas_na_identidade,
            "duplicatas_entre_identidades": selecao.duplicatas_entre_identidades,
            "imagens_excedentes": selecao.imagens_excedentes,
        },
        "extracao": {
            "recebidas": resumo.recebidas,
            "processadas": resumo.processadas,
            "rejeitadas_por_motivo": {
                str(motivo): n for motivo, n in resumo.por_motivo().items()
            },
        },
        "conjuntos": [
            {
                **asdict(r),
                "impostores_usados": int(experimento.pares[r.nome].impostoras.size),
                "pares_de_identidades_impostores": experimento.pares[
                    r.nome
                ].pares_de_identidades_impostores(),
            }
            for r in experimento.resumos
        ],
        "calibracao_validacao": [
            {
                "teto": c.teto,
                "validacao": _ponto(c.validacao),
                "treino_analise": _ponto(c.treino),
                "suficiencia": c.suficiencia,
            }
            for c in experimento.calibracoes
        ],
        "limiares_congelados": experimento.congelados,
        "metodo_principal": experimento.principal,
        "teste": [
            {
                "metodo": r.metodo,
                "limiar": r.limiar,
                **_metricas(r.matriz),
                "ic95_far": asdict(r.ic_far),
                "ic95_frr": asdict(r.ic_frr),
                "pares_de_identidades_impostores": r.pares_de_identidades,
                "far_maximo_regra_do_tres": r.far_maximo_regra_do_tres,
            }
            for r in experimento.resultados
        ],
        "replicas_bootstrap_descartadas": experimento.replicas_descartadas,
        "diferenca_para_baseline_ic95": {
            nome: {k: asdict(v) for k, v in ic.items()}
            for nome, ic in experimento.diferencas.items()
        },
        "auc_teste": experimento.auc,
        "eer_teste": _ponto(experimento.eer),
        "auc_rotulos_embaralhados_validacao": experimento.auc_rotulos_embaralhados,
        "genuinos_quase_duplicados": experimento.quase_duplicatas,
    }
    arquivo_json = destino / "resultado.json"
    arquivo_json.write_text(json.dumps(resultado, indent=2, ensure_ascii=False))

    arquivo_pares = destino / "pares.npz"
    np.savez_compressed(
        arquivo_pares,
        **{
            f"{nome}_{campo}": getattr(pares, campo)
            for nome, pares in experimento.pares.items()
            for campo in (
                "imagem_a",
                "imagem_b",
                "identidade_a",
                "identidade_b",
                "distancia",
                "rotulo",
            )
        },
    )
    return [arquivo_json, arquivo_pares]


# -- CLI ------------------------------------------------------------------


def _carregar_graficos() -> ModuleType:
    """Os graficos exigem matplotlib (requirements-experimentos.txt)."""
    from scripts import graficos_calibracao

    return graficos_calibracao


def _taxa(texto: str) -> float:
    valor = float(texto)
    if not 0.0 < valor < 1.0:
        raise argparse.ArgumentTypeError(f"deve estar em (0, 1); recebido {valor}")
    return valor


def _positivo(texto: str) -> int:
    valor = int(texto)
    if valor < 1:
        raise argparse.ArgumentTypeError(f"deve ser >= 1; recebido {valor}")
    return valor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Etapa 1: calibracao do limiar (S1)")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED_PADRAO)
    parser.add_argument("--far-alvo", type=_taxa, default=TETO_PRINCIPAL)
    parser.add_argument("--min-imagens", type=_positivo, default=MIN_IMAGENS)
    parser.add_argument("--max-imagens", type=_positivo, default=MAX_IMAGENS)
    parser.add_argument("--max-impostores", type=_positivo, default=MAX_IMPOSTORES)
    parser.add_argument("--replicas", type=_positivo, default=REPLICAS)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--cache", type=Path, default=CACHE_PADRAO)
    args = parser.parse_args(argv)

    if not args.dataset.is_dir():
        print(f"ERRO: diretorio nao encontrado: {args.dataset}", file=sys.stderr)
        return 2
    try:
        graficos = _carregar_graficos()
    except ImportError as exc:
        print(f"ERRO: {exc}. Instale requirements-experimentos.txt.", file=sys.stderr)
        return 2

    settings = get_settings()
    configurar_logging("WARNING")
    try:
        from src.infrastructure.face_recognition.deepface_adapter import (
            DeepFaceAdapter,
        )
    except ImportError as exc:
        print(f"ERRO: DeepFace indisponivel: {exc}", file=sys.stderr)
        return 2

    # Avaliacao A, sem prova de vida: o dataset e de fotografias.
    provider = DeepFaceAdapter(
        modelo=settings.face_model, detector=settings.face_detector, anti_spoofing=False
    )
    print("Etapa 1 -- calibracao do limiar (verificacao 1:1, SEM prova de vida)")
    print(f"Modelo: {settings.face_model} | detector: {settings.face_detector}")
    try:
        provider.preaquecer()
    except ModeloIndisponivel as erro:
        print(f"ERRO: o modelo nao carregou: {erro}", file=sys.stderr)
        return 2

    inventario = inventariar(args.dataset)
    relatar_inventario(inventario)
    hashes = {
        imagem: hash_do_arquivo(imagem)
        for imagens in inventario.imagens_por_pessoa.values()
        for imagem in imagens
    }
    selecao = selecionar(
        inventario.imagens_por_pessoa,
        hashes,
        args.min_imagens,
        args.max_imagens,
        args.seed,
    )
    relatar_selecao(selecao, args.min_imagens, args.max_imagens)

    config = ConfiguracaoDaExtracao(
        modelo=settings.face_model,
        detector=settings.face_detector,
        deepface=_versao("deepface"),
        opencv=_versao("opencv-python"),
        tensorflow=_versao("tensorflow"),
    )
    try:
        divisao = dividir_por_identidade(selecao.imagens_por_pessoa, args.seed)
        cache = CacheDeEmbeddings(args.cache, config)
    except (DadosInsuficientes, CacheIncompativel) as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 2
    print(f"Cache: {len(cache)} embeddings reaproveitaveis em {cache.caminho}")

    tabela, resumo = extrair(
        selecao, hashes, ler_imagem, provider.gerar_embedding, cache
    )
    relatar_extracao(resumo, tabela.linhas_por_identidade())

    tetos = sorted({*TETOS_DE_FAR, args.far_alvo})
    try:
        experimento = executar(
            tabela,
            divisao,
            baseline=settings.face_threshold,
            tetos=tetos,
            teto_principal=args.far_alvo,
            max_impostores=args.max_impostores,
            replicas=args.replicas,
            seed=args.seed,
        )
    except DadosInsuficientes as erro:
        print(f"ERRO: dados insuficientes: {erro}", file=sys.stderr)
        return 2

    relatar(experimento, args.seed, divisao.assinatura())

    metadados = {
        "dataset": args.dataset.name,
        "seed": args.seed,
        "assinatura_da_divisao": divisao.assinatura(),
        "proporcoes": "60/20/20 por identidade",
        "min_imagens": args.min_imagens,
        "max_imagens": args.max_imagens,
        "max_impostores": args.max_impostores,
        "replicas_bootstrap": args.replicas,
        "teto_principal": args.far_alvo,
        "baseline_face_threshold": settings.face_threshold,
        "extracao": asdict(config),
        "chave_do_cache": config.chave(),
        "versoes": {
            "python": platform.python_version(),
            **{
                pacote: _versao(pacote)
                for pacote in (
                    "numpy",
                    "deepface",
                    "tensorflow",
                    "tf-keras",
                    "opencv-python",
                    "matplotlib",
                )
            },
        },
    }
    arquivos = salvar(experimento, args.saida, metadados, selecao, resumo)
    arquivos += graficos.gerar(args.saida, experimento)
    print("\nArquivos (fora do Git, sob avaliacao/):")
    for arquivo in arquivos:
        print(f"  {arquivo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
