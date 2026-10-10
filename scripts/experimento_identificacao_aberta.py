"""Execucao controlada da avaliacao experimental de identificacao aberta 1:N.

O documento local de autorizacao e verificado antes de inventariar o dataset,
ler o cache ou importar o DeepFace. Os artefatos ficam em avaliacao/, ignorado
pelo Git; os manifestos contêm apenas hashes e contagens agregadas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from dataclasses import asdict
from importlib import metadata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.calibrar_limiar import (
    CacheDeEmbeddings,
    CacheIncompativel,
    ConfiguracaoDaExtracao,
    hash_do_arquivo,
    selecionar,
)
from scripts.divisao_por_identidade import DadosInsuficientes, dividir_por_identidade
from scripts.evaluate_model import ImagemIlegivel, inventariar, ler_imagem
from scripts.identificacao_aberta import (
    LIMIAR_ETAPA_1,
    LIMIAR_HISTORICO,
    Amostra,
    EstrategiaGaleria,
    FaseProtocolo,
    SelecaoLimiar,
    avaliar_protocolo,
    bootstrap_por_identidade,
    construir_protocolo,
    contar_quase_duplicatas_por_identidade,
    reduzir_referencias,
    selecionar_limiar_fpir,
)
from src.domain.entities.face_embedding import EmbeddingInvalido, FaceEmbedding
from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAIDA_PADRAO = PROJECT_ROOT / "avaliacao" / "resultados" / "etapa3"
CACHE_PADRAO = PROJECT_ROOT / "avaliacao" / "cache"
CACHE_ETAPA3 = CACHE_PADRAO / "etapa3"
MODELO = "Facenet512"
DETECTOR = "opencv"
TETO_FPIR = 0.001
MAX_IMAGENS_POR_IDENTIDADE = 10
MIN_IMAGENS_POR_IDENTIDADE = 2
REFERENCIAS_POR_IDENTIDADE = 1
REFERENCIAS_MULTIPLAS = 3
FRACAO_DESCONHECIDAS = 0.2
MAX_CONSULTAS_POR_IDENTIDADE = 5
REPLICAS_BOOTSTRAP = 1000
_MARCADOR_TESTE = ".teste-consumido.json"
_ARQUIVO_HASH_CONGELAMENTO = "congelamento.sha256"


class AutorizacaoAusente(PermissionError):
    """Documento de autorização ausente ou vazio; dataset não foi acessado."""


def _sha256_bytes(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest().upper()


def hash_json(valor: Any) -> str:
    canonico = json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(canonico)


def _caminho_cache_particao(execucao_hash: str, particao: str) -> Path:
    """Isola cache por execução e partição para não abrir embeddings do holdout."""
    if len(execucao_hash) != 64 or any(
        caractere not in "0123456789ABCDEF" for caractere in execucao_hash.upper()
    ):
        raise ValueError("Hash de execução inválido para cache experimental.")
    if particao not in {"validacao", "teste"}:
        raise ValueError("Partição inválida para cache experimental.")
    return CACHE_ETAPA3 / execucao_hash.upper() / particao


def _id_execucao(
    dataset_hash: str,
    assinatura_divisao: str,
    autorizacao_hash: str,
    seed: int,
    configuracao_extracao: dict[str, Any],
) -> str:
    return hash_json(
        {
            "dataset_sha256": dataset_hash,
            "assinatura_divisao": assinatura_divisao,
            "autorizacao_sha256": autorizacao_hash,
            "seed": seed,
            "extracao": configuracao_extracao,
            "protocolo": _configuracao_protocolo(),
        }
    )


def _configuracao_protocolo() -> dict[str, Any]:
    """Parâmetros que devem permanecer congelados entre validação e teste."""
    return {
        "proporcoes_identidades": [0.6, 0.2, 0.2],
        "min_imagens_por_identidade": MIN_IMAGENS_POR_IDENTIDADE,
        "max_imagens_por_identidade": MAX_IMAGENS_POR_IDENTIDADE,
        "referencias_principais": REFERENCIAS_POR_IDENTIDADE,
        "referencias_comparacao_pareada": REFERENCIAS_MULTIPLAS,
        "fracao_identidades_desconhecidas": FRACAO_DESCONHECIDAS,
        "max_consultas_por_identidade": MAX_CONSULTAS_POR_IDENTIDADE,
        "estrategia_galeria": EstrategiaGaleria.MENOR_DISTANCIA.value,
        "teto_fpir_t2": TETO_FPIR,
        "tamanhos_galeria": [1, 10, 25, 50, 100, "completo"],
        "replicas_bootstrap": REPLICAS_BOOTSTRAP,
    }


def verificar_autorizacao(caminho: Path) -> str:
    """Confirma apenas a presença de documento não vazio e devolve seu hash.

    A presença do arquivo não é uma validação jurídica automática. O relatório
    preserva essa distinção e o executor nunca cria esse documento.
    """
    try:
        dados = Path(caminho).read_bytes()
    except OSError as erro:
        raise AutorizacaoAusente from erro
    if not dados.strip():
        raise AutorizacaoAusente
    return _sha256_bytes(dados)


def validar_diretorio_saida(caminho: Path) -> Path:
    raiz = (PROJECT_ROOT / "avaliacao").resolve()
    destino = Path(caminho).resolve()
    if destino != raiz / "resultados" / "etapa3":
        raise ValueError("A saída deve ser exatamente avaliacao/resultados/etapa3.")
    return destino


def criar_manifesto_seguro(
    *,
    autorizacao_hash: str,
    dataset_hash: str,
    assinatura_divisao: str,
    seed: int,
    execucao_hash: str,
    contagens: dict[str, Any],
    limiar_t2: float | None,
    suficiencia_t2: str,
    limiar_t2_um_pareado: float | None = None,
    suficiencia_t2_um_pareado: str = "indisponivel",
    limiar_t2_tres_referencias: float | None = None,
    suficiencia_t2_tres_referencias: str = "indisponivel",
    fpir_validacao: float | None = None,
    fnir_validacao: float | None = None,
    configuracao: dict[str, Any] | None = None,
    configuracao_protocolo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Manifesto sem nomes, caminhos, hashes de imagens ou scores individuais."""
    return {
        "esquema": 2,
        "autorizacao_sha256": autorizacao_hash,
        "dataset_sha256": dataset_hash,
        "assinatura_divisao": assinatura_divisao,
        "seed": seed,
        "execucao_sha256": execucao_hash,
        "proporcoes_identidades": {
            "desenvolvimento": 0.6,
            "validacao": 0.2,
            "teste": 0.2,
        },
        "contagens": contagens,
        "extracao": configuracao or {},
        "protocolo": configuracao_protocolo or _configuracao_protocolo(),
        "limiares_congelados": {
            "T0_historico": LIMIAR_HISTORICO,
            "T1_etapa1": LIMIAR_ETAPA_1,
            "T2_validacao_1n": limiar_t2,
            "T2_validacao_1referencia_pareada": limiar_t2_um_pareado,
            "T2_validacao_3referencias": limiar_t2_tres_referencias,
        },
        "calibracao_T2": {
            "teto_fpir": TETO_FPIR,
            "fpir_validacao": fpir_validacao,
            "fnir_validacao": fnir_validacao,
            "suficiencia": suficiencia_t2,
            "observacao": (
                "A suficiência amostral é reportada separadamente; presença de "
                "zero falsos aceites não garante FPIR zero."
            ),
            "3_referencias_suficiencia": suficiencia_t2_tres_referencias,
            "1_referencia_pareada_suficiencia": suficiencia_t2_um_pareado,
        },
        "sem_ids_ou_caminhos": True,
    }


def reservar_teste_uma_vez(saida: Path, congelamento: dict[str, Any]) -> Path:
    """Cria um marcador atômico antes da leitura de qualquer dado do teste."""
    saida = validar_diretorio_saida(saida)
    saida.mkdir(parents=True, exist_ok=True)
    marcador = saida / _MARCADOR_TESTE
    registro = {
        "hash_congelamento": hash_json(congelamento),
        "protocolo": "teste final reservado antes de extrair ou pontuar consultas",
    }
    try:
        with marcador.open("x", encoding="utf-8") as arquivo:
            json.dump(registro, arquivo, ensure_ascii=False, sort_keys=True)
            arquivo.write("\n")
    except FileExistsError as erro:
        raise RuntimeError(
            "O teste final só pode ser consumido uma única vez."
        ) from erro
    return marcador


def _versao(pacote: str) -> str:
    try:
        return metadata.version(pacote)
    except metadata.PackageNotFoundError:
        return "ausente"


def _metadados_extracao(config: ConfiguracaoDaExtracao) -> dict[str, Any]:
    return {
        **asdict(config),
        "dimensao": 512,
        "preprocessamento": (
            "DeepFace.extract_faces; detector opencv; align=True; "
            "anti_spoofing=False; FaceNet512; L2"
        ),
        "cache_config_key": config.chave(),
        "python": platform.python_version(),
        "numpy": _versao("numpy"),
        "matplotlib": _versao("matplotlib"),
    }


def _fingerprint_dataset(hashes: dict[Path, str]) -> str:
    digest = hashlib.sha256()
    for _caminho, hash_imagem in sorted(hashes.items(), key=lambda item: str(item[0])):
        digest.update(hash_imagem.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def _token_identidade(nome: str, dataset_hash: str, seed: int) -> str:
    return hashlib.sha256(f"{dataset_hash}:{seed}:{nome}".encode()).hexdigest()


def _amostras_do_split(
    selecao: Any,
    hashes: dict[Path, str],
    embeddings: dict[str, FaceEmbedding],
    dataset_hash: str,
    seed: int,
) -> list[Amostra]:
    resultado: list[Amostra] = []
    for nome, caminhos in selecao.imagens_por_pessoa.items():
        identidade = _token_identidade(nome, dataset_hash, seed)
        for caminho in caminhos:
            imagem_id = hashes[caminho]
            embedding = embeddings.get(imagem_id)
            resultado.append(
                Amostra(
                    identidade_id=identidade,
                    imagem_id=imagem_id,
                    embedding=embedding,
                    falha_extracao=None
                    if embedding is not None
                    else "falha_de_extracao",
                )
            )
    return resultado


def _extrair_particao(
    selecao: Any,
    hashes: dict[Path, str],
    cache: CacheDeEmbeddings,
    gerar: Any,
) -> tuple[dict[str, FaceEmbedding], Counter[str]]:
    embeddings: dict[str, FaceEmbedding] = {}
    falhas: Counter[str] = Counter()
    tipos_esperados = (
        (NenhumRostoDetectado, "sem_rosto"),
        (MultiplosRostosDetectados, "multiplos_rostos"),
        (ImagemIlegivel, "imagem_invalida"),
        (OSError, "erro_de_leitura"),
        (ModeloIndisponivel, "falha_de_inferencia"),
        (EmbeddingInvalido, "embedding_invalido"),
    )
    excecoes_esperadas = tuple(tipo for tipo, _ in tipos_esperados)
    for caminhos in selecao.imagens_por_pessoa.values():
        for caminho in caminhos:
            digest = hashes[caminho]
            embedding = cache.obter(digest)
            if embedding is not None:
                embeddings[digest] = embedding
                continue
            try:
                embedding = gerar(ler_imagem(caminho))
            except excecoes_esperadas as erro:
                motivo = next(
                    nome for tipo, nome in tipos_esperados if isinstance(erro, tipo)
                )
                falhas[motivo] += 1
                continue
            except Exception as erro:
                # Não acrescentar caminho nem detalhes de imagem ao erro/log.
                raise RuntimeError(
                    "Falha inesperada durante extração biométrica."
                ) from erro
            if embedding.modelo != MODELO or embedding.dimensao != 512:
                raise ValueError("A extração não corresponde ao FaceNet512 esperado.")
            cache.guardar(digest, embedding)
            embeddings[digest] = embedding
    cache.salvar()
    return embeddings, falhas


def _selecionar_t2(protocolo: Any) -> SelecaoLimiar:
    return selecionar_limiar_fpir(
        protocolo,
        far_maximo=TETO_FPIR,
        estrategia=EstrategiaGaleria.MENOR_DISTANCIA,
    )


def _contagens_split(selecao: Any, split: tuple[str, ...], nome: str) -> dict[str, int]:
    return {
        "identidades": len(split),
        "imagens": sum(len(selecao.imagens_por_pessoa[item]) for item in split),
    }


def _identidades_fora_dos_splits(
    divisao: Any, identidades: set[str]
) -> tuple[str, ...]:
    return tuple(sorted(identidades - set(divisao.treino) - set(divisao.validacao)))


def _criar_extrator() -> Any:
    # Lazy import: em particular, main verifica autorização antes deste ponto.
    from src.infrastructure.face_recognition.deepface_adapter import DeepFaceAdapter

    return DeepFaceAdapter(MODELO, DETECTOR, anti_spoofing=False)


def _preparar(args: argparse.Namespace, autorizacao_hash: str) -> int:
    saida = validar_diretorio_saida(args.saida)
    if (saida / "congelamento.json").exists():
        print(
            "ERRO: já existe congelamento; use um novo checkout experimental.",
            file=sys.stderr,
        )
        return 2
    if not args.dataset.is_dir():
        print("ERRO: dataset ausente ou não é diretório.", file=sys.stderr)
        return 2

    inventario = inventariar(args.dataset)
    hashes = {
        imagem: hash_do_arquivo(imagem)
        for caminhos in inventario.imagens_por_pessoa.values()
        for imagem in caminhos
    }
    if not hashes:
        print("ERRO: não há imagens suportadas no dataset.", file=sys.stderr)
        return 2
    selecao = selecionar(
        inventario.imagens_por_pessoa,
        hashes,
        min_imagens=MIN_IMAGENS_POR_IDENTIDADE,
        max_imagens=MAX_IMAGENS_POR_IDENTIDADE,
        seed=args.seed,
    )
    dataset_hash = _fingerprint_dataset(
        {
            caminho: hashes[caminho]
            for imagens in selecao.imagens_por_pessoa.values()
            for caminho in imagens
        }
    )
    try:
        divisao = dividir_por_identidade(selecao.imagens_por_pessoa, seed=args.seed)
    except DadosInsuficientes:
        print("ERRO: identidades insuficientes para divisão 60/20/20.", file=sys.stderr)
        return 2

    config = ConfiguracaoDaExtracao(
        modelo=MODELO,
        detector=DETECTOR,
        deepface=_versao("deepface"),
        opencv=_versao("opencv-python"),
        tensorflow=_versao("tensorflow"),
    )
    metadados_extracao = _metadados_extracao(config)
    assinatura_divisao = divisao.assinatura()
    execucao_hash = _id_execucao(
        dataset_hash,
        assinatura_divisao,
        autorizacao_hash,
        args.seed,
        metadados_extracao,
    )
    cache = CacheDeEmbeddings(
        _caminho_cache_particao(execucao_hash, "validacao"), config
    )
    provider = _criar_extrator()
    provider.preaquecer()
    validacao = selecionar(
        {nome: selecao.imagens_por_pessoa[nome] for nome in divisao.validacao},
        hashes,
        min_imagens=MIN_IMAGENS_POR_IDENTIDADE,
        max_imagens=MAX_IMAGENS_POR_IDENTIDADE,
        seed=args.seed,
    )
    embeddings, falhas = _extrair_particao(
        validacao, hashes, cache, provider.gerar_embedding
    )
    amostras = _amostras_do_split(
        validacao, hashes, embeddings, dataset_hash, args.seed
    )
    ids_validacao = [
        _token_identidade(nome, dataset_hash, args.seed)
        for nome in validacao.imagens_por_pessoa
    ]
    protocolo = construir_protocolo(
        amostras,
        ids_validacao,
        seed=args.seed,
        referencias_por_identidade=REFERENCIAS_POR_IDENTIDADE,
        fracao_desconhecidas=FRACAO_DESCONHECIDAS,
        max_consultas_por_identidade=MAX_CONSULTAS_POR_IDENTIDADE,
        fase=FaseProtocolo.VALIDACAO,
    )
    t2 = _selecionar_t2(protocolo)
    protocolo_tres_referencias = None
    protocolo_um_pareado = None
    t2_tres_referencias = SelecaoLimiar(None, None, None, 0, 0, "dados_insuficientes")
    t2_um_pareado = SelecaoLimiar(None, None, None, 0, 0, "dados_insuficientes")
    ids_com_quatro_imagens = sum(
        len(imagens) >= 4 for imagens in validacao.imagens_por_pessoa.values()
    )
    if ids_com_quatro_imagens >= 1 and len(validacao.imagens_por_pessoa) >= 2:
        try:
            protocolo_tres_referencias = construir_protocolo(
                amostras,
                ids_validacao,
                seed=args.seed,
                referencias_por_identidade=REFERENCIAS_MULTIPLAS,
                fracao_desconhecidas=FRACAO_DESCONHECIDAS,
                max_consultas_por_identidade=MAX_CONSULTAS_POR_IDENTIDADE,
                fase=FaseProtocolo.VALIDACAO,
            )
            protocolo_um_pareado = reduzir_referencias(protocolo_tres_referencias, 1)
            t2_um_pareado = _selecionar_t2(protocolo_um_pareado)
            t2_tres_referencias = _selecionar_t2(protocolo_tres_referencias)
        except ValueError:
            # O número bruto de fotos não garante classes conhecidas e abertas.
            protocolo_tres_referencias = None
            protocolo_um_pareado = None
    ids_teste = _identidades_fora_dos_splits(divisao, set(selecao.imagens_por_pessoa))
    contagens = {
        "desenvolvimento": _contagens_split(selecao, divisao.treino, "desenvolvimento"),
        "validacao": _contagens_split(selecao, divisao.validacao, "validacao"),
        "teste": _contagens_split(selecao, ids_teste, "teste"),
        "selecao": {
            "duplicatas_exatas_mesma_identidade": selecao.duplicatas_na_identidade,
            "duplicatas_exatas_entre_identidades": selecao.duplicatas_entre_identidades,
            "identidades_com_poucas_imagens": selecao.identidades_com_poucas_imagens,
            "imagens_excedentes": selecao.imagens_excedentes,
        },
        "validacao_papeis": {
            "identidades_conhecidas": len(protocolo.identidades_conhecidas),
            "identidades_desconhecidas": len(protocolo.identidades_desconhecidas),
            "consultas_conhecidas": len(protocolo.consultas_conhecidas),
            "consultas_desconhecidas": len(protocolo.consultas_desconhecidas),
            "falhas_extracao_por_motivo": dict(sorted(falhas.items())),
            "pares_quase_duplicados_d_lt_0_01": contar_quase_duplicatas_por_identidade(
                protocolo
            ),
        },
        "validacao_3_referencias": (
            {
                "identidades_conhecidas": len(
                    protocolo_tres_referencias.identidades_conhecidas
                ),
                "identidades_desconhecidas": len(
                    protocolo_tres_referencias.identidades_desconhecidas
                ),
                "consultas_conhecidas": len(
                    protocolo_tres_referencias.consultas_conhecidas
                ),
                "consultas_desconhecidas": len(
                    protocolo_tres_referencias.consultas_desconhecidas
                ),
            }
            if protocolo_tres_referencias is not None
            else {"disponivel": False}
        ),
        "validacao_referencias_pareadas": (
            {
                "disponivel": True,
                "identidades_conhecidas": len(
                    protocolo_um_pareado.identidades_conhecidas
                ),
                "identidades_desconhecidas": len(
                    protocolo_um_pareado.identidades_desconhecidas
                ),
                "consultas_conhecidas": len(protocolo_um_pareado.consultas_conhecidas),
                "consultas_desconhecidas": len(
                    protocolo_um_pareado.consultas_desconhecidas
                ),
            }
            if protocolo_um_pareado is not None
            else {"disponivel": False}
        ),
    }
    manifesto = criar_manifesto_seguro(
        autorizacao_hash=autorizacao_hash,
        dataset_hash=dataset_hash,
        assinatura_divisao=assinatura_divisao,
        seed=args.seed,
        execucao_hash=execucao_hash,
        contagens=contagens,
        limiar_t2=t2.limiar,
        suficiencia_t2=t2.suficiencia,
        limiar_t2_um_pareado=t2_um_pareado.limiar,
        suficiencia_t2_um_pareado=t2_um_pareado.suficiencia,
        limiar_t2_tres_referencias=t2_tres_referencias.limiar,
        suficiencia_t2_tres_referencias=t2_tres_referencias.suficiencia,
        fpir_validacao=t2.fpir_validacao,
        fnir_validacao=t2.fnir_validacao,
        configuracao=metadados_extracao,
        configuracao_protocolo=_configuracao_protocolo(),
    )
    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / "congelamento.json"
    destino.write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (saida / _ARQUIVO_HASH_CONGELAMENTO).write_text(
        hash_json(manifesto) + "\n", encoding="ascii"
    )
    print("Congelamento de validação gravado; o teste não foi extraído nem avaliado.")
    return 0


def _avaliar(args: argparse.Namespace, autorizacao_hash: str) -> int:
    saida = validar_diretorio_saida(args.saida)
    if args.congelamento.resolve() != (saida / "congelamento.json").resolve():
        print(
            "ERRO: o congelamento deve estar no diretório fixo da Etapa 3.",
            file=sys.stderr,
        )
        return 2
    try:
        manifesto = json.loads(args.congelamento.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("ERRO: congelamento ausente ou inválido.", file=sys.stderr)
        return 2
    if manifesto.get("autorizacao_sha256") != autorizacao_hash:
        print("ERRO: autorização diferente da usada no congelamento.", file=sys.stderr)
        return 2
    if (
        manifesto.get("esquema") != 2
        or not manifesto.get("sem_ids_ou_caminhos")
        or manifesto.get("protocolo") != _configuracao_protocolo()
    ):
        print("ERRO: esquema de congelamento incompatível.", file=sys.stderr)
        return 2
    try:
        hash_congelamento = (
            (saida / _ARQUIVO_HASH_CONGELAMENTO).read_text(encoding="ascii").strip()
        )
    except OSError:
        print("ERRO: hash do congelamento ausente.", file=sys.stderr)
        return 2
    if hash_congelamento != hash_json(manifesto):
        print("ERRO: congelamento foi alterado após a calibração.", file=sys.stderr)
        return 2
    # Marcador exclusivo antes de validar/listar/hashar o dataset ou abrir cache.
    try:
        reservar_teste_uma_vez(saida, manifesto)
    except RuntimeError as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 2
    if not args.dataset.is_dir():
        print("ERRO: dataset ausente ou não é diretório.", file=sys.stderr)
        return 2
    inventario = inventariar(args.dataset)
    hashes = {
        imagem: hash_do_arquivo(imagem)
        for caminhos in inventario.imagens_por_pessoa.values()
        for imagem in caminhos
    }
    selecao = selecionar(
        inventario.imagens_por_pessoa,
        hashes,
        min_imagens=MIN_IMAGENS_POR_IDENTIDADE,
        max_imagens=MAX_IMAGENS_POR_IDENTIDADE,
        seed=int(manifesto["seed"]),
    )
    dataset_hash = _fingerprint_dataset(
        {
            caminho: hashes[caminho]
            for imagens in selecao.imagens_por_pessoa.values()
            for caminho in imagens
        }
    )
    if dataset_hash != manifesto.get("dataset_sha256"):
        print(
            "ERRO: dataset difere do usado para congelar a validação.", file=sys.stderr
        )
        return 2
    divisao = dividir_por_identidade(
        selecao.imagens_por_pessoa, seed=int(manifesto["seed"])
    )
    if divisao.assinatura() != manifesto.get("assinatura_divisao"):
        print(
            "ERRO: divisão de identidades não corresponde ao congelamento.",
            file=sys.stderr,
        )
        return 2
    metadados_extracao_congelados = manifesto.get("extracao")
    if not isinstance(metadados_extracao_congelados, dict):
        print("ERRO: metadados de extração ausentes no congelamento.", file=sys.stderr)
        return 2
    execucao_hash = _id_execucao(
        dataset_hash,
        divisao.assinatura(),
        autorizacao_hash,
        int(manifesto["seed"]),
        metadados_extracao_congelados,
    )
    if manifesto.get("execucao_sha256") != execucao_hash:
        print(
            "ERRO: assinatura da execução não corresponde ao congelamento.",
            file=sys.stderr,
        )
        return 2
    limiares = manifesto.get("limiares_congelados")
    if (
        not isinstance(limiares, dict)
        or limiares.get("T0_historico") != LIMIAR_HISTORICO
        or limiares.get("T1_etapa1") != LIMIAR_ETAPA_1
    ):
        print("ERRO: os limiares congelados são inválidos.", file=sys.stderr)
        return 2
    t2 = limiares.get("T2_validacao_1n")
    limiares_a_avaliar = {"T0": LIMIAR_HISTORICO, "T1": LIMIAR_ETAPA_1}
    if t2 is not None:
        if not isinstance(t2, (float, int)) or not 0.0 <= float(t2) <= 2.0:
            print("ERRO: T2 inválido no congelamento.", file=sys.stderr)
            return 2
        limiares_a_avaliar["T2"] = float(t2)
    t2_tres_referencias = limiares.get("T2_validacao_3referencias")
    limiares_congelados_teste = dict(limiares_a_avaliar)
    t2_um_pareado = limiares.get("T2_validacao_1referencia_pareada")
    if isinstance(t2_um_pareado, (float, int)):
        limiares_congelados_teste["T2_1referencia_pareada"] = float(t2_um_pareado)
    if isinstance(t2_tres_referencias, (float, int)):
        limiares_congelados_teste["T2_3referencias"] = float(t2_tres_referencias)
    identidades_teste = divisao.abrir_teste(limiares_congelados_teste)
    teste = selecionar(
        {nome: selecao.imagens_por_pessoa[nome] for nome in identidades_teste},
        hashes,
        min_imagens=MIN_IMAGENS_POR_IDENTIDADE,
        max_imagens=MAX_IMAGENS_POR_IDENTIDADE,
        seed=int(manifesto["seed"]),
    )
    config = ConfiguracaoDaExtracao(
        modelo=MODELO,
        detector=DETECTOR,
        deepface=_versao("deepface"),
        opencv=_versao("opencv-python"),
        tensorflow=_versao("tensorflow"),
    )
    if manifesto.get("extracao") != _metadados_extracao(config):
        print(
            "ERRO: versões ou configuração FaceNet512 diferem do congelamento.",
            file=sys.stderr,
        )
        return 2
    cache = CacheDeEmbeddings(_caminho_cache_particao(execucao_hash, "teste"), config)
    provider = _criar_extrator()
    provider.preaquecer()
    embeddings, falhas = _extrair_particao(
        teste, hashes, cache, provider.gerar_embedding
    )
    amostras = _amostras_do_split(
        teste, hashes, embeddings, dataset_hash, int(manifesto["seed"])
    )
    ids_teste = [
        _token_identidade(nome, dataset_hash, int(manifesto["seed"]))
        for nome in teste.imagens_por_pessoa
    ]
    protocolo = construir_protocolo(
        amostras,
        ids_teste,
        seed=int(manifesto["seed"]),
        referencias_por_identidade=REFERENCIAS_POR_IDENTIDADE,
        fracao_desconhecidas=FRACAO_DESCONHECIDAS,
        max_consultas_por_identidade=MAX_CONSULTAS_POR_IDENTIDADE,
        fase=FaseProtocolo.TESTE,
    )
    protocolos_pareados: dict[int, Any] = {}
    validacao_multi = manifesto.get("contagens", {}).get("validacao_3_referencias", {})
    if (
        isinstance(validacao_multi, dict)
        and validacao_multi.get("disponivel") is not False
        and sum(
            len(imagens) >= REFERENCIAS_MULTIPLAS + 1
            for imagens in teste.imagens_por_pessoa.values()
        )
        >= 1
        and len(teste.imagens_por_pessoa) >= 2
    ):
        try:
            protocolo_tres = construir_protocolo(
                amostras,
                ids_teste,
                seed=int(manifesto["seed"]),
                referencias_por_identidade=REFERENCIAS_MULTIPLAS,
                fracao_desconhecidas=FRACAO_DESCONHECIDAS,
                max_consultas_por_identidade=MAX_CONSULTAS_POR_IDENTIDADE,
                fase=FaseProtocolo.TESTE,
            )
            protocolos_pareados = {
                1: reduzir_referencias(protocolo_tres, 1),
                REFERENCIAS_MULTIPLAS: protocolo_tres,
            }
        except ValueError:
            # As imagens no teste podem não sustentar um protocolo pareado.
            protocolos_pareados = {}
    tamanhos = sorted({1, 10, 25, 50, 100, len(protocolo.identidades_conhecidas)})
    tamanhos = [
        tamanho
        for tamanho in tamanhos
        if tamanho <= len(protocolo.identidades_conhecidas)
    ]
    resultado: dict[str, Any] = {
        "esquema": 2,
        "conjunto": "teste_independente_por_identidade",
        "seed": int(manifesto["seed"]),
        "assinatura_divisao": divisao.assinatura(),
        "dataset_sha256": dataset_hash,
        "protocolo": {
            "identidades_conhecidas": len(protocolo.identidades_conhecidas),
            "identidades_desconhecidas": len(protocolo.identidades_desconhecidas),
            "consultas_conhecidas": len(protocolo.consultas_conhecidas),
            "consultas_desconhecidas": len(protocolo.consultas_desconhecidas),
            "falhas_extracao_por_motivo": dict(sorted(falhas.items())),
            "pares_quase_duplicados_d_lt_0_01": contar_quase_duplicatas_por_identidade(
                protocolo
            ),
        },
        "modelos": {},
        "comparacao_referencias": {},
        "comparacao_referencias_status": (
            "disponivel_pareada" if protocolos_pareados else "dados_insuficientes"
        ),
    }
    por_limiar = {
        nome: avaliar_protocolo(protocolo, limiar)
        for nome, limiar in limiares_a_avaliar.items()
    }
    relatorio_curva = avaliar_protocolo(protocolo, 2.0)
    for nome, limiar in limiares_a_avaliar.items():
        relatorio = por_limiar[nome]
        ic_fpir = bootstrap_por_identidade(
            relatorio, "fpir", REPLICAS_BOOTSTRAP, int(manifesto["seed"])
        )
        ic_fnir = bootstrap_por_identidade(
            relatorio, "fnir", REPLICAS_BOOTSTRAP, int(manifesto["seed"])
        )
        resultado["modelos"][nome] = {
            "limiar": limiar,
            "metricas": asdict(relatorio.metricas),
            "erros": asdict(relatorio.erros),
            "ic95_fpir_agrupado_identidade": asdict(ic_fpir) if ic_fpir else None,
            "ic95_fnir_agrupado_identidade": asdict(ic_fnir) if ic_fnir else None,
            "tamanho_galeria": relatorio.tamanho_galeria,
            "referencias_validas": relatorio.referencias_validas,
            "tempo_comparacao_mediano_ms": relatorio.tempo_comparacao_ms_por_consulta,
            "tempo_decisao_mediano_ms": relatorio.tempo_decisao_ms_por_consulta,
        }
    limiares_pareados = {
        1: t2_um_pareado,
        REFERENCIAS_MULTIPLAS: t2_tres_referencias,
    }
    for quantidade_referencias, protocolo_referencias in protocolos_pareados.items():
        limiares_referencias = {"T0": LIMIAR_HISTORICO, "T1": LIMIAR_ETAPA_1}
        limiar_t2_pareado = limiares_pareados[quantidade_referencias]
        if isinstance(limiar_t2_pareado, (float, int)):
            limiares_referencias["T2"] = float(limiar_t2_pareado)
        nome_cenario = f"{quantidade_referencias}_referencias_pareadas"
        resultado["comparacao_referencias"][nome_cenario] = {}
        for nome_limiar, limiar_referencia in limiares_referencias.items():
            relatorio_referencia = avaliar_protocolo(
                protocolo_referencias, limiar_referencia
            )
            resultado["comparacao_referencias"][nome_cenario][nome_limiar] = {
                "limiar": limiar_referencia,
                "metricas": asdict(relatorio_referencia.metricas),
                "erros": asdict(relatorio_referencia.erros),
                "tamanho_galeria": relatorio_referencia.tamanho_galeria,
                "referencias_validas": relatorio_referencia.referencias_validas,
            }
    por_tamanho: dict[int, Any] = {}
    resultado["comparacao_tamanho_galeria"] = {}
    for tamanho in tamanhos:
        relatorio = avaliar_protocolo(
            protocolo,
            float(t2) if t2 is not None else LIMIAR_HISTORICO,
            tamanho_galeria=tamanho,
        )
        por_tamanho[tamanho] = relatorio
        resultado["comparacao_tamanho_galeria"][str(tamanho)] = {
            "metricas": asdict(relatorio.metricas),
            "erros": asdict(relatorio.erros),
            "tempo_comparacao_mediano_ms": relatorio.tempo_comparacao_ms_por_consulta,
            "tempo_decisao_mediano_ms": relatorio.tempo_decisao_ms_por_consulta,
        }
    resultado["observacao_proveniencia"] = (
        "A separação é independente dentro deste dataset, mas sobreposição "
        "com identidades de estudos anteriores não pode ser excluída sem "
        "proveniência nominal autorizada."
    )
    from scripts.graficos_identificacao_aberta import gerar as gerar_graficos

    relatorios_referencias_grafico: dict[int, Any] = {}
    for quantidade, protocolo_referencias in protocolos_pareados.items():
        # T0 fixo isola o efeito da quantidade de referências no gráfico.
        relatorios_referencias_grafico[quantidade] = avaliar_protocolo(
            protocolo_referencias, LIMIAR_HISTORICO
        )
    nome_limiar_erros = "T2" if "T2" in por_limiar else "T0"
    arquivos_graficos = gerar_graficos(
        saida / "graficos",
        relatorio_curva=relatorio_curva,
        relatorio_erros=por_limiar[nome_limiar_erros],
        nome_limiar_erros=nome_limiar_erros,
        limiar_erros=limiares_a_avaliar[nome_limiar_erros],
        por_limiar=por_limiar,
        por_tamanho=por_tamanho,
        por_referencias=relatorios_referencias_grafico,
    )
    resultado["graficos"] = [arquivo.name for arquivo in arquivos_graficos]
    (saida / "resultado.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        "Avaliação final agregada gravada. Nenhum resultado por identidade "
        "foi persistido."
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Etapa 3: avaliação experimental 1:N open-set"
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)
    preparar = subparsers.add_parser(
        "preparar", help="calibra T2 na validação e congela"
    )
    avaliar = subparsers.add_parser(
        "avaliar", help="consome uma vez o teste final congelado"
    )
    for subparser in (preparar, avaliar):
        subparser.add_argument("--dataset", type=Path, required=True)
        subparser.add_argument("--autorizacao-dataset", type=Path, required=True)
        subparser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    preparar.add_argument("--seed", type=int, default=42)
    avaliar.add_argument(
        "--congelamento", type=Path, default=SAIDA_PADRAO / "congelamento.json"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Gate precede saída, inventário, leitura de imagens, cache e imports DeepFace.
    try:
        autorizacao_hash = verificar_autorizacao(args.autorizacao_dataset)
    except AutorizacaoAusente:
        print(
            "ERRO: documento de autorização ausente ou vazio; dataset não acessado.",
            file=sys.stderr,
        )
        return 2
    try:
        if args.comando == "preparar":
            return _preparar(args, autorizacao_hash)
        return _avaliar(args, autorizacao_hash)
    except (
        ValueError,
        OSError,
        CacheIncompativel,
        DadosInsuficientes,
        ImportError,
        RuntimeError,
        ModeloIndisponivel,
    ) as erro:
        print(f"ERRO: etapa 3 não executada ({type(erro).__name__}).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
