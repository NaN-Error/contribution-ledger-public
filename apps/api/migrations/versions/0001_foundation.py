"""Create the synthetic development marker; no user/contribution tables yet."""
from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("development_markers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_development_markers"),
        sa.UniqueConstraint("name", name="uq_development_markers_name"))


def downgrade() -> None:
    # Operator-only reversal. Never called by application startup or reset-development.
    op.drop_table("development_markers")
