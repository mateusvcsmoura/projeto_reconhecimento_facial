#!/bin/bash
set -euo pipefail

read_secret() {
    local destination="$1"
    local secret_file="$2"
    IFS= read -r "$destination" < "$secret_file" || true
    if [[ -z "${!destination}" ]]; then
        echo "A inicializacao exige arquivo de segredo nao vazio." >&2
        exit 1
    fi
}

read_secret app_password "$WEB_APP_DB_PASSWORD_FILE"
read_secret migrator_password "$WEB_MIGRATOR_DB_PASSWORD_FILE"
admin_password="${POSTGRES_PASSWORD:?Senha administrativa do PostgreSQL ausente}"

PGPASSWORD="$admin_password" psql --no-psqlrc --set=ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE facediff_app LOGIN;
CREATE ROLE facediff_migrator LOGIN;
REVOKE CONNECT ON DATABASE facediff FROM PUBLIC;
GRANT CONNECT ON DATABASE facediff TO facediff_app, facediff_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO facediff_app;
GRANT USAGE, CREATE ON SCHEMA public TO facediff_migrator;
ALTER DEFAULT PRIVILEGES FOR ROLE facediff_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO facediff_app;
ALTER DEFAULT PRIVILEGES FOR ROLE facediff_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO facediff_app;
SQL

printf '%s\n%s\n' "$app_password" "$app_password" \
    | PGPASSWORD="$admin_password" psql --no-psqlrc \
      --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
      --command='\password facediff_app' >/dev/null
printf '%s\n%s\n' "$migrator_password" "$migrator_password" \
    | PGPASSWORD="$admin_password" psql --no-psqlrc \
      --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
      --command='\password facediff_migrator' >/dev/null

unset app_password migrator_password admin_password
rm -f "$WEB_APP_DB_PASSWORD_FILE" "$WEB_MIGRATOR_DB_PASSWORD_FILE" \
    "$POSTGRES_PASSWORD_FILE"
