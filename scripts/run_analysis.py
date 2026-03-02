#!/usr/bin/env python3
"""CLI entry point for running stock analysis."""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.analysis_service import AnalysisService


def format_recommendation(transcript) -> str:
    """Format a recommendation for terminal output."""
    rec = transcript.recommendation
    if not rec:
        return "No recommendation generated."

    lines = []
    lines.append("=" * 60)
    lines.append(f"  RECOMMENDATION: {rec.position.value} — {rec.symbol}")
    lines.append(f"  Confidence: {rec.confidence}%")
    lines.append("=" * 60)

    if rec.entry_price:
        lines.append(f"  Entry Price:  ${rec.entry_price:.2f}")
    if rec.exit_price:
        lines.append(f"  Exit Price:   ${rec.exit_price:.2f}")
    if rec.stop_loss:
        lines.append(f"  Stop Loss:    ${rec.stop_loss:.2f}")
    if rec.risk_reward_ratio:
        lines.append(f"  Risk/Reward:  {rec.risk_reward_ratio:.1f}:1")
    if rec.time_horizon:
        lines.append(f"  Time Horizon: {rec.time_horizon}")

    lines.append("")
    lines.append("  BULL CASE:")
    lines.append(f"  {rec.bull_case}")
    lines.append("")
    lines.append("  BEAR CASE:")
    lines.append(f"  {rec.bear_case}")

    if rec.key_factors:
        lines.append("")
        lines.append("  KEY FACTORS:")
        for f in rec.key_factors:
            lines.append(f"    - {f}")

    if rec.estimated_upside_pct is not None:
        lines.append(f"\n  Estimated Upside:   {rec.estimated_upside_pct:+.1f}%")
    if rec.estimated_downside_pct is not None:
        lines.append(f"  Estimated Downside: {rec.estimated_downside_pct:+.1f}%")

    lines.append(f"\n  Agent Agreement: {rec.agent_agreement_level:.0%}")
    lines.append(f"  Tokens Used: {rec.total_tokens_used:,}")
    lines.append(f"  Analysis Time: {rec.analysis_duration_seconds:.1f}s")

    if rec.sector_etf_suggestion:
        lines.append(f"\n  Sector ETF: {rec.sector_etf_suggestion}")

    lines.append("=" * 60)

    # Debate summary
    lines.append("\n  AGENT POSITIONS:")
    for a in transcript.phase1_analyses:
        lines.append(f"    {a.agent_name}: {a.position.value} ({a.confidence}%)")

    return "\n".join(lines)


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_analysis.py <TICKER> [TICKER2 ...]")
        print("Example: python scripts/run_analysis.py NVDA AAPL")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    symbols = [s.upper().strip() for s in sys.argv[1:]]
    service = AnalysisService()

    for symbol in symbols:
        print(f"\nAnalyzing {symbol}...")
        try:
            transcript = await service.analyze_stock(symbol)
            print(format_recommendation(transcript))
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
