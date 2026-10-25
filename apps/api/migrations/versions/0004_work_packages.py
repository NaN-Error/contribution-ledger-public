"""Work-package scope revisions, attribution snapshots and submission history.

Additive to 0003. No seeded data, budget approvals or credit issuance.
"""
from alembic import op, context
import sqlalchemy as sa

revision = "0004_work_packages"
down_revision = "0003_policies_budgets"
branch_labels = None
depends_on = None

IMMUTABLE_TABLES = ('work_package_revisions', 'work_package_participants', 'work_package_events', 'work_submissions')


def install_guards():
    dialect = op.get_bind().dialect.name
    if dialect == 'postgresql':
        op.execute("""CREATE FUNCTION reject_work_history_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Work history cannot be updated or deleted'; END;
        $$ LANGUAGE plpgsql""")
        for table in IMMUTABLE_TABLES:
            op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} '
                       'FOR EACH ROW EXECUTE FUNCTION reject_work_history_mutation()')
        op.execute("CREATE TRIGGER work_packages_no_delete BEFORE DELETE ON work_packages FOR EACH ROW EXECUTE FUNCTION reject_work_history_mutation()")
        op.execute("""CREATE FUNCTION protect_work_package_binding() RETURNS trigger AS $$
        BEGIN
          IF ROW(NEW.id,NEW.workspace_id,NEW.project_id,NEW.milestone_id,NEW.allocation_id,NEW.policy_id,NEW.created_by,NEW.created_at)
             IS DISTINCT FROM ROW(OLD.id,OLD.workspace_id,OLD.project_id,OLD.milestone_id,OLD.allocation_id,OLD.policy_id,OLD.created_by,OLD.created_at)
          THEN RAISE EXCEPTION 'Work-package binding cannot be changed'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER work_package_binding BEFORE UPDATE ON work_packages FOR EACH ROW EXECUTE FUNCTION protect_work_package_binding()')
    elif dialect == 'sqlite':
        for table in IMMUTABLE_TABLES:
            for action in ('UPDATE', 'DELETE'):
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable work history'); END")
        op.execute("CREATE TRIGGER work_packages_no_delete BEFORE DELETE ON work_packages BEGIN SELECT RAISE(ABORT, 'immutable work binding'); END")
        condition = ' OR '.join(f'NEW.{c} IS NOT OLD.{c}' for c in ('id','workspace_id','project_id','milestone_id','allocation_id','policy_id','created_by','created_at'))
        op.execute(f"CREATE TRIGGER work_package_binding BEFORE UPDATE ON work_packages WHEN {condition} BEGIN SELECT RAISE(ABORT, 'immutable work binding'); END")


def upgrade():
    # New schema only; applied migrations 0001–0003 remain unchanged.
    op.create_table('work_packages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('milestone_id', sa.Uuid(), nullable=False),
    sa.Column('allocation_id', sa.Uuid(), nullable=False),
    sa.Column('policy_id', sa.Uuid(), nullable=False),
    sa.Column('state', sa.String(length=24), server_default='draft', nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('scope_revision', sa.Integer(), server_default='1', nullable=False),
    sa.Column('approved_revision', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("state IN ('draft','budget_approved','in_progress','submitted','changes_requested','cancelled','completed')", name=op.f('ck_work_packages_work_package_state')),
    sa.CheckConstraint("state NOT IN ('budget_approved','in_progress','submitted','completed') OR (approved_revision IS NOT NULL AND approved_revision = scope_revision)", name=op.f('ck_work_packages_work_package_approved_state')),
    sa.CheckConstraint('approved_revision IS NULL OR approved_revision = scope_revision', name=op.f('ck_work_packages_work_package_approval_revision')),
    sa.CheckConstraint('version >= 1 AND scope_revision >= 1', name=op.f('ck_work_packages_work_package_versions')),
    sa.ForeignKeyConstraint(['workspace_id', 'created_by'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_work_package_author'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'milestone_id', 'allocation_id'], ['budget_allocations.workspace_id', 'budget_allocations.project_id', 'budget_allocations.milestone_id', 'budget_allocations.id'], name='fk_work_package_allocation'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'milestone_id'], ['milestones.workspace_id', 'milestones.project_id', 'milestones.id'], name='fk_work_package_milestone'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'policy_id'], ['policy_versions.workspace_id', 'policy_versions.project_id', 'policy_versions.id'], name='fk_work_package_policy'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id'], ['projects.workspace_id', 'projects.id'], name='fk_work_package_project'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_work_packages')),
    sa.UniqueConstraint('allocation_id', name='uq_work_package_allocation'),
    sa.UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_work_package_scope')
    )
    op.create_index(op.f('ix_work_packages_project_id'), 'work_packages', ['project_id'], unique=False)
    op.create_table('work_package_revisions',
    sa.Column('package_id', sa.Uuid(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('allocation_version', sa.Integer(), nullable=False),
    sa.Column('document', sa.JSON(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('number >= 1 AND allocation_version >= 1', name=op.f('ck_work_package_revisions_work_revision_versions')),
    sa.ForeignKeyConstraint(['workspace_id', 'created_by'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_work_revision_author'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id'], ['work_packages.workspace_id', 'work_packages.project_id', 'work_packages.id'], name='fk_work_revision_package'),
    sa.PrimaryKeyConstraint('package_id', 'number', name=op.f('pk_work_package_revisions')),
    sa.UniqueConstraint('workspace_id', 'project_id', 'package_id', 'number', name='uq_work_revision_scope')
    )
    op.create_table('work_package_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('package_id', sa.Uuid(), nullable=False),
    sa.Column('scope_revision', sa.Integer(), nullable=False),
    sa.Column('package_version', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('package_version >= 1', name=op.f('ck_work_package_events_work_event_version')),
    sa.ForeignKeyConstraint(['workspace_id', 'actor_id'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_work_event_actor'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id', 'scope_revision'], ['work_package_revisions.workspace_id', 'work_package_revisions.project_id', 'work_package_revisions.package_id', 'work_package_revisions.number'], name='fk_work_event_revision'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_work_package_events')),
    sa.UniqueConstraint('package_id', 'package_version', name='uq_work_event_version')
    )
    op.create_index(op.f('ix_work_package_events_package_id'), 'work_package_events', ['package_id'], unique=False)
    op.create_table('work_package_participants',
    sa.Column('package_id', sa.Uuid(), nullable=False),
    sa.Column('scope_revision', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("kind IN ('coordinator','intended')", name=op.f('ck_work_package_participants_work_participant_kind')),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id', 'scope_revision'], ['work_package_revisions.workspace_id', 'work_package_revisions.project_id', 'work_package_revisions.package_id', 'work_package_revisions.number'], name='fk_work_participant_revision'),
    sa.ForeignKeyConstraint(['workspace_id', 'user_id'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_work_participant_member'),
    sa.PrimaryKeyConstraint('package_id', 'scope_revision', 'user_id', 'kind', name=op.f('pk_work_package_participants'))
    )
    op.create_table('work_submissions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('package_id', sa.Uuid(), nullable=False),
    sa.Column('scope_revision', sa.Integer(), nullable=False),
    sa.Column('package_version', sa.Integer(), nullable=False),
    sa.Column('submitted_by', sa.Uuid(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('snapshot_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('package_version >= 1', name=op.f('ck_work_submissions_work_submission_version')),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id', 'scope_revision'], ['work_package_revisions.workspace_id', 'work_package_revisions.project_id', 'work_package_revisions.package_id', 'work_package_revisions.number'], name='fk_work_submission_revision'),
    sa.ForeignKeyConstraint(['workspace_id', 'submitted_by'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_work_submission_actor'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_work_submissions')),
    sa.UniqueConstraint('package_id', 'package_version', name='uq_work_submission_version')
    )
    op.create_index(op.f('ix_work_submissions_package_id'), 'work_submissions', ['package_id'], unique=False)

    install_guards()


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline phase-4 downgrade is refused; record emptiness cannot be verified.')
    for table in ('work_packages', *IMMUTABLE_TABLES):
        if op.get_bind().execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first():
            raise RuntimeError('Phase-4 records exist. Refusing destructive downgrade; restore a verified backup instead.')
    if op.get_bind().dialect.name == 'postgresql':
        for table in IMMUTABLE_TABLES:
            op.execute(f'DROP TRIGGER IF EXISTS {table}_immutable ON {table}')
        op.execute('DROP TRIGGER IF EXISTS work_packages_no_delete ON work_packages')
        op.execute('DROP TRIGGER IF EXISTS work_package_binding ON work_packages')
        op.execute('DROP FUNCTION IF EXISTS reject_work_history_mutation()')
        op.execute('DROP FUNCTION IF EXISTS protect_work_package_binding()')
    # New schema only; applied migrations 0001–0003 remain unchanged.
    op.drop_index(op.f('ix_work_submissions_package_id'), table_name='work_submissions')
    op.drop_table('work_submissions')
    op.drop_table('work_package_participants')
    op.drop_index(op.f('ix_work_package_events_package_id'), table_name='work_package_events')
    op.drop_table('work_package_events')
    op.drop_table('work_package_revisions')
    op.drop_index(op.f('ix_work_packages_project_id'), table_name='work_packages')
    op.drop_table('work_packages')

