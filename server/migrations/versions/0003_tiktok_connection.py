"""Durable one-operator sessions and TikTok Login Kit authorization."""
from alembic import op
import sqlalchemy as sa

revision = "0003_tiktok_connection"
down_revision = "0002_cost_adjustments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("operator_sessions",
        sa.Column("session_hash", sa.String(64), primary_key=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("tiktok_oauth_intents",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("session_hash", sa.String(64), sa.ForeignKey("operator_sessions.session_hash"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)))
    op.create_table("tiktok_connections",
        sa.Column("connection_id", sa.String(36), primary_key=True),
        sa.Column("operator_id", sa.String(50), nullable=False, unique=True),
        sa.Column("provider_user_id", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("granted_scopes", sa.String(1000), nullable=False),
        sa.Column("encrypted_access_token", sa.String(4000)),
        sa.Column("encrypted_refresh_token", sa.String(4000)),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("manual_uk_evidence_ref", sa.String(500)),
        sa.Column("manual_affiliate_evidence_ref", sa.String(500)),
        sa.Column("manual_verified_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED','REFRESH_FAILED','UNKNOWN')", name="valid_connection_status"))


def downgrade():
    op.drop_table("tiktok_connections")
    op.drop_table("tiktok_oauth_intents")
    op.drop_table("operator_sessions")
