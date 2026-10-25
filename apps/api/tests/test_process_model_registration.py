"""Do not let pytest's shared imports mask cold-start worker failures."""
import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('entrypoint', ['app.workers.ai', 'app.auth.operator'])
def test_independent_process_resolves_all_model_foreign_keys(entrypoint):
    code = '''
import importlib
import sys
importlib.import_module(sys.argv[1])
from app.core.config import Settings
from app.db.session import Database
from app.db.base import Base
database = Database(Settings(db_password='synthetic-no-connection'))
assert 'ai_review_plans' in Base.metadata.tables
for table in Base.metadata.tables.values():
    for foreign_key in table.foreign_keys:
        assert foreign_key.column.table.name in Base.metadata.tables
assert 'engine' not in database.__dict__
'''
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('CL_')}
    result = subprocess.run([sys.executable, '-c', code, entrypoint],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
