import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server.models import Base
from server import growth_models
from server import growth_queue_models  # register growth tables with metadata
from server import action_effect_models  # register contracts, effects, outbox and evidence
from server import delivery_models  # register durable delivery identities

config = context.config
url = os.environ.get("DATABASE_URL")
if not url:
    raise RuntimeError("DATABASE_URL is required for migrations")
if url.startswith('postgresql://'):
    url = 'postgresql+psycopg://' + url[len('postgresql://'):]
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
