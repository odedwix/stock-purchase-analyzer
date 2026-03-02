# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent AI stock **investment opportunity** analyzer. Uses Ollama (local qwen2.5:32b) to run 5 specialist AI agents + 1 sector analyst that debate and produce recommendations: should you BUY, WAIT, or AVOID? Evaluates stocks the user does NOT own — framed as opportunity scanning, not position management. Collects world news, Reddit, Twitter/X, stock news, Fear & Greed, and economic data.

## Commands

```bash
# Install dependencies
uv pip install -e ".[dev,sentiment,economic,ollama]"

# Run Streamlit dashboard
streamlit run streamlit_app/app.py

# Run CLI analysis
python scripts/run_analysis.py NVDA AAPL

# Run tests
pytest tests/

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Architecture

### Data Flow
```
User selects stock → DataAggregator (8 parallel collectors) → StockDataPackage
→ DebateEngine:
  Phase 1: 5 agents analyze independently (sequential for rate limits)
  Sector Analysis: SectorAnalystAgent maps world events to sectors/ETFs
  Phase 2: debate rounds (skip if consensus, max 2 rounds)
  Phase 3: ModeratorAgent synthesis (entry/exit strategy, outlook, what-could-change)
→ Recommendation + SectorAnalysis
```

### Position Enum (Investment Opportunity Framing)
- `STRONG_BUY` / `BUY` — good opportunity at current price
- `WAIT` — not yet, wait for better entry (old: HOLD)
- `AVOID` — don't buy now, poor risk/reward (old: SELL)
- `STRONG_AVOID` — stay away entirely (old: STRONG_SELL)
- `_parse_position()` in `base_agent.py` maps old values from LLM output

### Key Layers

- **`src/data_collectors/`** — Fetch stock data from external APIs. All inherit `BaseCollector` (Template Method pattern with TTL caching). `aggregator.py` runs 8 collectors in parallel via `asyncio.gather`: price, fundamentals, technical, news (finviz), reddit (8 subreddits), fear_greed, world_news (Google News RSS, 17 search terms), twitter (Nitter RSS, 19 accounts incl. POTUS, Fed, Goldman, Buffett).

- **`src/agents/`** — Multi-agent debate system. 5 specialist agents inherit `BaseAgent`, each has a specialized prompt (`config/prompts/*.md`) framed as investment opportunity advisor. `SectorAnalystAgent` is separate (doesn't inherit BaseAgent). `debate_engine.py` orchestrates all phases. `llm_provider.py` abstracts Gemini/Groq/Ollama.

- **`src/models/`** — Pydantic data models. `Position` enum uses BUY/WAIT/AVOID. `Recommendation` has ~25 fields including detailed entry/exit strategy (aggressive/conservative), dual stop-loss, multi-timeframe outlook, what-could-change, influential figures. `DebateTranscript` includes sector_analysis dict.

- **`src/services/`** — `AnalysisService` is the top-level orchestrator. `PortfolioService` handles CSV import.

- **`streamlit_app/`** — Streamlit dashboard showing: entry/exit strategy (most prominent), bull/bear case, multi-timeframe outlook (6mo/1yr/long-term), what-could-change section, influential figures, sector impact analysis (3 timeframes), social media summaries (Reddit + Twitter), world news impact, full debate transcript.

- **`config/settings.py`** — All configuration via Pydantic Settings / env vars. Single source of truth for API keys, model selection, cache TTLs, watchlist.

### LLM Provider Abstraction
`src/agents/llm_provider.py` — `LLMProvider` ABC with `GeminiProvider`, `GroqProvider`, and `OllamaProvider`. Switch via `LLM_PROVIDER` env var. Current production: Ollama with qwen2.5:32b.

### Agent Debate Protocol
- Phase 1: Each agent calls `analyze()` independently (sequential with delay for API, parallel-safe for Ollama)
- Sector: `SectorAnalystAgent.analyze()` maps world events to 12 sectors across 3 timeframes
- Phase 2: Each agent calls `debate_respond()` seeing others' positions (1-2 rounds)
- Phase 3: `ModeratorAgent.synthesize()` produces final `Recommendation` with entry/exit strategy, outlook, what-could-change
- All outputs are structured JSON; robust parsing handles $-prefixed prices, trailing commas, dict-as-string errors, old HOLD/SELL values
- `TokenBudget` tracks usage

### JSON Parsing Helpers (in base_agent.py)
- `_extract_json()` — handles code blocks, trailing commas, comments, control chars
- `_clean_price()` — handles "$160", "$171.03 (support level)", percentages
- `_clean_string_list()` — converts dicts to strings for concessions
- `_parse_position()` — maps old HOLD/SELL to new WAIT/AVOID via `_POSITION_MAP`

## Environment Variables
See `.env.example`. For Ollama (recommended): set `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen2.5:32b`. No API keys needed for core functionality.
