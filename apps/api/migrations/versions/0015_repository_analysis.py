"""Add draft repository reports without changing credit or financial history."""
from alembic import op, context
import sqlalchemy as sa

revision = '0015_repository_analysis'
down_revision = '0014_security_recovery'
branch_labels = depends_on = None
TABLES = ('analysis_draft_revisions', 'analysis_drafts', 'repository_analyses')


def scope_fk(name):
    return sa.ForeignKeyConstraint(['workspace_id','project_id'], ['projects.workspace_id','projects.id'], name=name)


def upgrade():
    if not context.is_offline_mode() and op.get_context().dialect.name == 'sqlite':
        c = op.get_bind()
        if not c.connection.driver_connection.in_transaction: c.exec_driver_sql('BEGIN')
    op.create_table('repository_analyses',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('definition', sa.JSON(), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('progress', sa.JSON(), nullable=False),
        sa.Column('report', sa.JSON()),
        sa.Column('error_code', sa.String(100)),
        sa.Column('lease_token', sa.Uuid()),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('retry_after', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        scope_fk('fk_analysis_project'),
        sa.UniqueConstraint('project_id','request_id',name='uq_analysis_request'),
        sa.CheckConstraint("state IN ('queued','running','completed','failed','cancelled')",name='analysis_state'),
        sa.CheckConstraint('version >= 1', name='analysis_version'))
    op.create_index('ix_repository_analyses_project_id', 'repository_analyses', ['project_id'])
    op.create_table('analysis_drafts',
        sa.Column('project_id', sa.Uuid(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        scope_fk('fk_analysis_draft_project'), sa.CheckConstraint('version >= 1',name='analysis_draft_version'))
    op.create_table('analysis_draft_revisions',
        sa.Column('project_id', sa.Uuid(), primary_key=True),
        sa.Column('version', sa.Integer(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        scope_fk('fk_analysis_revision_project'),
        sa.UniqueConstraint('project_id','request_id',name='uq_analysis_revision_request'))
    native = op.get_context().dialect.name == 'postgresql'
    if native:
        op.execute("""CREATE FUNCTION reject_analysis_history() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'preserved analysis history'; END; $$""")
    for table in TABLES:
        actions = ('UPDATE','DELETE') if table == 'analysis_draft_revisions' else ('DELETE',)
        if native:
            op.execute(f'CREATE TRIGGER {table}_preserved BEFORE {" OR ".join(actions)} ON {table} FOR EACH ROW EXECUTE FUNCTION reject_analysis_history()')
            op.execute(f'CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION reject_analysis_history()')
            op.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC')
        else:
            for action in actions:
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'preserved analysis history'); END")
    columns = ['id','workspace_id','project_id','created_by','request_id','request_hash','definition','created_at']
    comparison = [f'NEW.{c}::text IS DISTINCT FROM OLD.{c}::text' if native else f'NEW.{c} IS NOT OLD.{c}' for c in columns]
    condition = "OLD.state = 'completed' OR " + ' OR '.join(comparison)
    if native:
        op.execute(f"""CREATE FUNCTION guard_analysis_report() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF {condition} THEN RAISE EXCEPTION 'immutable analysis report'; END IF; RETURN NEW; END; $$""")
        op.execute('CREATE TRIGGER repository_analyses_identity BEFORE UPDATE ON repository_analyses FOR EACH ROW EXECUTE FUNCTION guard_analysis_report()')
    else:
        op.execute(f"CREATE TRIGGER repository_analyses_identity BEFORE UPDATE ON repository_analyses WHEN {condition} BEGIN SELECT RAISE(ABORT,'immutable analysis report'); END")
    condition = ('NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.project_id IS DISTINCT FROM OLD.project_id'
        if native else 'NEW.workspace_id IS NOT OLD.workspace_id OR NEW.project_id IS NOT OLD.project_id')
    if native:
        op.execute(f"""CREATE FUNCTION guard_analysis_draft() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF {condition} THEN RAISE EXCEPTION 'immutable analysis scope'; END IF; RETURN NEW; END; $$""")
        op.execute('CREATE TRIGGER analysis_drafts_identity BEFORE UPDATE ON analysis_drafts FOR EACH ROW EXECUTE FUNCTION guard_analysis_draft()')
    else:
        op.execute(f"CREATE TRIGGER analysis_drafts_identity BEFORE UPDATE ON analysis_drafts WHEN {condition} BEGIN SELECT RAISE(ABORT,'immutable analysis scope'); END")


def downgrade():
    if not context.is_offline_mode():
        if any(op.get_bind().execute(sa.text(f'SELECT count(*) FROM {t}')).scalar_one() for t in TABLES):
            raise RuntimeError('Analysis history exists. Use a coordinated restore instead of discarding it.')
    for table in TABLES: op.drop_table(table)
    if op.get_context().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION guard_analysis_draft()')
        op.execute('DROP FUNCTION guard_analysis_report()')
        op.execute('DROP FUNCTION reject_analysis_history()')
