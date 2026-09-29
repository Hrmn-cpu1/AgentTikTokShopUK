"""Manual observation ledger and experiment trace."""
from alembic import op
import sqlalchemy as sa

revision = "0001_observation_store"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("experiments",
        sa.Column("experiment_id", sa.String(100), primary_key=True),
        sa.Column("decision_id", sa.String(100), nullable=False),
        sa.Column("product_id", sa.String(100), nullable=False),
        sa.Column("creative_id", sa.String(100), nullable=False),
        sa.Column("publication_action_id", sa.String(100), nullable=False, unique=True),
        sa.Column("authority_evidence_ref", sa.String(500), nullable=False),
        sa.Column("market", sa.String(2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market = 'UK' AND currency = 'GBP'", name="uk_gbp_only"),
    )
    op.create_table("commerce_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(100), sa.ForeignKey("experiments.experiment_id"), nullable=False),
        sa.Column("action_id", sa.String(100), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("external_event_id", sa.String(200), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("amount_gbp", sa.Numeric(18, 2), nullable=True),
        sa.Column("evidence_ref", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "external_event_id", name="uq_external_event"),
        sa.CheckConstraint("event_type IN ('PUBLISHED','ORDER_CREATED','DELIVERED','COMMISSION_SETTLED','REFUNDED')", name="known_event_type"),
        sa.CheckConstraint("amount_gbp IS NULL OR amount_gbp >= 0", name="nonnegative_amount"),
        sa.CheckConstraint("event_type NOT IN ('COMMISSION_SETTLED','REFUNDED') OR amount_gbp IS NOT NULL", name="economic_amount_required"),
    )
    op.create_table("experiment_costs",
        sa.Column("experiment_id", sa.String(100), sa.ForeignKey("experiments.experiment_id"), primary_key=True),
        sa.Column("amount_gbp", sa.Numeric(18, 2), nullable=False),
        sa.Column("evidence_ref", sa.String(500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_gbp >= 0", name="nonnegative_cost"),
    )
    op.create_index("uq_one_publication_per_experiment", "commerce_events", ["experiment_id"], unique=True,
                    sqlite_where=sa.text("event_type = 'PUBLISHED'"),
                    postgresql_where=sa.text("event_type = 'PUBLISHED'"))


def downgrade():
    op.drop_table("experiment_costs")
    op.drop_index("uq_one_publication_per_experiment", table_name="commerce_events")
    op.drop_table("commerce_events")
    op.drop_table("experiments")
