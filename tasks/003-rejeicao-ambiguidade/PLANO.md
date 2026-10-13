# Rejeição por ambiguidade — plano de implementação

> Executor Luna 6 High: usar `superpowers:executing-plans`, se disponível, e executar no próprio agente, sem delegação ou novo brainstorming.

**Objetivo:** recusar candidatos empatados/próximos com política optativa, integrada ao reconhecimento e à confirmação temporal.

**Arquitetura:** regra em matcher, política injetada no caso de uso, erro recuperável tratado nos três pontos da CLI. Reutilizar distâncias vetorizadas e composição existente.

**Stack:** Python/NumPy/Pydantic/Pytest existentes. Nenhuma dependência nova.

**Especificação:** [DESENHO.md](DESENHO.md), fonte normativa para contratos, precedência, fronteiras e mensagens.

## Restrições globais

- `FACE_AMBIGUITY_ENABLED=false`; margem None por padrão e obrigatória explicitamente ao habilitar. Zero recusa só empates; nenhum default positivo.
- Preservar tarefas 001/002, limiar 0.30, antispoofing, intervalo 8, tempos/contagem temporal e contratos anteriores por defaults opcionais.
- Não ler `.env` real, dados biométricos, webcam ou banco; não executar migrations, baixar pesos, treinar, instalar dependências ou alterar scripts experimentais.
- Não editar documentos históricos em `tasks/001-*` e `tasks/002-*`. Documentar nova análise apenas no pacote 003 e atualizar índice.
- Não rodar benchmark nem alegar ganho de latência/acurácia. Testar decisões e contagem de chamadas.

## Pontos de revisão

| Risco | Prova |
|---|---|
| Empate escolhido pela ordem | Tarefa 1: permutar galeria, política ligada/desligada |
| Segundo acima do limiar ou mesmo ID | Tarefa 1: concorrente acima de 0.30; IDs repetidos |
| None implícito/zero por coerção ativa política incorreta | Tarefa 2: Settings e composição, booleanos, margem ausente |
| Sequência temporal ou nome anterior sobrevivem à recusa | Tarefa 3: recusa durante acumulação/Enter, câmera continua |
| UI esconde motivo de recusa no Enter | Tarefa 3: orientação permanece sem contornar bloqueio |

## 0. Inspeção e baseline

- [x] Ler instruções do repositório, DESENHO.md, relatório da 002 e os arquivos indicados. Confirmar implementação atual; este plano não substitui inspeção.
- [x] Registrar `git status --short`, `git branch --show-current`, `git log -5 --oneline`; realizar verificação remota do PROMPT.md e preservar alterações preexistentes.
- [x] Usar `rg` para localizar chamadas de `melhor_candidato`, construtores de `ReconhecerAluno`, testes da CLI e composição. Existem chamadas posicionais de quatro argumentos e benchmark com assinatura antiga, que devem continuar funcionando.
- [x] Localizar ambiente existente e inspecionar fixtures antes de rodar baseline `tests/unit`. O número 707 é histórico, não resultado atual. Não importar DeepFace/cv2 reais.

## 1. Política e decisão no matcher

Alterar `src/domain/services/matcher.py`, `src/domain/errors.py` e `tests/unit/test_matcher.py`. Criar `tests/unit/test_matcher_ambiguidade.py` para os cenários novos se isso evitar ampliar excessivamente o teste antigo.

Produz: `PoliticaAmbiguidade(margem_minima)`, argumento keyword-only `ambiguidade=None` de `melhor_candidato`, erro `IdentificacaoAmbigua`. Retorno `Identificacao` inalterado.

- [x] Escrever testes e confirmar falha pela funcionalidade ausente antes de implementar.
- [x] Validar política direta: 0 e 2 aceitos; negativos, >2, NaN, infinitos, bool, string e None recusados. `ambiguidade` de tipo inesperado também falha explicitamente.
- [x] Provar baseline: dois IDs com mesmo vetor escolhem primeira linha quando política None; consulta/matriz/permutação com vencedor único devolvem resultado anterior. Não apagar teste de equivalência numérica já existente.
- [x] Política ligada: empate recusa para margens 0 e positiva independentemente da ordem; gap positivo menor recusa; maior aceita; único ID aceita se abaixo do limiar; galeria vazia retorna None; melhor fora do limiar retorna None mesmo em empate.
- [x] Para igualdade exata, consulta `[1,0]`, referências A=`[1,0]`, B=`[0,1]`: d1=0, d2=1. Margem 1 aceita; `np.nextafter(1.0, 2.0)` recusa; `np.nextafter(1.0, 0.0)` aceita. Não usar o matcher como oráculo de si mesmo.
- [x] Para candidatos próximos, usar vetores normalizados sintéticos com cossenos desejados e margem de teste 0.02/0.03, longe da fronteira de arredondamento. Exemplo d1 aproximado 0.29 e d2 0.31: margem 0.03 recusa mesmo com d2 acima de 0.30. Esses valores nunca viram defaults de produção.
- [x] Cobrir A/A sem B, A/A/B distante, A/A/B empatado e três ou mais IDs em ordens distintas: segundo competidor é outra identidade, não outra linha do mesmo ID.
- [x] Preservar erros por modelo/dimensão incompatíveis. Confirmar que entrada/galeria não são modificadas ao decidir.
- [x] Implementar cálculo único e redução linear do concorrente, mantendo operações numéricas do baseline; corrigir docstring sobre empate. Não fazer sorting global, clipping ou epsilon.
- [x] Rodar testes focais até aprovação.

## 2. Settings, aplicação, composição e orientação

Alterar `src/config/settings.py`, `.env.example`, `src/application/use_cases/reconhecer_aluno.py`, `src/main.py`, `src/presentation/cli/mensagens.py`; testes `test_prompts_e_settings.py`, `test_reconhecer_aluno.py`, `test_mensagens.py` e `test_main_temporal.py`.

Consome política/erro da tarefa 1. Produz argumento keyword-only `ambiguidade=None` de `ReconhecerAluno` e configuração do desenho. Não modificar API do adapter.

- [x] Testar Settings com `_env_file=None`, URL fictícia e ambiente isolado: default false/None; true sem margem falha; true com 0/positiva funciona; false com margem válida continua desligado; inválida fornecida falha mesmo desligado. Cobrir bool antes de coerção, NaN/inf, limites 0/2, string numérica de ambiente e variável vazia inválida.
- [x] Implementar campos/validadores e exemplo comentado conforme desenho. Erro de configuração deve mencionar `FACE_AMBIGUITY_MIN_MARGIN`; não instalar valor silenciosamente.
- [x] Testar caso de uso real com repos/provider falsos e matcher real: uma geração de embedding por chamada, recusa propagada como `IdentificacaoAmbigua`, identidade única/clara preservada, None para desconhecido. Defaults antigos e chamadas posicionais mantidos.
- [x] Implementar injeção da política e documentação da exceção. Não capturar a recusa no caso de uso como ausência de rosto.
- [x] Ampliar teste de composição de quatro para oito combinações qualidade/temporal/ambiguidade, com engine/repos/providers/janela falsos. Inspecionar política recebida pelo reconhecedor; None com flag desligada, margem explícita com flag ligada. Preservar asserts de quality, temporal, limiar e antispoofing.
- [x] Incluir `IdentificacaoAmbigua()` na enumeração de testes de mensagens; comprovar problema + ação e ausência de nomes/IDs/margens. Implementar orientação do desenho.
- [x] Rodar testes focais de configuração, aplicação, composição e mensagens.

## 3. Recusa recuperável nos três caminhos da CLI

Alterar `src/presentation/cli/menu.py`, `tests/unit/test_menu.py`, `tests/unit/test_menu_temporal.py`. Reutilizar relógio/câmera/provider roteirizados existentes. Mudança mínima; não reunir/reorganizar os laços nem reescrever cadastro.

- [x] Modo sem temporal: candidato A aceito, próximo ciclo ambíguo + Enter -> zero registro do resultado antigo; orientação amarela sem A/B, câmera aberta; próximo ciclo claro + Enter registra normalmente.
- [x] Modo temporal: duas observações A, ambiguidade na terceira, depois apenas uma A + Enter -> zero registro. Exigir N novas observações para permitir confirmação.
- [x] Ambiguidades repetidas: nenhum progresso/ID confirmado nem gravação. Não acrescentar frames ambíguos como votos válidos.
- [x] Enter após sequência A confirmada, nova captura ambígua -> não registrar, manter câmera e limpar histórico; próximo Enter não captura/inferencia confirmação sem reconstruir a sequência.
- [x] Testar orientação mantida quando Enter ocorre no mesmo frame ambíguo e entre comparações. Não substituir pelo nome anterior nem por texto genérico que esconda o motivo. Não usar string como estado de decisão.
- [x] Em pelo menos um teste temporal de ponta a ponta com fakes, usar `ReconhecerAluno` e matcher reais sobre embeddings sintéticos que produzam ambiguidade. Os demais podem lançar a exceção pelo roteirizador. Provar retorno à sequência válida após a recusa.
- [x] Implementar os handlers nos três pontos: limpar reconhecimento, observar None com timestamp em modo temporal, consultar estado e exibir orientação. Preservar handlers de qualidade; não capturar fraude/modelo/qualquer erro genérico como recusa recuperável.
- [x] Rodar testes da CLI e temporais, incluindo casos antigos de expiração, nova leitura no Enter, consumo de confirmação, fraude e liberação de recursos. Top-2 não adiciona inferências às já previstas.

## 4. Documentação, verificações e entrega

- [x] Atualizar README e ARCHITECTURE nas seções de decisão/configuração: diferença entre desconhecido, múltiplos rostos e ambiguidade de identidades; precedência do limiar; gap e margem; configuração explícita; reset temporal; ausência de calibração. Exemplo ativando zero deve dizer que rejeita somente empate exato.
- [x] Documentar que pode aumentar recusas, que grande gap não garante identidade correta e que política desligada preserva desempate antigo. Não apresentar redução de FAR/FPIR como comprovada.
- [x] Executar verificações finais com o ambiente existente (adaptar caminho se necessário):

```powershell
.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider
.\.venv-ml\Scripts\python.exe -m ruff check src scripts tests
.\.venv-ml\Scripts\python.exe -m mypy
git diff --check
```

- [x] Executar Ruff format check somente nos arquivos Python da tarefa, sem reformatação global. Se precisar de `--basetemp`, escolher diretório novo/exclusivo em `$env:TEMP`, sem apagar temporários preexistentes.
- [x] Não rodar migrations ou testes de integração/BDD ligados a PostgreSQL. Não há alteração de schema. Declarar esse limite e usar os testes de fluxo com fakes.
- [x] Revisar diff e staged: nenhuma mudança em provider, schema, configuração real, threshold ou dados; assinaturas antigas compatíveis; sem exemplos matemáticos apresentados como calibração. Corrigir somente problemas relacionados à tarefa.
- [x] Criar `tasks/003-rejeicao-ambiguidade/RESULTADO.md` com baseline, decisões, comandos/resultados reais, limitações e estado de publicação. Marcar caixas executadas e atualizar `tasks/README.md`, sem alegar push antecipadamente.
- [x] Executar commit e push pelo PROMPT.md. Relatar hash e confirmação do remoto ou impedimento concreto.
