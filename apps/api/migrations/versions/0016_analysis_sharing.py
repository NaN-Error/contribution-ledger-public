"""Preserve reviewed report disclosures and their separate revocations."""
from alembic import op, context
import sqlalchemy as sa

revision = '0016_analysis_sharing'
down_revision = '0015_repository_analysis'
branch_labels = depends_on = None
TABLES = ('analysis_publication_revocations', 'analysis_publications')


def scope_fk(name):
    return sa.ForeignKeyConstraint(['workspace_id', 'project_id'],
        ['projects.workspace_id', 'projects.id'], name=name)


def common():
    return [sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade():
    if not context.is_offline_mode() and op.get_context().dialect.name == 'sqlite':
        c = op.get_bind()
        if not c.connection.driver_connection.in_transaction: c.exec_driver_sql('BEGIN')
    op.create_table('analysis_publications', sa.Column('id', sa.Uuid(), primary_key=True),
        *common(), sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        scope_fk('fk_analysis_publication_project'),
        sa.UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_analysis_publication_scope'),
        sa.UniqueConstraint('project_id', 'request_id', name='uq_analysis_publication_request'))
    op.create_table('analysis_publication_revocations', sa.Column('publication_id', sa.Uuid(), primary_key=True),
        *common(), scope_fk('fk_analysis_revocation_project'),
        sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'publication_id'],
            ['analysis_publications.workspace_id', 'analysis_publications.project_id', 'analysis_publications.id'],
            name='fk_analysis_revocation_publication'),
        sa.UniqueConstraint('project_id', 'request_id', name='uq_analysis_revocation_request'))
    native = op.get_context().dialect.name == 'postgresql'
    for table in TABLES:
        if native:
            op.execute(f'CREATE TRIGGER {table}_preserved BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_analysis_history()')
            op.execute(f'CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION reject_analysis_history()')
            op.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC')
        else:
            for action in ('UPDATE', 'DELETE'):
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'preserved analysis sharing history'); END")


def downgrade():
    if not context.is_offline_mode():
        if any(op.get_bind().execute(sa.text(f'SELECT count(*) FROM {t}')).scalar_one() for t in TABLES):
            raise RuntimeError('Shared report history exists. Use a coordinated restore instead of discarding it.')
    for table in TABLES: op.drop_table(table)
