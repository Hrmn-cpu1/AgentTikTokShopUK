"""Durable one-operator authority and traceable experiment intents."""
from alembic import op
import sqlalchemy as sa

revision = '0005_server_authority'
down_revision = '0004_android_oauth_intent'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('capital_authorities',
        sa.Column('authority_id', sa.String(100), primary_key=True),
        sa.Column('operator_id', sa.String(50), nullable=False),
        sa.Column('available_capital_gbp', sa.Numeric(18, 2), nullable=False),
        sa.Column('capital_limit_gbp', sa.Numeric(18, 2), nullable=False),
        sa.Column('loss_limit_gbp', sa.Numeric(18, 2), nullable=False),
        sa.Column('minimum_allocation_score', sa.Integer(), nullable=False),
        sa.Column('approved_by', sa.String(50), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('evidence_ref', sa.String(500), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.CheckConstraint("available_capital_gbp >= 0 AND capital_limit_gbp >= 0 AND loss_limit_gbp >= 0 AND minimum_allocation_score BETWEEN 0 AND 100", name='valid_capital_bounds'),
        sa.CheckConstraint("status IN ('ACTIVE','REVOKED')", name='valid_capital_status'))
    op.create_table('product_evidence',
        sa.Column('product_id', sa.String(100), primary_key=True),
        sa.Column('listing_ref', sa.String(500), nullable=False),
        sa.Column('evidence_ref', sa.String(500), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('opportunity_evidence',
        sa.Column('opportunity_id', sa.String(100), primary_key=True),
        sa.Column('product_id', sa.String(100), sa.ForeignKey('product_evidence.product_id'), nullable=False),
        sa.Column('capital_required_gbp', sa.Numeric(18, 2), nullable=False),
        sa.Column('maximum_loss_gbp', sa.Numeric(18, 2), nullable=False),
        sa.Column('allocation_score', sa.Integer(), nullable=False),
        sa.Column('evidence_ref', sa.String(500), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('capital_required_gbp >= 0 AND maximum_loss_gbp >= 0 AND allocation_score BETWEEN 0 AND 100', name='valid_opportunity_bounds'))
    op.create_table('product_claims',
        sa.Column('claim_id', sa.String(100), primary_key=True),
        sa.Column('product_id', sa.String(100), sa.ForeignKey('product_evidence.product_id'), nullable=False),
        sa.Column('text', sa.String(1000), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('evidence_ref', sa.String(500)),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('VERIFIED','SUPPORTED','UNKNOWN','BLOCKED')", name='valid_claim_state'))
    op.add_column('experiments', sa.Column('opportunity_id', sa.String(100)))
    op.create_table('creative_artifacts',
        sa.Column('creative_id', sa.String(100), primary_key=True),
        sa.Column('experiment_id', sa.String(100), sa.ForeignKey('experiments.experiment_id'), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('claim_ids_json', sa.String(4000), nullable=False),
        sa.Column('evidence_ref', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('creative_approvals',
        sa.Column('approval_id', sa.String(100), primary_key=True),
        sa.Column('creative_id', sa.String(100), sa.ForeignKey('creative_artifacts.creative_id'), nullable=False),
        sa.Column('experiment_id', sa.String(100), sa.ForeignKey('experiments.experiment_id'), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('truth_hash', sa.String(64), nullable=False),
        sa.Column('approved_by', sa.String(50), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('evidence_ref', sa.String(500), nullable=False))
    op.create_table('launch_intents',
        sa.Column('packet_id', sa.String(100), primary_key=True),
        sa.Column('experiment_id', sa.String(100), sa.ForeignKey('experiments.experiment_id'), nullable=False, unique=True),
        sa.Column('approval_id', sa.String(100), sa.ForeignKey('creative_approvals.approval_id'), nullable=False),
        sa.Column('capital_authority_id', sa.String(100), sa.ForeignKey('capital_authorities.authority_id'), nullable=False),
        sa.Column('truth_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('length(packet_id) > 0', name='nonempty_packet_id'))
    op.create_table('learning_records',
        sa.Column('learning_id', sa.String(100), primary_key=True),
        sa.Column('experiment_id', sa.String(100), sa.ForeignKey('experiments.experiment_id'), nullable=False),
        sa.Column('economic_fingerprint', sa.String(64), nullable=False),
        sa.Column('contribution_gbp', sa.Numeric(18, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    with op.batch_alter_table('commerce_events') as batch:
        batch.add_column(sa.Column('parent_event_id', sa.String(36), sa.ForeignKey('commerce_events.event_id', name='fk_event_parent')))


def downgrade():
    with op.batch_alter_table('commerce_events') as batch:
        batch.drop_column('parent_event_id')
    op.drop_table('learning_records')
    op.drop_table('launch_intents')
    op.drop_table('creative_approvals')
    op.drop_table('creative_artifacts')
    op.drop_column('experiments', 'opportunity_id')
    op.drop_table('product_claims')
    op.drop_table('opportunity_evidence')
    op.drop_table('product_evidence')
    op.drop_table('capital_authorities')
