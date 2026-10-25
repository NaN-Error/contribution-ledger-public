"""Explicit local AI storage setup and narrowly privileged PostgreSQL worker provisioning."""
import argparse
import os
import re
from app.core.config import get_settings
from app.db.migration import expected_revision
from app.security.secrets.encrypted import initialize
from app.security.secrets.store import SecretUnavailable

ROLE='contribution_ledger_ai_worker'
ROLE_MARKER='Contribution ledger phase10 restricted AI worker v1'
READ_TABLES=('workspaces','workspace_memberships','projects','project_memberships','alembic_version',
 'ai_connections','ai_models','ai_jobs','ai_usage_buckets','ai_prices','ai_operation_events','ai_profiles','ai_profile_approvals','ai_usage_resolutions',
 'ai_review_packets','ai_review_plans','ai_review_grants','ai_review_revocations','ai_review_results')
WORK_TABLES=('ai_models','ai_jobs','ai_usage_buckets')
CONNECTION_COLUMNS=('next_refresh_at','last_catalog_at','last_error','retry_not_before')


def provision(settings,password):
    """Operator DB only. No password, key, connection string or raw SQL is printed."""
    if not re.fullmatch(r'[a-f0-9]{64}',password or ''):
        raise ValueError('A separately generated 64-hex-character AI worker database password is required.')
    # psycopg is a runtime dependency, imported only for a real PostgreSQL operation.
    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import make_url
    url=make_url(settings.database_url())
    with psycopg.connect(host=url.host,port=url.port,dbname=url.database,user=url.username,password=url.password) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT version_num FROM alembic_version')
            if cur.fetchone()[0]!=expected_revision():
                raise ValueError('Apply the current application migrations before provisioning the worker role.')
            cur.execute("SELECT oid,rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls,shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s",(ROLE,))
            existing=cur.fetchone()
            if existing:
                oid,*flags,marker=existing
                if any(flags) or marker!=ROLE_MARKER:raise ValueError('An unrelated or privileged role uses the reserved AI worker name; nothing was changed.')
                cur.execute('SELECT 1 FROM pg_auth_members WHERE member=%s OR roleid=%s LIMIT 1',(oid,oid))
                if cur.fetchone():raise ValueError('AI worker role membership requires an operator review.')
                cur.execute('SELECT 1 FROM pg_class WHERE relowner=%s UNION ALL SELECT 1 FROM pg_proc WHERE proowner=%s UNION ALL SELECT 1 FROM pg_namespace WHERE nspowner=%s UNION ALL SELECT 1 FROM pg_database WHERE datdba=%s LIMIT 1',(oid,oid,oid,oid))
                if cur.fetchone():raise ValueError('AI worker unexpectedly owns database objects; refusing to adopt the role.')
            else:
                cur.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS').format(sql.Identifier(ROLE)))
                cur.execute(sql.SQL('COMMENT ON ROLE {} IS {}').format(sql.Identifier(ROLE),sql.Literal(ROLE_MARKER)))
            cur.execute(sql.SQL('ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(ROLE),sql.Literal(password)))
            cur.execute(sql.SQL('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}').format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {}').format(sql.Identifier(ROLE)))
            cur.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public'")
            for table,column in cur.fetchall():
                cur.execute(sql.SQL('REVOKE ALL PRIVILEGES ({}) ON TABLE public.{} FROM {}').format(sql.Identifier(column),sql.Identifier(table),sql.Identifier(ROLE)))
            cur.execute(sql.SQL('REVOKE CREATE ON SCHEMA public FROM {}').format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(url.database),sql.Identifier(ROLE)))
            cur.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(ROLE)))
            for table in READ_TABLES:
                cur.execute(sql.SQL('GRANT SELECT ON TABLE public.{} TO {}').format(sql.Identifier(table),sql.Identifier(ROLE)))
            # The authorization JOIN needs only these two columns, not password hashes.
            cur.execute(sql.SQL('GRANT SELECT (id,is_active) ON TABLE public.users TO {}').format(sql.Identifier(ROLE)))
            for table in WORK_TABLES:
                cur.execute(sql.SQL('GRANT INSERT, UPDATE ON TABLE public.{} TO {}').format(sql.Identifier(table),sql.Identifier(ROLE)))
            cur.execute(sql.SQL('GRANT INSERT ON TABLE public.ai_operation_events, public.ai_review_results TO {}').format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL('GRANT EXECUTE ON FUNCTION public.cl_ai_packet_current(uuid) TO {}').format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL('GRANT UPDATE ({}) ON TABLE public.ai_connections TO {}').format(
                sql.SQL(',').join(map(sql.Identifier,CONNECTION_COLUMNS)),sql.Identifier(ROLE)))
            cur.execute(sql.SQL('GRANT EXECUTE ON FUNCTION public.cl_ai_lock_workspace(uuid) TO {}').format(sql.Identifier(ROLE)))
            # Fail closed if PUBLIC/custom grants bypass the deliberately narrow grants.
            cur.execute("SELECT has_schema_privilege(%s,'public','CREATE')",(ROLE,))
            if cur.fetchone()[0]:raise ValueError('PUBLIC/custom schema privileges permit worker object creation; harden the schema before enabling AI.')
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            tables=[v[0] for v in cur.fetchall()]
            for table in tables:
                cur.execute('SELECT has_table_privilege(%s,%s,\'SELECT\'),has_table_privilege(%s,%s,\'INSERT\'),has_table_privilege(%s,%s,\'UPDATE\'),has_table_privilege(%s,%s,\'DELETE\'),has_table_privilege(%s,%s,\'TRUNCATE\')',(ROLE,'public.'+table)*5)
                read,insert,update,delete,truncate=cur.fetchone()
                if (read and table not in READ_TABLES) or (insert and table not in (*WORK_TABLES,'ai_operation_events','ai_review_results')) or (update and table not in WORK_TABLES) or delete or truncate:
                    raise ValueError('Unexpected effective worker table privileges; provisioning was rolled back.')
            for table in tables:
                cur.execute("SELECT has_any_column_privilege(%s,%s,'SELECT'),has_any_column_privilege(%s,%s,'INSERT'),has_any_column_privilege(%s,%s,'UPDATE')",(ROLE,'public.'+table)*3)
                read,insert,update=cur.fetchone()
                if (read and table not in (*READ_TABLES,'users')) or (insert and table not in (*WORK_TABLES,'ai_operation_events','ai_review_results')) or (update and table not in (*WORK_TABLES,'ai_connections')):
                    raise ValueError('Unexpected effective worker column privileges; provisioning was rolled back.')
            cur.execute("SELECT attname FROM pg_attribute WHERE attrelid='public.ai_connections'::regclass AND attnum>0 AND NOT attisdropped")
            for (column,) in cur.fetchall():
                if column not in CONNECTION_COLUMNS:
                    cur.execute("SELECT has_column_privilege(%s,'public.ai_connections',%s,'UPDATE')",(ROLE,column))
                    if cur.fetchone()[0]:raise ValueError('Worker can change payer authorization; provisioning was rolled back.')
            cur.execute("SELECT attname FROM pg_attribute WHERE attrelid='public.users'::regclass AND attnum>0 AND NOT attisdropped")
            for (column,) in cur.fetchall():
                if column not in {'id','is_active'}:
                    cur.execute("SELECT has_column_privilege(%s,'public.users',%s,'SELECT')",(ROLE,column))
                    if cur.fetchone()[0]:raise ValueError('The worker can read unrelated account fields; provisioning was rolled back.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['initialize','provision-worker']);p.add_argument('--confirm',required=True)
    a=p.parse_args();s=get_settings();s.require_local_foundation()
    try:
        if a.action=='initialize':
            if a.confirm!='INITIALIZE_AI_STORAGE':raise ValueError('Explicit AI storage confirmation required.')
            initialize(s.ai_master_key_file,s.ai_credential_root)
            print('AI credential storage initialized or verified; existing master key preserved. Protect both separate volumes and backups.')
        else:
            if a.confirm!='PROVISION_AI_WORKER':raise ValueError('Explicit AI worker provisioning confirmation required.')
            provision(s,os.environ.get('CL_AI_DB_PASSWORD',''))
            print('Restricted AI worker role provisioned. No contribution, evidence, financial or account-write privilege was granted.')
    except (ValueError,SecretUnavailable) as exc:
        # ValueErrors here are fixed local validation messages, not remote exceptions.
        p.exit(1,('Protected credential storage is unavailable.' if isinstance(exc,SecretUnavailable) else str(exc))+'\n')
    except Exception:
        p.exit(1,'AI operator setup failed; inspect database readiness and local configuration. No raw credential or connection details were printed.\n')
if __name__=='__main__':main()
