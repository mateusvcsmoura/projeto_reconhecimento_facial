#!/bin/bash
set -euo pipefail
umask 077

secret_dir=/run/secrets
runtime_secret_dir=/run/postgresql/facediff-secrets
install -d -o postgres -g postgres -m 0700 "$runtime_secret_dir"

copy_secret() {
    local source_path="$1"
    local target_path="$2"
    install -o postgres -g postgres -m 0400 "$source_path" "$target_path"
}

copy_secret "$POSTGRES_PASSWORD_FILE" "$runtime_secret_dir/postgres_admin_password"
copy_secret "$secret_dir/web-app-db-password" "$runtime_secret_dir/web_app_db_password"
copy_secret "$secret_dir/web-migrator-db-password" "$runtime_secret_dir/web_migrator_db_password"
export POSTGRES_PASSWORD_FILE="$runtime_secret_dir/postgres_admin_password"
export WEB_APP_DB_PASSWORD_FILE="$runtime_secret_dir/web_app_db_password"
export WEB_MIGRATOR_DB_PASSWORD_FILE="$runtime_secret_dir/web_migrator_db_password"

exec /usr/local/bin/docker-entrypoint.sh "$@"
