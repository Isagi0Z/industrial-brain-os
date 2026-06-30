import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the backend app is importable from within the migrations directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.config.settings import settings  # noqa: E402

# Alembic Config object — access to values from alembic.ini
alembic_config = context.config

# Override the database URL dynamically from application settings.
# This ensures the migration always targets the same DB as the running app,
# regardless of what is written in alembic.ini.
_db_url = (
    f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)
alembic_config.set_main_option("sqlalchemy.url", _db_url)

# Configure Python logging from the alembic.ini [loggers] section
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# No SQLAlchemy ORM metadata — all migrations are raw SQL via op.execute()
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations without an active DB connection (generates SQL script)."""
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
