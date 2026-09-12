from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.models import Base

config = context.config
# Alembic stores this in a configparser ini, where "%" starts an interpolation token. A
# percent-encoded character in the password (Supabase passwords routinely contain one, and
# "%21" is simply "!") would otherwise abort migrations with "invalid interpolation syntax".
# Doubling the sign is configparser's escape; it reads back as a single "%".
config.set_main_option("sqlalchemy.url", settings.database_url_sync.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url_sync,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
