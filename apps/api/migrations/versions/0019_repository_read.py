"""Project/owner-scoped local GitHub read connections; no plaintext token."""
from alembic import op
import sqlalchemy as sa

revision='0019_repository_read'
down_revision='0018_desktop_profile'
branch_labels=depends_on=None


def upgrade():
    op.create_table('repository_read_connections',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('workspace_id',sa.Uuid(),nullable=False),
        sa.Column('project_id',sa.Uuid(),nullable=False),
        sa.Column('owner_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('method',sa.String(10),nullable=False),
        sa.Column('username',sa.String(39),nullable=False),
        sa.Column('credential_ref',sa.String(36)),
        sa.Column('repository_urls',sa.JSON(),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['workspace_id','project_id'],['projects.workspace_id','projects.id'],name='fk_repository_read_project'),
        sa.UniqueConstraint('project_id','owner_id',name='uq_repository_read_owner'),
        sa.CheckConstraint("method IN ('token','cli')",name='repository_read_method'),
        sa.CheckConstraint('version >= 1',name='repository_read_version'))
    if op.get_context().dialect.name=='postgresql':
        op.execute('REVOKE ALL ON TABLE repository_read_connections FROM PUBLIC')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM repository_read_connections')).scalar_one():
        raise RuntimeError('Connections exist. Preserve them and use coordinated restore.')
    op.drop_table('repository_read_connections')
