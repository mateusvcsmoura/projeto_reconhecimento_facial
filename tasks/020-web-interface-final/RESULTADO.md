# Resultado — tarefa 020: interface web responsiva

**Estado: parcial.** A interface e seus fluxos foram implementados no workspace,
os testes sintéticos passaram e o servidor local está disponível. A inspeção
visual por navegador, o E2E completo autenticado e o ensaio em dispositivos
continuam pendentes; não considero a aceitação visual nem o gate operacional
concluídos.

## Baseline e limites

- Branch `main`; HEAD inicial `9674a3a06ecd96d79eff25937a2385dee82ad5ac`.
- O gate `GATE_BACKEND_PARA_INTERFACE` está aprovado conforme os resultados
  atualizados das tarefas 019/019A. O gate operacional de dados reais segue
  `PENDENTE`.
- Preservei os diretórios `.pytest-*` preexistentes e não usei banco, webcam,
  Google Drive, VPS, imagens faciais ou credenciais operacionais. Nenhuma
  migration foi criada ou aplicada.
- O servidor foi iniciado em modo `test` com uma URL sintética de PostgreSQL
  apontando para uma porta sem serviço. A aplicação serve a interface; rotas que
  exigem banco não podem ser demonstradas nesse runtime.

## Implementação

- `src/presentation/web/app.py` publica os assets e serve a shell para landing,
  autenticação, gestão e fluxos de cadastro/presença, com cabeçalhos de segurança.
- `src/presentation/web/templates/index.html` fornece estrutura acessível e
  monta os módulos locais.
- `src/presentation/web/static/` contém o cliente de API, fluxos de página,
  câmera, estilo responsivo monocromático, canvas do hero e revelações de
  conteúdo acionadas pela viewport somente na landing. Capturas ficam em memória
  durante o envio; a interface não guarda frames nem coordenadas em storage
  persistente e não decide identidade, prova de vida ou presença.
- `tests/unit/test_web_apresentacao.py` verifica shell, assets, cabeçalhos e
  resposta JSON para caminho de API desconhecido. `tests/e2e/web/` contém oito
  testes sintéticos Node para polling, backoff, cancelamento, câmera fake,
  recusa de permissão, montagem da landing/login e comportamento do reveal com
  `IntersectionObserver` e movimento reduzido.
- Nenhuma dependência de frontend foi adicionada. A fonte usa fallback de sistema;
  não foi incluída Helvetica Now Display por falta de arquivo autorizado.

## Verificações executadas

Os comandos de teste e checagem executados nesta revisão foram:

```powershell
.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider -q -o 'addopts=' --disable-warnings --basetemp "$env:TEMP\pytest-task020-full-final-20261020"
.venv-ml\Scripts\python.exe -m pytest tests/unit/test_web_apresentacao.py -q --basetemp "$env:TEMP\pytest-task020-focus-final-20261020"
node --check src/presentation/web/static/app.mjs
node --check src/presentation/web/static/api.mjs
node --check src/presentation/web/static/camera.mjs
node --check src/presentation/web/static/hero.mjs
node --check src/presentation/web/static/scroll_reveal.mjs
node --test tests/e2e/web/frontend.test.mjs
.venv\Scripts\ruff.exe check src/presentation/web/app.py tests/unit/test_web_apresentacao.py
.venv\Scripts\ruff.exe format --check src/presentation/web/app.py tests/unit/test_web_apresentacao.py
.venv-ml\Scripts\python.exe -m mypy src scripts --show-error-codes
.venv-ml\Scripts\python.exe -m pip check
git diff --check
```

| Verificação | Resultado |
|---|---|
| `pytest tests/unit -p no:cacheprovider -q -o 'addopts=' --disable-warnings --basetemp <temporário exclusivo>` | 1.255 aprovados; 1 aviso de depreciação do adaptador datetime do SQLite/SQLAlchemy |
| `pytest tests/unit/test_web_apresentacao.py -q` | 3 aprovados |
| `node --test tests/e2e/web/frontend.test.mjs` | 8 aprovados |
| `node --check` nos módulos `.mjs` alterados | Aprovado |
| `ruff check` nos arquivos Python alterados | Aprovado |
| `ruff format --check src/presentation/web/app.py tests/unit/test_web_apresentacao.py` | Aprovado após formatar `app.py` |
| `mypy src scripts` | Aprovado; 158 arquivos fonte |
| `pip check` no ambiente de desenvolvimento | `No broken requirements found` |
| `git diff --check` | Aprovado; apenas avisos de normalização LF/CRLF do Git |

O `ruff check .` também passou, com avisos de acesso negado em diretórios
temporários preexistentes. A verificação de formatação global não é utilizável
neste workspace porque o Ruff tenta ler esses diretórios e retorna
`Expected a ruff source file`; a verificação foi limitada aos arquivos Python
alterados.

O smoke HTTP no servidor local retornou `200` para `/`, `/login`,
`/cadastro/sintetico`, `/presenca/sintetico`, `/assets/app.css` e
`/assets/app.mjs`. O endpoint desconhecido `/api/v1/rota-inexistente` retornou
`404` JSON. Isso comprova publicação da shell e dos assets, não autenticação,
acesso ao banco, autorização nem os fluxos de captura no browser.

## Servidor de inspeção e validações pendentes

O servidor local continua ativo em **http://127.0.0.1:8000**. A sessão do
processo foi iniciada pelo Codex; o usuário pode abrir esse endereço para
inspecionar a landing, login e estilo. Como o banco configurado é deliberadamente
inexistente, páginas de operação não completam chamadas de API. Não insira dados
reais ou biométricos nesse ambiente.

A enumeração do CUA retornou `apps: []` e `browsers: []`; as tentativas de criar
browser IAB e Chrome também informaram que o browser não está disponível. Por
isso não há screenshots, revisão visual em 320–2560 px, prova de contraste por
browser nem métricas de canvas/carregamento. Também não foram executados E2E
com autenticação e PostgreSQL, nem ensaios em Android/Chrome, iOS/Safari ou
notebook. Os testes Node exercitam doubles e DOM sintético, não equivalem a um
navegador completo.

## Ativação e rollback

Para iniciar manualmente em ambiente local, configure as variáveis `WEB_*`
conforme [`FACEDIFF-WEB-RUNTIME.md`](../../docs/FACEDIFF-WEB-RUNTIME.md) e rode:

```powershell
.venv-ml\Scripts\python.exe -m uvicorn src.web_main:create_web_app --factory --host 127.0.0.1 --port 8000
```

Esse comando não aplica migrations. Para encerrar o servidor desta execução,
use Ctrl+C na sessão correspondente. Não aponte a configuração de demonstração
para banco operacional. O rollback da implementação pode ser feito revertendo
os commits desta tarefa; nenhum dado ou schema foi alterado.

## Próximos gates

1. Disponibilizar um navegador controlável e repetir o teste visual da matriz,
   zoom, teclado, redução de movimento, estados de erro e fluxo de câmera.
2. Com PostgreSQL descartável autorizado e fixtures identificadas, executar E2E
   autenticado cobrindo ownership, CSV, recarga/idempotência e presença persistida.
3. Ensaiar dispositivos móveis/notebook e revisar acessibilidade visual/manual.
4. Manter deploy, VPS, Drive, dados reais e validação biométrica separados e
   pendentes de seus próprios gates e autorizações.

O resultado da tarefa permanece **parcial** até essas provas serem executadas.
