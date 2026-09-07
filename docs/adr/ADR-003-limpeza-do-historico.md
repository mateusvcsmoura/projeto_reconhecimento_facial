# ADR-003 — Remoção do banco legado do histórico do Git

- **Status:** aceito e executado
- **Data:** 2026-09-07
- **Problema relacionado:** A1 (`REFACTORING_PLAN.md` §3)

---

## Problema

O commit inicial do repositório (`08116cf`) versionou `escola.db`, o banco
SQLite do protótipo. A Fase 1 removeu o arquivo do índice
(`git rm --cached`), mas isso não o remove do histórico: o blob continuava
alcançável a partir de `main`, recuperável com um único comando por qualquer
pessoa com acesso ao repositório.

### O que estava exposto — e o que não estava

Verificado por inspeção direta do blob histórico:

| Presente | Ausente |
|---|---|
| 1 nome real de pessoa | Nenhuma imagem facial (`fotos/` estava vazia no commit) |
| 39 registros de presença, todos do mesmo dia | Nenhum embedding ou template biométrico (a coluna sequer existia) |
| Um caminho Windows com o nome de usuário abreviado de outra pessoa | |

Esta distinção importa e foi apurada tarde: o conteúdo é **dado pessoal**
sob a LGPD, mas **não é dado biométrico**. Documentos anteriores desta mesma
refatoração descreveram o problema como "dados biométricos no histórico", o
que superestimava a gravidade.

Fator atenuante adicional: o repositório é **privado** — confirmado por
requisição não autenticada à API do GitHub, que retorna 404.

## Alternativas consideradas

| Opção | A favor | Contra |
|---|---|---|
| **A — Aceitar e documentar** | Custo zero, risco zero de perder histórico | O dado continua recuperável por quem tem acesso ao repositório |
| **B — `git filter-repo`** | Remove o blob de todos os commits **preservando mensagens e estrutura**; só os hashes mudam | Irreversível; exige push forçado; quebra clones existentes; não alcança as refs de Pull Request retidas pelo GitHub |
| **C — Recriar o repositório** | Remoção garantida, inclusive das refs de PR | Destrói os PRs, os merges e a narrativa das fases |

### A tensão específica deste projeto

O histórico do Git **é um entregável acadêmico**: 33 commits documentam a
refatoração em fases, com as decisões explicadas nas mensagens. O
`CLAUDE.md` §1 pede exatamente que o projeto demonstre organização e
capacidade de evolução.

Isso descarta a opção C — que resolveria o problema destruindo a evidência
do trabalho — e favorece a B, porque o `filter-repo` reescreve apenas o
conteúdo das árvores, mantendo mensagens, autoria, ordem e merges.

## Decisão

**Opção B**, executada nesta ordem:

1. clone espelho do remoto, como rede de segurança;
2. `git filter-repo --path escola.db --invert-paths`;
3. reconexão do remote (o filter-repo o remove por segurança);
4. publicação forçada de `main`;
5. remoção das três branches de fase, local e remotamente — todas já
   mergeadas, apontando para hashes que deixaram de existir;
6. remoção do backup espelho, que continha exatamente o dado eliminado.

## Verificação

```bash
git rev-list --all --objects | grep escola.db    # 0 ocorrências
git log --all --oneline -- escola.db             # nenhum commit
git rev-list --all --count                       # 33 (histórico preservado)
pytest -q                                        # 122 passed
```

## Trade-offs aceitos

| Ganho | Custo |
|---|---|
| Dado pessoal fora do histórico | Todos os 33 hashes mudaram; qualquer clone anterior precisa ser refeito |
| Mensagens, autoria e merges preservados | Os Pull Requests #1–#3 passam a referenciar commits inexistentes em `main` |
| Repositório permanece apresentável | O arquivo legado se foi: o ETL não pode mais ser demonstrado sobre o dado original |

## Risco residual — declarado, não resolvido

O GitHub mantém os commits de Pull Requests em refs próprias
(`refs/pull/<n>/head`), que **não são apagadas por um push forçado**. O blob
continua alcançável por essas refs até que o GitHub colete o lixo, o que
exige abrir um chamado no suporte.

Como o repositório é privado e o conteúdo é um nome mais registros de
frequência — sem imagem e sem template biométrico —, esse resíduo foi
considerado aceitável. Se o repositório vier a se tornar público, a decisão
deve ser reavaliada **antes** da mudança de visibilidade.

## Lição registrada

O `.gitignore` deve existir antes do primeiro commit, e não depois do
primeiro incidente. A Fase 1 passou a bloquear `*.db`, `/fotos/`,
`/storage/` e `.env`; a Fase 2 corrigiu esses padrões para ficarem ancorados
na raiz, depois que `storage/` sem barra inicial excluiu por engano um
módulo de código.
