"""Create the launcher-owned practice database only when absent; never reset it."""
import os
import psycopg
from psycopg import sql

env = os.environ
with psycopg.connect(host=env['CL_DB_HOST'], port=env['CL_DB_PORT'],
                     user=env['CL_DB_USER'], password=env['CL_DB_PASSWORD'],
                     dbname='postgres', autocommit=True, connect_timeout=5) as connection:
    name = env['CL_DB_NAME']
    if name != 'contribution_ledger_practice':
        raise RuntimeError('Only the dedicated practice database is allowed.')
    if not connection.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
print('Practice database exists; saved contents retained.')
