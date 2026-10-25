#!/bin/bash
# Prepara o host Ubuntu da VPS para o deploy web: passos 4, 6 e 7 do
# deploy/web/README.md (arquivo de ambiente, segredos, modelos e tmpfs).
#
# Uso, com Docker Engine + Compose v2 instalados e o checkout em
# /opt/facediff/current:
#   sudo bash deploy/web/preparar_vps.sh --dominio facediff.exemplo.com --email voce@exemplo.com
#
# Pode rodar de novo, por exemplo depois de um git pull: WEB_IMAGE_TAG passa a
# apontar para o commit atual e segredos existentes nunca sao sobrescritos, pois
# as senhas do banco ficam gravadas no volume do PostgreSQL. Nao instala Docker,
# nao mexe em firewall e nao sobe a stack.
set -euo pipefail
umask 077

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ENV=/etc/facediff/web-deploy.env
UID_APP=10001
VOLUME_BANCO=facediff-web_postgres-data
# Chave fixa e publica do `rclone obscure` (fs/config/obscure do rclone). O
# rclone.conf guarda as senhas do crypt nesse formato; nao e criptografia.
CHAVE_OBSCURE=9c935b48730a554d6bfd7c63c886a92bd390198eb8128afbf4de162b8b95f638

falha() { echo "Erro: $*" >&2; exit 1; }
aviso() { echo "Aviso: $*" >&2; }
etapa() { echo "==> $*"; }
uso() {
    echo "Uso: sudo bash deploy/web/preparar_vps.sh --dominio DOMINIO --email EMAIL" >&2
    exit 2
}

dominio='' email=''
while (($#)); do
    case $1 in
        --dominio) dominio=${2:-}; shift 2 || uso ;;
        --email) email=${2:-}; shift 2 || uso ;;
        *) uso ;;
    esac
done
re_dominio='^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$'
re_email='^[^@[:space:]|&]+@[^@[:space:]|&]+$'
[[ $dominio =~ $re_dominio && $email =~ $re_email ]] || uso

((EUID == 0)) || falha "rode com sudo."
[[ $(uname -m) == x86_64 ]] || falha "as imagens do deploy sao x86-64."
for comando in docker git python3 openssl systemctl systemd-tmpfiles swapon; do
    command -v "$comando" >/dev/null || falha "comando ausente: $comando"
done
docker compose version >/dev/null 2>&1 || falha "Docker Compose v2 ausente."

valor_env() { sed -n "s/^$1=//p" "$ENV" | tail -n 1; }
definir_env() {
    if grep -q "^$1=" "$ENV"; then
        sed -i "s|^$1=.*|$1=$2|" "$ENV"
    else
        printf '%s=%s\n' "$1" "$2" >>"$ENV"
    fi
}

gravar_segredo() { # caminho dono conteudo; nunca sobrescreve
    local destino=$1 temporario
    [[ $destino == /* ]] || falha "caminho de segredo invalido no $ENV: '$destino'"
    if [[ -e $destino ]]; then
        echo "$destino: ja existe, mantido"
        return
    fi
    install -d -m 0700 "$(dirname "$destino")"
    temporario=$(mktemp "$destino.XXXXXX")
    printf '%s\n' "$3" >"$temporario"
    chown "$2:$2" "$temporario"
    chmod 0400 "$temporario"
    mv "$temporario" "$destino"
    echo "$destino: criado"
}

aleatorio() { openssl rand -hex 32; }

obscurecer() { # texto [iv_hex]: mesmo formato de `rclone obscure`
    local iv=${2:-$(openssl rand -hex 16)}
    {
        printf '%b' "$(sed 's/../\\x&/g' <<<"$iv")"
        printf '%s' "$1" | openssl enc -aes-256-ctr -K "$CHAVE_OBSCURE" -iv "$iv"
    } | openssl base64 -A | tr '+/' '-_' | tr -d '='
}

instalar() { # origem destino; mudou=1 quando o destino foi trocado
    install -d -m 0755 "$(dirname "$2")"
    mudou=0
    if ! cmp -s "$1" "$2"; then
        install -m 0644 "$1" "$2"
        mudou=1
    fi
}

etapa "Arquivo de ambiente $ENV"
install -d -m 0755 /etc/facediff
[[ -e $ENV ]] || install -m 0640 "$RAIZ/deploy/web/.env.example" "$ENV"
git_raiz() { git -c safe.directory="$RAIZ" -C "$RAIZ" "$@"; }
revisao=$(git_raiz rev-parse HEAD)
[[ -z $(git_raiz status --porcelain) ]] ||
    aviso "checkout com alteracoes locais; WEB_IMAGE_TAG=$revisao nao descreve o codigo exato."
definir_env WEB_IMAGE_TAG "$revisao"
definir_env WEB_DOMAIN "$dominio"
definir_env CADDY_ACME_EMAIL "$email"
echo "WEB_IMAGE_TAG=$revisao WEB_DOMAIN=$dominio"

etapa "Segredos"
senhas_banco=(
    "$(valor_env POSTGRES_PASSWORD_FILE)"
    "$(valor_env WEB_APP_DB_PASSWORD_FILE)"
    "$(valor_env WEB_MIGRATOR_DB_PASSWORD_FILE)"
)
if docker volume inspect "$VOLUME_BANCO" >/dev/null 2>&1; then
    for arquivo in "${senhas_banco[@]}"; do
        [[ -e $arquivo ]] || falha "o volume $VOLUME_BANCO ja existe e $arquivo sumiu;" \
            "uma senha nova nao bateria com o banco. Restaure o arquivo."
    done
fi
for arquivo in "${senhas_banco[@]}"; do
    gravar_segredo "$arquivo" root "$(aleatorio)"
done
senha_app=$(<"${senhas_banco[1]}")
senha_migrador=$(<"${senhas_banco[2]}")
gravar_segredo "$(valor_env WEB_DATABASE_URL_FILE)" "$UID_APP" \
    "postgresql+psycopg://facediff_app:$senha_app@postgres:5432/facediff"
gravar_segredo "$(valor_env ALEMBIC_DATABASE_URL_FILE)" "$UID_APP" \
    "postgresql+psycopg://facediff_migrator:$senha_migrador@postgres:5432/facediff"
gravar_segredo "$(valor_env WEB_SECRET_KEY_FILE)" "$UID_APP" "$(aleatorio)"
gravar_segredo "$(valor_env WEB_BACKUP_PG_SERVICE_FILE)" "$UID_APP" "[facediff]
host=postgres
port=5432
dbname=facediff
user=facediff_app
password=$senha_app"
# Vetor de obscure_test.go do rclone: confere a cifra antes de gravar as chaves.
[[ $(obscurecer potato 61616161616161616161616161616161) == YWFhYWFhYWFhYWFhYWFhYXMaGgIlEQ ]] ||
    falha "obscure divergiu do vetor de teste do rclone."
remote_crypt=$(valor_env WEB_BACKUP_LOCAL_CRYPT_REMOTE)
gravar_segredo "$(valor_env WEB_BACKUP_RCLONE_CONFIG_FILE)" "$UID_APP" "[local]
type = local

[${remote_crypt%:}]
type = crypt
remote = local:/var/lib/facediff/backup/encrypted
filename_encryption = standard
directory_name_encryption = false
password = $(obscurecer "$(aleatorio)")
password2 = $(obscurecer "$(aleatorio)")"

etapa "Modelos"
(umask 022 && cd "$RAIZ" &&
    python3 -m scripts.baixar_modelos --pasta-modelos "$(valor_env WEB_MODELS_HOST_DIR)")

etapa "tmpfs /run/facediff e unidade do Docker"
instalar "$RAIZ/deploy/web/run-facediff.mount.example" /etc/systemd/system/run-facediff.mount
instalar "$RAIZ/deploy/web/facediff-tmpfiles.conf" /etc/tmpfiles.d/facediff.conf
instalar "$RAIZ/deploy/web/docker.service.d/override.conf.example" \
    /etc/systemd/system/docker.service.d/override.conf
docker_mudou=$mudou
systemctl daemon-reload
systemctl enable --now run-facediff.mount
systemd-tmpfiles --create /etc/tmpfiles.d/facediff.conf
if ((docker_mudou)); then
    systemctl restart docker
fi
[[ -z $(swapon --noheadings --show) ]] ||
    aviso "swap ativo; o runbook pede host sem swap (ou swap cifrado) antes de dados reais."

etapa "Validando o compose"
docker compose --env-file "$ENV" -f "$RAIZ/deploy/web/compose.yaml" config --quiet

cat <<EOF

Host preparado. Proximos passos (deploy/web/README.md, passos 8 a 11):
  cd $RAIZ/deploy/web
  sudo docker compose --env-file $ENV build postgres app face-worker migrate backup caddy
  sudo docker compose --env-file $ENV up -d postgres
  sudo docker compose --env-file $ENV --profile admin run --rm --no-deps migrate
  sudo docker compose --env-file $ENV up -d app face-worker
  sudo docker compose --env-file $ENV run --rm --no-deps -it app python -m scripts.criar_admin_web
  sudo docker compose --env-file $ENV up -d caddy

O firewall precisa liberar TCP 80 e 443 para o Caddy, com SSH restrito.
Guarde fora da VPS uma copia de $(valor_env WEB_BACKUP_RCLONE_CONFIG_FILE):
sem as chaves dela, o backup cifrado nao pode ser restaurado.
EOF
