"""Add encrypted MFA factors and limited pre-authentication sessions.

No existing session is automatically marked MFA-verified. No factor is enrolled
by this migration. Earlier accounting, evidence and finance rows are unchanged.
"""
from alembic import op, context
import sqlalchemy as sa
revision = "0014_security_recovery"
down_revision = "0013_financial_distributions"
branch_labels = depends_on = None

def _begin_sqlite_ddl():
    # pysqlite legacy transaction control does not BEGIN for DDL/SELECT. Without
    # this, a later downgrade guard can roll back the revision but leave columns
    # dropped. Keep the whole migration chain inside the existing unit of work.
    if not context.is_offline_mode() and op.get_context().dialect.name == "sqlite":
        connection=op.get_bind()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")

def upgrade():
    _begin_sqlite_ddl()
    op.create_table("authenticators",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("encrypted_secret", sa.String(512)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("must_enroll", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enrollment_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_counter", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("recovery_hashes", sa.JSON(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False))
    if op.get_context().dialect.name == "sqlite":
        # A batch table copy would drop a parent referenced by captured GitHub
        # authorization flows. Add nullable fields in place with FK checks on.
        op.execute("ALTER TABLE browser_sessions ADD COLUMN pending_user_id CHAR(32) REFERENCES users(id)")
        op.execute("ALTER TABLE browser_sessions ADD COLUMN mfa_verified_at DATETIME")
    else:
        op.add_column("browser_sessions",sa.Column("pending_user_id",sa.Uuid()))
        op.create_foreign_key("fk_session_pending_user", "browser_sessions", "users", ["pending_user_id"], ["id"])
        op.add_column("browser_sessions",sa.Column("mfa_verified_at",sa.DateTime(timezone=True)))
    op.create_index("ix_browser_sessions_pending_user_id", "browser_sessions", ["pending_user_id"])

def downgrade():
    _begin_sqlite_ddl()
    if not context.is_offline_mode():
        count = op.get_bind().execute(sa.text("SELECT count(*) FROM authenticators")).scalar_one()
        if count:
            raise RuntimeError("MFA records exist. Restore a coordinated backup instead of deleting factors.")
    if op.get_context().dialect.name == "sqlite":
        # Modern SQLite supports in-place DROP COLUMN. Refuse an older engine
        # rather than turning off foreign keys or dropping referenced sessions.
        version=tuple(int(v) for v in op.get_bind().execute(sa.text("SELECT sqlite_version()")).scalar_one().split('.'))
        if version < (3,35,0):raise RuntimeError("Use restore; this SQLite version cannot safely remove the new columns")
        op.drop_index("ix_browser_sessions_pending_user_id",table_name="browser_sessions")
        op.execute("ALTER TABLE browser_sessions DROP COLUMN pending_user_id")
        op.execute("ALTER TABLE browser_sessions DROP COLUMN mfa_verified_at")
    else:
        op.drop_index("ix_browser_sessions_pending_user_id",table_name="browser_sessions")
        op.drop_constraint("fk_session_pending_user", "browser_sessions", type_="foreignkey")
        op.drop_column("browser_sessions","pending_user_id")
        op.drop_column("browser_sessions","mfa_verified_at")
    op.drop_table("authenticators")
