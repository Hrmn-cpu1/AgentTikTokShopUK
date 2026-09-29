"""Persist runtime transitions and content quality/learning eligibility."""
from alembic import op
import sqlalchemy as sa

revision = "0009_growth_runtime_quality"
down_revision = "0008_growth_control"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("growth_control") as batch:
        batch.drop_constraint("growth_control_mode", type_="check")
        batch.create_check_constraint(
            "growth_control_mode",
            "mode IN ('READY','RUNNING','PAUSED','STOPPED','ACTION_REQUIRED','BLOCKED','FAILED')",
        )

    with op.batch_alter_table("growth_creatives") as batch:
        batch.add_column(sa.Column("purpose", sa.String(40), nullable=False,
                                   server_default="LEGACY_UNCLASSIFIED"))
        batch.add_column(sa.Column("creative_learning_eligible", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("style_baseline_eligible", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("mrwho_public", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("exclusion_reason", sa.String(100)))
        batch.add_column(sa.Column("quality_status", sa.String(20), nullable=False,
                                   server_default="NOT_EVALUATED"))
        batch.add_column(sa.Column("quality_json", sa.Text(), nullable=False,
                                   server_default="{}"))

    with op.batch_alter_table("growth_observations") as batch:
        batch.add_column(sa.Column("publication_identity", sa.String(500)))
        batch.add_column(sa.Column("truth_classification", sa.String(30), nullable=False,
                                   server_default="UNKNOWN"))

    op.execute("UPDATE growth_creatives SET exclusion_reason='LEGACY_CLASSIFICATION_REVIEW_REQUIRED' "
               "WHERE purpose='LEGACY_UNCLASSIFIED'")

    op.create_table(
        "growth_state_transitions",
        sa.Column("transition_id", sa.String(100), primary_key=True),
        sa.Column("experiment_id", sa.String(100)),
        sa.Column("job_id", sa.String(100)),
        sa.Column("source_state", sa.String(40), nullable=False),
        sa.Column("target_state", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_growth_transition_experiment_time", "growth_state_transitions",
                    ["experiment_id", "transitioned_at"])


def downgrade():
    op.drop_index("ix_growth_transition_experiment_time", table_name="growth_state_transitions")
    op.drop_table("growth_state_transitions")
    with op.batch_alter_table("growth_observations") as batch:
        batch.drop_column("truth_classification")
        batch.drop_column("publication_identity")
    with op.batch_alter_table("growth_creatives") as batch:
        batch.drop_column("quality_json")
        batch.drop_column("quality_status")
        batch.drop_column("exclusion_reason")
        batch.drop_column("style_baseline_eligible")
        batch.drop_column("mrwho_public")
        batch.drop_column("creative_learning_eligible")
        batch.drop_column("purpose")
    with op.batch_alter_table("growth_control") as batch:
        batch.drop_constraint("growth_control_mode", type_="check")
        batch.create_check_constraint("growth_control_mode", "mode IN ('READY','PAUSED','STOPPED')")
