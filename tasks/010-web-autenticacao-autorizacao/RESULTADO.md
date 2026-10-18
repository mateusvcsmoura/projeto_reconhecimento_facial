# Resultado — tarefa 010: autenticação e autorização web

**Estado: concluída e publicada na `main`, sem deploy.** A revisão `0005` foi
aplicada ao banco local de desenvolvimento `escola`; a suíte de integração
PostgreSQL passou em banco descartável identificado. Após autorização explícita
do usuário, implementação, testes e documentação foram publicados em commits
separados; o push para `origin/main` foi confirmado.

Baseline: branch `main`, HEAD inicial
`47a7df993242c015a3c6719da92f95a582adaa1d`, sem alterações rastreadas antes da
tarefa. A implementação, os testes e a documentação foram organizados em três
commits por escopo.

## O que foi implementado

- Contas web separadas dos alunos, papéis `professor` e `admin`, usuário
  normalizado com NFKC/casefold, perfil de professor e armazenamento Argon2id.
- Sessões opacas com somente hashes persistidos, expiração por inatividade e
  absoluta, rotação no login, revogação e verificação de versão da credencial.
- Cookie `Secure`, `HttpOnly` e `SameSite=Lax`; checagem de `Origin`, CSRF,
  respostas `no-store`, limitação de tentativas por conta/IP e erros de login
  indistinguíveis.
- Troca e redefinição de senha, credencial temporária de uso único, desativação
  de contas e proteção para manter ao menos um administrador ativo.
- Autorização de turma carregada no servidor: professor acessa somente turma
  sob sua responsabilidade; turma legada sem responsável não é exposta. A
  transferência exige admin e justificativa.
- Eventos de auditoria na mesma transação das alterações. A revisão `0005`
  cria as tabelas, a FK opcional do responsável e proteção append-only no
  PostgreSQL.
- Bootstrap local de admin por `python -m scripts.criar_admin_web`, com senha
  digitada em prompt oculto e sem endpoint público.

O provider de autenticação é injetado na API web sem carregar OpenCV, DeepFace,
TensorFlow, PyTorch ou MediaPipe. As rotas não iniciam captura facial nem
alteram embeddings, anti-spoofing ou regras da CLI.

## Dependências e arquivos

`requirements-web.txt` agora fixa `argon2-cffi==25.1.0` e
`argon2-cffi-bindings==26.1.0`. A API, os casos de uso e o repositório estão em
`src/presentation/web/routes/auth.py`, `src/application/use_cases/` e
`src/infrastructure/repositories/postgres_conta_repository.py`. A revisão está
em `migrations/versions/0005_web_auth.py`; há testes unitários em
`tests/unit/test_web_auth.py` e testes PostgreSQL opt-in em
`tests/integration/test_web_auth_postgresql.py`.

Também foram atualizados `src/config/web_settings.py`,
`src/infrastructure/database/models.py`, `src/presentation/web/app.py`,
`src/web_main.py`, `scripts/criar_admin_web.py`,
`docs/FACEDIFF-WEB-AUTH.md`, `docs/FACEDIFF-WEB-RUNTIME.md`,
`docs/FACEDIFF-WEB-ROADMAP.md`, `docs/README.md`, `tasks/README.md`,
`tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.

## Verificações executadas

| Comando/checagem | Resultado |
|---|---|
| `python -m pytest tests/unit -p no:cacheprovider --basetemp <diretório-exclusivo> -q -o addopts= --tb=short` | 984 passaram em 10,86 s. |
| `pytest tests/unit/test_web_auth.py` | 14 testes passaram; código 0. |
| `pytest tests/integration/test_web_auth_postgresql.py` com opt-in task010 | 3 passaram em 4,86 s no PostgreSQL 18.6. |
| Ruff nos arquivos Python alterados | `All checks passed!` |
| Ruff format nos arquivos Python alterados | 13 arquivos já formatados. |
| `python -m mypy --python-executable .venv-ml\Scripts\python.exe src scripts` | Sem problemas em 93 arquivos fonte. |
| `.venv-ml\Scripts\python.exe -m pip check` | `No broken requirements found.` |
| `git diff --check` | Sem erros de whitespace. |
| Alembic `upgrade head --sql` com URL PostgreSQL fictícia e modo offline | Sucesso; SQL inclui `0005`, tabelas, trigger append-only e FK de responsável. Não abriu conexão nem aplicou DDL. |
| Alembic `history --verbose` | `0005 (head)`, parent `0004`. |
| `alembic upgrade head` em `localhost/escola` | Aplicou `0004 -> 0005`; conferidos 5/5 tabelas, trigger append-only e coluna nullable. |
| `alembic check` em `localhost/escola` | `No new upgrade operations detected.` |

Os testes exercitam rotas HTTP e banco PostgreSQL real local, incluindo
unicidade, perfil de professor, trigger append-only, rollback atômico de
auditoria e ownership de turma. O primeiro run do módulo revelou contaminação
entre casos: a fixture compartilhava dados e um teste assumia tabelas vazias.
O caso isolado passou; a fixture foi ajustada para limpar as tabelas antes de
cada teste e o módulo completo passou em seguida.

## Pendências e limites

O usuário autorizou em 18/10/2026 migrations e testes com escrita em bancos
locais de desenvolvimento/teste, incluindo reset e seed sintético. O módulo de
integração exige o opt-in
`FACE_WEB_AUTH_TEST_DB_AUTORIZACAO=AUTORIZO_MIGRAR_BANCO_DESCARTAVEL_TASK_010`,
nome com marcador e comentário exato de descarte. Foi criado
`task010_web_auth_test_20261018`; a fixture aplicou as revisões e, ao final,
removeu os dados de teste e reverteu o schema a `base`. Nenhuma imagem facial ou
dado operacional foi usado. Após o teardown, restou apenas a tabela
`alembic_version` sem revisões aplicadas; não há tabelas da aplicação no banco
descartável.

A migration `0005` foi aplicada à base local existente `escola`, após confirmar
host local e head `0004`. Não houve reset nem seed nessa base. Nenhuma conta
web foi criada nela; o bootstrap administrativo não foi executado. A verificação
agregada após a migration encontrou zero contas, sessões, eventos de auditoria e
turmas com responsável web.

Também permanecem pendentes implantação, proxy HTTPS real e revisão operacional
da referência independente exigida para redefinição de senha. Os testes
sintéticos não provam segurança operacional ou comportamento de concorrência.

## Ativação e reversão

Para preparar o runtime, instale `requirements-web.txt`, configure as variáveis
`WEB_*` por um gestor seguro e defina `WEB_PUBLIC_ORIGIN` HTTPS. O banco local
`escola` já está no head `0005`; os outros ambientes exigem migração coordenada
após validar o destino. Crie o primeiro admin no terminal local com
`python -m scripts.criar_admin_web`; a senha é solicitada sem eco. Consulte
[`docs/FACEDIFF-WEB-AUTH.md`](../../docs/FACEDIFF-WEB-AUTH.md) e
[`docs/FACEDIFF-WEB-RUNTIME.md`](../../docs/FACEDIFF-WEB-RUNTIME.md) para os
detalhes de configuração. O runtime e o bootstrap administrativo não foram
iniciados nesta execução.

Para reverter a aplicação, pare o runtime web e reverta somente as alterações
da tarefa 010 após revisar o diff. O banco de teste ficou sem tabelas da
aplicação e no schema `base`. No banco local `escola`, downgrade de `0005` só é
permitido sem contas, sessões, auditoria ou turmas atribuídas; a migration
recusa downgrade que perderia esses dados. Preserve backup antes de reverter
schema. Nenhum rollback do banco local foi executado.
