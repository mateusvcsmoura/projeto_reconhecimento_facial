# FaceDiff web — contas, sessões e autorização

Atualizado em 18/10/2026 pela tarefa
010 — autenticação e autorização.
O código e a migration estão publicados na `main`. Em 18/10/2026, `0005` foi aplicada
ao banco local de desenvolvimento `escola`; os três testes de integração
PostgreSQL passaram em um banco descartável identificado. Não houve deploy.

## Contas e credenciais

As contas web ficam separadas dos alunos e da biometria. O usuário é normalizado
com NFKC, espaços externos removidos e `casefold`, e possui unicidade no banco.
Os papéis são `professor` e `admin`; professor tem perfil próprio associado à
conta. Senhas são armazenadas em Argon2id (`argon2-cffi==25.1.0`, custo
`time_cost=3`, memória 64 MiB e paralelismo 4). A política exige 12–256
caracteres, até 1024 bytes UTF-8, sem regras artificiais de composição.

O primeiro admin só pode ser criado pelo comando local explícito
`python -m scripts.criar_admin_web`. Usuário e senha são pedidos em prompts; o
comando não recebe senha por argumento, não cria endpoint público e não substitui
uma conta existente. Repetir o bootstrap com o mesmo usuário é no-op; havendo
outro admin, o comando informa que o bootstrap já foi feito.

Criação de conta e redefinição administrativa entregam uma credencial temporária
uma única vez na resposta HTTP, válida por 30 minutos. O login com essa
credencial só pode ocorrer uma vez e exige troca de senha. Redefinição exige
justificativa e referência de verificação independente, revoga as sessões
existentes e incrementa a versão da credencial. A referência registrada é um
identificador de verificação externa; a API não comprova por si só que a etapa
operacional independente foi realizada.

## Sessões, CSRF e limite de tentativas

O cookie `facediff_session` contém um token aleatório de 256 bits; o banco guarda
somente SHA-256 do token. O cookie é `Secure`, `HttpOnly`, `SameSite=Lax`, tem
caminho `/api/v1` e vida máxima de 8 horas. A sessão também expira após 30
minutos sem atividade. O login emite sessão nova e revoga a sessão apresentada
no cookie anterior. Logout, troca/redefinição de senha e desativação revogam as
sessões correspondentes. A versão de credencial é conferida em cada request.

Toda mutação autenticada exige `Origin` igual a `WEB_PUBLIC_ORIGIN` e o header
`X-CSRF-Token`. O token CSRF é derivado por HMAC da sessão, o banco persiste
somente o seu hash e `GET /api/v1/auth/csrf` permite recuperá-lo após recarga da
aplicação. Respostas de autenticação e administração usam `Cache-Control:
no-store`. Em produção, `WEB_PUBLIC_ORIGIN` HTTPS é obrigatório.

Cinco falhas em 15 minutos bloqueiam temporariamente a chave de conta ou de IP
por outros 15 minutos. As chaves persistidas são HMACs com a chave web; usuário
e IP não ficam registrados na tabela de limite. Login inexistente, senha
incorreta, conta inativa e credencial temporária usada retornam a mesma resposta
401; o bloqueio retorna 429.

Sem proxy, o endereço remoto da conexão é usado. Atrás de proxy, configurar
`WEB_TRUSTED_PROXY_CIDRS` com os CIDRs exatos dos proxies controlados pela
aplicação; somente então o primeiro endereço não confiável da cadeia
`X-Forwarded-For` é usado. Não confiar em cabeçalhos encaminhados de clientes
diretos nem configurar redes amplas sem necessidade.

## Autorização de turmas e auditoria

`turmas.responsavel_professor_id` é nullable apenas para manter turmas legadas
sem responsável. A migration não inventa professores. Professor só consulta
turma que o servidor encontrou e cujo perfil é seu responsável; turma sem
responsável não aparece para professor. Admin tem acesso explícito. Transferir
responsabilidade requer admin, justificativa e fica auditado.

Eventos de login bem-sucedido, bootstrap, criação/desativação de conta, troca e
redefinição de senha, logout e transferência usam a mesma transação da mutação.
Falha ao gravar auditoria reverte a alteração. `eventos_auditoria_web` não
guarda senhas, tokens ou biometria; em PostgreSQL, trigger bloqueia `UPDATE` e
`DELETE`. Exclusão de contas não é oferecida pela API.

## Rotas

| Método e rota | Contrato |
|---|---|
| `POST /api/v1/auth/login` | Recebe usuário/senha; retorna estado mínimo da conta e token CSRF; define cookie seguro |
| `POST /api/v1/auth/logout` | Exige sessão, Origin e CSRF; revoga sessão |
| `POST /api/v1/auth/trocar-senha` | Exige sessão, Origin e CSRF; credencial temporária força troca e encerra sessões |
| `GET /api/v1/auth/csrf` | Recupera token CSRF da sessão autenticada, sem alterar `/me` |
| `GET /api/v1/me` | Retorna somente usuário autenticado, id, papel, ativo e troca obrigatória |
| `POST /api/v1/admin/contas` | Admin cria conta e recebe credencial temporária uma vez |
| `POST /api/v1/admin/contas/{id}/redefinir-senha` | Admin informa justificativa e referência de verificação independente |
| `POST /api/v1/admin/contas/{id}/desativar` | Desativa conta e revoga sessões; preserva ao menos um admin ativo |
| `POST /api/v1/admin/turmas/{id}/responsavel` | Admin transfere a turma para professor ativo com justificativa |
| `GET /api/v1/turmas/{id}` | Retorna dados mínimos apenas ao responsável ou admin |

Não há telas ou fluxo visual nesta etapa. O runtime não aplica migrations no
boot. Para configurar o admin inicial, defina as variáveis `WEB_*` por um meio
seguro e execute o comando explícito em terminal local; nunca coloque a senha na
linha de comando ou em arquivo versionado.

## Migration e reversão

A revisão `0005` expande o schema `0004` com contas, perfis de professor,
sessões, limite de login, auditoria e responsável de turma. Ela foi compilada
offline e aplicada ao banco local `escola`, que agora está em `0005`. O módulo
`tests/integration/test_web_auth_postgresql.py` passou 3 testes em
`task010_web_auth_test_20261018`, com comentário identificador e opt-in; a
fixture limpou os dados sintéticos e reverteu o schema desse banco para `base`
(restou somente a tabela `alembic_version` vazia).
Nenhuma conta web foi criada em `escola`.

O downgrade de `0005` recusa remoção se houver conta, sessão, auditoria ou turma
com responsável. Para o banco local, prefira rollback de
aplicação com schema expandido; reversão de schema exige cópia de segurança e
análise dos dados, sem apagá-los para forçar o downgrade. Veja o
resultado de execução
para comandos e evidências exatas desta etapa.
