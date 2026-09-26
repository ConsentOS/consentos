import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from src.models import Base

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment if set
database_url = os.environ.get("DATABASE_URL")
if database_url:
    # Alembic needs the synchronous driver
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    config.set_main_option("sqlalchemy.url", database_url)

# Set up Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

CORE_TABLES = frozenset(Base.metadata.tables)


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep autogenerate from proposing changes to tables core does not own.

    An extension package creates its own tables in the same database and
    tracks them in its own Alembic history. Those tables are absent from
    this repository's metadata, so without this filter ``alembic revision
    --autogenerate`` sees them as orphans and emits ``DROP TABLE`` for
    every one of them, along with the extension's own version table.
    Running that migration would destroy the extension's data and the
    means of rebuilding it.

    Only reflected objects are filtered: anything present in core's own
    metadata is always included.

    The trade-off: deleting a core model no longer produces a
    ``DROP TABLE`` automatically, because the table stops being in
    ``CORE_TABLES`` at the same moment. Removing a table is rare and
    deliberate, so write that migration by hand.
    """
    if reflected:
        if type_ == "table":
            return name in CORE_TABLES
        table = getattr(obj, "table", None)
        if table is not None:
            return table.name in CORE_TABLES
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
