"""Add atomic action contract, effect ledger and fenced transactional outbox."""
from alembic import op
import sqlalchemy as sa

revision = "0012_action_effect_outbox"
down_revision = "0011_growth_worker_fencing"
branch_labels = None
depends_on = None


IMMUTABLE_COLUMNS = (
    "idempotency_key", "action_type", "market", "experiment_id", "creative_id",
    "artifact_id", "job_id", "job_attempt_id", "required_capability", "provider",
    "target_account_id", "business_parameters", "business_parameters_digest",
    "request_digest", "artifact_sha256", "requested_at", "created_at", "contract_version",
    "lease_owner", "lease_generation", "lease_attempt_id",
)


def upgrade():
    with op.batch_alter_table("growth_jobs") as batch:
        batch.create_unique_constraint("uq_growth_job_id_creative", ["job_id", "creative_id"])
    with op.batch_alter_table("growth_media_artifacts") as batch:
        batch.create_unique_constraint("uq_media_artifact_creative", ["artifact_id", "creative_id"])

    op.create_table(
        "action_contracts",
        sa.Column("action_contract_id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("action_type", sa.String(60), nullable=False),
        sa.Column("market", sa.String(2), nullable=False),
        sa.Column("experiment_id", sa.String(100), nullable=False),
        sa.Column("creative_id", sa.String(100), sa.ForeignKey("growth_creatives.creative_id"), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(100), nullable=False),
        sa.Column("job_attempt_id", sa.String(36), nullable=False),
        sa.Column("required_capability", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("target_account_id", sa.String(200)),
        sa.Column("business_parameters", sa.Text(), nullable=False),
        sa.Column("business_parameters_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("lease_owner", sa.String(100), nullable=False),
        sa.Column("lease_generation", sa.BigInteger(), nullable=False),
        sa.Column("lease_attempt_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id", "creative_id"],
            ["growth_media_artifacts.artifact_id", "growth_media_artifacts.creative_id"],
            name="fk_action_contract_artifact_creative"),
        sa.ForeignKeyConstraint(["job_id", "creative_id"],
            ["growth_jobs.job_id", "growth_jobs.creative_id"], name="fk_action_contract_job_creative"),
        sa.UniqueConstraint("idempotency_key", name="uq_action_contract_idempotency"),
        sa.CheckConstraint("length(business_parameters_digest) = 64 AND length(request_digest) = 64", name="action_contract_digest_length"),
        sa.CheckConstraint("length(artifact_sha256) = 64", name="action_contract_artifact_sha_length"),
        sa.CheckConstraint("contract_version > 0", name="action_contract_version_positive"),
        sa.CheckConstraint("status IN ('PREPARED','REJECTED','CANCELLED')", name="action_contract_status"),
        sa.CheckConstraint("market IN ('BR','UK','US','DE','FR','ES','JP','KR','CN','IN','ID','VN','TH','SG','RU')", name="action_contract_market"),
    )
    op.create_index("ix_action_contract_creative_created", "action_contracts", ["creative_id", "created_at"])

    op.create_table(
        "effect_ledger",
        sa.Column("effect_id", sa.String(36), primary_key=True),
        sa.Column("effect_key", sa.String(300), nullable=False),
        sa.Column("action_contract_id", sa.String(36), sa.ForeignKey("action_contracts.action_contract_id"), nullable=False),
        sa.Column("operation", sa.String(60), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("current_attempt", sa.Integer(), nullable=False),
        sa.Column("provider_reference", sa.String(300)),
        sa.Column("reconciliation_required", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_class", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("effect_key", name="uq_effect_key"),
        sa.UniqueConstraint("action_contract_id", name="uq_effect_action_contract"),
        sa.UniqueConstraint("effect_id", "action_contract_id", name="uq_effect_contract_pair"),
        sa.CheckConstraint("state IN ('PREPARED','DISPATCH_PENDING','UNKNOWN','RECONCILIATION_REQUIRED','CONFIRMED','REJECTED','FAILED_BEFORE_EFFECT')", name="effect_state"),
        sa.CheckConstraint("length(request_digest) = 64 AND length(artifact_sha256) = 64", name="effect_digest_length"),
        sa.CheckConstraint("current_attempt >= 0", name="effect_attempt_nonnegative"),
        sa.CheckConstraint("state NOT IN ('UNKNOWN','RECONCILIATION_REQUIRED') OR reconciliation_required = TRUE", name="effect_unknown_requires_reconciliation"),
        sa.CheckConstraint("state != 'CONFIRMED' OR confirmed_at IS NOT NULL", name="effect_confirmation_timestamp"),
    )
    op.create_index("ix_effect_reconciliation", "effect_ledger", ["reconciliation_required", "updated_at"])

    op.create_table(
        "effect_outbox",
        sa.Column("outbox_id", sa.String(36), primary_key=True),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("effect_id", sa.String(36), nullable=False),
        sa.Column("action_contract_id", sa.String(36), nullable=False),
        sa.Column("dedupe_key", sa.String(300), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.String(100)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_generation", sa.BigInteger(), nullable=False),
        sa.Column("lease_attempt_id", sa.String(36)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(200)),
        sa.ForeignKeyConstraint(["effect_id", "action_contract_id"],
            ["effect_ledger.effect_id", "effect_ledger.action_contract_id"], name="fk_outbox_effect_contract"),
        sa.UniqueConstraint("dedupe_key", name="uq_effect_outbox_dedupe"),
        sa.UniqueConstraint("outbox_id", "effect_id", name="uq_outbox_id_effect_pair"),
        sa.CheckConstraint("state IN ('PENDING','CLAIMED','ACKED')", name="outbox_state"),
        sa.CheckConstraint("length(payload_digest) = 64", name="outbox_payload_digest_length"),
        sa.CheckConstraint("lease_generation >= 0 AND revision >= 0 AND attempts >= 0", name="outbox_counters_nonnegative"),
        sa.CheckConstraint("state != 'ACKED' OR acked_at IS NOT NULL", name="outbox_ack_timestamp"),
        sa.CheckConstraint("state != 'CLAIMED' OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL AND lease_attempt_id IS NOT NULL)", name="outbox_claim_lease"),
    )
    op.create_index("ix_effect_outbox_due", "effect_outbox", ["state", "available_at", "lease_until"])

    op.create_table(
        "effect_attempts",
        sa.Column("attempt_id", sa.String(36), primary_key=True),
        sa.Column("effect_id", sa.String(36), nullable=False),
        sa.Column("outbox_id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(100), sa.ForeignKey("growth_jobs.job_id"), nullable=False),
        sa.Column("job_attempt_id", sa.String(36), nullable=False),
        sa.Column("job_worker_id", sa.String(100), nullable=False),
        sa.Column("job_lease_generation", sa.BigInteger(), nullable=False),
        sa.Column("outbox_worker_id", sa.String(100), nullable=False),
        sa.Column("outbox_lease_generation", sa.BigInteger(), nullable=False),
        sa.Column("outbox_attempt_id", sa.String(36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("result_class", sa.String(60), nullable=False),
        sa.Column("error_class", sa.String(100)),
        sa.Column("provider_request_id", sa.String(200)),
        sa.Column("provider_response_digest", sa.String(64)),
        sa.ForeignKeyConstraint(["outbox_id", "effect_id"],
            ["effect_outbox.outbox_id", "effect_outbox.effect_id"], name="fk_effect_attempt_outbox_effect"),
        sa.ForeignKeyConstraint(["effect_id"], ["effect_ledger.effect_id"], name="fk_effect_attempt_effect"),
        sa.UniqueConstraint("effect_id", "outbox_attempt_id", name="uq_effect_outbox_attempt"),
        sa.CheckConstraint("length(job_attempt_id) > 0 AND length(outbox_attempt_id) > 0 AND length(job_worker_id) > 0 AND length(outbox_worker_id) > 0", name="effect_attempt_identity"),
        sa.CheckConstraint("job_lease_generation > 0 AND outbox_lease_generation > 0", name="effect_attempt_generation_positive"),
        sa.CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="effect_attempt_time_order"),
        sa.CheckConstraint("provider_response_digest IS NULL OR length(provider_response_digest) = 64", name="effect_attempt_response_digest"),
    )
    op.create_index("ix_effect_attempts_effect_started", "effect_attempts", ["effect_id", "started_at"])

    op.create_table(
        "effect_evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("effect_id", sa.String(36), sa.ForeignKey("effect_ledger.effect_id"), nullable=False),
        sa.Column("evidence_type", sa.String(60), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("source_reference", sa.String(1000), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("effect_id", "evidence_type", "payload_digest", name="uq_effect_evidence_digest"),
        sa.CheckConstraint("classification IN ('SYSTEM_OBSERVED','PROVIDER_OBSERVED','OWNER_REPORTED','RECONCILIATION_RESULT')", name="effect_evidence_classification"),
        sa.CheckConstraint("length(payload_digest) = 64", name="effect_evidence_digest_length"),
    )
    op.create_index("ix_effect_evidence_effect_observed", "effect_evidence", ["effect_id", "observed_at"])

    immutable_sql = " OR ".join(f"OLD.{column} IS NOT NEW.{column}" for column in IMMUTABLE_COLUMNS)
    if op.get_bind().dialect.name == "sqlite":
        op.execute(f"""CREATE TRIGGER trg_action_contract_immutable BEFORE UPDATE ON action_contracts
            WHEN {immutable_sql} BEGIN SELECT RAISE(ABORT, 'action contract fields are immutable'); END""")
    elif op.get_bind().dialect.name == "postgresql":
        comparisons = ", ".join(f"OLD.{column}" for column in IMMUTABLE_COLUMNS)
        new_values = ", ".join(f"NEW.{column}" for column in IMMUTABLE_COLUMNS)
        op.execute(f"""CREATE FUNCTION guard_action_contract_immutable() RETURNS trigger AS $$
            BEGIN IF ROW({comparisons}) IS DISTINCT FROM ROW({new_values}) THEN
              RAISE EXCEPTION 'action contract fields are immutable' USING ERRCODE = '23514';
            END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER trg_action_contract_immutable BEFORE UPDATE ON action_contracts FOR EACH ROW EXECUTE FUNCTION guard_action_contract_immutable()")


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_action_contract_immutable")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_action_contract_immutable ON action_contracts")
        op.execute("DROP FUNCTION IF EXISTS guard_action_contract_immutable()")
    op.drop_index("ix_effect_evidence_effect_observed", table_name="effect_evidence")
    op.drop_table("effect_evidence")
    op.drop_index("ix_effect_attempts_effect_started", table_name="effect_attempts")
    op.drop_table("effect_attempts")
    op.drop_index("ix_effect_outbox_due", table_name="effect_outbox")
    op.drop_table("effect_outbox")
    op.drop_index("ix_effect_reconciliation", table_name="effect_ledger")
    op.drop_table("effect_ledger")
    op.drop_index("ix_action_contract_creative_created", table_name="action_contracts")
    op.drop_table("action_contracts")
    with op.batch_alter_table("growth_media_artifacts") as batch:
        batch.drop_constraint("uq_media_artifact_creative", type_="unique")
    with op.batch_alter_table("growth_jobs") as batch:
        batch.drop_constraint("uq_growth_job_id_creative", type_="unique")
