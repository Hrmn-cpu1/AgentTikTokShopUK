"""Add worker heartbeat and monotonic lease fencing identity."""
from alembic import op
import sqlalchemy as sa

revision = "0011_growth_worker_fencing"
down_revision = "0010_durable_media_artifacts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("growth_jobs", sa.Column("lease_acquired_at", sa.DateTime(timezone=True)))
    op.add_column("growth_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column("growth_jobs", sa.Column("lease_generation", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("growth_jobs", sa.Column("lease_attempt_id", sa.String(36)))
    op.add_column("growth_jobs", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("growth_jobs", "revision")
    op.drop_column("growth_jobs", "lease_attempt_id")
    op.drop_column("growth_jobs", "lease_generation")
    op.drop_column("growth_jobs", "heartbeat_at")
    op.drop_column("growth_jobs", "lease_acquired_at")
