"""Preparação isolada do experimento de verificação facial binária.

Os dados biométricos são carregados somente depois do gate de autorização.
Preparar os modelos lê treino e validação; o teste exige um congelamento válido.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

import joblib  # type: ignore[import-untyped]
import numpy as np
import sklearn  # type: ignore[import-untyped]

from scripts.classificadores_binarios import (
    ModeloSelecionado,
    caracteristicas_da_distancia,
    treinar_e_selecionar_modelos,
)

HASH_PARES_ETAPA1 = "BF40A75899A76334F2A2D11354C9D8DB6F8F5BAD74D7E9675B98D7DFDEA46058"
SEED_ETAPA1 = 42
ASSINATURA_DIVISAO_ETAPA1 = "4c7ddc45f322ec3c"
LIMIAR_M1_ETAPA1 = 0.42817932706540435
TETO_FAR_ETAPA1 = 0.001
CONTAGENS_ESPERADAS: dict[str, dict[str, int]] = {
    "treino": {
        "identidades": 999,
        "imagens": 3502,
        "pares_genuinos": 7319,
        "impostores_usados": 1000000,
    },
    "validacao": {
        "identidades": 333,
        "imagens": 1062,
        "pares_genuinos": 2052,
        "impostores_usados": 561339,
    },
    "teste": {
        "identidades": 336,
        "imagens": 1099,
        "pares_genuinos": 2001,
        "impostores_usados": 601350,
    },
}

_CHAVES_PARES = (
    "imagem_a",
    "imagem_b",
    "identidade_a",
    "identidade_b",
    "distancia",
    "rotulo",
)
_VERSAO_ESQUEMA = 1
_NOME_ARQUIVO_MODELOS = "modelos.joblib"
_NOME_MANIFESTO = "congelamento.json"
_NOME_HASH_MANIFESTO = "congelamento.sha256"
ETAPA2_ROOT = (
    Path(__file__).resolve().parents[1]
    / "avaliacao"
    / "resultados"
    / "etapa2"
)
_NOME_MARCADOR_TESTE = ".teste-consumido.json"


@dataclass(frozen=True, slots=True)
class ParesEtapa1:
    """Pares rotulados e sem nomes pessoais exportados pela Etapa 1."""

    conjunto: str
    imagem_a: np.ndarray
    imagem_b: np.ndarray
    identidade_a: np.ndarray
    identidade_b: np.ndarray
    distancia: np.ndarray
    rotulo: np.ndarray


def _sha256_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest().upper()


def _reservar_avaliacao_teste(
    entrada: Path, congelamento: Path, *, seed: int, replicas: int
) -> Path:
    """Consome uma única avaliação final do teste por checkout.

    O arquivo é criado exclusivamente antes da leitura do split teste. Assim,
    execuções concorrentes ou novas saídas não conseguem reabrir o mesmo
    holdout para outra configuração ou semente.
    """
    marcador = ETAPA2_ROOT / _NOME_MARCADOR_TESTE
    marcador.parent.mkdir(parents=True, exist_ok=True)
    registro = {
        "hash_pares_etapa1": _sha256_arquivo(Path(entrada) / "pares.npz"),
        "hash_congelamento": _sha256_arquivo(Path(congelamento)),
        "seed_bootstrap": seed,
        "replicas_bootstrap": replicas,
    }
    try:
        with marcador.open("x", encoding="utf-8") as arquivo:
            json.dump(registro, arquivo, ensure_ascii=False, sort_keys=True)
            arquivo.write("\n")
    except FileExistsError as erro:
        raise FileExistsError(
            "O conjunto de teste desta etapa já teve uma avaliação iniciada."
        ) from erro
    return marcador


def _json_canonico(valor: Any) -> bytes:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash_json(valor: Any) -> str:
    return hashlib.sha256(_json_canonico(valor)).hexdigest().upper()


def _conjunto_por_nome(resultado: dict[str, Any], nome: str) -> dict[str, Any]:
    conjuntos = resultado.get("conjuntos")
    if not isinstance(conjuntos, list):
        raise ValueError("Metadados da Etapa 1 sem lista de subconjuntos.")
    encontrados = [item for item in conjuntos if item.get("nome") == nome]
    if len(encontrados) != 1:
        raise ValueError(f"Metadados da Etapa 1 incompatíveis no subconjunto {nome}.")
    return encontrados[0]


def _validar_contagens(resultado: dict[str, Any]) -> dict[str, dict[str, int]]:
    observadas: dict[str, dict[str, int]] = {}
    for nome, esperadas in CONTAGENS_ESPERADAS.items():
        conjunto = _conjunto_por_nome(resultado, nome)
        chaves = (
            "identidades",
            "imagens",
            "pares_genuinos",
            "impostores_usados",
        )
        observadas[nome] = {}
        for chave in chaves:
            valor = conjunto.get(chave)
            if not isinstance(valor, int) or valor != esperadas[chave]:
                raise ValueError(
                    f"Contagem incompatível da Etapa 1: {nome}/{chave}."
                )
            observadas[nome][chave] = valor
    return observadas


def validar_metadados_etapa1(entrada: Path) -> dict[str, Any]:
    """Confere proveniência S1 sem consultar campos de métricas do teste."""
    entrada = Path(entrada)
    caminho_resultado = entrada / "resultado.json"
    caminho_pares = entrada / "pares.npz"
    if not caminho_resultado.is_file() or not caminho_pares.is_file():
        raise FileNotFoundError("Artefatos de entrada da Etapa 1 estão incompletos.")
    try:
        resultado = json.loads(caminho_resultado.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise ValueError("Não foi possível ler os metadados da Etapa 1.") from erro

    digest_pares = _sha256_arquivo(caminho_pares)
    if digest_pares != HASH_PARES_ETAPA1:
        raise ValueError("Hash do arquivo de pares da Etapa 1 incompatível.")
    metadados = resultado.get("metadados")
    if not isinstance(metadados, dict):
        raise ValueError("Metadados da Etapa 1 ausentes.")
    if metadados.get("dataset") != "lfw":
        raise ValueError("Dataset da Etapa 1 incompatível.")
    if metadados.get("seed") != SEED_ETAPA1:
        raise ValueError("Seed da divisão da Etapa 1 incompatível.")
    if metadados.get("assinatura_da_divisao") != ASSINATURA_DIVISAO_ETAPA1:
        raise ValueError("Assinatura da divisão da Etapa 1 incompatível.")
    if not math.isclose(
        float(metadados.get("teto_principal", -1)), TETO_FAR_ETAPA1, abs_tol=1e-12
    ):
        raise ValueError("Teto de FAR da Etapa 1 incompatível.")
    if not math.isclose(
        float(metadados.get("baseline_face_threshold", -1)), 0.30, abs_tol=1e-12
    ):
        raise ValueError("Baseline operacional histórico da Etapa 1 incompatível.")

    extracao_config = metadados.get("extracao")
    esperado_extracao = {
        "modelo": "Facenet512",
        "detector": "opencv",
        "alinhamento": True,
        "prova_de_vida": False,
        "normalizacao": "L2",
        "versao": "1",
    }
    if not isinstance(extracao_config, dict) or any(
        extracao_config.get(chave) != valor
        for chave, valor in esperado_extracao.items()
    ):
        raise ValueError("Configuração de extração da Etapa 1 incompatível.")

    contagens = _validar_contagens(resultado)
    selecao = resultado.get("selecao")
    if not isinstance(selecao, dict):
        raise ValueError("Resumo de seleção da Etapa 1 ausente.")
    if (
        selecao.get("duplicatas_na_identidade") != 0
        or selecao.get("duplicatas_entre_identidades") != 2
    ):
        raise ValueError("Auditoria de duplicatas exatas da Etapa 1 incompatível.")
    quase_duplicadas = resultado.get("genuinos_quase_duplicados")
    if not isinstance(quase_duplicadas, dict) or any(
        quase_duplicadas.get(nome) != 0 for nome in CONTAGENS_ESPERADAS
    ):
        raise ValueError("Foram detectadas quase duplicatas entre pares genuínos.")

    extracao = resultado.get("extracao")
    falhas_esperadas = {"sem rosto detectado": 162, "multiplos rostos": 595}
    if (
        not isinstance(extracao, dict)
        or extracao.get("recebidas") != 6420
        or extracao.get("processadas") != 5663
        or extracao.get("rejeitadas_por_motivo") != falhas_esperadas
        or sum(falhas_esperadas.values()) + 5663 != 6420
    ):
        raise ValueError("Contagens de falha de extração da Etapa 1 incompatíveis.")

    calibracoes = resultado.get("calibracao_validacao")
    if not isinstance(calibracoes, list):
        raise ValueError("Calibração de validação da Etapa 1 ausente.")
    candidatas = [
        item
        for item in calibracoes
        if math.isclose(float(item.get("teto", -1)), TETO_FAR_ETAPA1)
    ]
    if len(candidatas) != 1:
        raise ValueError("Baseline calibrado da Etapa 1 indisponível ou ambíguo.")
    limiar_m1 = float(candidatas[0].get("validacao", {}).get("limiar", float("nan")))
    if not math.isclose(limiar_m1, LIMIAR_M1_ETAPA1, abs_tol=1e-9):
        raise ValueError("Limiar calibrado M1 da Etapa 1 incompatível.")

    # Somente estes campos agregados compõem a proveniência; os campos
    # históricos `teste` e `auc_teste` não são consumidos nem copiados.
    proveniencia = {
        "dataset": "lfw",
        "seed_divisao": SEED_ETAPA1,
        "assinatura_da_divisao": ASSINATURA_DIVISAO_ETAPA1,
        "teto_far": TETO_FAR_ETAPA1,
        "extracao": extracao_config,
        "versoes": metadados.get("versoes", {}),
        "selecao": {
            "identidades": selecao.get("identidades"),
            "imagens": selecao.get("imagens"),
            "duplicatas_na_identidade": selecao.get("duplicatas_na_identidade"),
            "duplicatas_entre_identidades": selecao.get("duplicatas_entre_identidades"),
        },
        "falhas_extracao": extracao,
        "conjuntos": contagens,
        "limiar_m1_validacao": limiar_m1,
        "hash_pares_npz": digest_pares,
    }
    return {
        "sha256_pares_npz": digest_pares,
        "hash_proveniencia_s1": _hash_json(proveniencia),
        "proveniencia_s1": proveniencia,
        "limiar_m1": limiar_m1,
    }


def validar_pares(pares: ParesEtapa1) -> None:
    """Verifica dimensões, valores e coerência dos rótulos de pares."""
    vetores = {chave: np.asarray(getattr(pares, chave)) for chave in _CHAVES_PARES}
    tamanhos = {vetor.size for vetor in vetores.values()}
    if any(vetor.ndim != 1 for vetor in vetores.values()) or len(tamanhos) != 1:
        raise ValueError(
            "Arrays dos pares devem ser vetores unidimensionais alinhados."
        )
    quantidade = next(iter(tamanhos), 0)
    if quantidade == 0:
        raise ValueError("O subconjunto não contém pares.")
    if not np.issubdtype(vetores["distancia"].dtype, np.number):
        raise ValueError("As distâncias devem ser numéricas.")
    if not np.isfinite(vetores["distancia"]).all():
        raise ValueError("As distâncias devem ser finitas.")
    rotulos = vetores["rotulo"]
    if not np.isin(rotulos, [0, 1]).all():
        raise ValueError("Os rótulos devem ser binários 0/1.")
    if np.any(vetores["imagem_a"] == vetores["imagem_b"]):
        raise ValueError("Um par não pode comparar a mesma imagem consigo própria.")
    esperados = (vetores["identidade_a"] == vetores["identidade_b"]).astype(
        rotulos.dtype
    )
    if not np.array_equal(rotulos, esperados):
        raise ValueError("Os rótulos não correspondem às identidades dos pares.")


def validar_separacao(
    treino: ParesEtapa1, validacao: ParesEtapa1, teste: ParesEtapa1
) -> None:
    """Recusa identidades ou imagens repetidas entre subconjuntos."""
    _validar_particoes(
        {"treino": treino, "validacao": validacao, "teste": teste}
    )


def _validar_particoes(particoes: dict[str, ParesEtapa1]) -> None:
    itens = list(particoes.items())
    for nome, pares in itens:
        if pares.conjunto != nome:
            raise ValueError(f"Subconjunto esperado {nome} recebido incorretamente.")
        validar_pares(pares)
    for indice, (_, esquerda) in enumerate(itens):
        ids_esquerda = np.unique(
            np.concatenate([esquerda.identidade_a, esquerda.identidade_b])
        )
        imgs_esquerda = np.unique(
            np.concatenate([esquerda.imagem_a, esquerda.imagem_b])
        )
        for _, direita in itens[indice + 1 :]:
            ids_direita = np.unique(
                np.concatenate([direita.identidade_a, direita.identidade_b])
            )
            imgs_direita = np.unique(
                np.concatenate([direita.imagem_a, direita.imagem_b])
            )
            if np.intersect1d(ids_esquerda, ids_direita).size:
                raise ValueError("Há sobreposição de identidade entre subconjuntos.")
            if np.intersect1d(imgs_esquerda, imgs_direita).size:
                raise ValueError("Há sobreposição de imagem entre subconjuntos.")


def _validar_contagem_real(
    pares: ParesEtapa1, esperadas: dict[str, int]
) -> None:
    identidades = np.unique(np.concatenate([pares.identidade_a, pares.identidade_b]))
    imagens = np.unique(np.concatenate([pares.imagem_a, pares.imagem_b]))
    genuinos = int(np.count_nonzero(pares.rotulo == 1))
    impostores = int(np.count_nonzero(pares.rotulo == 0))
    if (
        identidades.size != esperadas["identidades"]
        or imagens.size != esperadas["imagens"]
        or genuinos != esperadas["pares_genuinos"]
        or impostores != esperadas["impostores_usados"]
    ):
        raise ValueError(
            f"Contagens dos pares divergem dos metadados em {pares.conjunto}."
        )
    canonicos = np.column_stack(
        [
            np.minimum(pares.imagem_a, pares.imagem_b),
            np.maximum(pares.imagem_a, pares.imagem_b),
        ]
    )
    if np.unique(canonicos, axis=0).shape[0] != canonicos.shape[0]:
        raise ValueError(f"Pares de imagem duplicados em {pares.conjunto}.")


def _validar_manifesto(
    congelamento: Path, arquivo_pares: Path
) -> tuple[dict[str, Any], Path]:
    manifesto_path = Path(congelamento)
    assinatura_path = manifesto_path.with_name(_NOME_HASH_MANIFESTO)
    if not manifesto_path.is_file() or not assinatura_path.is_file():
        raise ValueError("Manifesto ou hash do congelamento ausente.")
    digest_manifesto = _sha256_arquivo(manifesto_path)
    esperado_manifesto = assinatura_path.read_text(encoding="ascii").strip().upper()
    if digest_manifesto != esperado_manifesto:
        raise ValueError("Hash do manifesto de congelamento inválido.")
    try:
        manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise ValueError("Manifesto do congelamento inválido.") from erro
    obrigatorias = {
        "schema_version",
        "seed_modelo",
        "seed_divisao_s1",
        "assinatura_da_divisao_s1",
        "hash_pares_npz",
        "hash_proveniencia_s1",
        "proveniencia_s1",
        "arquivo_modelos",
        "sha256_modelos",
        "modelos",
        "baselines",
    }
    if not isinstance(manifesto, dict) or not obrigatorias.issubset(manifesto):
        raise ValueError("Manifesto do congelamento incompleto.")
    if manifesto["schema_version"] != _VERSAO_ESQUEMA:
        raise ValueError("Versão do manifesto de congelamento incompatível.")
    if manifesto["hash_proveniencia_s1"] != _hash_json(manifesto["proveniencia_s1"]):
        raise ValueError("Hash da proveniência da Etapa 1 inválido.")
    if manifesto["hash_pares_npz"] != _sha256_arquivo(Path(arquivo_pares)):
        raise ValueError("Hash dos dados de origem diverge do congelamento.")
    nome_modelos = manifesto["arquivo_modelos"]
    if not isinstance(nome_modelos, str) or Path(nome_modelos).name != nome_modelos:
        raise ValueError("Caminho do arquivo de modelos inválido.")
    caminho_modelos = manifesto_path.parent / nome_modelos
    if not caminho_modelos.is_file() or _sha256_arquivo(caminho_modelos) != manifesto[
        "sha256_modelos"
    ]:
        raise ValueError("Hash do artefato de modelos inválido.")
    assinatura = manifesto.get("assinatura_da_divisao_s1")
    if assinatura != manifesto["proveniencia_s1"].get("assinatura_da_divisao"):
        raise ValueError("Assinatura de divisão incompatível no congelamento.")
    seed = manifesto.get("seed_divisao_s1")
    if seed != manifesto["proveniencia_s1"].get("seed_divisao"):
        raise ValueError("Seed de divisão incompatível no congelamento.")
    baselines = manifesto["baselines"]
    if not isinstance(baselines, dict) or baselines.get("M0", {}).get(
        "limiar_distancia"
    ) != 0.30 or baselines.get("M1", {}).get("limiar_distancia") != LIMIAR_M1_ETAPA1:
        raise ValueError("Baselines congelados incompatíveis.")
    return manifesto, caminho_modelos


def carregar_pares_etapa1(
    arquivo: Path,
    conjunto: Literal["treino", "validacao", "teste"],
    *,
    congelamento_validado: Path | None = None,
) -> ParesEtapa1:
    """Carrega somente as seis matrizes do split solicitado."""
    arquivo = Path(arquivo)
    if conjunto == "teste":
        if congelamento_validado is None:
            raise PermissionError("O split de teste exige congelamento válido.")
        _validar_manifesto(Path(congelamento_validado), arquivo)
    prefixo = f"{conjunto}_"
    with np.load(arquivo, allow_pickle=False) as dados:
        pares = ParesEtapa1(
            conjunto=conjunto,
            **{chave: np.asarray(dados[prefixo + chave]) for chave in _CHAVES_PARES},
        )
    validar_pares(pares)
    return pares


def _verificar_autorizacao(caminho: Path) -> str:
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(
            "Documento local de autorização do dataset não encontrado."
        )
    if caminho.stat().st_size == 0:
        raise ValueError("Documento de autorização do dataset está vazio.")
    return _sha256_arquivo(caminho)


def _versao_pacote(nome: str) -> str | None:
    try:
        return version(nome)
    except PackageNotFoundError:
        return None


def _metadados_do_modelo(modelo: ModeloSelecionado) -> dict[str, Any]:
    dados: dict[str, Any] = {
        "parametros": modelo.parametros,
        "limiar_score": modelo.limiar_score,
        "far_treino": modelo.far_treino,
        "frr_treino": modelo.frr_treino,
        "far_validacao": modelo.far_validacao,
        "frr_validacao": modelo.frr_validacao,
        "tempo_treino_s": modelo.tempo_treino_s,
    }
    if modelo.nome == "M2":
        dados["coeficiente"] = float(modelo.estimador.coef_[0, 0])
        dados["intercepto"] = float(modelo.estimador.intercept_[0])
    if modelo.nome == "M4":
        dados["profundidade"] = int(modelo.estimador.get_depth())
        dados["folhas"] = int(modelo.estimador.get_n_leaves())
        dados["limiares_arvore"] = [
            float(valor)
            for valor in modelo.estimador.tree_.threshold
            if valor != -2.0
        ]
    return dados


def preparar_experimento(
    entrada: Path,
    saida: Path,
    autorizacao_dataset: Path,
    *,
    seed: int = 42,
) -> Path:
    """Treina apenas após autorização, sem abrir matrizes do subconjunto teste."""
    hash_autorizacao = _verificar_autorizacao(autorizacao_dataset)
    destino = Path(saida)
    manifesto_path = destino / _NOME_MANIFESTO
    assinatura_path = destino / _NOME_HASH_MANIFESTO
    caminho_modelos = destino / _NOME_ARQUIVO_MODELOS
    if any(
        path.exists()
        for path in (manifesto_path, assinatura_path, caminho_modelos)
    ):
        raise FileExistsError("Já existe um artefato de congelamento neste destino.")
    metadados_s1 = validar_metadados_etapa1(Path(entrada))
    pares_path = Path(entrada) / "pares.npz"
    if _sha256_arquivo(pares_path) != metadados_s1["sha256_pares_npz"]:
        raise ValueError("O arquivo de pares mudou após a validação dos metadados.")

    treino = carregar_pares_etapa1(pares_path, "treino")
    validacao = carregar_pares_etapa1(pares_path, "validacao")
    _validar_particoes({"treino": treino, "validacao": validacao})
    contagens = metadados_s1["proveniencia_s1"]["conjuntos"]
    _validar_contagem_real(treino, contagens["treino"])
    _validar_contagem_real(validacao, contagens["validacao"])
    modelos = treinar_e_selecionar_modelos(
        caracteristicas_da_distancia(treino.distancia),
        treino.rotulo,
        caracteristicas_da_distancia(validacao.distancia),
        validacao.rotulo,
        far_maximo=TETO_FAR_ETAPA1,
        seed=seed,
    )

    destino.mkdir(parents=True, exist_ok=True)
    caminho_temporario = destino / f"{_NOME_ARQUIVO_MODELOS}.tmp"
    joblib.dump(modelos, caminho_temporario)
    os.replace(caminho_temporario, caminho_modelos)

    proveniencia = metadados_s1["proveniencia_s1"]
    indisponiveis = {
        nome: "nenhuma configuração produziu limiar elegível na validação"
        for nome in ("M2", "M3", "M4")
        if nome not in modelos
    }
    manifesto: dict[str, Any] = {
        "schema_version": _VERSAO_ESQUEMA,
        "seed_modelo": int(seed),
        "seed_divisao_s1": int(proveniencia["seed_divisao"]),
        "assinatura_da_divisao_s1": proveniencia["assinatura_da_divisao"],
        "hash_pares_npz": metadados_s1["sha256_pares_npz"],
        "hash_proveniencia_s1": metadados_s1["hash_proveniencia_s1"],
        "proveniencia_s1": proveniencia,
        "autorizacao_dataset": {
            "caminho_logico": "documento-local-de-autorizacao",
            "sha256": hash_autorizacao,
        },
        "arquivo_modelos": _NOME_ARQUIVO_MODELOS,
        "sha256_modelos": _sha256_arquivo(caminho_modelos),
        "versoes": {
            "python": platform.python_version(),
            "plataforma": platform.platform(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": _versao_pacote("joblib"),
            "matplotlib": _versao_pacote("matplotlib"),
        },
        "baselines": {
            "M0": {"regra": "distancia <= 0.30", "limiar_distancia": 0.30},
            "M1": {
                "regra": "limiar calibrado pela Etapa 1 em validação",
                "limiar_distancia": float(metadados_s1["limiar_m1"]),
            },
        },
        "modelos": {
            nome: _metadados_do_modelo(modelo) for nome, modelo in modelos.items()
        },
        "indisponiveis": indisponiveis,
    }
    manifesto_temporario = destino / f"{_NOME_MANIFESTO}.tmp"
    manifesto_temporario.write_bytes(_json_canonico(manifesto) + b"\n")
    os.replace(manifesto_temporario, manifesto_path)
    assinatura_path.write_text(_sha256_arquivo(manifesto_path) + "\n", encoding="ascii")
    return manifesto_path


def carregar_congelamento(
    congelamento: Path, arquivo_pares: Path
) -> dict[str, ModeloSelecionado]:
    """Valida checksums e coerência antes de desserializar estimadores locais."""
    manifesto, caminho_modelos = _validar_manifesto(congelamento, arquivo_pares)
    carregados = joblib.load(caminho_modelos)
    if not isinstance(carregados, dict) or set(carregados) != set(manifesto["modelos"]):
        raise ValueError("Modelos serializados não correspondem ao manifesto.")
    for nome, modelo in carregados.items():
        if not isinstance(modelo, ModeloSelecionado) or modelo.nome != nome:
            raise ValueError("Estimador serializado incompatível com o manifesto.")
        metadados = manifesto["modelos"][nome]
        if modelo.parametros != metadados["parametros"] or not math.isclose(
            modelo.limiar_score, float(metadados["limiar_score"]), abs_tol=1e-12
        ):
            raise ValueError("Parâmetros congelados divergem do manifesto.")
    return carregados


def avaliar_experimento(
    entrada: Path,
    congelamento: Path,
    saida: Path,
    *,
    seed: int = 42,
    replicas: int = 1000,
) -> Path:
    """Libera teste depois de validar o congelamento e as partições."""
    from scripts.avaliacao_classificadores import avaliar_no_teste, salvar_resultado
    from scripts.graficos_classificacao import gerar_graficos

    metadados_s1 = validar_metadados_etapa1(Path(entrada))
    pares_path = Path(entrada) / "pares.npz"
    modelos = carregar_congelamento(Path(congelamento), pares_path)
    if (
        metadados_s1["hash_proveniencia_s1"]
        != json.loads(Path(congelamento).read_text(encoding="utf-8"))[
            "hash_proveniencia_s1"
        ]
    ):
        raise ValueError("Metadados da Etapa 1 mudaram desde o congelamento.")
    destino = Path(saida)
    if (destino / "resultado.json").exists() or (destino / "graficos").exists():
        raise FileExistsError("A avaliação final já existe neste destino.")
    treino = carregar_pares_etapa1(pares_path, "treino")
    validacao = carregar_pares_etapa1(pares_path, "validacao")
    _reservar_avaliacao_teste(
        Path(entrada), Path(congelamento), seed=seed, replicas=replicas
    )
    teste = carregar_pares_etapa1(
        pares_path, "teste", congelamento_validado=Path(congelamento)
    )
    validar_separacao(treino, validacao, teste)
    resultado = avaliar_no_teste(teste, modelos, seed=seed, replicas=replicas)
    destino.mkdir(parents=True, exist_ok=True)
    caminho_resultado = salvar_resultado(resultado, destino / "resultado.json")
    gerar_graficos(
        resultado,
        destino / "graficos",
        origem_real_verificada=True,
    )
    return caminho_resultado


def _inteiro_nao_negativo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError as erro:
        raise argparse.ArgumentTypeError("informe um inteiro") from erro
    if valor < 0:
        raise argparse.ArgumentTypeError("o valor não pode ser negativo")
    return valor


def _inteiro_positivo(texto: str) -> int:
    valor = _inteiro_nao_negativo(texto)
    if valor == 0:
        raise argparse.ArgumentTypeError("o valor precisa ser positivo")
    return valor


def _validar_saida_local(caminho: Path) -> Path:
    permitido = ETAPA2_ROOT.resolve()
    destino = Path(caminho).resolve()
    if not destino.is_relative_to(permitido):
        raise ValueError(
            "As saídas experimentais devem ficar em avaliacao/resultados/etapa2."
        )
    return destino


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Experimento isolado de classificadores para verificação facial 1:1."
        )
    )
    comandos = parser.add_subparsers(dest="comando", required=True)
    preparar = comandos.add_parser("preparar", help="treina e congela sem ler o teste")
    preparar.add_argument("--entrada", type=Path, required=True)
    preparar.add_argument("--saida", type=Path, required=True)
    preparar.add_argument("--autorizacao-dataset", type=Path, required=True)
    preparar.add_argument("--seed", type=_inteiro_nao_negativo, default=42)
    avaliar = comandos.add_parser(
        "avaliar", help="avalia uma única vez o teste congelado"
    )
    avaliar.add_argument("--entrada", type=Path, required=True)
    avaliar.add_argument("--congelamento", type=Path, required=True)
    avaliar.add_argument("--saida", type=Path, required=True)
    avaliar.add_argument("--seed", type=_inteiro_nao_negativo, default=42)
    avaliar.add_argument("--replicas", type=_inteiro_positivo, default=1000)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI de duas fases; erros nunca imprimem imagens, vetores ou IDs."""
    parser = _criar_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as erro:
        return int(erro.code) if isinstance(erro.code, int) else 2
    try:
        saida = _validar_saida_local(args.saida)
        if args.comando == "preparar":
            congelamento = preparar_experimento(
                args.entrada,
                saida,
                args.autorizacao_dataset,
                seed=args.seed,
            )
            print(f"Congelamento experimental criado: {congelamento}")
            return 0
        raiz = Path(__file__).resolve().parents[1]
        permitido = (raiz / "avaliacao" / "resultados" / "etapa2").resolve()
        congelamento = Path(args.congelamento).resolve()
        if not congelamento.is_relative_to(permitido):
            raise ValueError(
                "O congelamento deve ficar em avaliacao/resultados/etapa2."
            )
        avaliar_experimento(
            args.entrada,
            congelamento,
            saida,
            seed=args.seed,
            replicas=args.replicas,
        )
        print("Avaliação congelada concluída; relatório agregado salvo localmente.")
        return 0
    except (
        FileNotFoundError,
        FileExistsError,
        PermissionError,
        ValueError,
        OSError,
    ) as erro:
        print(f"Etapa 2 interrompida: {type(erro).__name__}: {erro}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
