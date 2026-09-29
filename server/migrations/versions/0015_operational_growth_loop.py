"""Operational growth loop: policy, quotas, scheduler and follower truth.

Revision ID: 0015_operational_growth_loop
Revises: 0014_delivery_gateway
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_operational_growth_loop"
down_revision = "0014_delivery_gateway"
branch_labels = None
depends_on = None


def upgrade():
    # Batch mode keeps this migration valid in the SQLite E2E harness while
    # producing equivalent constraints in PostgreSQL production.
    with op.batch_alter_table("growth_creatives") as batch:
        batch.add_column(sa.Column("policy_status", sa.String(24), nullable=False,
                                   server_default="NOT_EVALUATED"))

    with op.batch_alter_table("growth_follower_snapshots") as batch:
        batch.add_column(sa.Column("truth_classification", sa.String(30), nullable=False,
                                   server_default="UNKNOWN"))
        batch.create_check_constraint("follower_truth_classification",
            "truth_classification IN ('UNKNOWN','OWNER_REPORTED','PROVIDER_VERIFIED')")

    with op.batch_alter_table("growth_control") as batch:
        batch.add_column(sa.Column("scheduler_enabled", sa.Boolean(), nullable=False,
                                   server_default=sa.text("true")))
        batch.add_column(sa.Column("scheduler_interval_seconds", sa.Integer(), nullable=False,
                                   server_default="300"))
        batch.add_column(sa.Column("daily_experiment_quota", sa.Integer(), nullable=False,
                                   server_default="3"))
        batch.add_column(sa.Column("daily_handoff_quota", sa.Integer(), nullable=False,
                                   server_default="3"))
        batch.add_column(sa.Column("follower_goal", sa.Integer(), nullable=False,
                                   server_default="1000"))
        batch.add_column(sa.Column("last_scheduler_tick_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint("growth_scheduler_interval_min",
            "scheduler_interval_seconds >= 60")
        batch.create_check_constraint("growth_daily_experiment_quota",
            "daily_experiment_quota BETWEEN 1 AND 24")
        batch.create_check_constraint("growth_daily_handoff_quota",
            "daily_handoff_quota BETWEEN 1 AND 24")
        batch.create_check_constraint("growth_follower_goal_positive",
            "follower_goal >= 1")

    op.create_table(
        "growth_policy_assessments",
        sa.Column("assessment_id", sa.String(36), primary_key=True),
        sa.Column("creative_id", sa.String(100), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("policy_pack_version", sa.String(60), nullable=False),
        sa.Column("policy_status", sa.String(24), nullable=False),
        sa.Column("originality_status", sa.String(24), nullable=False),
        sa.Column("creative_dna_digest", sa.String(64), nullable=False),
        sa.Column("originality_signature", sa.String(64), nullable=False),
        sa.Column("provenance_digest", sa.String(64), nullable=False),
        sa.Column("aigc_classification", sa.String(50), nullable=False),
        sa.Column("disclosure_required", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["creative_id"], ["growth_creatives.creative_id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["growth_media_artifacts.artifact_id"]),
        sa.UniqueConstraint("artifact_id", name="uq_growth_policy_artifact"),
        sa.CheckConstraint(
            "policy_status IN ('POLICY_PASS','POLICY_REVIEW','POLICY_FAIL')",
            name="growth_policy_status"),
        sa.CheckConstraint(
            "originality_status IN ('ORIGINAL','DUPLICATE','REVIEW')",
            name="growth_originality_status"),
    )
    op.create_index("ix_growth_policy_creative_time", "growth_policy_assessments",
        ["creative_id", "evaluated_at"])
    op.create_index("ix_growth_policy_signature", "growth_policy_assessments",
        ["originality_signature"])

    op.create_table(
        "growth_quota_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("creative_id", sa.String(100), nullable=True),
        sa.Column("delivery_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["creative_id"], ["growth_creatives.creative_id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_growth_quota_idempotency"),
        sa.CheckConstraint("event_type IN ('EXPERIMENT','HANDOFF')",
                           name="growth_quota_event_type"),
    )
    op.create_index("ix_growth_quota_type_time", "growth_quota_events",
        ["event_type", "occurred_at"])

    op.create_table(
        "growth_scheduler_ticks",
        sa.Column("tick_id", sa.String(36), primary_key=True),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("creative_id", sa.String(100), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('STARTED','WAITING','BLOCKED','GOAL_REACHED','QUOTA_REACHED')",
            name="growth_scheduler_decision"),
    )
    op.create_index("ix_growth_scheduler_tick_time", "growth_scheduler_ticks",
        ["observed_at"])


def downgrade():
    op.drop_index("ix_growth_scheduler_tick_time", table_name="growth_scheduler_ticks")
    op.drop_table("growth_scheduler_ticks")

    op.drop_index("ix_growth_quota_type_time", table_name="growth_quota_events")
    op.drop_table("growth_quota_events")

    op.drop_index("ix_growth_policy_signature", table_name="growth_policy_assessments")
    op.drop_index("ix_growth_policy_creative_time", table_name="growth_policy_assessments")
    op.drop_table("growth_policy_assessments")

    with op.batch_alter_table("growth_control") as batch:
        batch.drop_constraint("growth_follower_goal_positive", type_="check")
        batch.drop_constraint("growth_daily_handoff_quota", type_="check")
        batch.drop_constraint("growth_daily_experiment_quota", type_="check")
        batch.drop_constraint("growth_scheduler_interval_min", type_="check")
        batch.drop_column("last_scheduler_tick_at")
        batch.drop_column("follower_goal")
        batch.drop_column("daily_handoff_quota")
        batch.drop_column("daily_experiment_quota")
        batch.drop_column("scheduler_interval_seconds")
        batch.drop_column("scheduler_enabled")

    with op.batch_alter_table("growth_follower_snapshots") as batch:
        batch.drop_constraint("follower_truth_classification", type_="check")
        batch.drop_column("truth_classification")

    with op.batch_alter_table("growth_creatives") as batch:
        batch.drop_column("policy_status")
