"""Historical reconstruction and preserved opening-balance snapshots.

No historical source becomes accepted credit in this migration. Existing records
and all prior migrations are unchanged. Generated DDL reviewed with scoped FKs.
"""
from alembic import op, context
import sqlalchemy as sa

revision = '0012_historical_reconstruction'
down_revision = '0011_ai_evidence_review'
branch_labels = None
depends_on = None

TABLES = ('reconstruction_source_claims','reconstruction_missing_claims',
          'reconstruction_candidates','opening_balance_snapshots',
          'reconstruction_events','reconstruction_batches')
SEALED = ('reconstruction_events','opening_balance_snapshots')
IDENTITIES = {
    'reconstruction_batches': ['id','workspace_id','project_id','milestone_id','policy_id','created_by','request_id','request_hash','definition','created_at'],
    'reconstruction_candidates': ['id','workspace_id','project_id','batch_id','created_by','created_at'],
    'reconstruction_source_claims': ['id','workspace_id','project_id','batch_id','source_id','entity_key','created_at'],
    'reconstruction_missing_claims': ['id','workspace_id','project_id','batch_id','created_by','request_id','request_hash','document','created_at'],
}


def guards():
    native=op.get_bind().dialect.name=='postgresql'
    if native:
        op.execute("""CREATE FUNCTION reject_reconstruction_history() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'preserved reconstruction history'; END; $$ LANGUAGE plpgsql""")
    for table in TABLES:
        if native:
            actions='UPDATE OR DELETE' if table in SEALED else 'DELETE'
            op.execute(f'CREATE TRIGGER {table}_preserved BEFORE {actions} ON {table} FOR EACH ROW EXECUTE FUNCTION reject_reconstruction_history()')
            op.execute(f'CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION reject_reconstruction_history()')
            op.execute(f'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE {table} FROM PUBLIC')
        else:
            for action in (('UPDATE','DELETE') if table in SEALED else ('DELETE',)):
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'preserved reconstruction history'); END")
    for table,columns in IDENTITIES.items():
        clauses=[f'NEW.{c}::text IS DISTINCT FROM OLD.{c}::text' if native else f'NEW.{c} IS NOT OLD.{c}' for c in columns]
        if table=='reconstruction_candidates':
            clauses.append("OLD.package_id IS NOT NULL AND NEW.package_id IS DISTINCT FROM OLD.package_id" if native else "OLD.package_id IS NOT NULL AND NEW.package_id IS NOT OLD.package_id")
        if table=='reconstruction_batches':clauses.append("OLD.state = 'frozen'")
        condition=' OR '.join('('+x+')' for x in clauses)
        if native:
            op.execute(f"""CREATE FUNCTION guard_{table}() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF {condition} THEN RAISE EXCEPTION 'immutable reconstruction identity'; END IF; RETURN NEW; END; $$""")
            op.execute(f'CREATE TRIGGER {table}_identity BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_{table}()')
        else:
            op.execute(f"CREATE TRIGGER {table}_identity BEFORE UPDATE ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT,'immutable reconstruction identity'); END")


def upgrade():
# Reviewed additive DDL; historical migrations are intentionally unchanged.
    op.create_table('reconstruction_batches',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('milestone_id', sa.Uuid(), nullable=False),
    sa.Column('policy_id', sa.Uuid(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('definition', sa.JSON(), nullable=False),
    sa.Column('state', sa.String(length=16), server_default='draft', nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("state IN ('draft','approved','frozen')", name=op.f('ck_reconstruction_batches_reconstruction_state')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_reconstruction_batches_reconstruction_version')),
    sa.ForeignKeyConstraint(['workspace_id', 'created_by'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_reconstruction_author'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'milestone_id'], ['milestones.workspace_id', 'milestones.project_id', 'milestones.id'], name='fk_reconstruction_milestone'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'policy_id'], ['policy_versions.workspace_id', 'policy_versions.project_id', 'policy_versions.id'], name='fk_reconstruction_policy'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id'], ['projects.workspace_id', 'projects.id'], name='fk_reconstruction_project'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reconstruction_batches')),
    sa.UniqueConstraint('milestone_id', name='uq_reconstruction_milestone'),
    sa.UniqueConstraint('project_id', 'created_by', 'request_id', name='uq_reconstruction_request'),
    sa.UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_reconstruction_scope')
    )
    op.create_index(op.f('ix_reconstruction_batches_project_id'), 'reconstruction_batches', ['project_id'], unique=False)
    op.create_table('opening_balance_snapshots',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('batch_id', sa.Uuid(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('record', sa.JSON(), nullable=False),
    sa.Column('record_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id', 'created_by'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_opening_snapshot_actor'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'batch_id'], ['reconstruction_batches.workspace_id', 'reconstruction_batches.project_id', 'reconstruction_batches.id'], name='fk_opening_snapshot_batch'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_opening_balance_snapshots')),
    sa.UniqueConstraint('batch_id', name='uq_opening_snapshot_batch')
    )
    op.create_index(op.f('ix_opening_balance_snapshots_project_id'), 'opening_balance_snapshots', ['project_id'], unique=False)
    op.create_table('reconstruction_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('batch_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=False),
    sa.Column('command_hash', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('record', sa.JSON(), nullable=False),
    sa.Column('record_hash', sa.String(length=64), nullable=False),
    sa.Column('previous_hash', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('version >= 1', name=op.f('ck_reconstruction_events_reconstruction_event_version')),
    sa.ForeignKeyConstraint(['workspace_id', 'actor_id'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_reconstruction_event_actor'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'batch_id'], ['reconstruction_batches.workspace_id', 'reconstruction_batches.project_id', 'reconstruction_batches.id'], name='fk_reconstruction_event_batch'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reconstruction_events')),
    sa.UniqueConstraint('batch_id', 'version', name='uq_reconstruction_event_version'),
    sa.UniqueConstraint('project_id', 'actor_id', 'request_id', name='uq_reconstruction_event_request')
    )
    op.create_index(op.f('ix_reconstruction_events_batch_id'), 'reconstruction_events', ['batch_id'], unique=False)
    op.create_index(op.f('ix_reconstruction_events_project_id'), 'reconstruction_events', ['project_id'], unique=False)
    op.create_table('reconstruction_candidates',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('batch_id', sa.Uuid(), nullable=False),
    sa.Column('package_id', sa.Uuid(), nullable=True),
    sa.Column('state', sa.String(length=16), server_default='draft', nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('document', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("state IN ('draft','linked','rejected','superseded')", name=op.f('ck_reconstruction_candidates_candidate_state')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_reconstruction_candidates_candidate_version')),
    sa.ForeignKeyConstraint(['workspace_id', 'created_by'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_candidate_author'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'batch_id'], ['reconstruction_batches.workspace_id', 'reconstruction_batches.project_id', 'reconstruction_batches.id'], name='fk_candidate_batch'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id'], ['work_packages.workspace_id', 'work_packages.project_id', 'work_packages.id'], name='fk_candidate_package'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reconstruction_candidates')),
    sa.UniqueConstraint('package_id', name='uq_candidate_package'),
    sa.UniqueConstraint('workspace_id', 'project_id', 'batch_id', 'id', name='uq_candidate_scope')
    )
    op.create_index(op.f('ix_reconstruction_candidates_batch_id'), 'reconstruction_candidates', ['batch_id'], unique=False)
    op.create_index(op.f('ix_reconstruction_candidates_project_id'), 'reconstruction_candidates', ['project_id'], unique=False)
    op.create_table('reconstruction_missing_claims',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('batch_id', sa.Uuid(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('document', sa.JSON(), nullable=False),
    sa.Column('state', sa.String(length=16), server_default='open', nullable=False),
    sa.Column('candidate_id', sa.Uuid(), nullable=True),
    sa.Column('resolution_reason', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("state IN ('open','included','declined')", name=op.f('ck_reconstruction_missing_claims_missing_claim_state')),
    sa.ForeignKeyConstraint(['workspace_id', 'created_by'], ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name='fk_missing_claim_author'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'batch_id', 'candidate_id'], ['reconstruction_candidates.workspace_id', 'reconstruction_candidates.project_id', 'reconstruction_candidates.batch_id', 'reconstruction_candidates.id'], name='fk_missing_claim_candidate'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'batch_id'], ['reconstruction_batches.workspace_id', 'reconstruction_batches.project_id', 'reconstruction_batches.id'], name='fk_missing_claim_batch'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reconstruction_missing_claims')),
    sa.UniqueConstraint('project_id', 'created_by', 'request_id', name='uq_missing_claim_request')
    )
    op.create_index(op.f('ix_reconstruction_missing_claims_project_id'), 'reconstruction_missing_claims', ['project_id'], unique=False)
    op.create_table('reconstruction_source_claims',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('batch_id', sa.Uuid(), nullable=False),
    sa.Column('candidate_id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('entity_key', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'batch_id', 'candidate_id'], ['reconstruction_candidates.workspace_id', 'reconstruction_candidates.project_id', 'reconstruction_candidates.batch_id', 'reconstruction_candidates.id'], name='fk_source_claim_candidate'),
    sa.ForeignKeyConstraint(['workspace_id', 'project_id', 'source_id'], ['github_source_versions.workspace_id', 'github_source_versions.project_id', 'github_source_versions.id'], name='fk_source_claim_source'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reconstruction_source_claims')),
    sa.UniqueConstraint('project_id', 'entity_key', name='uq_reconstruction_entity')
    )
    op.create_index(op.f('ix_reconstruction_source_claims_candidate_id'), 'reconstruction_source_claims', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_reconstruction_source_claims_project_id'), 'reconstruction_source_claims', ['project_id'], unique=False)
    # ### end Alembic commands ###
    guards()


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline downgrade cannot verify empty reconstruction history.')
    for table in TABLES:
        if op.get_bind().execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first():
            raise RuntimeError('Reconstruction history exists; refusing destructive downgrade. Restore a verified backup instead.')
    for table in TABLES:op.drop_table(table)
    if op.get_bind().dialect.name=='postgresql':
        for table in IDENTITIES:op.execute(f'DROP FUNCTION IF EXISTS guard_{table}()')
        op.execute('DROP FUNCTION IF EXISTS reject_reconstruction_history()')
