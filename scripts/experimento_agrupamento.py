"""Executor autorizado e isolado para clustering experimental da Etapa 4."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections.abc import Mapping
from dataclasses import asdict
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agrupamento_embeddings import (
    SelecaoHiperparametros,
    calcular_metricas_externas,
    contar_embeddings_duplicados,
    diagnosticar_estabilidade,
    executar_dbscan,
    executar_kmeans,
    normalizar_embeddings,
    selecionar_dbscan,
    selecionar_kmeans,
)
from scripts.calibrar_limiar import (
    CacheDeEmbeddings,
    CacheIncompativel,
    ConfiguracaoDaExtracao,
    Tabela,
    extrair,
    hash_do_arquivo,
    selecionar,
)
from scripts.divisao_por_identidade import DadosInsuficientes, dividir_por_identidade
from scripts.evaluate_model import inventariar, ler_imagem
from scripts.experimento_identificacao_aberta import (
    AutorizacaoAusente,
    verificar_autorizacao,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAIDA_PADRAO = PROJECT_ROOT / "avaliacao" / "resultados" / "etapa4"
CACHE_ETAPA4 = PROJECT_ROOT / "avaliacao" / "cache" / "etapa4"
MODELO = "Facenet512"
DETECTOR = "opencv"
SEED_PADRAO = 42
MIN_IMAGENS_POR_IDENTIDADE = 2
MAX_IMAGENS_POR_IDENTIDADE = 10
_ARQUIVO_CONGELAMENTO = "congelamento.json"
_ARQUIVO_HASH_CONGELAMENTO = "congelamento.sha256"
_ARQUIVO_MARCADOR_TESTE = ".teste-consumido.json"


class RevisaoAutorizacaoPendente(PermissionError):
    """Revisao externa/institucional da finalidade ainda nao foi confirmada."""


def verificar_gate_autorizacao(caminho: Path, *, revisao_confirmada: bool) -> str:
    """Exige atestacao do operador e documento; nao valida juridicamente seu teor."""
    if not revisao_confirmada:
        raise RevisaoAutorizacaoPendente
    return verificar_autorizacao(caminho)


def hash_json(valor: Any) -> str:
    canonico = json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonico).hexdigest().upper()


def validar_diretorio_saida(caminho: Path) -> Path:
    raiz = (PROJECT_ROOT / "avaliacao").resolve()
    destino = Path(caminho).resolve()
    if destino != raiz / "resultados" / "etapa4":
        raise ValueError("A saida deve estar em avaliacao/resultados/etapa4.")
    return destino


def caminho_cache_particao(execucao_hash: str, particao: str) -> Path:
    if len(execucao_hash) != 64 or any(
        caractere not in "0123456789ABCDEF" for caractere in execucao_hash.upper()
    ):
        raise ValueError("Hash de execucao invalido para cache experimental.")
    if particao not in {"desenvolvimento", "validacao", "teste"}:
        raise ValueError("Particao invalida para cache experimental.")
    return CACHE_ETAPA4 / execucao_hash.upper() / particao


def _versao(pacote: str) -> str:
    try:
        return metadata.version(pacote)
    except metadata.PackageNotFoundError:
        return "ausente"


def _configuracao_extracao() -> ConfiguracaoDaExtracao:
    return ConfiguracaoDaExtracao(
        modelo=MODELO,
        detector=DETECTOR,
        deepface=_versao("deepface"),
        opencv=_versao("opencv-python"),
        tensorflow=_versao("tensorflow"),
    )


def _metadados_extracao(configuracao: ConfiguracaoDaExtracao) -> dict[str, Any]:
    return {
        **asdict(configuracao),
        "dimensao": 512,
        "python": platform.python_version(),
        "numpy": _versao("numpy"),
        "scikit_learn": _versao("scikit-learn"),
        "matplotlib": _versao("matplotlib"),
        "preprocessamento": (
            "DeepFace FaceNet512; detector opencv; alinhamento=True; "
            "anti_spoofing=False; normalizacao L2"
        ),
    }


def _protocolo() -> dict[str, Any]:
    return {
        "divisao_identidades": [0.6, 0.2, 0.2],
        "min_imagens_por_identidade": MIN_IMAGENS_POR_IDENTIDADE,
        "max_imagens_por_identidade": MAX_IMAGENS_POR_IDENTIDADE,
        "dbscan_eps": [0.10, 0.20, 0.35, 0.50, 0.75],
        "dbscan_min_samples": [2, 3, 5],
        "dbscan_cobertura_minima": 0.5,
        "kmeans_n_clusters": [2, 3, 5, 8, 13],
        "kmeans_n_init": 10,
        "criterio_selecao": "silhouette cosseno + cobertura; sem rotulos",
        "estabilidade": {"fracao": 0.8, "repeticoes": 5, "seed_offset": 1},
    }


def _fingerprint_dataset(hashes: Mapping[Path, str]) -> str:
    digest = hashlib.sha256()
    for _caminho, hash_imagem in sorted(hashes.items(), key=lambda item: str(item[0])):
        digest.update(hash_imagem.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def _hash_execucao(
    *,
    dataset_hash: str,
    assinatura_divisao: str,
    autorizacao_hash: str,
    seed: int,
    extracao: dict[str, Any],
) -> str:
    return hash_json(
        {
            "dataset_sha256": dataset_hash,
            "assinatura_divisao": assinatura_divisao,
            "autorizacao_sha256": autorizacao_hash,
            "seed": seed,
            "extracao": extracao,
            "protocolo": _protocolo(),
        }
    )


def criar_manifesto_seguro(
    *,
    autorizacao_hash: str,
    dataset_hash: str,
    assinatura_divisao: str,
    execucao_hash: str,
    seed: int,
    configuracoes: dict[str, dict[str, float | int] | None],
    contagens: dict[str, Any],
    diagnosticos: dict[str, Any],
    extracao: dict[str, Any],
) -> dict[str, Any]:
    """Manifesto agregado; nao persiste nomes, caminhos nem vetores."""
    return {
        "esquema": 1,
        "autorizacao_sha256": autorizacao_hash,
        "dataset_sha256": dataset_hash,
        "assinatura_divisao": assinatura_divisao,
        "execucao_sha256": execucao_hash,
        "seed": seed,
        "configuracoes_congeladas": configuracoes,
        "contagens": contagens,
        "diagnosticos_desenvolvimento_validacao": diagnosticos,
        "extracao": extracao,
        "protocolo": _protocolo(),
        "sem_ids_caminhos_ou_embeddings": True,
    }


def reservar_teste_uma_vez(saida: Path, congelamento_hash: str) -> Path:
    saida = validar_diretorio_saida(saida)
    saida.mkdir(parents=True, exist_ok=True)
    marcador = saida / _ARQUIVO_MARCADOR_TESTE
    conteudo = {
        "congelamento_sha256": congelamento_hash,
        "protocolo": "holdout reservado antes de inventariar/extrair a particao teste",
    }
    try:
        with marcador.open("x", encoding="utf-8") as arquivo:
            json.dump(conteudo, arquivo, sort_keys=True, ensure_ascii=False)
            arquivo.write("\n")
    except FileExistsError as erro:
        raise RuntimeError(
            "O teste final da Etapa 4 so pode ser consumido uma vez."
        ) from erro
    return marcador


def _selecionar_dataset(
    dataset: Path, seed: int
) -> tuple[Any, dict[Path, str], Any, str]:
    inventario = inventariar(dataset)
    hashes = {
        imagem: hash_do_arquivo(imagem)
        for caminhos in inventario.imagens_por_pessoa.values()
        for imagem in caminhos
    }
    if not hashes:
        raise ValueError("Dataset autorizado sem imagens suportadas.")
    selecao = selecionar(
        inventario.imagens_por_pessoa,
        hashes,
        min_imagens=MIN_IMAGENS_POR_IDENTIDADE,
        max_imagens=MAX_IMAGENS_POR_IDENTIDADE,
        seed=seed,
    )
    if len(selecao.imagens_por_pessoa) < 6:
        raise DadosInsuficientes("Sao necessarias ao menos seis identidades elegiveis.")
    dataset_hash = _fingerprint_dataset(
        {
            caminho: hashes[caminho]
            for imagens in selecao.imagens_por_pessoa.values()
            for caminho in imagens
        }
    )
    divisao = dividir_por_identidade(selecao.imagens_por_pessoa, seed=seed)
    return selecao, hashes, divisao, dataset_hash


def _extrair_particao(
    selecao_global: Any,
    identidades: tuple[str, ...],
    hashes: dict[Path, str],
    cache: CacheDeEmbeddings,
    gerar: Any,
    seed: int,
) -> tuple[Tabela, dict[str, int]]:
    selecao_split = selecionar(
        {nome: selecao_global.imagens_por_pessoa[nome] for nome in identidades},
        hashes,
        min_imagens=MIN_IMAGENS_POR_IDENTIDADE,
        max_imagens=MAX_IMAGENS_POR_IDENTIDADE,
        seed=seed,
    )
    tabela, resumo = extrair(selecao_split, hashes, ler_imagem, gerar, cache)
    if tabela.vetores.size and (
        tabela.vetores.ndim != 2
        or tabela.vetores.shape[1] != 512
        or not np.isfinite(tabela.vetores).all()
    ):
        raise ValueError("Embeddings extraidos nao correspondem ao FaceNet512 valido.")
    return tabela, {
        motivo.value: quantidade for motivo, quantidade in resumo.por_motivo().items()
    }


def _criar_extrator() -> Any:
    # Importacao sob demanda: so ocorre depois do gate de autorizacao.
    from src.infrastructure.face_recognition.deepface_adapter import DeepFaceAdapter

    return DeepFaceAdapter(MODELO, DETECTOR, anti_spoofing=False)


def _resultado_interno(
    matriz: np.ndarray,
    configuracoes: dict[str, dict[str, float | int] | None],
    *,
    seed: int,
) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    if matriz.shape[0] == 0:
        return resultado
    matriz = normalizar_embeddings(matriz)
    for nome, configuracao in configuracoes.items():
        if configuracao is None:
            resultado[nome] = {"estado": "indisponivel_sem_configuracao"}
            continue
        try:
            agrupamento = (
                executar_dbscan(
                    matriz,
                    eps=float(configuracao["eps"]),
                    min_samples=int(configuracao["min_samples"]),
                )
                if nome == "dbscan"
                else executar_kmeans(
                    matriz,
                    n_clusters=int(configuracao["n_clusters"]),
                    seed=seed,
                )
            )
        except ValueError:
            resultado[nome] = {"estado": "dados_insuficientes"}
            continue
        resultado[nome] = asdict(agrupamento.diagnosticos)
    return resultado


def _sumario_selecao(selecao: SelecaoHiperparametros) -> dict[str, Any]:
    return {
        "configuracao_selecionada": selecao.configuracao_selecionada,
        "criterio": selecao.criterio,
        "motivo_indisponibilidade": selecao.motivo_indisponibilidade,
        "candidatos": [asdict(candidato) for candidato in selecao.candidatos],
    }


def _preparar(args: argparse.Namespace, autorizacao_hash: str) -> int:
    saida = validar_diretorio_saida(args.saida)
    congelamento_path = saida / _ARQUIVO_CONGELAMENTO
    if congelamento_path.exists():
        print(
            "ERRO: congelamento existente; use diretório experimental limpo.",
            file=sys.stderr,
        )
        return 2
    if not args.dataset.is_dir():
        print("ERRO: dataset ausente ou não é diretório.", file=sys.stderr)
        return 2

    selecao, hashes, divisao, dataset_hash = _selecionar_dataset(
        args.dataset, args.seed
    )
    configuracao_extracao = _configuracao_extracao()
    metadados_extracao = _metadados_extracao(configuracao_extracao)
    execucao_hash = _hash_execucao(
        dataset_hash=dataset_hash,
        assinatura_divisao=divisao.assinatura(),
        autorizacao_hash=autorizacao_hash,
        seed=args.seed,
        extracao=metadados_extracao,
    )
    extrator = _criar_extrator()
    extrator.preaquecer()
    tabelas: dict[str, Tabela] = {}
    falhas: dict[str, dict[str, int]] = {}
    for nome, identidades in (
        ("desenvolvimento", divisao.treino),
        ("validacao", divisao.validacao),
    ):
        cache = CacheDeEmbeddings(
            caminho_cache_particao(execucao_hash, nome), configuracao_extracao
        )
        tabelas[nome], falhas[nome] = _extrair_particao(
            selecao, identidades, hashes, cache, extrator.gerar_embedding, args.seed
        )

    matriz_desenvolvimento = tabelas["desenvolvimento"].vetores
    selecoes: dict[str, SelecaoHiperparametros] = {}
    if matriz_desenvolvimento.shape[0] >= 3:
        selecoes["dbscan"] = selecionar_dbscan(matriz_desenvolvimento)
        selecoes["kmeans"] = selecionar_kmeans(matriz_desenvolvimento, seed=args.seed)
    configuracoes = {
        nome: selecao_hyper.configuracao_selecionada
        for nome, selecao_hyper in selecoes.items()
    }
    for nome in ("dbscan", "kmeans"):
        configuracoes.setdefault(nome, None)
    estabilidade: dict[str, Any] = {}
    if matriz_desenvolvimento.shape[0] >= 4:
        for nome, configuracao in configuracoes.items():
            if configuracao is None:
                continue
            estabilidade[nome] = asdict(
                diagnosticar_estabilidade(
                    matriz_desenvolvimento,
                    configuracao,
                    algoritmo=nome,  # type: ignore[arg-type]
                    seed=args.seed,
                )
            )
    diagnosticos = {
        "desenvolvimento": {
            "selecao": {
                nome: _sumario_selecao(item) for nome, item in selecoes.items()
            },
            "estabilidade_subamostragem": estabilidade,
            "duplicatas_embeddings": (
                contar_embeddings_duplicados(matriz_desenvolvimento)
                if matriz_desenvolvimento.shape[0] > 1
                else None
            ),
        },
        "validacao": _resultado_interno(
            tabelas["validacao"].vetores, configuracoes, seed=args.seed
        ),
    }
    contagens: dict[str, Any] = {
        nome: {
            "identidades": len(identidades),
            "imagens_planejadas": sum(
                len(selecao.imagens_por_pessoa[identidade])
                for identidade in identidades
            ),
            "embeddings_extraidos": int(tabelas[nome].vetores.shape[0]),
            "falhas_extracao": falhas[nome],
        }
        for nome, identidades in (
            ("desenvolvimento", divisao.treino),
            ("validacao", divisao.validacao),
        )
    }
    contagens["teste"] = {
        "identidades_reservadas": len(
            set(selecao.imagens_por_pessoa)
            - set(divisao.treino)
            - set(divisao.validacao)
        ),
        "estado": "nao_extraido_ou_avaliado",
    }
    contagens["selecao_dataset"] = {
        "duplicatas_exatas_mesma_identidade": selecao.duplicatas_na_identidade,
        "duplicatas_exatas_entre_identidades": selecao.duplicatas_entre_identidades,
        "identidades_com_poucas_imagens": selecao.identidades_com_poucas_imagens,
        "imagens_excedentes": selecao.imagens_excedentes,
    }
    manifesto = criar_manifesto_seguro(
        autorizacao_hash=autorizacao_hash,
        dataset_hash=dataset_hash,
        assinatura_divisao=divisao.assinatura(),
        execucao_hash=execucao_hash,
        seed=args.seed,
        configuracoes=configuracoes,
        contagens=contagens,
        diagnosticos=diagnosticos,
        extracao=metadados_extracao,
    )
    saida.mkdir(parents=True, exist_ok=True)
    temporario = congelamento_path.with_suffix(".tmp")
    temporario.write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporario.replace(congelamento_path)
    # Hash the JSON form that was actually persisted; JSON object keys are
    # strings even when diagnostics originally used integer cluster labels.
    manifesto_persistido = json.loads(congelamento_path.read_text(encoding="utf-8"))
    (saida / _ARQUIVO_HASH_CONGELAMENTO).write_text(
        hash_json(manifesto_persistido) + "\n", encoding="ascii"
    )
    print("Parâmetros congelados; as identidades de teste não foram extraídas.")
    return 0


def _carregar_congelamento(path: Path) -> tuple[dict[str, Any], str]:
    try:
        manifesto = json.loads(path.read_text(encoding="utf-8"))
        hash_esperado = (
            path.with_name(_ARQUIVO_HASH_CONGELAMENTO)
            .read_text(encoding="ascii")
            .strip()
        )
    except (OSError, json.JSONDecodeError) as erro:
        raise ValueError("Congelamento ausente ou inválido.") from erro
    hash_atual = hash_json(manifesto)
    if hash_esperado != hash_atual or manifesto.get("esquema") != 1:
        raise ValueError("Congelamento alterado ou incompatível.")
    if manifesto.get("protocolo") != _protocolo():
        raise ValueError("Protocolo do congelamento difere do código atual.")
    if not manifesto.get("sem_ids_caminhos_ou_embeddings"):
        raise ValueError("Congelamento não atende aos requisitos de privacidade.")
    return manifesto, hash_atual


def _avaliar(args: argparse.Namespace, autorizacao_hash: str) -> int:
    saida = validar_diretorio_saida(args.saida)
    congelamento_path = args.congelamento
    if congelamento_path.resolve() != (saida / _ARQUIVO_CONGELAMENTO).resolve():
        print(
            "ERRO: congelamento deve estar no diretório fixo da Etapa 4.",
            file=sys.stderr,
        )
        return 2
    try:
        manifesto, hash_congelamento = _carregar_congelamento(congelamento_path)
    except ValueError as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 2
    if manifesto.get("autorizacao_sha256") != autorizacao_hash:
        print("ERRO: documento de autorização difere do congelamento.", file=sys.stderr)
        return 2
    configuracao_extracao = _configuracao_extracao()
    metadados_extracao = _metadados_extracao(configuracao_extracao)
    if manifesto.get("extracao") != metadados_extracao:
        print(
            "ERRO: versão/configuração FaceNet512 difere do congelamento.",
            file=sys.stderr,
        )
        return 2
    try:
        reservar_teste_uma_vez(saida, hash_congelamento)
    except RuntimeError as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 2
    if not args.dataset.is_dir():
        print("ERRO: dataset ausente ou não é diretório.", file=sys.stderr)
        return 2

    try:
        selecao, hashes, divisao, dataset_hash = _selecionar_dataset(
            args.dataset, int(manifesto["seed"])
        )
    except (ValueError, DadosInsuficientes, OSError) as erro:
        print(
            f"ERRO: dados de teste não utilizáveis ({type(erro).__name__}).",
            file=sys.stderr,
        )
        return 2
    execucao_hash = _hash_execucao(
        dataset_hash=dataset_hash,
        assinatura_divisao=divisao.assinatura(),
        autorizacao_hash=autorizacao_hash,
        seed=int(manifesto["seed"]),
        extracao=metadados_extracao,
    )
    if (
        dataset_hash != manifesto.get("dataset_sha256")
        or divisao.assinatura() != manifesto.get("assinatura_divisao")
        or execucao_hash != manifesto.get("execucao_sha256")
    ):
        print(
            "ERRO: dataset/divisão não correspondem ao congelamento.", file=sys.stderr
        )
        return 2
    configuracoes = manifesto.get("configuracoes_congeladas")
    if not isinstance(configuracoes, dict) or not any(configuracoes.values()):
        print("ERRO: nenhum algoritmo tem configuração selecionada.", file=sys.stderr)
        return 2
    parametros_congelados: dict[str, float] = {}
    for nome, configuracao in configuracoes.items():
        if not isinstance(configuracao, dict):
            continue
        valor = configuracao.get("eps", configuracao.get("n_clusters", 1.0))
        if isinstance(valor, (float, int)):
            parametros_congelados[nome] = float(valor)
    if not parametros_congelados:
        print("ERRO: parametros congelados invalidos.", file=sys.stderr)
        return 2
    try:
        identidades_teste = divisao.abrir_teste(parametros_congelados)
    except (RuntimeError, ValueError) as erro:
        print(
            f"ERRO: holdout não pôde ser aberto ({type(erro).__name__}).",
            file=sys.stderr,
        )
        return 2

    cache = CacheDeEmbeddings(
        caminho_cache_particao(execucao_hash, "teste"), configuracao_extracao
    )
    extrator = _criar_extrator()
    extrator.preaquecer()
    tabela, falhas = _extrair_particao(
        selecao,
        identidades_teste,
        hashes,
        cache,
        extrator.gerar_embedding,
        int(manifesto["seed"]),
    )
    resultado: dict[str, Any] = {
        "esquema": 1,
        "conjunto": "teste_independente_por_identidade",
        "seed": int(manifesto["seed"]),
        "assinatura_divisao": divisao.assinatura(),
        "dataset_sha256": dataset_hash,
        "contagens": {
            "identidades_teste": len(identidades_teste),
            "imagens_planejadas": sum(
                len(selecao.imagens_por_pessoa[identidade])
                for identidade in identidades_teste
            ),
            "embeddings_extraidos": int(tabela.vetores.shape[0]),
            "falhas_extracao": falhas,
        },
        "algoritmos": {},
        "graficos": [],
        "observacao_transdutiva": (
            "Cada algoritmo foi reajustado sem rotulos dentro da particao teste; "
            "isso nao equivale a predicao indutiva para novas amostras."
        ),
    }
    resultados_teste = {}
    matriz_teste = tabela.vetores
    if matriz_teste.shape[0]:
        matriz_teste = normalizar_embeddings(matriz_teste)
        y_teste = tabela.identidade.astype(np.int64, copy=False)
        for nome, configuracao in configuracoes.items():
            item: dict[str, Any] = {"configuracao": configuracao}
            if not isinstance(configuracao, dict):
                item["estado"] = "indisponivel_sem_configuracao"
                resultado["algoritmos"][nome] = item
                continue
            try:
                agrupamento = (
                    executar_dbscan(
                        matriz_teste,
                        eps=float(configuracao["eps"]),
                        min_samples=int(configuracao["min_samples"]),
                    )
                    if nome == "dbscan"
                    else executar_kmeans(
                        matriz_teste,
                        n_clusters=int(configuracao["n_clusters"]),
                        seed=int(manifesto["seed"]),
                    )
                )
            except ValueError:
                item["estado"] = "dados_insuficientes_para_configuracao_congelada"
                resultado["algoritmos"][nome] = item
                continue
            resultados_teste[nome] = agrupamento
            item["estado"] = agrupamento.diagnosticos.status
            item["metricas_internas"] = asdict(agrupamento.diagnosticos)
            # Os rotulos verdadeiros so entram aqui, depois de congelar e ajustar
            # o agrupamento sem supervisao na particao reservada.
            item["metricas_externas"] = calcular_metricas_externas(
                y_teste, agrupamento.rotulos
            )
            resultado["algoritmos"][nome] = item
    else:
        resultado["estado"] = "nenhum_embedding_extraido"
        for nome, configuracao in configuracoes.items():
            resultado["algoritmos"][nome] = {
                "estado": "indisponivel_sem_embeddings",
                "configuracao": configuracao,
            }
    if resultados_teste:
        from scripts.graficos_agrupamento import gerar

        arquivos = gerar(
            saida / "graficos",
            matriz_teste,
            tabela.identidade,
            resultados_teste,
            _candidatos_dbscan_para_grafico(manifesto),
            _carregar_cache_embeddings(
                execucao_hash, configuracao_extracao, "desenvolvimento"
            ),
        )
        resultado["graficos"] = [arquivo.name for arquivo in arquivos]
    destino = saida / "resultado.json"
    temporario = destino.with_suffix(".tmp")
    temporario.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporario.replace(destino)
    print("Métricas agregadas do teste gravadas sem IDs individuais ou embeddings.")
    return 0


def _candidatos_dbscan_para_grafico(
    manifesto: dict[str, Any],
) -> list[tuple[float, float | None]]:
    selecao = (
        manifesto.get("diagnosticos_desenvolvimento_validacao", {})
        .get("desenvolvimento", {})
        .get("selecao", {})
        .get("dbscan", {})
    )
    candidatos = selecao.get("candidatos", []) if isinstance(selecao, dict) else []
    resultado: list[tuple[float, float | None]] = []
    for candidato in candidatos:
        diagnosticos = candidato.get("diagnosticos")
        if not isinstance(diagnosticos, dict):
            continue
        silhouette = diagnosticos.get("silhouette_cosseno")
        resultado.append(
            (
                float(diagnosticos["percentual_ruido"]),
                None if silhouette is None else float(silhouette),
            )
        )
    return resultado


def _carregar_cache_embeddings(
    execucao_hash: str,
    configuracao: ConfiguracaoDaExtracao,
    particao: str,
) -> np.ndarray:
    cache = CacheDeEmbeddings(
        caminho_cache_particao(execucao_hash, particao), configuracao
    )
    return cache.matriz()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Etapa 4: clustering de embeddings")
    subparsers = parser.add_subparsers(dest="comando", required=True)
    preparar = subparsers.add_parser(
        "preparar", help="seleciona parâmetros sem abrir teste"
    )
    avaliar = subparsers.add_parser(
        "avaliar", help="abre e avalia teste congelado uma vez"
    )
    for subparser in (preparar, avaliar):
        subparser.add_argument("--dataset", type=Path, required=True)
        subparser.add_argument("--autorizacao-dataset", type=Path, required=True)
        subparser.add_argument(
            "--confirmar-revisao-autorizacao",
            action="store_true",
            help=(
                "declara que a autorização foi revisada para esta finalidade e "
                "que as aprovações institucionais necessárias foram obtidas"
            ),
        )
        subparser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    preparar.add_argument("--seed", type=int, default=SEED_PADRAO)
    avaliar.add_argument(
        "--congelamento", type=Path, default=SAIDA_PADRAO / _ARQUIVO_CONGELAMENTO
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        autorizacao_hash = verificar_gate_autorizacao(
            args.autorizacao_dataset,
            revisao_confirmada=args.confirmar_revisao_autorizacao,
        )
    except RevisaoAutorizacaoPendente:
        print(
            "ERRO: revisão externa/institucional da autorização pendente; "
            "dataset não acessado.",
            file=sys.stderr,
        )
        return 2
    except AutorizacaoAusente:
        print("ERRO: documento ausente/vazio; dataset não acessado.", file=sys.stderr)
        return 2
    try:
        if args.comando == "preparar":
            return _preparar(args, autorizacao_hash)
        return _avaliar(args, autorizacao_hash)
    except (
        CacheIncompativel,
        DadosInsuficientes,
        ImportError,
        OSError,
        ValueError,
        RuntimeError,
    ) as erro:
        print(f"ERRO: Etapa 4 não executada ({type(erro).__name__}).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
