# Resultado — tarefa 005: consolidação e demonstração acadêmica

**Execução:** 13/10/2026. **Base analisada:** `main` em
`e5cc9612ede18d49ba48fdd60795016abbad953e`, igual a `origin/main` após
`git fetch origin`; divergência `0 0`. O projeto é uma atividade da
disciplina de IA da Fatec, não um TCC.

Antes das alterações, o checkout tinha `tasks/README.md` modificado com a
entrada preparada para a 005, o pacote `tasks/005-consolidacao-demonstracao/`
não rastreado e quatro diretórios preexistentes `.pytest-stage4-tmp-20261010*`
não rastreados. O pacote e a entrada do índice integram a entrega; os quatro
diretórios temporários foram preservados e ficaram fora do staging.

## Escopo entregue

Foi criado [`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](../../docs/ESTADO-ATUAL-E-EVIDENCIAS.md)
como referência para o pipeline atual, defaults, tarefas 001–004, evidências,
limites e pendências. O registro também diferencia as fases de refatoração,
as etapas experimentais de ML e as tarefas numeradas da conversa.

Foram reconciliados `AGENTS.md`, `CLAUDE.md`, `REFACTORING_PLAN.md`,
`README.md` e `ARCHITECTURE.md`. As descrições do protótipo monolítico e SQLite
foram qualificadas como baseline histórico; o plano original agora aponta
para `docs/baseline-arquitetura.md`. O estado atual mantém PostgreSQL,
FaceNet512, limiar `0.30`, anti-spoofing habilitado e políticas optativas
desligadas por padrão.

O roteiro de [`docs/apresentacao.md`](../../docs/apresentacao.md) foi
substituído por demonstração offline de cinco minutos, sem câmera, banco,
modelo ou dados faciais. Os documentos acadêmicos de ML preservam a Etapa 5
histórica de 10/10/2026 e acrescentam a atualização das tarefas 001–004:
[`consolidação`](../../docs/ML-CONSOLIDACAO-ACADEMICA.md),
[`matriz`](../../docs/ML-MATRIZ-RASTREABILIDADE.md),
[`guia de reprodutibilidade`](../../docs/ML-GUIA-REPRODUTIBILIDADE.md),
[`roteiro acadêmico`](../../docs/ML-ROTEIRO-APRESENTACAO.md) e
[`perguntas e respostas`](../../docs/ML-PERGUNTAS-BANCA.md). O índice de
[`tasks/README.md`](../README.md) aponta para este resultado.

## Divergências reconciliadas

| Afirmação anterior | Fonte de conferência | Situação e correção |
|---|---|---|
| `CLAUDE.md` descrevia o protótipo imaturo, SQLite e ausência de testes como estado atual. | `src/main.py`, `src/config/settings.py`, adaptadores, `ARCHITECTURE.md` e relatórios 001–004. | Eram fatos do baseline de 07/09/2026. Foram preservados na seção histórica; o estado atual recebe link para o registro de evidências. |
| O cabeçalho de `REFACTORING_PLAN.md` dizia que nenhuma alteração havia sido realizada e apontava `ARCHITECTURE.md` como baseline. | Notas de execução das fases no plano; `docs/baseline-arquitetura.md`; arquitetura atual. | O plano e a auditoria são históricos. O cabeçalho foi corrigido para apontar ao baseline preservado e ao estado atual. A validação de instalação limpa por outra pessoa permanece pendente. |
| `docs/apresentacao.md` dependia de webcam, PostgreSQL e apontava 281 testes. | Testes sintéticos selecionados, CLI do benchmark, relatório 004 e arquivos de evidência. | Roteiro substituído por fluxo offline de cinco minutos. Não instrui desligar anti-spoofing nem executar uma demonstração operacional sem autorização. |
| “Confiança em porcentagem” poderia ser lida como probabilidade; o consentimento da CLI aponta para a opção 3 ao falar em exclusão, embora a exclusão esteja na opção 5. | `src/presentation/cli/confianca.py`, `src/presentation/cli/menu.py`, resultados das tarefas. | README esclarece que o número deriva linearmente da distância e não é probabilidade calibrada. O erro na mensagem da CLI foi registrado como pendência por exigir mudança de código fora do escopo. |
| Prioridades 001–003 e benchmark 004 apareciam como trabalhos futuros; contagens 518/812 podiam parecer atuais ou acumuláveis. | Relatórios 001–004 e inspeção dos três JSONs da tarefa 004. | As entregas foram marcadas como implementadas; orientação explícita, múltiplas referências e avaliação biométrica autorizada permanecem pendentes. Contagens são snapshots por execução, não cumulativas; 518 é histórico da Etapa 5, 812 da tarefa 004 e 167 da seleção executada aqui. |

Os três JSONs consultados na tarefa 004 têm, cada um,
`status=ok`, 240 comparações, zero divergências de status/ID e numéricas,
zero distâncias não finitas e erro absoluto máximo
`1.1920928955078125e-7` ante tolerância `1e-5`. A configuração e os resultados
completos continuam nos arquivos históricos; nenhuma medição padrão foi
repetida nesta tarefa.

## Verificações executadas

Os módulos e fixtures foram inspecionados antes da execução. Os quatro
módulos selecionados usam arrays/embeddings sintéticos e relógio controlado;
nenhum solicita fixtures de banco, câmera ou modelo. `tests/conftest.py`
define fixtures PostgreSQL para outros testes, mas a seleção abaixo não as
usa. Não foi lido `.env` nem acessados `storage/` ou `avaliacao/`.

```powershell
$task005Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("rf-task005-" + [guid]::NewGuid().ToString("N"))
.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_qualidade_captura.py tests/unit/test_consistencia_temporal.py tests/unit/test_matcher_ambiguidade.py tests/unit/test_benchmark_matcher.py -q -p no:cacheprovider --basetemp $task005Temp
```

**Código de saída 0; 167 testes aprovados.** A saída `-q` mostrou 167 pontos
sem falhas ou skips; stderr vazio. O diretório temporário ficou fora do
repositório.

```powershell
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --help
```

**Código de saída 0.** A ajuda descreveu os argumentos e informou que o
benchmark sintético não mede inferência nem desempenho biométrico.

```powershell
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --tamanhos 10 --consultas-por-cenario 2 --rodadas 2 --aquecimento 1
```

**Código de saída 0; validação `ok`; 12 comparações; zero divergências;
erro absoluto máximo `1.1920928955078125e-7`, abaixo da tolerância `1e-5`.
Não foi passado `--saida-json`, portanto o smoke não gravou artefato. As
razões de mediana variaram por cenário, incluindo `0.947` no empate de
referência; os tempos do smoke não são evidência de desempenho.

As duas apresentações totalizam os tempos declarados: 15 minutos no roteiro
acadêmico (1+2+2+2+5+2+1) e cinco minutos na demonstração offline. Foram
verificados 116 links locais em 17 arquivos Markdown, sem falhas; quatro links
externos foram ignorados, sem acesso à rede. A verificação UTF-8 não encontrou
caracteres de substituição ou BOM. `git diff --check` e
`git diff --cached --check` terminaram com código 0 e sem erros de whitespace.
O Git avisou que normalizará LF para CRLF em alguns arquivos Windows e não
conseguiu ler o ignore global em `%USERPROFILE%/.config/git/ignore`; isso não
alterou o diff nem o conjunto staged.

Na revisão manual do diff staged, confirmei que seus 17 caminhos são somente
a documentação e os arquivos da tarefa 005 previstos no prompt. A mensagem
da CLI sobre a opção de exclusão segue registrada como pendência porque sua
correção exige código fora do escopo; os quatro diretórios temporários
preexistentes foram preservados.
Não foram executados pytest sem seleção, integração/BDD, migrations, Ruff,
mypy, suíte completa ou benchmarks padrão.

## Limites e publicação

Os relatórios 001–004 e as três medições padrão foram consultados, não
reexecutados. Os 167 testes desta tarefa cobrem somente quatro módulos. O
smoke valida execução e equivalência funcional em vetores artificiais, não
acurácia, FPS ou latência ponta a ponta. `tracemalloc` não é RSS. Não houve
avaliação com dados faciais, validação ética/licença, acesso à câmera/modelo/
banco, instalação de dependências ou alteração de código operacional.

Este resultado foi escrito antes do commit e do push; a publicação ainda
estava pendente ao fechá-lo. O hash e a confirmação remota são informados na
resposta final, sem um commit adicional apenas para registrar o próprio hash.
