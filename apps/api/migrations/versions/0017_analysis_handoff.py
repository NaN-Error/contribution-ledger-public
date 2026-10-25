"""Pin reviewed dashboard outcomes in the ordinary historical acceptance path."""
from alembic import op, context
import sqlalchemy as sa

revision = '0017_analysis_handoff'
down_revision = '0016_analysis_sharing'
branch_labels = depends_on = None
TABLES = ('analysis_source_claims', 'analysis_handoffs')


def scope_fk(name):
    return sa.ForeignKeyConstraint(['workspace_id', 'project_id'],
        ['projects.workspace_id', 'projects.id'], name=name)


def upgrade():
    if not context.is_offline_mode() and op.get_context().dialect.name == 'sqlite':
        c = op.get_bind()
        if not c.connection.driver_connection.in_transaction: c.exec_driver_sql('BEGIN')
    op.create_index('uq_analysis_report_scope', 'repository_analyses', ['workspace_id', 'project_id', 'id'], unique=True)
    op.create_table('analysis_handoffs', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), nullable=False), sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('report_id', sa.Uuid(), nullable=False), sa.Column('package_id', sa.Uuid(), nullable=False),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False), sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False), sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        scope_fk('fk_analysis_handoff_project'),
        sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'report_id'],
            ['repository_analyses.workspace_id', 'repository_analyses.project_id', 'repository_analyses.id'], name='fk_analysis_handoff_report'),
        sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id'],
            ['work_packages.workspace_id', 'work_packages.project_id', 'work_packages.id'], name='fk_analysis_handoff_package'),
        sa.UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_analysis_handoff_scope'),
        sa.UniqueConstraint('project_id', 'request_id', name='uq_analysis_handoff_request'),
        sa.UniqueConstraint('package_id', name='uq_analysis_handoff_package'))
    op.create_table('analysis_source_claims', sa.Column('project_id', sa.Uuid(), primary_key=True),
        sa.Column('entity_key', sa.String(64), primary_key=True), sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('handoff_id', sa.Uuid(), nullable=False), scope_fk('fk_analysis_claim_project'),
        sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'handoff_id'],
            ['analysis_handoffs.workspace_id', 'analysis_handoffs.project_id', 'analysis_handoffs.id'], name='fk_analysis_claim_handoff'))
    for table in TABLES:
        if op.get_context().dialect.name == 'postgresql':
            op.execute(f'CREATE TRIGGER {table}_preserved BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_analysis_history()')
            op.execute(f'CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION reject_analysis_history()')
            op.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC')
        else:
            for action in ('UPDATE', 'DELETE'):
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'preserved analysis handoff history'); END")


def downgrade():
    if not context.is_offline_mode():
        if any(op.get_bind().execute(sa.text(f'SELECT count(*) FROM {t}')).scalar_one() for t in TABLES):
            raise RuntimeError('Reviewed handoff history exists. Use a coordinated restore instead of discarding it.')
    for table in TABLES: op.drop_table(table)
    op.drop_index('uq_analysis_report_scope', table_name='repository_analyses')
