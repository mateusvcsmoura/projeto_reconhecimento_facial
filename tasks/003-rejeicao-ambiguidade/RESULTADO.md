# Resultado — tarefa 003: rejeição por ambiguidade

## Implementação

O matcher agora aceita uma política opcional de margem entre as duas menores
distâncias de identidades distintas. Com a política desligada, a decisão
anterior permanece, inclusive a escolha da primeira linha em empate. Com a
política ligada, o melhor candidato precisa primeiro atender a
`FACE_THRESHOLD`; depois, o matcher usa o mesmo vetor de distâncias para
encontrar linearmente a concorrência mais próxima. Distâncias de linhas com o
mesmo ID não concorrem entre si.

`FACE_AMBIGUITY_ENABLED` continua `false` por padrão. A margem permanece None
até ser fornecida e é obrigatória quando a política é ligada. O valor precisa
ser finito no intervalo [0, 2], inclusive quando a flag está desligada. Margem
zero recusa empates exatos calculados; margem positiva recusa gaps menores que
ela, e gap positivo igual à margem é aceito. Nenhum valor positivo é
recomendado ou calibrado nesta entrega.

`IdentificacaoAmbigua` propaga pelo caso de uso e recebe uma orientação própria
na CLI. A recusa remove o candidato atual; no fluxo temporal, também é enviada
ao confirmador como observação ausente com o timestamp da captura. Os três
caminhos de reconhecimento continuam na câmera e não registram a identidade
recusada. A comparação não adiciona extração de embedding ou multiplicação
matricial.

## Evidências

Baseline antes das mudanças:

```text
.venv-ml/Scripts/python.exe -m pytest tests/unit -p no:cacheprovider
707 passed in 29.69s
```

Validação final, com diretório temporário exclusivo fora do repositório:

```text
.venv-ml/Scripts/python.exe -m pytest tests/unit -p no:cacheprovider --basetemp C:\Users\User\AppData\Local\Temp\pytest-task003-final3-xMNMSF
776 passed in 7.04s

.venv-ml/Scripts/python.exe -m ruff check src scripts tests
All checks passed!

.venv-ml/Scripts/python.exe -m mypy
Success: no issues found in 69 source files

.venv-ml/Scripts/python.exe -m ruff format --check src/application/use_cases/reconhecer_aluno.py src/config/settings.py src/domain/errors.py src/domain/services/matcher.py src/main.py src/presentation/cli/mensagens.py src/presentation/cli/menu.py tests/unit/test_main_temporal.py tests/unit/test_matcher_ambiguidade.py tests/unit/test_mensagens.py tests/unit/test_menu.py tests/unit/test_menu_temporal.py tests/unit/test_prompts_e_settings.py tests/unit/test_reconhecer_aluno.py
14 files already formatted

git diff --check
exit 0
```

Os testes cobrem fronteiras exatas com vetores sintéticos, margem zero e
positiva, permutações, IDs repetidos, identidade desconhecida, incompatibilidade
de modelo/dimensão, composição das oito combinações das flags e recuperação da
sequência temporal após a recusa. O fluxo temporal ponta a ponta usa
`ReconhecerAluno` e matcher reais com provider, câmera, relógio e embeddings
sintéticos; também confirma uma nova sequência válida depois da ambiguidade.

## Limites

Os resultados demonstram comportamento funcional do software e contagem de
chamadas. Não medem acurácia, FAR, FPIR, desempenho computacional nem calibração
biométrica. Uma margem positiva pode aumentar recusas, e um gap grande não
garante identidade correta. `FACE_THRESHOLD=0.30` e o anti-spoofing foram
preservados. Não foram executados testes de integração/BDD, migrations, modelo
real, câmera, banco operacional ou avaliação com dados faciais.

Nenhum arquivo `.env` real, provider de reconhecimento, schema, banco ou dado
biométrico foi alterado. Os diretórios `.pytest-stage4-tmp-*` que já estavam no
checkout foram preservados.

## Publicação

O `PROMPT.md` autoriza commit e push de forma explícita. No momento da criação
deste relatório, a validação está concluída e o conteúdo segue para revisão de
staging e publicação em `main`; a confirmação do commit e do remoto será
informada na resposta da execução.
