from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (register models)
from app.db import Base

config = context.config
target_metadata = Base.metadata


def run():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run()
