"""Add durable delivery gateway identity and state.

Revision ID: 0014_delivery_gateway
Revises: 0013_effect_confirm_link
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_delivery_gateway"
down_revision = "0013_effect_confirm_link"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "delivery_effects",
        sa.Column("delivery_id", sa.String(36), primary_key=True),
        sa.Column("action_contract_id", sa.String(36), nullable=False),
        sa.Column("effect_id", sa.String(36), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("creative_id", sa.String(100), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("target", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("target_account_id", sa.String(200), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("provider_reference", sa.String(300), nullable=True),
        sa.Column("public_post_id", sa.String(300), nullable=True),
        sa.Column("failure_class", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["effect_id", "action_contract_id"],
            ["effect_ledger.effect_id", "effect_ledger.action_contract_id"],
            name="fk_delivery_effect_contract"),
        sa.ForeignKeyConstraint(["artifact_id", "creative_id"],
            ["growth_media_artifacts.artifact_id", "growth_media_artifacts.creative_id"],
            name="fk_delivery_artifact_creative"),
        sa.UniqueConstraint("effect_id", name="uq_delivery_effect"),
        sa.UniqueConstraint("action_contract_id", name="uq_delivery_contract"),
        sa.CheckConstraint(
            "target IN ('ANDROID_SHARE_HANDOFF','TIKTOK_OFFICIAL_DIRECT_POST','TIKTOK_OFFICIAL_UPLOAD_DRAFT')",
            name="delivery_target"),
        sa.CheckConstraint(
            "state IN ('UNKNOWN','PREPARED','HANDOFF_INITIATED','DISPATCHED','PROCESSING','FAILED','CONFIRMED')",
            name="delivery_state"),
        sa.CheckConstraint("length(artifact_sha256) = 64", name="delivery_artifact_sha_length"),
        sa.CheckConstraint(
            "(target = 'ANDROID_SHARE_HANDOFF' AND provider = 'ANDROID_SHARE') OR "
            "(target IN ('TIKTOK_OFFICIAL_DIRECT_POST','TIKTOK_OFFICIAL_UPLOAD_DRAFT') "
            "AND provider = 'TIKTOK_OFFICIAL')",
            name="delivery_provider_matches_target"),
        sa.CheckConstraint("state != 'CONFIRMED' OR confirmed_at IS NOT NULL",
            name="delivery_confirmation_timestamp"),
    )
    op.create_index("ix_delivery_state_updated", "delivery_effects", ["state", "updated_at"])
    op.create_index("ix_delivery_provider_reference", "delivery_effects", ["provider", "provider_reference"])

def downgrade():
    op.drop_index("ix_delivery_provider_reference", table_name="delivery_effects")
    op.drop_index("ix_delivery_state_updated", table_name="delivery_effects")
    op.drop_table("delivery_effects")
