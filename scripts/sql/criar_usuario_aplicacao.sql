-- Usuario da aplicacao com privilegio minimo.
--
-- Ate a Fase 5 a aplicacao conectava com o dono do banco, que pode criar e
-- destruir tabelas. Um bug -- ou um SQL injetado -- teria alcance de DDL
-- sobre uma base de dado biometrico. Principio do menor privilegio.
--
-- Separacao adotada:
--   * migracoes  -> usuario dono (DDL), usado APENAS por `alembic upgrade`
--   * aplicacao  -> usuario abaixo, so DML, usado por `python -m src.main`
--
-- Uso (ajuste a senha e execute como dono do banco):
--   psql -U escola -d escola -v senha="'TROQUE_ESTA_SENHA'" \
--        -f scripts/sql/criar_usuario_aplicacao.sql

\set ON_ERROR_STOP on

-- 1. O papel. NOSUPERUSER/NOCREATEDB/NOCREATEROLE sao explicitos de
--    proposito: o padrao ja e esse, mas escrever deixa a intencao no codigo.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'escola_app') THEN
        CREATE ROLE escola_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

ALTER ROLE escola_app PASSWORD :senha;

-- 2. Conectar e enxergar o schema, sem poder criar objetos nele.
GRANT CONNECT ON DATABASE escola TO escola_app;
GRANT USAGE ON SCHEMA public TO escola_app;
REVOKE CREATE ON SCHEMA public FROM escola_app;

-- 3. Somente DML nas tabelas existentes.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO escola_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO escola_app;

-- 4. Mesmo tratamento para tabelas criadas por migrations futuras.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO escola_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO escola_app;

-- 5. A tabela de controle do Alembic e do processo de migracao, nao da
--    aplicacao. Sem acesso de escrita, um bug nao consegue mentir sobre a
--    versao do schema.
REVOKE ALL ON TABLE alembic_version FROM escola_app;
GRANT SELECT ON TABLE alembic_version TO escola_app;
