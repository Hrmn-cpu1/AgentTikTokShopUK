"""Append later observed costs without overwriting the initial evidence."""
from alembic import op
import sqlalchemy as sa

revision = "0002_cost_adjustments"
down_revision = "0001_observation_store"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("experiment_cost_adjustments",
        sa.Column("adjustment_id", sa.String(100), primary_key=True),
        sa.Column("experiment_id", sa.String(100), sa.ForeignKey("experiments.experiment_id"), nullable=False),
        sa.Column("amount_gbp", sa.Numeric(18, 2), nullable=False),
        sa.Column("evidence_ref", sa.String(500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_gbp > 0", name="positive_adjustment"),
    )


def downgrade():
    op.drop_table("experiment_cost_adjustments")
