# Etapa 2 — Plano de Implementação

> **Para agentes de implementação:** SUB-SKILL OBRIGATÓRIA: usar `superpowers:subagent-driven-development` (recomendado) ou `superpowers:executing-plans` para executar este plano tarefa por tarefa. Os passos usam caixas de seleção (`- [ ]`).

**Objetivo:** implementar um fluxo reproduzível e isolado para comparar M0–M4 em verificação facial 1:1, permitindo somente testes sintéticos enquanto a autorização de uso do LFW não estiver documentada.

**Arquitetura:** reutilizar o artefato de pares, métricas e bootstrap por identidade da Etapa 1; adicionar módulos em `scripts/` para ajuste, orquestração, avaliação e gráficos. A preparação congela os classificadores e limiares sem abrir os arrays do teste; uma segunda execução verifica o congelamento antes de avaliar o teste. Saídas sensíveis ficam em `avaliacao/resultados/etapa2/`.

**Stack:** Python, NumPy, scikit-learn, joblib, matplotlib, pytest; scikit-learn `1.9.1`, matplotlib `3.11.2`; dependências em `.venv-ml`.

**Especificação:** `docs/superpowers/specs/2026-10-10-etapa-2-classificadores-supervisionados-design.md`.

## Restrições globais

- M0 permanece `distância <= 0.30`; M1 usa o limiar validado da Etapa 1, `0.4282`.
- Seed padrão `42`; split da Etapa 1 `4c7ddc45f322ec3c`; teto de FAR de seleção `0.001`.
- M2 testa `C ∈ {0.1, 1, 10}` e `class_weight ∈ {None, "balanced"}`; M4 testa `max_depth ∈ {1, 2, 3}`; M3 usa `GaussianNB` padrão.
- Nenhum ajuste ou seleção usa o teste. A avaliação final só começa após carregar e validar o congelamento.
- Treino com LFW exige documento de autorização de uso; sem ele, executar somente testes sintéticos e registrar avaliação experimental pendente.
- Não usar imagens ou embeddings de alunos; não conectar ao PostgreSQL nem registrar biometria em logs.
- Não modificar webcam, anti-spoofing, FaceNet512, matcher, `FACE_THRESHOLD`, banco, migrations ou interface.
- Manter pares, modelos e gráficos em `avaliacao/resultados/etapa2/`, fora do Git; não fazer commits.
- SVM fica fora do escopo. Nenhum modelo experimental será integrado à aplicação ou à Etapa 3.

## Foco da revisão

1. Arrays do teste acessados antes do congelamento — coberto por `test_preparar_nao_carrega_arrays_de_teste` (Tarefa 2).
2. IDs de imagem/identidade sobrepostos entre partições ou rótulos que não correspondem aos IDs — coberto por `test_validar_particoes_detecta_vazamento` e `test_validar_pares_confere_rotulos_com_identidades` (Tarefa 2).
3. Classe ausente, valores não finitos ou FAR de validação sem um limiar elegível — coberto por `test_classes_ausentes_e_sem_limiar_sao_recusadas` e `test_caracteristicas_rejeitam_valores_nao_finitos_ou_shape` (Tarefa 1).
4. Congelamento parcial, adulterado ou incompatível com os dados de entrada — coberto por `test_carregar_congelamento_verifica_hash_e_metadados` (Tarefa 2).
5. Pares correlacionados tratados como observações independentes ou métricas sem denominador — coberto por `test_bootstrap_por_identidade_e_reprodutivel` e `test_metricas_sem_denominador_sao_nulas` (Tarefa 3).

---

## Arquivos e responsabilidades

- Criar `requirements-ml.txt`: dependências de desenvolvimento mais scikit-learn e matplotlib, sem alterar os requisitos operacionais.
- Criar `scripts/classificadores_binarios.py`: vetor de características, candidatos M2–M4, treino e seleção na validação.
- Criar `scripts/experimento_classificacao_binaria.py`: leitor do formato da Etapa 1, gate de autorização, integridade dos splits, preparação/congelamento, CLI e persistência local.
- Criar `scripts/avaliacao_classificadores.py`: métricas, bootstrap por identidade, calibração e latências no teste congelado.
- Criar `scripts/graficos_classificacao.py`: oito gráficos produzidos somente a partir da avaliação real congelada.
- Criar `tests/unit/test_classificadores_binarios.py`, `tests/unit/test_experimento_classificacao_binaria.py`, `tests/unit/test_avaliacao_classificadores.py` e `tests/unit/test_graficos_classificacao.py`: fixtures sintéticas; nenhum rosto ou serviço externo.
- Criar `docs/ML-ETAPA-2-RESULTADO.md`: relatório de 21 seções; métricas e figuras biométricas ficam pendentes enquanto a autorização não existir.
- Reutilizar, sem modificar, `scripts/metricas.py`, `scripts/calibrar_limiar.py` (`Pares`, `bootstrap_por_identidade`, `Intervalo`, `intervalo_95`) e o formato `resultado.json`/`pares.npz` da Etapa 1.

## Tarefa 1: Dependências isoladas e classificadores

**Arquivos:** criar `requirements-ml.txt`, `scripts/classificadores_binarios.py`, `tests/unit/test_classificadores_binarios.py`.

**Interfaces:**

- `caracteristicas_da_distancia(distancias: np.ndarray) -> np.ndarray`: recebe vetor 1-D finito e retorna matriz `float64` de forma `(n, 1)`.
- `selecionar_limiar_por_far(rotulos: np.ndarray, escores: np.ndarray, far_maximo: float = 0.001) -> tuple[float, float, float] | None`: maior aceitação de positivos sob o FAR pontual máximo, por meio de `metricas.limiar_para_far_maximo` aplicado a `-escores`; retorna `(limiar_score, FAR_val, FRR_val)`.
- `ModeloSelecionado`: dataclass com `nome`, `estimador`, `parametros`, `limiar_score`, FAR/FRR de treino e validação e `tempo_treino_s`.
- `treinar_e_selecionar_modelos(X_treino, y_treino, X_validacao, y_validacao, *, far_maximo: float = 0.001, seed: int = 42) -> dict[str, ModeloSelecionado]`: ajusta somente em treino e escolhe hiperparâmetros/limiares na validação.

- [x] **Passo 1: escrever testes que falham:** `test_caracteristicas_da_distancia_gera_coluna_float64` confirma forma `(n, 1)`; `test_caracteristicas_rejeitam_valores_nao_finitos_ou_shape` confirma `ValueError`; `test_limiar_score_respeita_far_maximo_e_empates` confirma FAR ≤ 0,001 e desempate estável; `test_treina_m2_m3_m4_com_grade_definida` confirma só as grades declaradas; `test_classes_ausentes_e_sem_limiar_sao_recusadas` confirma falha explícita.
- [x] **Passo 2: confirmar a falha:** `.\.venv-ml\Scripts\python.exe -m pytest tests\unit\test_classificadores_binarios.py -q` falhou inicialmente pela interface inexistente.
- [x] **Passo 3: criar `requirements-ml.txt`** com `-r requirements-dev.txt`, `scikit-learn==1.9.1` e `matplotlib==3.11.2`; criado `.venv-ml` a partir de `.venv`, sem instalar pacotes no `.venv-app`.
- [x] **Passo 4: implementar** as quatro interfaces. Usar `LogisticRegression(solver="lbfgs", max_iter=1000, random_state=seed)`, seis combinações de `C`/`class_weight`, `GaussianNB(var_smoothing=1e-9)` e árvores com `criterion="gini"`, `random_state=seed` e profundidades 1/2/3. Escores são `predict_proba(X)[:, índice_da_classe_1]`.
- [x] **Passo 5: escolher candidatos** pelo menor FRR de validação entre configurações com FAR pontual ≤ 0,001; desempatar por menor FAR, limiar de score mais estrito e ordem fixa da grade. Sem limiar elegível, reportar candidato indisponível; não inventar um limiar. Para a configuração escolhida, computar FAR/FRR em treino com o limiar validado, somente como diagnóstico de overfitting.
- [x] **Passo 6: verificar:** dependências instaladas no `.venv-ml`; teste focal e suíte completa aprovados. O teste verifica entradas inválidas, grades e seleção sem limiar admissível.

## Tarefa 2: Leitura de pares, gate e congelamento em duas fases

**Arquivos:** criar `scripts/experimento_classificacao_binaria.py` e `tests/unit/test_experimento_classificacao_binaria.py`.

**Interfaces:**

- `ParesEtapa1`: dataclass com `conjunto`, `imagem_a`, `imagem_b`, `identidade_a`, `identidade_b`, `distancia` e `rotulo`.
- `carregar_pares_etapa1(arquivo: Path, conjunto: Literal["treino", "validacao", "teste"], *, congelamento_validado: Path | None = None) -> ParesEtapa1`: usa `np.load(..., allow_pickle=False)` e lê somente as chaves do split pedido; recusa `teste` sem congelamento válido.
- `validar_pares(pares: ParesEtapa1) -> None`: valida dimensões iguais, distância finita, rótulos 0/1 e equivalência `rotulo == (identidade_a == identidade_b)`.
- `validar_separacao(treino: ParesEtapa1, validacao: ParesEtapa1, teste: ParesEtapa1) -> None`: recusa identidades ou índices de imagem cruzando partições.
- `preparar_experimento(entrada: Path, saida: Path, autorizacao_dataset: Path, *, seed: int = 42) -> Path`: treina M2–M4, verifica os metadados da Etapa 1 e grava artefato congelado, sem ler arrays do teste.
- `avaliar_experimento(entrada: Path, congelamento: Path, saida: Path) -> Path`: valida hash/configuração congelada, então libera teste, valida separação e chama avaliação/gráficos.

- [x] **Passo 1: escrever testes que falham:** `test_validar_pares_confere_rotulos_com_identidades` exige erro para rótulo contraditório; `test_validar_particoes_detecta_vazamento` exige erro para imagem/identidade repetida; `test_preparar_nao_carrega_arrays_de_teste` usa spy que lança se uma chave `teste_*` for acessada; `test_preparacao_exige_documento_autorizacao` confirma falha antes de `np.load`; `test_metadados_s1_incompativeis_sao_recusados` cobre hash/seed/contagens; `test_congelamento_serializa_e_recarrega_modelos` compara predições; `test_carregar_congelamento_verifica_hash_e_metadados` recusa artefato alterado.
- [x] **Passo 2: confirmar a falha:** `.\.venv-ml\Scripts\python.exe -m pytest tests\unit\test_experimento_classificacao_binaria.py -q` deve falhar nas interfaces/guardas ausentes.
- [x] **Passo 3: implementar** leitor compatível com as chaves atuais de `pares.npz` (`{split}_{imagem_a,imagem_b,identidade_a,identidade_b,distancia,rotulo}`) e metadados de `resultado.json`. Consumir somente `metadados`, `selecao`, `extracao` e `limiares_congelados`; ignorar campos históricos `teste`/`auc_teste`. Verificar SHA-256 do `pares.npz` `BF40A75899A76334F2A2D11354C9D8DB6F8F5BAD74D7E9675B98D7DFDEA46058`, seed 42, assinatura `4c7ddc45f322ec3c`, contagens de falha de extração, duplicatas exatas/quase duplicatas e M1 `FAR<=0.1% == 0.4282`; falhar fechado se incompatíveis.
- [x] **Passo 4: exigir** que `autorizacao_dataset` aponte para um documento local existente e não vazio antes de qualquer leitura/ajuste de pares reais. Registrar caminho lógico e SHA-256 no manifesto, nunca o conteúdo do documento em logs.
- [x] **Passo 5: congelar** modelos via joblib e manifesto JSON com seed, assinatura/hash dos dados, versões, hiperparâmetros, coeficiente/intercepto LR, profundidade/folhas/limiares da árvore, limiares de score, métricas de validação e hash do arquivo de modelos. M0/M1 são registrados com score `-distância` e limiares `-0.30`/`-0.4282`.
- [x] **Passo 6: implementar a liberação do teste** somente após verificação do hash do modelo, manifesto e artefato de origem. Após liberar, ler o teste uma vez e validar vazamento de identidade/imagem antes de calcular métricas.
- [x] **Passo 7: verificar:** repetir os testes focais; esperado: preparação não toca nas chaves de teste, artefato adulterado é recusado e a avaliação só abre o teste com o congelamento íntegro.

## Tarefa 3: Métricas, incerteza e tempo

**Arquivos:** criar `scripts/avaliacao_classificadores.py` e `tests/unit/test_avaliacao_classificadores.py`.

**Interfaces:**

- `avaliar_escores(rotulos: np.ndarray, escores: np.ndarray, limiar_score: float, *, probabilidades: np.ndarray | None = None) -> dict[str, float | int | None]`: retorna TP/TN/FP/FN, FAR/FRR, acurácia, precisão, recall, F1, AUC, EER e Brier quando probabilidades estiverem disponíveis.
- `avaliar_no_teste(pares: ParesEtapa1, modelos: Mapping[str, ModeloSelecionado], *, seed: int = 42, replicas: int = 1000) -> ResultadoEtapa2`: inclui M0/M1 e os modelos congelados, escores por par, métricas, CIs, calibração e tempos.
- `ResultadoEtapa2`: guarda dados de score/rótulo necessários para gráficos durante a execução, resultados agregados e estimativa por método; não serializa IDs de identidade/imagem no relatório.

- [x] **Passo 1: escrever testes que falham:** `test_metricas_confusao_e_auc_respeitam_orientacao_do_score` confirma TP/TN/FP/FN e AUC; `test_auc_logistica_univariada_espelha_distancia` confirma ordenação monotônica; `test_metricas_sem_denominador_sao_nulas` confirma `None`; `test_brier_existe_so_com_probabilidades` confirma ausência para baselines; `test_bootstrap_por_identidade_e_reprodutivel` confirma réplicas repetíveis; `test_zero_fp_aplica_regra_dos_tres_por_par_de_identidades` confirma resolução conservadora; `test_far_so_atendido_com_limite_superior_abaixo_do_teto` confirma “não demonstrado” quando incerteza cruza 0,001.
- [x] **Passo 2: confirmar a falha:** `.\.venv-ml\Scripts\python.exe -m pytest tests\unit\test_avaliacao_classificadores.py -q` deve falhar antes da implementação.
- [x] **Passo 3: implementar** as métricas reaproveitando `scripts/metricas.py`; converter score para `-score` para manter a convenção de distância menor = positivo. Reusar `Pares`, `bootstrap_por_identidade` e `intervalo_95` da Etapa 1, com seed 42 e 1.000 réplicas. Calcular EER por interpolação linear no cruzamento entre FAR e FRR da ROC empírica exata, nunca usando EER para escolher limiar.
- [x] **Passo 4: computar** Brier, quantis de probabilidades e dados de calibração apenas para M2–M4. Para distância por classe, registrar média, desvio-padrão, assimetria, curtose e quantis empíricos versus quantis gaussianos como diagnóstico descritivo do GaussianNB; isso não escolhe modelos. Registrar probabilidades como escores condicionados à amostragem/ponderação, nunca como probabilidade real de identidade.
- [x] **Passo 5: medir** treino selecionado e inferência vetorizada em uma coluna: uma chamada de aquecimento e dez chamadas cronometradas do conjunto, reportando mediana do tempo total e por par.
- [x] **Passo 6: classificar o teto:** registrar pares de identidades impostoras distintos; com zero falsos aceites, reportar também o limite `3/n` por essa contagem efetiva. No teste, marcar atendimento a FAR ≤ 0,001 somente se FAR pontual, limite superior do IC de 95% por identidade e, quando aplicável, `3/n` forem todos ≤ 0,001; do contrário, “não demonstrado”. Reutilizar a mesma seed/reamostragem para diferenças pareadas de FAR/FRR versus M0. Não reabrir seleção após avaliação.
- [x] **Passo 7: verificar:** teste focal aprovado; validar que o teste de referência detecta IC reprodutível, que pares da mesma identidade são reamostrados como grupo e que taxas sem denominador retornam `None`.

## Tarefa 4: Gráficos

**Arquivos:** criar `scripts/graficos_classificacao.py` e `tests/unit/test_graficos_classificacao.py`.

**Interface:** `gerar_graficos(resultado: ResultadoEtapa2, destino: Path) -> list[Path]` salva SVGs somente após avaliação real e devolve caminhos.

- [x] **Passo 1: escrever `test_gerar_graficos_retorna_oito_svg_rotulados`** para conferir nomes/títulos com conjunto usado; monkeypatch do salvamento impede arquivos gráficos sintéticos em disco.
- [x] **Passo 2: confirmar a falha:** `.\.venv-ml\Scripts\python.exe -m pytest tests\unit\test_graficos_classificacao.py -q` deve falhar até existir a interface.
- [x] **Passo 3: implementar** matrizes de confusão, ROC, FAR versus FRR, comparação de métricas, distribuições de distância, calibração LR, árvore e latência. Usar os escores/rótulos produzidos por `avaliar_no_teste`, nunca números digitados ou dados inventados.
- [x] **Passo 4: verificar:** teste focal aprovado sem criar SVGs de resultados sintéticos. Não executar a geração real enquanto o gate do dataset estiver pendente.

## Tarefa 5: CLI, relatório e verificação final

**Arquivos:** completar `scripts/experimento_classificacao_binaria.py`; criar `docs/ML-ETAPA-2-RESULTADO.md`.

- [x] **Passo 1: escrever `test_cli_preparar_exige_autorizacao` e `test_cli_avaliar_exige_congelamento`** para verificar argumentos e códigos de saída; usar fixture sintética em `tmp_path`, sem caminho LFW.
- [x] **Passo 2: implementar comandos:**
  - Preparação: `python -m scripts.experimento_classificacao_binaria preparar --entrada avaliacao/resultados/etapa1 --saida avaliacao/resultados/etapa2 --autorizacao-dataset <documento>`.
  - Avaliação: `python -m scripts.experimento_classificacao_binaria avaliar --entrada avaliacao/resultados/etapa1 --congelamento avaliacao/resultados/etapa2/congelamento.json --saida avaliacao/resultados/etapa2`.
  - Ambos registram seed/versões; somente avaliação gera gráficos e métricas finais. Esses comandos sobre LFW não serão executados sem autorização documentada.
- [x] **Passo 3: criar o relatório** com as 21 seções exigidas. Marcar métricas, hiperparâmetros selecionados, figuras reais e análise de erros como pendentes; incluir como proveniência da Etapa 1 os totais por split (999/333/336 identidades, 3.502/1.062/1.099 imagens, 1.007.319/563.391/603.351 pares, com 7.319/2.052/2.001 genuínos e 1.000.000/561.339/601.350 impostores) e 757 falhas de extração, sem apresentá-los como resultado da Etapa 2.
- [x] **Passo 4: registrar** a limitação da autorização LFW, teste S1 historicamente aberto, sobreposição potencial com treino FaceNet512, desbalanceamento e dependência entre pares; justificar SVM fora do escopo por usar somente distância escalar. Declarar “implementação concluída, avaliação experimental pendente” enquanto não houver liberação.
- [x] **Passo 5: rodar testes relevantes:** `.\.venv-ml\Scripts\python.exe -m pytest tests\unit\test_classificadores_binarios.py tests\unit\test_experimento_classificacao_binaria.py tests\unit\test_avaliacao_classificadores.py tests\unit\test_graficos_classificacao.py -q`; esperado: todos aprovados.
- [x] **Passo 6: rodar a suíte completa e qualidade:** `.\.venv-ml\Scripts\python.exe -m pytest`, `.\.venv-ml\Scripts\ruff.exe check .` e `.\.venv-ml\Scripts\mypy.exe`; resolver falhas introduzidas e registrar exatamente o resultado.
- [x] **Passo 7: revisar o diff final** para confirmar que somente os arquivos experimentais/documentação previstos mudaram e que não houve alterações em `src/`, configurações operacionais, banco, interface, nem artefatos biométricos rastreados.
