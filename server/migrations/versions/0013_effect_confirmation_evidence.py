"""Link confirmed effects to the evidence that established them."""
from alembic import op
import sqlalchemy as sa

revision = "0013_effect_confirmation_evidence"
down_revision = "0012_action_effect_outbox"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("effect_evidence") as batch:
        batch.create_unique_constraint("uq_effect_evidence_id_effect_pair", ["evidence_id", "effect_id"])
    with op.batch_alter_table("effect_ledger") as batch:
        batch.add_column(sa.Column("confirmation_evidence_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_effect_confirmation_evidence", "effect_evidence",
            ["confirmation_evidence_id", "effect_id"], ["evidence_id", "effect_id"])
        batch.create_check_constraint("effect_confirmation_evidence",
            "state != 'CONFIRMED' OR confirmation_evidence_id IS NOT NULL")


def downgrade():
    with op.batch_alter_table("effect_ledger") as batch:
        batch.drop_constraint("effect_confirmation_evidence", type_="check")
        batch.drop_constraint("fk_effect_confirmation_evidence", type_="foreignkey")
        batch.drop_column("confirmation_evidence_id")
    with op.batch_alter_table("effect_evidence") as batch:
        batch.drop_constraint("uq_effect_evidence_id_effect_pair", type_="unique")
