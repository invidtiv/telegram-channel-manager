"""Database configuration and session management."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, inspect
import os

# Create data directory if it doesn't exist
_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(_data_dir, exist_ok=True)

# SQLite async database URL (absolute path so it works from any CWD)
DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(_data_dir, 'telegram_channels.db')}"

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Base class for models
Base = declarative_base()


async def get_db():
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def _migrate_token_occurrences(sync_conn):
    """Drop token_occurrences if it exists without the token column.

    This is a lightweight migration for the scanner cache table. Scan results
    are regenerated on each run, so dropping the table is safe.
    """
    from sqlalchemy import Table, MetaData
    inspector = inspect(sync_conn)
    if inspector.has_table("token_occurrences"):
        columns = {c["name"] for c in inspector.get_columns("token_occurrences")}
        if "token" not in columns:
            meta = MetaData()
            Table("token_occurrences", meta, autoload_with=sync_conn)
            meta.drop_all(sync_conn, tables=[meta.tables["token_occurrences"]])


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(_migrate_token_occurrences)
        await conn.run_sync(Base.metadata.create_all)
