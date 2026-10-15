# Plano executável — 007: captura automática

> **Luna 6 High:** executar com `superpowers:executing-plans`, no próprio agente. Desenho aprovado internamente; não reabrir planejamento. Usar testes focados antes de ampliar a verificação.

**Objetivo:** cadastro e presença sem ESPAÇO/ENTER, com espera validada, confirmação recente e uma operação por abertura.

**Arquitetura:** controlador temporal puro, sondagem/preparação/persistência separadas no cadastro e orquestração automática na CLI. Preservar modo manual e worker de landmarks.

**Stack:** bibliotecas já existentes; nenhuma instalação. **Spec:** [DESENHO.md](DESENHO.md).

## 1. Inspeção e baseline

- [ ] Ler AGENTS.md, CLAUDE.md, instructions/, desenho e resultado/correção da006. Verificar código real e registrar status/branch/HEAD. Preparação em `f4763c7`, main.
- [ ] Preservar alterações alheias e temporários. Conferir remoto/divergência conforme prompt antes de editar.
- [ ] Inspecionar fixtures dos testes afetados para manter verificação sem banco/câmera/modelos reais.

## 2. Controlador e configuração

Criar `src/domain/services/captura_automatica.py` e `tests/unit/test_captura_automatica.py`; alterar `src/config/settings.py` e `tests/unit/test_prompts_e_settings.py`.

- [ ] Implementar com testes prévios contratos/defaults definidos no desenho: true, espera5, intervalo0.5, validade2 e mínimo3.
- [ ] Testar fronteiras de tempo exatamente iguais, imediatamente abaixo/acima, relógio repetido/regressivo, NaN/Inf/bool, ausência, troca de chave, gap e inferência lenta.
- [ ] Provar que consultar não conta frame, não renova validade e não confirma apenas por tempo; estado de memória limitado e reinício completo.
- [ ] Com temporal optativo ligado, projetar uso conjunto preservando parâmetros atuais e sem obrigar espera5 a caber no deque de N timestamps.

## 3. Cadastro em fases sem side effects prematuros

Alterar `src/application/use_cases/cadastrar_aluno.py` e `tests/unit/test_cadastrar_aluno.py`; reutilizar `FacePreparada`/`FaceRecognition` existentes.

- [ ] Testar `validar_captura`: extrair_face_unica uma vez, nenhum embedding/storage/repository write.
- [ ] Testar `preparar_captura`: provider.preparar_cadastro uma vez, sem persistência, recorte/embedding correspondentes.
- [ ] Testar `concluir_cadastro`: consentimento explícito e identificação revalidados, uma persistência com preparação aprovada, erros propagados.
- [ ] Manter `executar` compatível, incluindo consentimento/identificação antes de inferência. Preservar testes existentes; evitar extrações duplicadas.
- [ ] Não modificar o algoritmo do DeepFace nem seu worker MediaPipe. Só atualizar comentários/contratos desatualizados se necessário.

## 4. Fluxos automáticos e composição

Alterar `src/presentation/cli/menu.py`, `src/main.py`; criar `tests/unit/test_menu_automatico.py` e `tests/unit/test_main_automatico.py`. Reutilizar `Janela.mostrar` e relógio injetado. Para evitar crescer o menu já extenso, extrair orquestração nova em `src/presentation/cli/captura_automatica.py` se necessário, sem refatorar os caminhos manuais fora do escopo.

- [ ] Injetar `ParametrosCapturaAutomatica | None` no menu; main passa parâmetros quando flag true. None mantém comportamento manual para compatibilidade e testes antigos explicitamente manuais.
- [ ] Implementar busca imediata, agenda por tempo, estados e mensagens. Não usar sleep de espera, tarefas concorrentes ou número de frames como relógio.
- [ ] Cadastro: preservar validação/consentimento anteriores à câmera; sondar sem gravação, contar, obter nova captura final, preparar, verificar ESC/frescor e concluir uma vez.
- [ ] Reconhecimento: mapear ID, reiniciar em None/erro/troca/expiração; exigir ConfirmadorTemporal quando habilitado; reidentificar frame novo e registrar mesma identidade uma vez.
- [ ] Rever idade depois de viewer.mostrar: o worker de landmarks pode atrasar. Verificar ESC também depois da inferência final, antes de persistir.
- [ ] Captura recusada reinicia na mesma janela. Infraestrutura e persistência falhando encerram/reportam; não emitir falso sucesso ou repetir gravações.
- [ ] Sucesso ou presença já existente encerra sessão e retorna ao menu; sem nova foto no reconhecimento. Sem mensagem pedindo ENTER/ESPAÇO no automático.

## 5. Regressões obrigatórias

- [ ] Com relógio e câmera dublados, ambos os fluxos funcionam com sequência de teclas sem SPACE/ENTER; SPACE/ENTER precoces não contornam critérios.
- [ ] ESC durante busca, contagem e após validação final cancela sem persistir. Não afirmar cancelamento retroativo depois da gravação.
- [ ] Nenhuma face, múltiplas, baixa qualidade, fraude, desconhecido, ambiguidade, mudança de identidade e expiração nunca disparam gravação indevida.
- [ ] Inferência ou viewer lentos invalidam candidato; frame final diferente do observado não usa identidade/recorte antigo.
- [ ] Três observações cedo demais não bastam; 5 segundos com menos de três não bastam; intervalo excessivo reinicia; espera7 configurada é respeitada.
- [ ] Sucesso e presença duplicada chamam persistência uma vez; falha no banco/storage não repete automaticamente.
- [ ] Galeria vazia não abre câmera; consentimento recusado não abre câmera; registro automático não salva fotos.
- [ ] Recursos liberados em sucesso/cancelamento/erro. Landmarks false/indisponíveis não impedem automação; desenho continua somente em cópia.
- [ ] Modo manual false mantém comportamentos testados em `test_menu.py` e `test_menu_temporal.py`. Temporal ligado no automático acrescenta seus requisitos; desligado não remove o mínimo3 da automação.

## 6. Verificar e documentar

Na raiz, executar cada comando individualmente e registrar resultado/código de saída. Criar basetemp exclusivo no diretório temporário do sistema; não usar nem apagar diretórios antigos inacessíveis.

```powershell
$task007Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("rf-task007-" + [guid]::NewGuid().ToString("N"))
.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_captura_automatica.py tests/unit/test_menu_automatico.py tests/unit/test_main_automatico.py tests/unit/test_cadastrar_aluno.py tests/unit/test_menu.py tests/unit/test_menu_temporal.py tests/unit/test_prompts_e_settings.py -q -p no:cacheprovider --basetemp $task007Temp
.\.venv-ml\Scripts\python.exe -m ruff check src tests
.\.venv-ml\Scripts\python.exe -m mypy
git diff --check
```

- [ ] Após focados aprovados, rodar uma vez `pytest tests/unit` com outro basetemp exclusivo e cacheprovider desabilitado; format --check somente nos Python alterados. Corrigir falhas pertinentes, sem instalar pacotes.
- [ ] Não rodar integração/BDD com banco, app principal, câmera ou downloads de modelo. Se ambiente indisponível, registrar bloqueio em vez de fabricar resultados.
- [ ] Atualizar `.env.example`, README.md e ARCHITECTURE.md; criar `docs/CAPTURA-AUTOMATICA.md` com estados, defaults, fallback manual, limites e roteiro manual para o usuário (sem executá-lo com dados reais).
- [ ] Atualizar pontualmente `docs/ESTADO-ATUAL-E-EVIDENCIAS.md`, sem reescrever relatórios001–006. Incluir distinção entre testes funcionais e validação visual/biométrica não realizada.
- [ ] Criar `tasks/007-captura-automatica/RESULTADO.md`: baseline, mudanças, comandos/resultados reais, limites, avaliação manual pendente e estado honesto antes da publicação. Atualizar índice.

## 7. Publicar

- [ ] Revisar diff e staged, somente caminhos explícitos da tarefa, incluindo pacote preparado. Nunca adicionar .env, imagens, modelos ou alterações alheias.
- [ ] Commit em PT-BR: `feat: automatiza captura de cadastro e registro de presença`. Sem Co-Authored-By e usando somente identidade/credenciais Git existentes do solicitante.
- [ ] Push main e confirmação conforme prompt. Não declarar concluído com falha de teste obrigatório. Não criar outro commit só para inserir hash no relatório.

Parar após entrega e publicação verificadas. Não ampliar para fila contínua, novas referências, head pose, calibração ou migração.
