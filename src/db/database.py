"""SQLite database connection manager using aiosqlite."""

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "analyses.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    position TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    entry_price REAL,
    exit_price REAL,
    bull_case TEXT,
    bear_case TEXT,
    agent_agreement REAL,
    tokens_used INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0,
    transcript_json TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analyses_symbol ON analyses(symbol);
CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vix REAL,
    sp500 REAL,
    fear_greed INTEGER,
    sector_analysis_json TEXT,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON market_snapshots(created_at);
"""


async def get_db() -> aiosqlite.Connection:
    """Get a database connection. Creates the database file if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    """Initialize the database schema."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
        logger.info(f"Database initialized at {DB_PATH}")
    finally:
        await db.close()
