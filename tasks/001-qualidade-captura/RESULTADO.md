# Resultado — 001: qualidade de captura

Data da execução: 13/10/2026.

## Implementação

Foi adicionada uma política optativa, baseada apenas em NumPy, para avaliar a
menor dimensão da face, a luminância média e a variância do Laplaciano no
recorte BGR. Os erros de recusa têm orientações próprias. A configuração
`FACE_QUALITY_ENABLED` permanece `false` por padrão; quando habilitada, os
limites iniciais são 80 px, luminância de 40 a 215 e nitidez mínima 100. São
heurísticas de engenharia, sem calibração biométrica.

O adaptador aplica a política antes de gerar o embedding e exige as dimensões
originais `facial_area.w/h` do detector quando a política está ativa. O novo
contrato `preparar_cadastro` retorna o recorte e o embedding da mesma
detecção. O cadastro permite uma nova captura após recusa sem repetir os
dados de identificação e consentimento. No reconhecimento, a recusa limpa o
candidato do ciclo, mostra orientação amarela e mantém a câmera aberta. O
viewer desenha os overlays em uma cópia do frame.

Foram atualizados `src/domain/errors.py`, `src/domain/services/`,
`src/config/settings.py`, `src/infrastructure/face_recognition/`,
`src/application/use_cases/cadastrar_aluno.py`, `src/main.py`,
`src/presentation/cli/`, `tests/fakes.py`, testes unitários, `.env.example`,
`README.md` e `ARCHITECTURE.md`. Não foram adicionadas dependências. O limiar
operacional `FACE_THRESHOLD=0.30` e o anti-spoofing foram preservados.

## Verificação

Baseline anterior às alterações:

```text
.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider
518 passed in 29.56s
```

Verificações finais executadas após a implementação:

| Comando | Resultado |
|---|---|
| `.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider` | 611 passed in 6.45s |
| `.\.venv-ml\Scripts\python.exe -m ruff check src scripts tests` | All checks passed |
| `.\.venv-ml\Scripts\python.exe -m mypy` | Success: no issues found in 68 source files |
| `.\.venv-ml\Scripts\python.exe -m ruff format --check` nos 20 arquivos Python da tarefa | 20 files already formatted |
| `git diff --check` | Código de saída 0; sem erros |

O ambiente usado foi `.venv-ml`, Python 3.14.3. `py -0p` informou que não
há outras instalações de Python registradas no launcher. Os testes de
qualidade usam arrays sintéticos e dublês; não houve avaliação biométrica.
Não foram executados testes de integração/BDD nem migrations, pois podem
acessar PostgreSQL. Os testes novos de Settings desativam explicitamente a
leitura de arquivo de ambiente (`_env_file=None`).

## Limites e publicação

A luminância média não descreve todas as condições de contraluz, e ruído
pode elevar a medida de nitidez. Os testes demonstram comportamento do
software, não acurácia facial ou adequação dos limites para uso operacional.
Não foram usados rostos reais, datasets externos, webcam, modelos carregados
ou banco operacional.

O commit de implementação `0ddf6e02ae947e87461c69ed7ca6f372adcf2b6d`
(`feat: adiciona validacao de qualidade de captura`) foi enviado por
`git push origin main`. A confirmação imediatamente posterior retornou o
mesmo hash em `git rev-parse HEAD` e em
`git ls-remote origin refs/heads/main`. O checkout estava na branch `main` e
alinhado a `origin/main`. Os diretórios temporários preexistentes e o
`AGENTS.md` fornecido pelo usuário ficaram fora do commit.
