"""Alembic 遷移環境。呼叫端可透過 config.attributes["connection"] 傳入既有的同步連線（測試用）。"""

from logging.config import fileConfig

from sqlalchemy import Connection, create_engine

from alembic import context
from app.config import load_settings
from app.storage.models import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _migrate(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _migrate(connection)
        return
    engine = create_engine(load_settings().database_url)
    try:
        with engine.connect() as conn:
            _migrate(conn)
    finally:
        engine.dispose()


run_migrations_online()
