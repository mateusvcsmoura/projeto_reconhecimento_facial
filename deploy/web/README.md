# Artefatos de implantação FaceDiff Web

Este diretório prepara uma implantação Ubuntu 24.04 x86-64 com Docker Compose,
Caddy, API, worker facial único, PostgreSQL local e backup one-shot. São
artefatos revisáveis: esta tarefa não cria VPS, DNS, firewall, volumes, banco,
certificados nem stack em execução. A interface visual continua fora deste
escopo.

O ponto de entrada público é somente Caddy. A API recebe tráfego apenas pela
rede interna `web`; PostgreSQL, API, worker e backup usam `data`, marcada como
interna. O worker não tem rota de saída. Somente Caddy tem TCP 80/443 publicados
e rede externa para ACME; somente backup tem rede separada de saída HTTPS para
um remote futuro. Não se publica UDP/443, PostgreSQL 5432 nem API 8000, e nenhum
serviço monta `docker.sock`.

## Arquivos e versões-base

- `compose.yaml`: serviços `caddy`, `app`, `face-worker`, `postgres`, `backup` e
  o comando manual `migrate`, perfis `ops` e `admin`, redes, limites e mounts.
- `Dockerfile`: estágios separados para API HTTP, worker ML, migração, backup,
  Caddy e inicialização do PostgreSQL. A API instala apenas
  `requirements-web.txt`; o worker instala a stack FaceNet512/MiniFASNet e um
  ambiente MediaPipe separado, preservando fornecedores distintos de `cv2`.
- `Caddyfile`: TLS automático, proxy somente para `app:8000` e filtros dos logs.
- `.env.example`: caminhos e valores demonstrativos, sem credenciais.
- `run-facediff.mount.example` e `facediff-tmpfiles.conf`: mount tmpfs limitado
  do host e diretórios privados temporários.
- `postgres-init/001-web-roles.sh`: primeira inicialização do volume cria papéis
  `facediff_app` e `facediff_migrator` com credenciais distintas.

Imagens-base foram consultadas no Docker Hub em 19/10/2026 e fixadas por digest:
Python `3.12-slim-bookworm`, PostgreSQL `16.15-bookworm` e Caddy
`2.11.4-alpine`. Os registros oficiais mostram os digests e plataformas nas
páginas do [Python](https://hub.docker.com/layers/library/python/3.12-slim-bookworm/),
[PostgreSQL](https://hub.docker.com/layers/library/postgres/16.15-bookworm/images/sha256-efdf07c2f9d4df592783dcc8ea5f6db02efbf5f6452b527225ff5e58364570e9)
e [Caddy](https://hub.docker.com/layers/library/caddy/2.11.4-alpine/images/sha256-040e9f7480b80b6d4a7e5013a21159b950a63dcbdb956e38abe2387fb28d9ec0).
O arquivo rclone Linux AMD64 é da versão oficial `1.75.2` e o build verifica
seu SHA-256 antes de extrair o binário; [a versão e o artefato oficial](https://downloads.rclone.org/v1.75.2/)
estão publicados pelo projeto rclone.

Os requisitos Python diretos permanecem fixados nos arquivos versionados do
projeto. Bibliotecas nativas do worker e dependências transitivas de APT são
resolvidas dos repositórios assinados Debian/PGDG durante o build; portanto,
reproduzir exatamente bytes de imagens exige registrar também a revisão de
repositórios na task019. A referência de deployment deve ser o SHA do commit
que gerou as imagens, preenchido em `WEB_IMAGE_TAG`; não usar `latest`.

## Preparação manual do host

Faça estas etapas somente após revisar o contrato, elegibilidade, orçamento,
backup e capacidade. Não estão executadas por esta tarefa.

1. Confirme KVM2/Ubuntu 24.04 x86-64, acesso administrativo por chave SSH,
   firewall do provedor e do host. Permita SSH/22 somente dos endereços
   administrativos; permita TCP/80 e TCP/443 para Caddy. Não abra 5432 ou 8000.
   Como Docker pode inserir regras próprias de NAT, prove o bloqueio de portas
   externamente após configurar as regras. Não publique HTTP por IP para pedir
   acesso à câmera.
2. Confirme DNS A/AAAA do domínio escolhido, ausência de conflitos de rede com
   `172.28.50.0/24` e conectividade ACME. O CIDR web é configurável por
   `WEB_NETWORK_CIDR`; use um bloco privado livre no host.
3. Instale Docker Engine e Compose v2 suportados no Ubuntu. O operador administra
   o daemon no host; nenhum container de aplicação recebe socket ou acesso ao
   daemon.
4. Crie `/etc/facediff` e `/etc/facediff/secrets` fora do checkout. Copie
   `.env.example` para `/etc/facediff/web-deploy.env`, substitua
   `WEB_IMAGE_TAG` pelo SHA imutável do código, e mantenha o arquivo de ambiente
   sem valores secretos. Crie os oito arquivos referenciados nele: senha
   PostgreSQL admin, senha do papel de aplicação, senha do papel migrador, URL
   da API, chave HMAC web, URL Alembic, arquivo `pg_service` e `rclone.conf`.
   Use senhas aleatórias fortes, URL-encode nas URLs de banco e mantenha os
   segredos fora do repositório. Configure propriedade numérica 10001 e modo
   `0400` nos arquivos lidos por app/worker; o wrapper PostgreSQL copia seus
   três arquivos de inicialização para tmpfs como UID 999. Restrinja a pasta
   de origem ao administrador do host e ao Docker Engine.
5. As URLs de banco são distintas: `postgresql+psycopg://facediff_app:...@postgres:5432/facediff`
   para API/worker e a mesma forma com `facediff_migrator` para Alembic. O papel
   admin do PostgreSQL é usado apenas na criação inicial do volume. Não passe
   senhas como argumentos de linha de comando.
6. Coloque manualmente e com origem/licença já aprovada os arquivos locais em
   `/srv/facediff/models`: `face_landmarker.task` e, sob
   `home/.deepface/weights/`, `facenet512_weights.h5`,
   `2.7_80x80_MiniFASNetV2.pth` e `4_0_0_80x80_MiniFASNetV1SE.pth`. O worker
   monta essa árvore como somente leitura e falha antes de iniciar se algum
   modelo faltar. Não existe download de modelo no boot; o worker também não
   tem rede de saída.
7. Instale e ative o tmpfs compartilhado entre API/worker:

   ```sh
   sudo install -m 0644 deploy/web/run-facediff.mount.example /etc/systemd/system/run-facediff.mount
   sudo install -m 0644 deploy/web/facediff-tmpfiles.conf /etc/tmpfiles.d/facediff.conf
   sudo install -d -m 0755 /etc/systemd/system/docker.service.d
   sudo install -m 0644 deploy/web/docker.service.d/override.conf.example /etc/systemd/system/docker.service.d/override.conf
   sudo systemctl daemon-reload
   sudo systemctl enable --now run-facediff.mount
   sudo systemd-tmpfiles --create /etc/tmpfiles.d/facediff.conf
   sudo systemctl restart docker
   ```

   `/run/facediff` é tmpfs de 1 GiB, `nosuid,nodev,noexec`, perdido no reboot.
   Capturas, manutenção, dump plaintext e staging de transporte ficam em
   subpastas distintas com modo `0700`; app e worker compartilham exatamente a
   mesma pasta de capturas. O limite de captura continua 300 MiB. Swap pode
   persistir páginas de memória em disco; desative swap para esse host ou
   configure criptografia adequada e valide a política antes de receber dados.
   Desative core dumps (`ulimit -c 0` na unidade Docker/host) e monitore RAM:
   tmpfs consome memória conforme é usado. O tamanho é um teto, não uma reserva.
8. Copie o repositório para `/opt/facediff/current`, instale o arquivo de
   ambiente e valide a configuração antes de construir:

   ```sh
   cd /opt/facediff/current/deploy/web
   docker compose --env-file /etc/facediff/web-deploy.env config --quiet
   docker compose --env-file /etc/facediff/web-deploy.env build postgres app face-worker migrate backup caddy
   ```

   `config --quiet` não inicia serviços. A validação do Caddy, também sem
   iniciar o proxy, é:

   ```sh
   docker compose --env-file /etc/facediff/web-deploy.env run --rm --no-deps caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
   ```

9. Inicialize o banco vazio e aguarde `healthy`. A inicialização cria apenas
   os papéis do banco; não aplica schema:

   ```sh
   docker compose --env-file /etc/facediff/web-deploy.env up -d postgres
   docker compose --env-file /etc/facediff/web-deploy.env ps
   ```

   O script de roles só roda em volume PostgreSQL vazio. Se ele falhar, não
   apague nem recrie o volume para forçar nova tentativa; inspecione a causa e
   execute um procedimento administrativo revisado usando o papel admin.
10. Faça backup comprovado antes da primeira migration. O roundtrip PostgreSQL /
    rclone da task017 ainda não foi validado, portanto este exemplo de backup
    não é evidência de recuperação testada. A aplicação do schema é sempre
    explícita e usa o papel migrador:

    ```sh
    docker compose --env-file /etc/facediff/web-deploy.env --profile admin run --rm --no-deps migrate
    ```

    Migrations não rodam no entrypoint nem no `up`. Não use downgrade automático;
    revisões podem recusar rollback destrutivo. Se uma versão antiga não for
    compatível com schema atualizado, restaure backup em banco/volume novo e
    validado, e só depois planeje a troca.
11. Suba API e worker, crie o primeiro admin pelo prompt local e, depois da API
    ficar pronta, habilite o proxy:

    ```sh
    docker compose --env-file /etc/facediff/web-deploy.env up -d app face-worker
    docker compose --env-file /etc/facediff/web-deploy.env run --rm --no-deps -it app python -m scripts.criar_admin_web
    docker compose --env-file /etc/facediff/web-deploy.env up -d caddy
    ```

    A API tem `/health/live` (processo) e `/health/ready` (dependência de banco).
    O worker só fica healthy depois que os modelos carregam, o marcador de
    prontidão é criado e ele confirma que o processo ainda detém o advisory lock
    exclusivo PostgreSQL. Reinício invalida jobs ativos sem replay, conforme a
    task012; faça atualização do worker com a fila ociosa e confira as tentativas
    depois. Caddy não serve página: ele só encaminha para API.
12. Confira `docker compose ps`, `docker compose logs --since 10m app face-worker
    postgres caddy`, readiness, certificado e teste de rede a partir de outra
    conexão. Uvicorn não registra access log. O Caddy remove URI completa,
    cookies, Authorization e `Set-Cookie` de access/runtime logs. Ainda assim,
    revise logs de aplicação e proxy antes de aceitar tráfego; não passe tokens
    em URL.

## Segredos, backup e operação

As redes Compose separam os caminhos, mas uma rede bridge por si só não limita
saída por porta/protocolo. Antes de operar, configure e valide no host o
firewall de saída: Caddy precisa alcançar os endpoints ACME; o worker deve
permanecer sem saída; backup deve alcançar somente HTTPS e o destino aprovado.
Verifique as regras efetivas após iniciar Docker, pois regras NAT podem alterar
o comportamento de firewalls comuns. O arquivo Compose sozinho não prova esse
isolamento de egress.

Compose monta cada arquivo sensível apenas nos serviços que o declaram; a fonte
fica no host, fora do YAML e da imagem. A documentação oficial do Docker descreve
esse grant explícito de secrets por serviço em [Compose secrets](https://docs.docker.com/reference/compose-file/secrets/).
O administrador local que executa Compose tem acesso ao daemon rootful, por isso
host/admin continuam parte do limite de confiança.

Crie o arquivo de serviço PostgreSQL com host `postgres`, porta `5432`, banco
`facediff` e papel `facediff_app`. O `rclone.conf` contém um remote `crypt` local
`facediff-local-crypt`, com `filename_encryption=standard`,
`directory_name_encryption=false`, remote raw `local` em
`/var/lib/facediff/backup/encrypted` e as chaves de cifra. Essa configuração
fica em arquivo secreto no host; o diretório destino é volume persistente
cifrado antes de gravar os bytes. Não configure `WEB_BACKUP_EXTERNAL_RAW_REMOTE`
nem credencial Google até concluir o gate de restore real e autorizar o destino.

Para o timer diário, instale os exemplos `ops/systemd/facediff-web-backup.*.example`
sob `/etc/systemd/system`, confira caminhos e usuário root do serviço
(necessário para chamar o daemon Docker; o container não recebe socket), e então
ative o timer:

```sh
sudo install -m 0644 ops/systemd/facediff-web-backup.service.example /etc/systemd/system/facediff-web-backup.service
sudo install -m 0644 ops/systemd/facediff-web-backup.timer.example /etc/systemd/system/facediff-web-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now facediff-web-backup.timer
sudo systemctl list-timers facediff-web-backup.timer
```

O serviço usa `docker compose run --rm --no-deps backup` e falha fechado se
PostgreSQL não estiver ativo. O volume de backup e o estado do rclone persistem;
dump plaintext fica só no tmpfs. A cópia local está no mesmo host e não cobre
perda total da VPS. Task017 está parcial: exige primeiro validar `pg_dump`,
`cryptcheck`, restauração e exclusões em ambiente descartável antes de tratar
esse timer como recuperação confiável.

## Limites iniciais e rollback

`.env.example` sugere limites máximos de containers somando 5,75 GiB de RAM, mais
até 1 GiB de tmpfs compartilhado e `/dev/shm` do banco. Restam aproximadamente
2,25 GiB nominais para kernel, Docker e margem, antes de considerar page cache e
picos; os limites de CPU somam mais que 2 vCPU. São apenas guardas de engenharia,
não carga validada ou promessa de concorrência. A task019 deve medir aquecimento,
inferência, memória, backup, concorrência e fila no hardware real e ajustar
limites antes de qualquer operação.

Para rollback de código, pare o tráfego em Caddy, preserve volumes, selecione o
commit anterior, reconstrua com `WEB_IMAGE_TAG` daquele commit e só inicie a
versão antiga depois de verificar sua compatibilidade com a revisão do banco.
Não execute `docker compose down -v`, não apague volumes para “corrigir” falha e
não faça downgrade Alembic sem uma revisão que prove a reversibilidade. Se o
schema não aceitar a versão anterior, restaure uma cópia comprovada para novo
destino e mantenha o atual intacto até validar a troca. Para rollback total,
consulte o procedimento de encerramento em
[`FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`](../../docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md).

## Domínio e custo histórico consultado

Consulta pública em 19/10/2026: a página da Hostinger informa KVM2 a USD 8.99/mês
no termo promocional mostrado e renovação a USD 14.99/mês por ciclo de dois anos;
é uma captura da página global, não cotação regional, fiscal nem preço do
contrato do solicitante. A regra pública do domínio grátis indica VPS KVM novo
com contratação de 12 meses ou mais e somente TLD `.cloud` ou `.tech`; o artigo
de elegibilidade exclui planos mensais. Portanto a oferta não prova domínio
grátis num plano VPS de um mês. Revalidar termos, moeda, preço de renovação,
elegibilidade e domínio no checkout/contrato do usuário antes de decidir. Não
comprar domínio/VPS nesta task. Fontes oficiais consultadas: [preços Hostinger
VPS](https://www.hostinger.com/vps-hosting) e [elegibilidade do domínio VPS](https://www.hostinger.com/support/8317599-what-free-domains-are-available-at-hostinger/).
