"""Persist evidence-backed CreativeDNA before automatic video production.

Revision ID: 0016_creative_dna
Revises: 0015_operational_growth_loop
"""
from alembic import op
import sqlalchemy as sa


revision = "0016_creative_dna"
down_revision = "0015_operational_growth_loop"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "growth_creative_dna",
        sa.Column("dna_id", sa.String(36), primary_key=True),
        sa.Column("creative_id", sa.String(100), nullable=False),
        sa.Column("source_priority", sa.String(40), nullable=False),
        sa.Column("references_json", sa.Text(), nullable=False),
        sa.Column("patterns_json", sa.Text(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["creative_id"], ["growth_creatives.creative_id"]),
        sa.UniqueConstraint("creative_id", name="uq_growth_creative_dna_creative"),
        sa.CheckConstraint(
            "source_priority IN ('OWN_RESULTS_FIRST','PUBLIC_REFERENCE_PRIOR')",
            name="growth_creative_dna_priority",
        ),
        sa.CheckConstraint("length(evidence_digest) = 64", name="growth_creative_dna_digest"),
    )
    op.create_index("ix_growth_creative_dna_created", "growth_creative_dna", ["created_at"])


def downgrade():
    op.drop_index("ix_growth_creative_dna_created", table_name="growth_creative_dna")
    op.drop_table("growth_creative_dna")
