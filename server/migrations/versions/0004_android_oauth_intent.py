"""Bind browser OAuth callback to its initiating Android or web session."""
from alembic import op
import sqlalchemy as sa

revision = "0004_android_oauth_intent"
down_revision = "0003_tiktok_connection"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tiktok_oauth_intents", sa.Column("platform", sa.String(10), nullable=False,
        server_default="WEB"))


def downgrade():
    op.drop_column("tiktok_oauth_intents", "platform")
