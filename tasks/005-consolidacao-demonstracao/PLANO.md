# Plano executável — tarefa 005

Executor: **Luna 6 High**. [Desenho](DESENHO.md) aprovado internamente. Executar em ordem, no próprio agente, sem nova rodada de planejamento.

## 1. Confirmar fontes

1. Ler `AGENTS.md`, `CLAUDE.md`, instruções adicionais aplicáveis e o desenho.
2. Registrar branch, HEAD e status; base da preparação `main`, `e5cc961`. Preservar alterações alheias e temporários inacessíveis.
3. Conferir remoto/divergência conforme o prompt antes de editar.
4. Ler resultados 001–004, três JSONs da 004 e documentos previstos no desenho.
5. Confirmar comportamento em settings, qualidade, adaptador DeepFace, confirmação temporal, matcher/ambiguidade, casos de uso e menus. Localizar nomes com `rg`, sem depender da memória.
6. Inspecionar os quatro módulos de testes abaixo e suas fixtures antes de executá-los. Confirmar que não acionam modelos, câmera, banco ou dados reais.

Organizar as divergências como “afirmação → fonte → atual/histórico → correção”. Não criar outro arquivo permanente apenas para essa tabela.

## 2. Criar registro atual

Criar `docs/ESTADO-ATUAL-E-EVIDENCIAS.md` seguindo o desenho. Registrar implementações, defaults, fontes e pendências; explicar as séries de numeração. Registrar 812 unitários e as três medições como evidência histórica da 004. Conferir JSONs sem repetir o protocolo longo ou sobrescrever evidências.

## 3. Reconciliar memórias

Editar `AGENTS.md`, `CLAUDE.md`, `REFACTORING_PLAN.md`, `README.md` e `ARCHITECTURE.md`. Fazer ajustes pontuais e links para o registro atual. Conferir menções a TCC, protótipo/SQLite como estado atual, ausência de testes, contagens sem contexto, probabilidades de reconhecimento e prioridades já implementadas. Preservar ocorrências legitimamente históricas; não fazer substituição global de números.

## 4. Organizar material acadêmico e demonstração

Atualizar os seis documentos acadêmicos/de apresentação listados no desenho. Sugestão de roteiro de 15 minutos, incluindo a demonstração:

| Bloco | Minutos |
|---|---:|
| Problema e escopo | 1 |
| Arquitetura e embeddings | 2 |
| Controles 001–003 | 2 |
| Experimentos acadêmicos e limitações | 2 |
| Demonstração offline | 5 |
| Leitura das evidências da 004 | 2 |
| Pendências e conclusão | 1 |

A demonstração explica os controles com testes sintéticos existentes, executa o smoke e consulta evidências históricas. Incluir comandos completos, o que observar e o que os resultados não permitem concluir. Demonstração operacional real depende de autorização própria, fora desta tarefa.

## 5. Verificar documentação e comandos

Usar o ambiente existente `.venv-ml`; não instalar dependências. Após inspecionar fixtures, executar os comandos individualmente na raiz, registrando códigos de saída:

```powershell
$task005Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("rf-task005-" + [guid]::NewGuid().ToString("N"))
.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_qualidade_captura.py tests/unit/test_consistencia_temporal.py tests/unit/test_matcher_ambiguidade.py tests/unit/test_benchmark_matcher.py -q -p no:cacheprovider --basetemp $task005Temp
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --help
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --tamanhos 10 --consultas-por-cenario 2 --rodadas 2 --aquecimento 1
git diff --check
```

O smoke não grava JSON e não fundamenta conclusão de desempenho. A contagem dessa seleção é própria; não reutilizar “812 passed”. Não rodar pytest sem seleção, integração/BDD, migrations ou suíte completa. Não criar testes nem repetir benchmarks longos. Ruff/mypy não são necessários nesta entrega documental.

Se faltar ambiente ou houver falha, registrar o motivo. Corrigir comandos/documentos quando esse for o problema; não alterar implementação para fazer a demonstração passar. Não publicar a tarefa como concluída com verificação obrigatória pendente.

Conferir ainda:

- Links locais novos/alterados e âncoras, manualmente ou com script temporário sem dependências e sem arquivo versionado. Não verificar links externos pela rede.
- Afirmações atuais contra código e relatórios; cada número deve ter origem, escopo e unidade.
- Soma dos tempos, distinção de evidência funcional/computacional/biométrica e UTF-8 íntegro.
- Diff completo e `git diff --name-only`: somente documentos permitidos, nenhum histórico alterado.

## 6. Registrar e publicar

Criar `tasks/005-consolidacao-demonstracao/RESULTADO.md` com baseline, alterações, divergências resolvidas, comandos/códigos de saída/resultados, evidências apenas consultadas e limitações. Não antecipar sucesso de publicação.

Atualizar `tasks/README.md`. Revisar e fazer staging por caminhos explícitos da entrega, incluindo o pacote preparado. Commit sugerido `docs: consolida evidencias e demonstracao academica`; push `origin main` e confirmação conforme [PROMPT.md](PROMPT.md). Informar hash na resposta final, sem commit adicional apenas para registrar o próprio hash.

Encerrar quando documentação, verificações, relatório e publicação estiverem concluídos. Não ampliar para nova feature ou coleta experimental.
