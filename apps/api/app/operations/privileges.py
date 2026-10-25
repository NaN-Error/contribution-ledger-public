"""A deliberately separate API runtime role. Operator access remains trusted.

The application role is not a table owner, superuser, schema creator or migration
operator. Database triggers continue to guard finalized histories. This is not
row-level security; per-project access is still enforced in the application.
"""
import os
from sqlalchemy import text
from app.db.base import Base
ROLE='contribution_ledger_runtime'

def verify_runtime_role(connection):
    if connection.dialect.name!='postgresql':raise ValueError('Restricted staging requires native PostgreSQL')
    row=connection.execute(text('SELECT current_user,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
    if row[0]!=ROLE or any(row[1:]):raise ValueError('The staging API must use its nonprivileged runtime role')
    owned=connection.execute(text("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)")).scalar_one()
    if owned or connection.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one():
        raise ValueError('The runtime role must not own schema objects or create schema contents')
    if connection.execute(text("SELECT has_table_privilege(current_user,'public.contribution_events','TRUNCATE')")).scalar_one():
        raise ValueError('The runtime role must not truncate contribution history')

def provision_runtime(database,password,confirm):
    if confirm!='PROVISION-RESTRICTED-API' or len(password)<32:raise ValueError('Explicit provisioning and a strong generated password are required')
    from psycopg import sql
    with database.engine.begin() as c:
        if c.dialect.name!='postgresql':raise ValueError('Native PostgreSQL required')
        exists=c.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':ROLE}).first()
        if not exists:c.exec_driver_sql('CREATE ROLE '+ROLE+' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT')
        else:
            # A reused privileged/member role must be reviewed, not silently blessed.
            flags=c.execute(text('SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=:role'),{'role':ROLE}).scalar_one()
            membership=c.execute(text('SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=:role)'),{'role':ROLE}).scalar_one()
            if flags or membership:raise ValueError('Existing runtime role has unexpected privileges')
        raw=c.connection.driver_connection
        with raw.cursor() as cur:cur.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(ROLE),sql.Literal(password)))
        c.exec_driver_sql('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        c.exec_driver_sql('GRANT USAGE ON SCHEMA public TO '+ROLE)
        c.exec_driver_sql('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM '+ROLE)
        for table in sorted(Base.metadata.tables):
            # Table names come only from declared code, never request input.
            c.exec_driver_sql(f'GRANT SELECT, INSERT, UPDATE ON TABLE public."{table}" TO {ROLE}')
        c.exec_driver_sql('GRANT SELECT ON TABLE public.alembic_version TO '+ROLE)
        for table in ('browser_sessions','recovery_tokens','auth_throttle_buckets'):
            c.exec_driver_sql(f'GRANT DELETE ON TABLE public."{table}" TO {ROLE}')
        c.exec_driver_sql('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO '+ROLE)
        c.exec_driver_sql('REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM '+ROLE)
        c.exec_driver_sql('REVOKE CREATE ON SCHEMA public FROM '+ROLE)
    return {'runtime_role':ROLE,'provisioned':True,'native_startup_check_required':True}
