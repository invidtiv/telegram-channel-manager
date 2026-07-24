"""Database configuration and session management."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, inspect, text
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


def _migrate_bot_identity(sync_conn):
    """Add the stable Telegram bot identity to pre-migration databases."""
    inspector = inspect(sync_conn)
    if not inspector.has_table("bots"):
        return
    columns = {column["name"] for column in inspector.get_columns("bots")}
    if "telegram_bot_id" not in columns:
        sync_conn.execute(text("ALTER TABLE bots ADD COLUMN telegram_bot_id BIGINT"))
    sync_conn.execute(text(
        """
        UPDATE bots
        SET telegram_bot_id = NULL
        WHERE telegram_bot_id IN (
            SELECT telegram_bot_id
            FROM bots
            WHERE telegram_bot_id IS NOT NULL
            GROUP BY telegram_bot_id
            HAVING COUNT(*) > 1
        )
        """
    ))
    sync_conn.execute(text(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_bots_telegram_bot_id
        ON bots (telegram_bot_id)
        WHERE telegram_bot_id IS NOT NULL
        """
    ))
    sync_conn.execute(text(
        """
        UPDATE bots
        SET telegram_bot_id = CAST(substr(token, 1, instr(token, ':') - 1) AS INTEGER)
        WHERE rowid IN (
            SELECT MIN(rowid)
            FROM bots
            WHERE token != '' AND instr(token, ':') > 1
            GROUP BY substr(token, 1, instr(token, ':') - 1)
        )
          AND telegram_bot_id IS NULL
          AND token != ''
          AND instr(token, ':') > 1
        """
    ))


def _seed_default_account(sync_conn):
    """Attach legacy records to a default account without duplicating them."""
    session_name = os.getenv("SESSION_NAME", "list_channels_session")
    label = os.getenv("TELEGRAM_ACCOUNT_LABEL", "Primary")
    country_code = os.getenv("TELEGRAM_ACCOUNT_COUNTRY", "").upper()[:2]
    existing = sync_conn.execute(text(
        "SELECT 1 FROM telegram_accounts WHERE id = 'default'"
    )).first()
    if existing:
        return
    sync_conn.execute(text(
        """
        INSERT OR IGNORE INTO telegram_accounts
            (id, label, country_code, phone_hint, session_name, is_default, created_at, updated_at)
        VALUES
            ('default', :label, :country_code, '', :session_name, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    ), {"label": label, "country_code": country_code, "session_name": session_name})
    sync_conn.execute(text(
        """
        INSERT OR IGNORE INTO channel_accounts (account_id, channel_id, last_seen_at)
        SELECT 'default', id, CURRENT_TIMESTAMP FROM channels
        """
    ))
    sync_conn.execute(text(
        """
        INSERT OR IGNORE INTO bot_accounts (account_id, bot_id, last_seen_at)
        SELECT 'default', id, CURRENT_TIMESTAMP FROM bots
        """
    ))


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(_migrate_token_occurrences)
        await conn.run_sync(_migrate_bot_identity)
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_seed_default_account)
