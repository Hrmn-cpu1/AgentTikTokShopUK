"""Persist operator controls for the growth agent."""
from alembic import op
import sqlalchemy as sa

revision = "0008_growth_control"
down_revision = "0007_growth_queue"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "growth_control",
        sa.Column("control_id", sa.String(20), primary_key=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode IN ('READY','PAUSED','STOPPED')", name="growth_control_mode"),
    )

def downgrade():
    op.drop_table("growth_control")
