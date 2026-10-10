"""Avaliacao do modelo de reconhecimento facial.

Isto NAO e teste de software. Teste de software verifica se o pipeline faz
o que promete; avaliacao de modelo mede se o modelo ACERTA -- e sao coisas
diferentes (instructions/03-qa.md, secao 4).

Serve para responder com dado uma pergunta que hoje e respondida por
heranca: quanto deve valer FACE_THRESHOLD?

Estrutura esperada do conjunto (docs/ML-EXPERIMENT-SETUP.md):

    avaliacao/datasets/<nome>/
      pessoa-1/  foto-a.jpg  foto-b.jpg  ...
      pessoa-2/  foto-a.jpg  ...

Pares GENUINOS saem de dentro de cada pasta; IMPOSTORES, entre pastas
distintas.

Dois modos:

    # Estrutura + divisao por identidade. Sem DeepFace, sem metricas.
    python -m scripts.evaluate_model --dataset avaliacao/datasets/x --validar-divisao

    # Exploratorio: extrai embeddings e calcula FAR/FRR sobre TODOS os pares.
    # O limiar sugerido e o erro saem dos mesmos pares -- serve para olhar,
    # nao para calibrar (lacuna G4). Exige Python 3.12/3.13 com DeepFace.
    python -m scripts.evaluate_model --dataset avaliacao/datasets/x

Esta e a Avaliacao A (reconhecimento), SEM prova de vida. Anti-spoofing e
outra avaliacao, com outro dataset e outras metricas.

NUNCA versione o conjunto de imagens: `avaliacao/` esta no .gitignore.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.divisao_por_identidade import (
    DadosInsuficientes,
    dividir_por_identidade,
    verificar_suficiencia,
)
from scripts.metricas import (
    area_sob_a_curva,
    eer,
    far_frr,
    limiar_para_far_maximo,
)
from src.config.logging import configurar_logging
from src.config.settings import get_settings
from src.domain.entities.face_embedding import EmbeddingInvalido, FaceEmbedding
from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
)

EXTENSOES = {".jpg", ".jpeg", ".png"}
SEED_PADRAO = 42

# Quantas falhas listar uma a uma; o resumo por motivo e sempre completo.
LIMITE_DE_DETALHES = 20


class ImagemIlegivel(Exception):
    """Arquivo vazio ou em formato que o decodificador nao entende."""


class Motivo(StrEnum):
    SEM_ROSTO = "sem rosto detectado"
    MULTIPLOS_ROSTOS = "multiplos rostos"
    ERRO_DE_LEITURA = "erro de leitura"
    FALHA_DE_INFERENCIA = "falha de inferencia"
    EMBEDDING_INVALIDO = "embedding invalido"
    PROVA_DE_VIDA = "recusada pela prova de vida"


# Falhas ESPERADAS de uma imagem individual. Qualquer outra excecao aborta a
# avaliacao: conta-la como "imagem ruim" esconderia um defeito do pipeline
# atras de uma estatistica (o `except Exception` que existia aqui, lacuna G5).
_MOTIVOS: tuple[tuple[type[Exception], Motivo], ...] = (
    (NenhumRostoDetectado, Motivo.SEM_ROSTO),
    (MultiplosRostosDetectados, Motivo.MULTIPLOS_ROSTOS),
    (PossivelFraude, Motivo.PROVA_DE_VIDA),
    (ModeloIndisponivel, Motivo.FALHA_DE_INFERENCIA),
    (EmbeddingInvalido, Motivo.EMBEDDING_INVALIDO),
    (ImagemIlegivel, Motivo.ERRO_DE_LEITURA),
    (OSError, Motivo.ERRO_DE_LEITURA),
)
_ERROS_ESPERADOS = tuple(tipo for tipo, _ in _MOTIVOS)


def _motivo(erro: Exception) -> Motivo:
    return next(motivo for tipo, motivo in _MOTIVOS if isinstance(erro, tipo))


@dataclass(frozen=True, slots=True)
class Inventario:
    imagens_por_pessoa: dict[str, list[Path]]
    # Arquivos que nao entram na avaliacao: extensao fora de EXTENSOES ou
    # soltos na raiz do dataset. Contados para que a amostra menor apareca.
    ignorados: list[Path]

    @property
    def total_de_imagens(self) -> int:
        return sum(len(imagens) for imagens in self.imagens_por_pessoa.values())


@dataclass(frozen=True, slots=True)
class Falha:
    imagem: Path
    motivo: Motivo
    detalhe: str


@dataclass(slots=True)
class ResumoDaExtracao:
    recebidas: int = 0
    processadas: int = 0
    falhas: list[Falha] = field(default_factory=list)

    def por_motivo(self) -> Counter[Motivo]:
        return Counter(falha.motivo for falha in self.falhas)


def inventariar(dataset: Path) -> Inventario:
    """Imagens por identidade (uma pasta por pessoa), em ordem estavel."""
    imagens_por_pessoa: dict[str, list[Path]] = {}
    ignorados: list[Path] = []

    for item in sorted(dataset.iterdir()):
        if not item.is_dir():
            ignorados.append(item)
            continue
        imagens = []
        for arquivo in sorted(item.iterdir()):
            if arquivo.is_file() and arquivo.suffix.lower() in EXTENSOES:
                imagens.append(arquivo)
            else:
                ignorados.append(arquivo)
        imagens_por_pessoa[item.name] = imagens

    return Inventario(imagens_por_pessoa, ignorados)


def ler_imagem(caminho: Path) -> Any:
    """Le e decodifica a imagem ANTES do modelo.

    Separa "arquivo ruim" de "modelo falhou": entregue como caminho, uma
    imagem corrompida ou com acento no nome (o DeepFace exige ASCII) voltaria
    do adaptador como ModeloIndisponivel. `np.fromfile` + `imdecode` aceita
    caminhos com acento e usa o mesmo decodificador do `cv2.imread`.
    """
    dados = np.fromfile(caminho, dtype=np.uint8)  # OSError se inacessivel
    if dados.size == 0:
        raise ImagemIlegivel("arquivo vazio")

    import cv2  # so existe no ambiente com DeepFace

    imagem = cv2.imdecode(dados, cv2.IMREAD_COLOR)
    if imagem is None:
        raise ImagemIlegivel("formato nao decodificavel")
    return imagem


def extrair_embeddings(
    imagens_por_pessoa: dict[str, list[Path]],
    ler: Callable[[Path], Any],
    gerar: Callable[[Any], FaceEmbedding],
) -> tuple[dict[str, list[FaceEmbedding]], ResumoDaExtracao]:
    """Um embedding por imagem, agrupado por pessoa, com toda falha contada.

    Pessoa sem nenhum embedding valido fica fora do resultado -- e aparece
    na diferenca entre identidades recebidas e avaliadas.
    """
    por_pessoa: dict[str, list[FaceEmbedding]] = {}
    resumo = ResumoDaExtracao()

    for pessoa, imagens in imagens_por_pessoa.items():
        vetores = []
        for imagem in imagens:
            resumo.recebidas += 1
            try:
                vetores.append(gerar(ler(imagem)))
            except _ERROS_ESPERADOS as erro:
                resumo.falhas.append(Falha(imagem, _motivo(erro), str(erro)))
            except Exception as erro:
                # Nao e falha de imagem, e defeito: aborta, dizendo onde.
                erro.add_note(f"Imagem em processamento: {imagem}")
                raise
        resumo.processadas += len(vetores)
        if vetores:
            por_pessoa[pessoa] = vetores

    return por_pessoa, resumo


def montar_pares(
    por_pessoa: dict[str, list[FaceEmbedding]],
) -> tuple[np.ndarray, np.ndarray]:
    """Distancias dos pares genuinos e dos impostores."""
    genuinas: list[float] = []
    impostoras: list[float] = []

    for vetores in por_pessoa.values():
        for a, b in itertools.combinations(vetores, 2):
            genuinas.append(a.distancia_cosseno(b))

    pessoas = list(por_pessoa)
    for nome_a, nome_b in itertools.combinations(pessoas, 2):
        for a in por_pessoa[nome_a]:
            for b in por_pessoa[nome_b]:
                impostoras.append(a.distancia_cosseno(b))

    return np.array(genuinas), np.array(impostoras)


def relatar_inventario(inventario: Inventario) -> None:
    com_imagem = sum(1 for imgs in inventario.imagens_por_pessoa.values() if imgs)
    print(
        f"Identidades (pastas): {len(inventario.imagens_por_pessoa)} "
        f"| com 1+ imagem: {com_imagem}"
    )
    print(f"Imagens ({', '.join(sorted(EXTENSOES))}): {inventario.total_de_imagens}")
    if inventario.ignorados:
        print(
            "Arquivos ignorados (fora do formato esperado): "
            f"{len(inventario.ignorados)}"
        )


def relatar_extracao(
    resumo: ResumoDaExtracao, por_pessoa: dict[str, list[FaceEmbedding]]
) -> None:
    print("\n=== Extracao ===")
    print(f"Imagens recebidas : {resumo.recebidas}")
    print(f"Processadas       : {resumo.processadas}")
    print(f"Rejeitadas        : {len(resumo.falhas)}")
    for motivo, quantidade in resumo.por_motivo().most_common():
        print(f"  {motivo:<28}: {quantidade}")

    for falha in resumo.falhas[:LIMITE_DE_DETALHES]:
        print(
            f"  - {falha.imagem.parent.name}/{falha.imagem.name}: "
            f"{falha.motivo} ({falha.detalhe})"
        )
    if len(resumo.falhas) > LIMITE_DE_DETALHES:
        print(f"  ... e mais {len(resumo.falhas) - LIMITE_DE_DETALHES}")

    com_par = sum(1 for vetores in por_pessoa.values() if len(vetores) >= 2)
    print(
        f"Identidades avaliadas: {len(por_pessoa)} "
        f"| com 2+ embeddings (geram pares genuinos): {com_par}"
    )
    if resumo.falhas:
        print(
            f"AVISO: a amostra avaliada ({resumo.processadas} imagens) e menor "
            f"que a recebida ({resumo.recebidas})."
        )


def relatar(genuinas: np.ndarray, impostoras: np.ndarray, limiar_atual: float) -> None:
    print(
        "\n*** MODO EXPLORATORIO: limiar sugerido e erro medidos sobre os MESMOS "
        "pares.\n*** Resultado otimista; NAO use para fixar FACE_THRESHOLD. "
        "Ver docs/ML-EXPERIMENT-SETUP.md."
    )
    print(f"\nPares genuinos : {genuinas.size}")
    print(f"Pares impostores: {impostoras.size}")
    print(
        f"\nDistancia genuina  -- media {genuinas.mean():.4f} "
        f"| min {genuinas.min():.4f} | max {genuinas.max():.4f}"
    )
    print(
        f"Distancia impostora -- media {impostoras.mean():.4f} "
        f"| min {impostoras.min():.4f} | max {impostoras.max():.4f}"
    )
    print(f"\nAUC: {area_sob_a_curva(genuinas, impostoras):.4f}")

    ponto_eer = eer(genuinas, impostoras)
    print(
        f"EER: {(ponto_eer.far + ponto_eer.frr) / 2:.4f} "
        f"no limiar {ponto_eer.limiar:.4f}"
    )

    far_atual, frr_atual = far_frr(genuinas, impostoras, limiar_atual)
    print(
        f"\nFACE_THRESHOLD atual ({limiar_atual:.2f}): "
        f"FAR {far_atual:.4f} | FRR {frr_atual:.4f}"
    )

    print("\nLimiar sugerido por teto de FAR:")
    print(f"{'FAR maximo':>11} | {'limiar':>8} | {'FAR':>7} | {'FRR':>7}")
    print("-" * 42)
    for teto in (0.0, 0.001, 0.01, 0.05):
        ponto = limiar_para_far_maximo(genuinas, impostoras, teto)
        if ponto is None:
            print(f"{teto:>11.3f} |  (nenhum limiar atinge este teto)")
            continue
        print(
            f"{teto:>11.3f} | {ponto.limiar:>8.4f} | "
            f"{ponto.far:>7.4f} | {ponto.frr:>7.4f}"
        )

    print(
        "\nPara controle de presenca, escolha pelo teto de FAR: recusar um "
        "aluno legitimo\ncusta uma segunda tentativa; aceitar um impostor "
        "corrompe o registro oficial.\n"
    )


def validar_divisao(dataset: Path, seed: int) -> int:
    """Confere se o dataset sustenta o protocolo treino/validacao/teste.

    So le a estrutura de pastas: nao carrega modelo, nao calcula metrica.
    As contagens sao POTENCIAIS -- a extracao ainda pode recusar imagens.
    """
    inventario = inventariar(dataset)
    relatar_inventario(inventario)

    contagem = {
        pessoa: len(imagens)
        for pessoa, imagens in inventario.imagens_por_pessoa.items()
        if imagens
    }
    try:
        divisao = dividir_por_identidade(contagem, seed)
        resumos = divisao.resumir(contagem)
        verificar_suficiencia(resumos)
    except DadosInsuficientes as erro:
        print(f"ERRO: dados insuficientes para a divisao: {erro}", file=sys.stderr)
        return 2

    print(f"\n=== Divisao por identidade (seed {seed}) ===")
    print(
        f"{'conjunto':>10} | {'ident.':>6} | {'imagens':>7} | "
        f"{'genuinos':>8} | {'impostores':>10}"
    )
    print("-" * 55)
    for r in resumos:
        print(
            f"{r.nome:>10} | {r.identidades:>6} | {r.imagens:>7} | "
            f"{r.pares_genuinos:>8} | {r.pares_impostores:>10}"
        )
    # A construcao da Divisao ja recusa sobreposicao; chegar aqui e a prova.
    print("\nSobreposicao de identidades entre conjuntos: nenhuma (verificada)")
    print(f"Assinatura da divisao: {divisao.assinatura()}")
    print(
        "Contagens potenciais: a extracao pode recusar imagens. "
        "Nenhuma metrica e calculada neste modo."
    )
    return 0


def avaliar_exploratorio(dataset: Path) -> int:
    settings = get_settings()
    configurar_logging("WARNING")

    try:
        from src.infrastructure.face_recognition.deepface_adapter import (
            DeepFaceAdapter,
        )
    except ImportError as exc:
        print(f"ERRO: DeepFace indisponivel: {exc}", file=sys.stderr)
        print("Use um Python 3.12 ou 3.13 com as dependencias.", file=sys.stderr)
        return 2

    # Avaliacao A, sem prova de vida: o conjunto e composto de fotografias, e
    # recusa-las derrotaria a propria medicao. A eficacia do anti-spoofing e
    # a Avaliacao B, com dataset de ataques (docs/ML-EXPERIMENT-SETUP.md).
    provider = DeepFaceAdapter(
        modelo=settings.face_model,
        detector=settings.face_detector,
        anti_spoofing=False,
    )

    print("Avaliacao A -- reconhecimento facial, SEM prova de vida")
    print(f"Modelo: {settings.face_model} | detector: {settings.face_detector}")
    try:
        provider.preaquecer()
    except ModeloIndisponivel as erro:
        print(f"ERRO: o modelo nao carregou: {erro}", file=sys.stderr)
        return 2

    print(f"Lendo {dataset}...")
    inventario = inventariar(dataset)
    relatar_inventario(inventario)

    por_pessoa, resumo = extrair_embeddings(
        inventario.imagens_por_pessoa, ler_imagem, provider.gerar_embedding
    )
    relatar_extracao(resumo, por_pessoa)

    if len(por_pessoa) < 2:
        print("ERRO: sao necessarias ao menos 2 pessoas.", file=sys.stderr)
        return 2

    genuinas, impostoras = montar_pares(por_pessoa)
    if genuinas.size == 0:
        print(
            "ERRO: nenhum par genuino. Cada pessoa precisa de 2+ imagens.",
            file=sys.stderr,
        )
        return 2

    relatar(genuinas, impostoras, settings.face_threshold)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avaliacao FAR/FRR do modelo")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--validar-divisao",
        action="store_true",
        help="valida estrutura e divisao por identidade, sem modelo e sem metricas",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help=f"semente da divisao (padrao {SEED_PADRAO}); exige --validar-divisao",
    )
    args = parser.parse_args(argv)

    if args.seed is not None and not args.validar_divisao:
        parser.error("--seed so se aplica com --validar-divisao")

    if not args.dataset.is_dir():
        print(f"ERRO: diretorio nao encontrado: {args.dataset}", file=sys.stderr)
        return 2

    if args.validar_divisao:
        seed = SEED_PADRAO if args.seed is None else args.seed
        return validar_divisao(args.dataset, seed)
    return avaliar_exploratorio(args.dataset)


if __name__ == "__main__":
    raise SystemExit(main())
