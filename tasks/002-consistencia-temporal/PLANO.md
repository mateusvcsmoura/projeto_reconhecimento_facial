# Consistência temporal — plano de implementação

> Executor: Luna 6 High, no próprio agente. Usar `superpowers:executing-plans` quando disponível. Executar as caixas em ordem, sem novo brainstorming ou delegação.

**Objetivo:** exigir sequência consistente e vigente antes do registro, com nova leitura de confirmação no Enter.

**Arquitetura:** serviço de domínio recebe somente IDs/timestamps; CLI fornece relógio monotônico, eventos de reconhecimento e confirmação manual. Configuração optativa, sem mudanças no matcher ou provider.

**Stack:** Python/biblioteca padrão, Pydantic Settings, Pytest e ferramentas existentes.

**Especificação:** [DESENHO.md](DESENHO.md). Os contratos, limites inclusivos, defaults e mensagens ali definidos são normativos.

## Restrições globais

- `FACE_TEMPORAL_ENABLED=false`, mínimo 3 observações, janela 5.0 s, validade 2.0 s.
- Preservar tarefa 001, `FACE_THRESHOLD=0.30`, antispoofing e intervalo de comparação 8.
- Nenhum dataset, biometria real, webcam, modelo carregado, banco, migration, novo pacote ou benchmark.
- Testar com relógio manual e dublês; não usar sleeps ou o relógio real em asserts de tempo.
- Não alterar arquivos da tarefa 001 nem marcar seus resultados históricos como reexecutados.
- Commit/push somente após aprovação das verificações, conforme PROMPT.md.

## Pontos de revisão

| Risco | Prova prevista |
|---|---|
| Tempo contado após inferência lenta | Tarefa 2: relógio avança no provider e na leitura da câmera |
| Candidato continua registrável entre ciclos/na espera da tecla | Tarefa 2: expiração fora do frame 8 e durante `mostrar` |
| Enter conta o mesmo frame novamente ou registra outra pessoa | Tarefa 2: câmera com sentinelas distintas e troca A/B na confirmação |
| `None`, qualidade ou exceção reaproveitam histórico | Tarefas 1–2: interrupção, reentrada e recursos liberados |
| Flag altera baseline ou novos settings ignoram composição | Tarefas 2–3: modo desligado, quatro combinações e teste de main |

## 0. Inspecionar e registrar baseline

- [x] Ler AGENTS.md, CLAUDE.md, instructions/, desenho e código relacionado. Conferir relatório da 001 e preservar sua implementação.
- [x] Executar `git status --short`, `git branch --show-current` e `git log -4 --oneline`; registrar HEAD e trabalho preexistente. Fazer a verificação de remoto do prompt antes de editar produto.
- [x] Localizar ambiente existente. O anterior usou `.venv-ml`/Python 3.14.3 para testes com dublês; isso não comprova compatibilidade do DeepFace real com esse Python.
- [x] Inspecionar `tests/conftest.py` e testes selecionados; rodar somente baseline unitário, sem fixtures de banco. O registro anterior de 611 testes é histórico, não resultado desta execução.

## 1. Serviço puro de consistência e configuração

Criar `src/domain/services/consistencia_temporal.py` e `tests/unit/test_consistencia_temporal.py`. Alterar `src/config/settings.py`, `.env.example` e `tests/unit/test_prompts_e_settings.py`.

Produz as interfaces `ParametrosTemporais`, `EstadoTemporal`, `ConfirmadorTemporal.observar/consultar/reiniciar` do desenho. Não importar apresentação/aplicação/IO no módulo de domínio.

- [x] Escrever testes inicialmente falhando pela ausência do serviço. Usar IDs 1/2 e tempos explícitos.
- [x] Fixar casos: estado vazio; A@0, A@0.5 incompleto; A@1 completa; B reinicia contagem; `None` limpa; A/B alternados nunca confirmam; desconhecido entre As exige reinício.
- [x] Fixar bordas: consultar(3.0) após última A@1 ainda confirma; consultar(3.0001) limpa. Repetir consulta não acrescenta nem renova. A@3 depois de A@0.5 começa em 1. Janela curta do exemplo normativo remove somente eventos antigos.
- [x] Fixar estado limitado e continuidade: longa sequência da mesma pessoa mantém contagem N e continua confirmada com timestamps recentes; não reiniciar arbitrariamente a cada janela desde a primeira observação. Testar `reiniciar`, timestamp repetido/regressivo e argumentos inválidos sem mutação parcial.
- [x] Implementar dataclasses e serviço usando deque de tamanho máximo N, seguindo algoritmo do desenho. Expiração mantém marcador de última observação, `reiniciar` remove esse marcador.
- [x] Testar configuração: defaults, overrides via ambiente e kwargs, mínimo 1/0/negativo/fracionário/bool recusado; tempos zero/negativo/NaN/inf/bool recusados; validade maior que janela recusada; igualdade aceita. Não ler `.env`: usar `_env_file=None`, URL fictícia e monkeypatch de variáveis pertinentes.
- [x] Implementar Settings e comentários da `.env.example`; valores heurísticos optativos e independentes da qualidade.
- [x] Executar testes focais e corrigir até aprovação. Validar também dataclass construída diretamente, sem Pydantic.

## 2. Integrar sequência, exibição e confirmação manual

Alterar `src/presentation/cli/menu.py`. Criar `tests/unit/test_menu_temporal.py`. Usar ou ampliar minimamente `tests/fakes.py`; preservar `tests/unit/test_menu.py` como regressão do modo desligado.

Consome serviço da tarefa 1 e `Reconhecimento` existente. Acrescenta `temporal: ParametrosTemporais | None = None` e `relogio: Callable[[], float] = time.monotonic` a MenuCLI. Não alterar assinatura de `ReconhecerAluno.identificar`.

- [x] Criar relógio falso com instante ajustável, câmera de frames distintos, janela de teclas e provider com resultados/erros sequenciais. A passagem de tempo deve ocorrer por eventos controlados (leitura, inferência, mostrar), não por quantidade de chamadas ao relógio.
- [x] Escrever cenários falhando antes da integração. Contar chamadas ao registro, inferência e leitura; comparar ID efetivamente registrado.
- [x] Testar Enter antes de N: nenhuma presença e nenhuma inferência de confirmação; N ciclos válidos sem Enter: nenhuma presença; N + Enter: exatamente uma nova leitura e identificação antes de registrar o ID correto.
- [x] Testar Enter no mesmo frame de comparação e entre comparações: não reutilizar frame exibido nem resultado armazenado; uma inferência adicional, não duas extras. ESC nunca gera essa inferência.
- [x] Testar A confirmado + nova leitura B/None/qualidade ruim: nenhum registro. B reinicia em 1; qualidade preserva mensagem e câmera aberta. Usar `ReconhecerAluno` real com embeddings sintéticos em pelo menos um cenário de `None` para provar que desconhecido não é convertido em voto.
- [x] Testar múltiplos rostos e ausência via provider falso -> `None` do caso de uso -> sequência interrompida; qualidade após 2 As também exige recompor N.
- [x] Testar expiração entre comparações, durante `mostrar`, durante leitura bloqueante da câmera e durante inferência (normal e confirmação). Nenhum desses casos pode renovar idade datando o resultado no final do processamento.
- [x] Testar fraude/modelo/câmera com falha durante confirmação: zero registro e recursos liberados segundo tratamento existente. Não engolir falha de infraestrutura.
- [x] Testar confirmação consumida, segundo Enter sem nova sequência, presença já registrada e reentrada no modo. No modo temporal, consumir também o caso de duplicata; no desligado, manter aviso imediato no segundo Enter existente.
- [x] Implementar a integração conforme §§5–7 do desenho. Colher tempo antes da leitura, observar somente frames efetivamente analisados, consultar após inferência/a cada frame/ao receber Enter. Criar serviço local por sessão; manter regra numérica no domínio, mensagens e IO na CLI.
- [x] Organizar auxiliares privados pequenos para o fluxo sem duplicar o menu inteiro. Não refatorar cadastro ou demais opções. Rodar os testes temporais e os testes anteriores da 001 juntos.

## 3. Composição e documentação

Alterar `src/main.py`; criar `tests/unit/test_main_temporal.py` ou ampliar o teste existente de composição sem copiar toda a infraestrutura de mocks. Alterar somente seções relevantes de README e ARCHITECTURE.

- [x] Testar composição com engine/repos/câmera/DeepFace falsos, inspecionando argumentos recebidos pelo MenuCLI: None com flag desligada, parâmetros corretos quando ligada e overrides respeitados.
- [x] Testar quatro combinações de `FACE_QUALITY_ENABLED`/`FACE_TEMPORAL_ENABLED`: políticas independentes, threshold 0.30 e antispoofing preservados. Não abrir banco ao importar main; reutilizar o padrão de módulos falsos da 001.
- [x] Implementar composição e comprovar que não há estado temporal global entre chamadas de reconhecimento.
- [x] Documentar ativação, três observações analisadas (não três frames renderizados), janela/validade, confirmação extra no Enter, reset após registro e custo adicional somente no Enter elegível.
- [x] Documentar correlação de frames, possibilidade de erro consistente, buffering da câmera e ausência de calibração biométrica. Não prometer redução de falsos positivos ou latência medida.

## 4. Verificar, registrar e publicar

- [x] Executar testes focais durante as tarefas, depois a suíte unitária e verificações abaixo. Se o ambiente mudou, adaptar o caminho mantendo escopo e registrar o comando efetivo.

```powershell
.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider
.\.venv-ml\Scripts\python.exe -m ruff check src scripts tests
.\.venv-ml\Scripts\python.exe -m mypy
git diff --check
```

- [x] Executar Ruff format check somente nos arquivos Python da tarefa; não reformatar globalmente. Se pytest exigir `--basetemp`, escolher diretório novo e exclusivo em `$env:TEMP`; não reutilizar/apagar os temporários preexistentes.
- [x] Não executar migrations ou suíte de integração/BDD com PostgreSQL; esta tarefa não altera schema. Declarar esse limite, cobrindo o fluxo com fakes na suíte unitária.
- [x] Revisar diff: mudança restrita à temporalidade, 001 preservada, sem novos imports de cv2/DeepFace no domínio, sem persistência de histórico, sem dados/secrets e sem alteração de threshold/antispoofing/matcher.
- [x] Criar `tasks/002-consistencia-temporal/RESULTADO.md` com baseline, implementação, comandos/resultados reais, limitações, divergências justificadas e estado de publicação. Atualizar caixas executadas e índice. Não marcar push concluído antes de confirmá-lo.
- [x] Executar commit/push do PROMPT.md; responder com hash e evidência de publicação. Se houver impedimento, registrar estado parcial, não inventar resultado nem contornar proteção de branch.
