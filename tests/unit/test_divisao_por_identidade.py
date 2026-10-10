"""Etapa 0 -- divisao do dataset por identidade.

O que se protege aqui e a validade da futura calibracao: se a mesma pessoa
cair em dois conjuntos, ou se o teste puder ser consultado na escolha do
limiar, o erro reportado sai otimista e nenhum teste de software acusaria.
Identidades sinteticas; nenhum dado biometrico.
"""

from __future__ import annotations

import itertools
import random

import pytest

from scripts.divisao_por_identidade import (
    MINIMO_DE_IDENTIDADES_POR_CONJUNTO,
    DadosInsuficientes,
    Divisao,
    ResumoDoConjunto,
    UsoIndevidoDoTeste,
    VazamentoDeIdentidade,
    dividir_por_identidade,
    verificar_suficiencia,
)

PESSOAS = [f"pessoa-{i:02d}" for i in range(20)]


def _todas(divisao: Divisao) -> list[tuple[str, ...]]:
    return [divisao.treino, divisao.validacao, divisao.abrir_teste(0.30)]


def test_mesma_seed_produz_a_mesma_divisao() -> None:
    a = dividir_por_identidade(PESSOAS, seed=7)
    b = dividir_por_identidade(PESSOAS, seed=7)
    assert _todas(a) == _todas(b)
    assert a.assinatura() == b.assinatura()


def test_ordem_de_entrada_nao_muda_a_divisao() -> None:
    """O disco pode listar as pastas em qualquer ordem."""
    embaralhadas = PESSOAS[:]
    random.Random(99).shuffle(embaralhadas)
    a = dividir_por_identidade(PESSOAS, seed=7)
    b = dividir_por_identidade(embaralhadas, seed=7)
    assert _todas(a) == _todas(b)


def test_seed_diferente_produz_divisao_diferente() -> None:
    assinaturas = {
        dividir_por_identidade(PESSOAS, seed=s).assinatura() for s in range(5)
    }
    assert len(assinaturas) > 1


def test_nenhuma_identidade_em_dois_conjuntos_e_nenhuma_perdida() -> None:
    for seed in range(30):
        conjuntos = _todas(dividir_por_identidade(PESSOAS, seed=seed))
        for a, b in itertools.combinations(conjuntos, 2):
            assert not set(a) & set(b)
        assert sorted(itertools.chain(*conjuntos)) == sorted(PESSOAS)


def test_proporcoes_padrao_60_20_20() -> None:
    divisao = dividir_por_identidade(PESSOAS, seed=1)
    assert [len(c) for c in _todas(divisao)] == [12, 4, 4]


def test_construir_divisao_com_sobreposicao_e_recusado() -> None:
    with pytest.raises(VazamentoDeIdentidade, match="treino e teste"):
        Divisao(seed=0, treino=("a", "b"), validacao=("c", "d"), teste=("a", "e"))


def test_dataset_pequeno_demais_e_recusado() -> None:
    poucas = PESSOAS[: 3 * MINIMO_DE_IDENTIDADES_POR_CONJUNTO - 1]
    with pytest.raises(DadosInsuficientes, match="ao menos 6"):
        dividir_por_identidade(poucas, seed=1)


def test_dataset_minimo_divide_com_dois_por_conjunto() -> None:
    divisao = dividir_por_identidade(PESSOAS[:6], seed=1)
    assert [len(c) for c in _todas(divisao)] == [2, 2, 2]


def test_proporcoes_que_esvaziam_o_treino_sao_recusadas() -> None:
    with pytest.raises(DadosInsuficientes, match="treino"):
        dividir_por_identidade(PESSOAS[:8], seed=1, proporcoes=(0.1, 0.45, 0.45))


@pytest.mark.parametrize(
    "proporcoes", [(0.5, 0.2, 0.2), (0.8, 0.2, 0.0), (1.2, -0.1, -0.1)]
)
def test_proporcoes_invalidas_sao_recusadas(
    proporcoes: tuple[float, float, float],
) -> None:
    with pytest.raises(ValueError, match="proporcoes"):
        dividir_por_identidade(PESSOAS, seed=1, proporcoes=proporcoes)


def test_identidade_repetida_na_entrada_e_recusada() -> None:
    with pytest.raises(ValueError, match="repetidas"):
        dividir_por_identidade([*PESSOAS, PESSOAS[0]], seed=1)


def test_teste_lacrado_so_abre_uma_vez_e_registra_o_limiar() -> None:
    divisao = dividir_por_identidade(PESSOAS, seed=1)
    assert not divisao.teste_utilizado

    teste = divisao.abrir_teste(limiar_congelado=0.27)
    assert len(teste) == 4
    assert divisao.teste_utilizado
    assert divisao.limiar_congelado == 0.27

    with pytest.raises(UsoIndevidoDoTeste, match=r"0\.27"):
        divisao.abrir_teste(limiar_congelado=0.25)


def test_resumir_nao_abre_o_teste() -> None:
    """Contar imagens e pares do teste nao e usa-lo para decidir."""
    divisao = dividir_por_identidade(PESSOAS, seed=1)
    divisao.resumir(dict.fromkeys(PESSOAS, 3))
    assert not divisao.teste_utilizado


def test_resumir_conta_pares_como_a_forca_bruta() -> None:
    contagem = {p: (i % 4) + 1 for i, p in enumerate(PESSOAS)}
    divisao = dividir_por_identidade(PESSOAS, seed=3)
    resumos = {r.nome: r for r in divisao.resumir(contagem)}

    for nome, conjunto in zip(
        ("treino", "validacao", "teste"), _todas(divisao), strict=True
    ):
        imagens = [(p, n) for p in conjunto for n in range(contagem[p])]
        genuinos = impostores = 0
        for (pa, _), (pb, _) in itertools.combinations(imagens, 2):
            if pa == pb:
                genuinos += 1
            else:
                impostores += 1
        assert resumos[nome].pares_genuinos == genuinos
        assert resumos[nome].pares_impostores == impostores
        assert resumos[nome].imagens == len(imagens)


def test_resumir_ignora_identidade_sem_imagem() -> None:
    """Quem teve todas as imagens recusadas nao conta como identidade."""
    divisao = Divisao(
        seed=0, treino=("a", "b", "c"), validacao=("d", "e"), teste=("f", "g")
    )
    treino = divisao.resumir({"a": 2, "b": 1})[0]
    assert treino.identidades == 2
    assert treino.imagens == 3
    assert treino.pares_genuinos == 1
    assert treino.pares_impostores == 2


def test_suficiencia_aponta_conjunto_sem_pares() -> None:
    resumos = [
        ResumoDoConjunto("treino", 3, 6, 3, 12),
        ResumoDoConjunto("validacao", 2, 2, 0, 1),
        ResumoDoConjunto("teste", 1, 2, 1, 0),
    ]
    with pytest.raises(DadosInsuficientes) as erro:
        verificar_suficiencia(resumos)
    assert "validacao: nenhum par genuino" in str(erro.value)
    assert "teste: nenhum par impostor" in str(erro.value)
    assert "treino" not in str(erro.value)


def test_suficiencia_aceita_conjuntos_completos() -> None:
    verificar_suficiencia([ResumoDoConjunto("treino", 2, 4, 2, 4)])
