"""Persist immutable render artifact identity and storage verification state."""
from alembic import op
import sqlalchemy as sa

revision = "0010_durable_media_artifacts"
down_revision = "0009_growth_runtime_quality"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "growth_media_artifacts",
        sa.Column("artifact_id", sa.String(36), primary_key=True),
        sa.Column("creative_id", sa.String(100), sa.ForeignKey("growth_creatives.creative_id"), nullable=False),
        sa.Column("experiment_id", sa.String(100), nullable=False),
        sa.Column("render_job_id", sa.String(100), sa.ForeignKey("growth_jobs.job_id"), nullable=False),
        sa.Column("source_render_attempt", sa.String(100), nullable=False),
        sa.Column("storage_provider", sa.String(40), nullable=False, server_default="RAILWAY_VOLUME"),
        sa.Column("object_key", sa.String(1000), nullable=False),
        sa.Column("staging_key", sa.String(1000), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="video/mp4"),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("codec", sa.String(30), nullable=False),
        sa.Column("quality_status", sa.String(20), nullable=False),
        sa.Column("quality_manifest", sa.Text(), nullable=False),
        sa.Column("storage_state", sa.String(30), nullable=False, server_default="STORAGE_PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failure_reason", sa.String(200)),
        sa.UniqueConstraint("render_job_id", "source_render_attempt", name="uq_media_job_attempt"),
        sa.CheckConstraint("storage_provider = 'RAILWAY_VOLUME'", name="media_storage_provider"),
        sa.CheckConstraint("storage_state IN ('RENDERED_TEMPORARY','STORAGE_PENDING','STORING','STORED_UNVERIFIED','STORED_VERIFIED','STORAGE_FAILED','ARTIFACT_DISCARDED','ARTIFACT_MISSING','ARTIFACT_CORRUPT','UNKNOWN')", name="media_storage_state"),
        sa.CheckConstraint("size_bytes > 0 AND duration_ms > 0 AND width > 0 AND height > 0 AND version > 0", name="media_positive_metadata"),
        sa.CheckConstraint("length(sha256) = 64", name="media_sha256_length"),
    )
    op.create_index("ix_media_creative_state_created", "growth_media_artifacts",
                    ["creative_id", "storage_state", "created_at"])


def downgrade():
    op.drop_index("ix_media_creative_state_created", table_name="growth_media_artifacts")
    op.drop_table("growth_media_artifacts")
