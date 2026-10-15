# Resultado — tarefa 007: captura automática

**Data:** 15/10/2026
**Branch/base:** `main`, base `f4763c7c72b2c2875576b8a0e070fc23074d28c7`; antes da implementação, `origin/main` estava no mesmo commit.
**Ambiente de testes:** `.venv-ml`, Python 3.14.3.
**Escopo:** testes unitários locais; sem câmera, banco, modelo externo ou dados faciais reais.

## Implementação

O modo automático agora é o padrão. `FACE_AUTO_CAPTURE_ENABLED=false` conserva
os fluxos manuais existentes. O controlador puro mantém apenas chave,
timestamps e contagem; exige três observações distintas, o tempo mínimo e
evidência recente. A agenda usa o relógio monotônico e mede o intervalo após o
fim de cada análise, enquanto a janela segue exibindo vídeo e processando ESC.

No cadastro, identificação e consentimento continuam antes de abrir a câmera.
`validar_captura` sonda a face sem gerar embedding ou persistir. Depois da
sequência, o caso de uso prepara uma `FacePreparada` de um frame novo e a
persiste uma vez, somente após novas checagens de idade e ESC. A API manual
`executar(...)` segue compatível e valida consentimento/identificação antes
do processamento.

No reconhecimento, o ID precisa permanecer igual durante a sequência e um
frame novo deve reidentificar o mesmo aluno. Quando `FACE_TEMPORAL_ENABLED`
está ligado, o confirmador temporal existente também precisa estar atual e
confirmado para esse ID. Cada sessão registra no máximo uma presença — ou
informa que ela já existia — e então libera a câmera. ENTER e ESPAÇO não
antecipam ações automáticas. Erros recuperáveis reiniciam a sequência; falhas
técnicas encerram a operação e não repetem persistência.

Foram adicionadas as quatro configurações em Settings e `.env.example`, sem
novas dependências. O desenho de landmarks permanece visual: a janela segue
desenhando sobre uma cópia, e o prazo da captura é revisto depois da exibição.

## Arquivos

- Novos: `src/domain/services/captura_automatica.py`,
  `src/presentation/cli/captura_automatica.py`,
  `tests/unit/test_captura_automatica.py`,
  `tests/unit/test_menu_automatico.py`,
  `tests/unit/test_main_automatico.py`,
  `docs/CAPTURA-AUTOMATICA.md` e este relatório.
- Alterados: `src/application/use_cases/cadastrar_aluno.py`,
  `src/config/settings.py`, `src/main.py`, `src/presentation/cli/menu.py`,
  `tests/unit/test_cadastrar_aluno.py`, `tests/unit/test_menu.py`,
  `tests/unit/test_prompts_e_settings.py`, `.env.example`, `README.md`,
  `ARCHITECTURE.md`, `docs/ESTADO-ATUAL-E-EVIDENCIAS.md` e `tasks/README.md`.
- Os arquivos `DESENHO.md`, `PLANO.md` e `PROMPT.md` foram preparados antes
  desta execução e foram preservados.

## Verificações executadas

Todas as verificações usaram `.venv-ml` e não abriram recursos reais.

| Comando | Resultado |
|---|---|
| `.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_captura_automatica.py tests/unit/test_menu_automatico.py tests/unit/test_main_automatico.py tests/unit/test_cadastrar_aluno.py tests/unit/test_menu.py tests/unit/test_menu_temporal.py tests/unit/test_prompts_e_settings.py -q -p no:cacheprovider --basetemp $env:TEMP\rf-task007-focused-last` | Aprovado; todas as barras chegaram a 100%, sem falhas. |
| `.\.venv-ml\Scripts\python.exe -m pytest tests/unit -q -p no:cacheprovider --basetemp <pasta-temporaria-única>` | Aprovado; os 911 testes unitários coletados chegaram a 100%, sem falhas. O diretório temporário foi criado fora do workspace. |
| `.\.venv-ml\Scripts\python.exe -m pytest tests/unit --collect-only -q -p no:cacheprovider --basetemp <pasta-temporaria-única>` | 911 testes unitários coletados. |
| `.\.venv-ml\Scripts\python.exe -m ruff check src tests` | Aprovado: todos os checks passaram. |
| `.\.venv-ml\Scripts\python.exe -m mypy` | Aprovado: nenhum problema em 76 módulos fonte. |
| `.\.venv-ml\Scripts\python.exe -m ruff format --check <12 arquivos Python alterados>` | Aprovado: 12 arquivos já estavam formatados. |
| `git diff --check` | Aprovado; apenas avisos do Git sobre normalização de LF/CRLF em arquivos Markdown existentes. |

Não foram executados testes de integração/BDD, smoke com webcam, inferência
real, consulta ao banco ou instalação de dependências. Não foram alterados
FaceNet512, o threshold `0.30`, anti-spoofing, os modelos ou dados existentes.

## Limitações e avaliação manual

Os limites de tempo são parâmetros iniciais de engenharia, não calibrados com
pessoas. Frames consecutivos são correlacionados; a espera não comprova
melhora de acurácia. O timestamp é coletado antes da leitura e não prova que o
sensor entregou um frame novo. Na sondagem de cadastro valida-se apenas que há
uma face única em cada análise: não há rastreamento biométrico que prove que a
mesma pessoa permaneceu diante da câmera durante toda a sequência. A
preparação final continua sujeita às políticas de qualidade e anti-spoofing
que já existiam.

O roteiro visual com uma pessoa está em
[`docs/CAPTURA-AUTOMATICA.md`](../../docs/CAPTURA-AUTOMATICA.md) e não foi
executado. A implementação funcional está concluída; a inspeção visual e
qualquer avaliação biométrica permanecem pendentes.

## Ativação e rollback

O `.env.example` fornece `FACE_AUTO_CAPTURE_ENABLED=true`, espera de 5 s,
amostragem de 0,5 s e idade máxima de 2 s. Para iniciar a aplicação, use
`python -m src.main`. Para recuperar o fluxo manual, defina
`FACE_AUTO_CAPTURE_ENABLED=false` e reinicie a aplicação. Isso não requer
migração de banco, recálculo de embeddings nem alteração dos outros controles.

## Estado e publicação

**Estado da implementação:** concluída e verificada automaticamente; avaliação
visual manual pendente. A autorização explícita para commit e push na `main`
foi fornecida no prompt da tarefa. A publicação será confirmada após a revisão
do diff staged e pela comparação entre o HEAD local e `origin/main`.
