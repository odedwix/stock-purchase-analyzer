"""Repository for analysis CRUD operations."""

import json
import logging
from datetime import datetime

from src.db.database import get_db, init_db
from src.models.analysis import DebateTranscript

logger = logging.getLogger(__name__)


async def _ensure_db():
    """Ensure the database is initialized."""
    await init_db()


async def save_analysis(transcript: DebateTranscript) -> int:
    """Save a DebateTranscript to the database. Returns the row ID."""
    await _ensure_db()
    rec = transcript.recommendation

    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO analyses
               (symbol, position, confidence, entry_price, exit_price,
                bull_case, bear_case, agent_agreement, tokens_used,
                duration_seconds, transcript_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                transcript.symbol,
                rec.position.value if rec else "WAIT",
                rec.confidence if rec else 0,
                rec.entry_price if rec else None,
                rec.exit_price if rec else None,
                rec.bull_case if rec else "",
                rec.bear_case if rec else "",
                rec.agent_agreement_level if rec else 0,
                rec.total_tokens_used if rec else 0,
                rec.analysis_duration_seconds if rec else 0,
                transcript.model_dump_json(),
                transcript.created_at.isoformat(),
            ),
        )
        await db.commit()
        row_id = cursor.lastrowid
        logger.info(f"Saved analysis #{row_id} for {transcript.symbol}")
        return row_id
    finally:
        await db.close()


async def list_analyses(symbol: str | None = None, limit: int = 50) -> list[dict]:
    """List analyses with summary fields (no full transcript JSON).

    Returns list of dicts with: id, symbol, position, confidence, entry_price,
    exit_price, bull_case, bear_case, agent_agreement, tokens_used,
    duration_seconds, created_at.
    """
    await _ensure_db()
    db = await get_db()
    try:
        if symbol:
            cursor = await db.execute(
                """SELECT id, symbol, position, confidence, entry_price, exit_price,
                          bull_case, bear_case, agent_agreement, tokens_used,
                          duration_seconds, created_at
                   FROM analyses WHERE symbol = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (symbol, limit),
            )
        else:
            cursor = await db.execute(
                """SELECT id, symbol, position, confidence, entry_price, exit_price,
                          bull_case, bear_case, agent_agreement, tokens_used,
                          duration_seconds, created_at
                   FROM analyses ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_analysis(analysis_id: int) -> DebateTranscript | None:
    """Load a single full analysis by ID."""
    await _ensure_db()
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT transcript_json FROM analyses WHERE id = ?", (analysis_id,)
        )
        row = await cursor.fetchone()
        if row:
            return DebateTranscript.model_validate_json(row["transcript_json"])
        return None
    finally:
        await db.close()


async def get_analyses_for_comparison(ids: list[int]) -> list[DebateTranscript]:
    """Load multiple full transcripts for side-by-side comparison."""
    await _ensure_db()
    db = await get_db()
    try:
        placeholders = ",".join("?" * len(ids))
        cursor = await db.execute(
            f"SELECT id, transcript_json FROM analyses WHERE id IN ({placeholders}) ORDER BY id",
            ids,
        )
        rows = await cursor.fetchall()
        return [DebateTranscript.model_validate_json(row["transcript_json"]) for row in rows]
    finally:
        await db.close()


async def delete_analysis(analysis_id: int) -> bool:
    """Delete a saved analysis."""
    await _ensure_db()
    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def save_market_snapshot(
    vix: float | None,
    sp500: float | None,
    fear_greed: int | None,
    sector_analysis: dict | None,
) -> int:
    """Save a market overview snapshot."""
    await _ensure_db()
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO market_snapshots (vix, sp500, fear_greed, sector_analysis_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                vix,
                sp500,
                fear_greed,
                json.dumps(sector_analysis) if sector_analysis else None,
                datetime.now().isoformat(),
            ),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_latest_market_snapshot() -> dict | None:
    """Get the most recent market snapshot."""
    await _ensure_db()
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM market_snapshots ORDER BY created_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            result = dict(row)
            if result.get("sector_analysis_json"):
                result["sector_analysis"] = json.loads(result["sector_analysis_json"])
            return result
        return None
    finally:
        await db.close()
