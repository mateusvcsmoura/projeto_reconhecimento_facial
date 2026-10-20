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
  câmera, estilo responsivo monocromático, canvas do hero, revelações de
  conteúdo acionadas pela viewport e cursor magnético complementar na landing
  e nas telas de login/troca de senha. As passagens entre as seções de fluxo e
  dúvidas também revelam suas
  linhas estruturais, enquanto a lista abre cada resposta com deslocamento e
  opacidade sutis. A landing usa curvas largas na base do hero, no FAQ e no
  rodapé, além de uma forma radial discreta no fluxo, para suavizar a sucessão
  de seções. O ornamento do fluxo permanece confinado à largura da seção, sem
  criar rolagem horizontal. O cursor nativo permanece visível; o disco de 40px não intercepta
  eventos, usa `mix-blend-mode: exclusion` para ficar branco sobre preto e preto
  sobre branco, e é atraído aos dois links magnéticos com fator `0.55`. Capturas
  ficam em memória durante o envio; a interface não guarda frames nem coordenadas em
  storage persistente e não decide identidade, prova de vida ou presença. A animação
  é persistente e tem seus keyframes atualizados, evitando que o cursor volte ao
  canto da viewport entre frames. O login reaproveita a logo com inversão para
  o painel escuro e anima a entrada ordenada de suas informações e do formulário;
  o botão principal é um alvo magnético. Essas animações respeitam a preferência
  por movimento reduzido.
- `src/presentation/web/static/img/hero-section-img.jpg`, fornecida para a
  landing, substitui o canvas e a moldura facial genérica do hero. O CSS cobre
  apenas a área gráfica e ancora o recorte à direita, mantendo a área escura do
  título livre em desktop e mobile. É uma arte abstrata sem pessoa
  identificável; a exceção de CI e `.gitignore` vale somente para esse arquivo,
  enquanto as demais imagens continuam bloqueadas.
- `src/presentation/web/static/img/logo.png`, fornecida para a marca, substitui
  o monograma provisório `FD` e o texto adjacente nos cabeçalhos claros da
  landing e dos links de aluno. O link mantém um rótulo acessível; os cabeçalhos
  escuros preservam a wordmark textual, pois a logo fornecida foi desenhada para
  fundo claro. As exceções explícitas de CI e `.gitignore` permitem apenas essa
  logo e a arte abstrata do hero; todas as demais imagens seguem bloqueadas. A
  derivação publicada recorta o espaço externo da imagem para 256×256px,
  converte o fundo preto opaco em transparência e usa o monograma preto a 52px
  no cabeçalho, sem o bloco escuro sobre o fundo claro.
- Na navegação móvel, o acionador textual foi substituído por um SVG de menu
  preto, com área de toque de 44px e rótulo acessível preservado.
- No FAQ, a pergunta aberta recebe realce de baixa opacidade somente no
  cabeçalho; a resposta mantém o fundo da seção para evitar blocos cinza
  desproporcionais.
- `tests/unit/test_web_apresentacao.py` verifica shell, assets, cabeçalhos e
  resposta JSON para caminho de API desconhecido. `tests/e2e/web/` contém doze
  testes sintéticos Node para polling, backoff, cancelamento, câmera fake,
  recusa de permissão, montagem da landing/login e comportamento do reveal com
  `IntersectionObserver`, incluindo os contêineres de transição das seções,
  limite horizontal do ornamento, movimento reduzido e cursor magnético com suporte a
  mouse, toque, alvos e cleanup.
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
node --check src/presentation/web/static/magnetic_cursor.mjs
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
| `node --test tests/e2e/web/frontend.test.mjs` | 12 aprovados, incluindo transições estruturais, limite horizontal, atração persistente, alvos, cleanup, toque e movimento reduzido |
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
`/assets/app.mjs`. Após adicionar o cursor, `/assets/magnetic_cursor.mjs` e
`/assets/app.css` também retornaram `200`. O endpoint desconhecido
`/api/v1/rota-inexistente` retornou
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
