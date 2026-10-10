# Guia de reprodutibilidade das Etapas 0–5

Este guia separa verificações de software, que podem usar fixtures sintéticas, de experimentos biométricos, que exigem autorização e governança próprias. **Nenhum experimento biométrico foi executado durante a Etapa 5.** Não usar imagens ou embeddings de alunos cadastrados.

## Requisitos e ambientes

- A aplicação com DeepFace exige Python **3.12 ou 3.13**, conforme o README, além de webcam, PostgreSQL configurado e pesos/modelos necessários. A instalação pode baixar dependências pesadas.
- Os experimentos tabulares/agrupamento estão em `requirements-ml.txt`, que inclui `requirements-dev.txt`, `scikit-learn==1.9.1` e `matplotlib==3.11.2`. A orientação existente é manter esse ambiente isolado em `.venv-ml`.
- `requirements-dev.txt` contém NumPy, pytest, pytest-cov, pytest-bdd, Ruff e mypy; não inclui OpenCV nem DeepFace. Os testes unitários substituem esses adaptadores por doubles.
- A validação desta consolidação ocorreu em Windows PowerShell, Python 3.14.3, NumPy 2.5.3, scikit-learn 1.9.1, Matplotlib 3.11.2, pytest 9.1.1, Ruff 0.16.6 e mypy 2.3.1. Esse ambiente foi usado para testes e lint; não é evidência de compatibilidade operacional do DeepFace no Python 3.14.
- O experimento histórico da Etapa 1 registra Python 3.12.0rc2, DeepFace 0.0.92, TensorFlow/tf-keras 2.21.0, OpenCV 4.13.0.92 e NumPy 2.5.3. O congelamento original contém mais metadados; esses valores são históricos e não foram reconstruídos nesta etapa.

## Criar ambiente de qualidade/ML

Com Python instalado e `py` configurado no Windows, os relatórios registram estes comandos para criar e instalar o ambiente experimental:

```powershell
py -3.12 -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install -r requirements-ml.txt
```

Para testar somente a camada de desenvolvimento sem as dependências experimentais, o repositório também documenta:

```powershell
python -m pip install -r requirements-dev.txt
```

Os arquivos de requisitos fixam versões das dependências. Não instalar as dependências ML no ambiente operacional `.venv-app` como parte desta consolidação.

## Comandos de qualidade

Os comandos executados nesta Etapa 5 foram:

```powershell
& '.\.venv-ml\Scripts\python.exe' -m pytest tests/unit --basetemp "$env:TEMP\pytest-stage5-unit-20261010"
& '.\.venv-ml\Scripts\ruff.exe' check src scripts tests
& '.\.venv-ml\Scripts\mypy.exe'
```

Resultado atual: **518 testes unitários passaram**, Ruff não encontrou problemas e mypy verificou 67 arquivos sem apontamentos. A suíte completa documentada na Etapa 4 passou historicamente com 597 testes. Ela não foi repetida na Etapa 5, porque os testes de integração/BDD dependem de PostgreSQL e o escopo desta etapa proíbe acessar o banco. A configuração dos testes de integração alerta que eles usam um banco descartável e manipulam o schema; não executar `pytest` sem revisar essa pré-condição.

Para executar somente os testes focais de uma etapa, os caminhos existentes são:

```powershell
python -m pytest tests/unit/test_divisao_por_identidade.py tests/unit/test_evaluate_model.py tests/unit/test_metricas.py
python -m pytest tests/unit/test_calibrar_limiar.py
python -m pytest tests/unit/test_classificadores_binarios.py tests/unit/test_avaliacao_classificadores.py tests/unit/test_experimento_classificacao_binaria.py tests/unit/test_graficos_classificacao.py
python -m pytest tests/unit/test_identificacao_aberta.py tests/unit/test_experimento_identificacao_aberta.py
python -m pytest tests/unit/test_agrupamento_embeddings.py tests/unit/test_experimento_agrupamento.py
```

As linhas acima descrevem testes de software e não executam modelos sobre faces. O comando de lint integral registrado pelo projeto é `ruff check .`; na verificação atual foi usado `ruff check src scripts tests`, que cobriu os diretórios de código e testes sem percorrer diretórios temporários locais inacessíveis. Para tipagem, o comando configurado é `mypy`.

## Dados e proteção

O protocolo coloca datasets, caches de embeddings e resultados sob `avaliacao/`, diretório ignorado pelo Git. Extensões comuns de imagem, vídeo e vetores também são ignoradas, e o CI tem verificação de arquivos sensíveis. Antes de qualquer autorização futura, confirme `git check-ignore -v` e `git status --short`, origem, finalidade, termos, autorização institucional, retenção e armazenamento local. Embeddings também são dados biométricos; não os comitar nem enviar para serviço externo.

O LFW já foi usado na Etapa 1. Seu teste histórico já foi consultado; repetir o dataset com outra seed não cria um holdout historicamente independente. Os relatórios das Etapas 2–4 mantêm o gate fechado porque não foi localizada autorização específica para esses usos posteriores. Não carregar LFW durante a reprodução só porque ele está presente no disco.

## Reprodução dos protocolos experimentais

Os comandos a seguir vêm dos CLIs e dos relatórios das etapas, mas são **referências bloqueadas por autorização**. Não executá-los até que haja evidência legítima de autorização para o dataset, finalidade, armazenamento e procedimento, além de revisão institucional quando aplicável. O documento passado por parâmetro não é validado juridicamente pelo software.

### Infraestrutura e Etapa 1

```powershell
python -m scripts.evaluate_model --dataset avaliacao/datasets/<dataset-aprovado> --validar-divisao --seed 42
python -m scripts.calibrar_limiar --dataset avaliacao/datasets/<dataset-aprovado> --seed 42 --far-alvo 0.001
```

`evaluate_model --validar-divisao` valida estrutura e divisão, sem inferência facial. A calibração exige dados autorizados e ambiente com DeepFace e Matplotlib. O LFW do relatório histórico não está autorizado por este guia para nova execução.

### Etapa 2 — pares 1:1

```powershell
python -m scripts.experimento_classificacao_binaria preparar `
  --entrada avaliacao/resultados/etapa1 `
  --saida avaliacao/resultados/etapa2 `
  --autorizacao-dataset <documento-local-legítimo> `
  --seed 42

python -m scripts.experimento_classificacao_binaria avaliar `
  --entrada avaliacao/resultados/etapa1 `
  --congelamento avaliacao/resultados/etapa2/congelamento.json `
  --saida avaliacao/resultados/etapa2 `
  --seed 42 `
  --replicas 1000
```

O documento da Etapa 2 descreve a entrada como artefatos de pares da Etapa 1; conferir o caminho e integridade dos artefatos reais e a licença/autorização antes de qualquer execução. O teste é consumido de acordo com o protocolo congelado.

### Etapa 3 — identificação open-set 1:N

```powershell
python -m scripts.experimento_identificacao_aberta preparar `
  --dataset avaliacao/datasets/<dataset-aprovado> `
  --autorizacao-dataset <documento-local-legítimo> `
  --seed 42

python -m scripts.experimento_identificacao_aberta avaliar `
  --dataset avaliacao/datasets/<mesmo-dataset> `
  --autorizacao-dataset <mesmo-documento-local>
```

### Etapa 4 — clustering

```powershell
python -m scripts.experimento_agrupamento preparar `
  --dataset avaliacao/datasets/<dataset-aprovado> `
  --autorizacao-dataset <documento-local-legítimo> `
  --confirmar-revisao-autorizacao `
  --seed 42

python -m scripts.experimento_agrupamento avaliar `
  --dataset avaliacao/datasets/<mesmo-dataset> `
  --autorizacao-dataset <mesmo-documento-local> `
  --confirmar-revisao-autorizacao
```

A flag `--confirmar-revisao-autorizacao` é uma declaração de que a revisão ocorreu; ela não substitui uma decisão legítima. O teste é reservado e consumido uma vez; não remover marcadores de teste para repetir a avaliação.

## Resultados, seeds e limitações

- Seed histórica principal: 42. Divisões, amostragens e configurações são registradas pelos próprios scripts e relatórios.
- Os resultados históricos da Etapa 1 estão em [`ML-ETAPA-1-RESULTADO.md`](ML-ETAPA-1-RESULTADO.md) e nos artefatos locais não versionados citados por ele. Os documentos das Etapas 2–4 contêm protocolos, não resultados biométricos.
- Resultados futuros, se autorizados, devem ficar em `avaliacao/resultados/` e ser agregados antes de divulgação. Não compartilhar imagens, nomes ou identificadores de pessoas.
- Uma reprodução do mesmo dataset/seed não remove sobreposição potencial com o treinamento do FaceNet512 nem muda o domínio de imagens públicas para webcam.
- Métricas de software, métricas de verificação 1:1, identificação 1:N e clustering são objetivos diferentes; não comparar números entre tarefas sem explicitar denominadores e protocolo.
