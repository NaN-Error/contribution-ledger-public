"""Create the dedicated personal database only if absent. Never reset it."""
import os
import psycopg
from psycopg import sql

assert os.environ['CL_DB_NAME'] == 'contribution_ledger_desktop'
with psycopg.connect(host='127.0.0.1',port=int(os.environ['CL_DB_PORT']),dbname='postgres',
    user=os.environ['CL_DB_USER'],password=os.environ['CL_DB_PASSWORD'],autocommit=True,connect_timeout=5) as connection:
    name=os.environ['CL_DB_NAME']
    if not connection.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
