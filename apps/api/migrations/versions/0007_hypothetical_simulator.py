"""Separate saved non-payable examples; no account or financial data is seeded."""
from alembic import op, context
import sqlalchemy as sa

revision = '0007_hypothetical_simulator'
down_revision = '0006_human_credit'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('simulation_scenarios',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('source_policy_id', sa.Uuid(), nullable=False),
        sa.Column('calculation_policy_id', sa.Uuid(), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('snapshot_hash', sa.String(64), nullable=False),
        sa.Column('record_hash', sa.String(64), nullable=False),
        sa.Column('record', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id', 'project_id'], ['projects.workspace_id', 'projects.id'], name='fk_simulation_project'),
        sa.ForeignKeyConstraint(['workspace_id', 'created_by'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_simulation_author'),
        sa.ForeignKeyConstraint(['workspace_id','project_id','source_policy_id'], ['policy_versions.workspace_id','policy_versions.project_id','policy_versions.id'], name='fk_simulation_source_policy'),
        sa.ForeignKeyConstraint(['workspace_id','project_id','calculation_policy_id'], ['policy_versions.workspace_id','policy_versions.project_id','policy_versions.id'], name='fk_simulation_calculation_policy'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_simulation_scenarios')),
        sa.UniqueConstraint('workspace_id','project_id','request_id', name='uq_simulation_request'))
    op.create_index(op.f('ix_simulation_scenarios_project_id'), 'simulation_scenarios', ['project_id'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""CREATE FUNCTION reject_simulation_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'immutable hypothetical scenario'; END; $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER simulation_scenarios_immutable BEFORE UPDATE OR DELETE ON simulation_scenarios FOR EACH ROW EXECUTE FUNCTION reject_simulation_mutation()')
        op.execute('CREATE TRIGGER simulation_scenarios_no_truncate BEFORE TRUNCATE ON simulation_scenarios FOR EACH STATEMENT EXECUTE FUNCTION reject_simulation_mutation()')
        op.execute('REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE simulation_scenarios FROM PUBLIC')
    else:
        for action in ('UPDATE', 'DELETE'):
            op.execute(f"CREATE TRIGGER simulation_scenarios_no_{action.lower()} BEFORE {action} ON simulation_scenarios BEGIN SELECT RAISE(ABORT, 'immutable hypothetical scenario'); END")


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline downgrade cannot verify that saved scenarios are empty.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM simulation_scenarios LIMIT 1')).first():
        raise RuntimeError('Saved scenarios exist; refusing destructive downgrade. Restore a verified backup instead.')
    op.drop_table('simulation_scenarios')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION IF EXISTS reject_simulation_mutation()')
