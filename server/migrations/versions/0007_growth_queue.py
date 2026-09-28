"""Add durable growth worker queue."""
from alembic import op
import sqlalchemy as sa

revision = "0007_growth_queue"
down_revision = "0006_growth_engine"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "growth_jobs",
        sa.Column("job_id", sa.String(100), primary_key=True),
        sa.Column("creative_id", sa.String(100), sa.ForeignKey("growth_creatives.creative_id"), nullable=False),
        sa.Column("job_type", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(100)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('PENDING','RUNNING','SUCCEEDED','RETRY','FAILED','BLOCKED')", name="growth_job_state"),
        sa.CheckConstraint("attempts >= 0", name="growth_job_attempts_nonnegative"),
    )
    op.create_index("ix_growth_jobs_due", "growth_jobs", ["state", "available_at"])

def downgrade():
    op.drop_index("ix_growth_jobs_due", table_name="growth_jobs")
    op.drop_table("growth_jobs")
