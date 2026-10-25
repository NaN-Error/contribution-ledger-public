"""Opt-in personal desktop identity and bounded one-use launch ticket."""
from alembic import op
import sqlalchemy as sa

revision = '0018_desktop_profile'
down_revision = '0017_analysis_handoff'
branch_labels = depends_on = None


def upgrade():
    op.create_table('desktop_profiles', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('ticket_hash', sa.String(64)), sa.Column('ticket_expires_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('id = 1', name='desktop_singleton'))
    if op.get_context().dialect.name == 'postgresql':
        op.execute('REVOKE ALL ON TABLE desktop_profiles FROM PUBLIC')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM desktop_profiles')).scalar_one():
        raise RuntimeError('Personal profile exists. Preserve it and use a coordinated restore.')
    op.drop_table('desktop_profiles')
