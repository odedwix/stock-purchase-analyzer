# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent AI stock **investment opportunity** analyzer. Uses Anthropic Claude Haiku 4.5 (default) or Groq (free tier) to run 5 specialist AI agents + 1 sector analyst that debate and produce recommendations: should you BUY, WAIT, or AVOID? Evaluates stocks the user does NOT own — framed as opportunity scanning, not position management. Collects world news, Reddit, Twitter/X, stock news, Fear & Greed, economic indicators, insider trading, employee sentiment, quarterly earnings, analyst actions, and institutional holders.

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
User selects stock → DataAggregator (11 parallel collectors) → StockDataPackage
→ DebateEngine:
  Phase 1: 5 agents + sector analyst analyze in parallel (Anthropic/Ollama) or sequential (Groq/Gemini)
  Phase 2: debate rounds (skip if consensus, max 2 rounds)
  Phase 3: ModeratorAgent synthesis (entry/exit strategy, outlook, what-could-change, moat assessment)
→ Recommendation + SectorAnalysis → saved to SQLite
```

### Position Enum (Investment Opportunity Framing)
- `STRONG_BUY` / `BUY` — good opportunity at current price
- `WAIT` — not yet, wait for better entry (old: HOLD)
- `AVOID` — don't buy now, poor risk/reward (old: SELL)
- `STRONG_AVOID` — stay away entirely (old: STRONG_SELL)
- `_parse_position()` in `base_agent.py` maps old values from LLM output

### Key Layers

- **`src/data_collectors/`** — Fetch stock data from external APIs. All inherit `BaseCollector` (Template Method pattern with TTL caching). `aggregator.py` runs 11 collectors in parallel via `asyncio.gather`: price, fundamentals (+ quarterly earnings, analyst actions, institutional holders, competitors, earnings news RSS, business description, dividend history), technical, news (finviz), reddit (8 subreddits), fear_greed, world_news (Google News RSS, 17 search terms), twitter (Nitter RSS, 19 accounts incl. POTUS, Fed, Goldman, Buffett), economic (VIX, Treasury yields, S&P 500, Dollar Index via yfinance), insider (SEC EDGAR Form 4 filings), employee_sentiment (career subreddits + Google News RSS with relevance scoring and recurring issue detection).

- **`src/agents/`** — Multi-agent debate system. 5 specialist agents inherit `BaseAgent`, each has a specialized prompt (`config/prompts/*.md`) framed as investment opportunity advisor. Stock analyst prompt includes business model & competitive moat analysis (section 4b). `SectorAnalystAgent` is separate (doesn't inherit BaseAgent). `debate_engine.py` orchestrates all phases with parallel execution for Anthropic/Ollama. `llm_provider.py` abstracts Anthropic/Gemini/Groq/Ollama. Moderator outputs `moat_assessment` (WIDE/NARROW/NONE).

- **`src/models/`** — Pydantic data models. `Position` enum uses BUY/WAIT/AVOID. `FundamentalsData` includes business_description, quarterly_earnings, analyst_actions, top_institutional_holders, competitor_tickers, earnings_news, dividend_history_summary. `EmployeeSentimentData` includes recurring_issues detection. `Recommendation` has ~27 fields including detailed entry/exit strategy, dual stop-loss, multi-timeframe outlook, what-could-change, influential figures, moat_assessment. `DebateTranscript` includes sector_analysis dict.

- **`src/services/`** — `AnalysisService` is the top-level orchestrator. `PortfolioService` handles CSV import.

- **`src/db/`** — SQLite persistence. `database.py` manages schema (analyses + market_snapshots tables). `analysis_repo.py` provides CRUD: `save_analysis()`, `list_analyses()`, `get_analysis()`, `get_analyses_for_comparison()`, `delete_analysis()`.

- **`streamlit_app/`** — Streamlit dashboard showing: market overview (VIX, Fear & Greed, S&P 500), sector performance, quick look (fundamentals + charts + business overview + quarterly earnings + analyst actions + institutional holders), LLM provider toggle (Anthropic/Groq), past analysis dropdown (loads from SQLite), entry/exit strategy (most prominent), moat assessment, bull/bear case, multi-timeframe outlook (6mo/1yr/long-term), what-could-change section, influential figures, sector impact analysis (3 timeframes), social media summaries (Reddit + Twitter), world news impact, employee sentiment with recurring issues, full debate transcript with rebuttals.

- **`config/settings.py`** — All configuration via Pydantic Settings / env vars. Single source of truth for API keys, model selection, cache TTLs, watchlist. Default provider: Anthropic.

### LLM Provider Abstraction
`src/agents/llm_provider.py` — `LLMProvider` ABC with `AnthropicProvider`, `GeminiProvider`, `GroqProvider`, and `OllamaProvider`. Switch via `LLM_PROVIDER` env var or sidebar toggle. Default: Anthropic with claude-haiku-4-5-20251001. Fallback: Ollama with qwen2.5:32b.

### Agent Debate Protocol
- Phase 1: Each agent calls `analyze()` independently (parallel for Anthropic/Ollama, sequential with delay for Groq/Gemini)
  - `debate_engine.py`: `_run_single_agent` logs per-agent results (position, confidence, argument count)
  - Detailed data enrichment via `_format_data`:
    - Stock Analyst: business overview, quarterly earnings, analyst actions, institutional holders, dividend history, insider trading, short interest, beta, competitors
    - Sentiment Specialist: employee sentiment with recurring issues
    - Macro Economist: business description and employee count
- Sector: `SectorAnalystAgent.analyze()` maps world events to 12 sectors across 3 timeframes
- Phase 2: Each agent calls `debate_respond()` seeing others' positions (1-2 rounds)
  - `_run_single_debate` preserves Phase 1 position/confidence on failure instead of defaulting to WAIT/0
  - Better error type logging
- Phase 3: `ModeratorAgent.synthesize()` produces final `Recommendation` with entry/exit strategy, outlook, what-could-change, moat_assessment
- All outputs are structured JSON; robust parsing handles $-prefixed prices, trailing commas, dict-as-string errors, old HOLD/SELL values
- `TokenBudget` tracks usage

### JSON Parsing Helpers (in base_agent.py)
- `analyze()` — robust parsing with 5 fallback levels:
  - Uses `.get()` with fallbacks for key_arguments (claim→argument→point, evidence→data→support→reasoning)
  - Normalizes strength values to valid Literal ("strong"|"moderate"|"weak") before Pydantic creation
  - Clamps confidence to 0-100 range before passing to model
  - Catches all exceptions including Pydantic ValidationError
  - Phase 1 fallback extracts position & confidence from raw text instead of hardcoding WAIT/30%
  - Logs input/output char counts, token counts, first 500 chars on parse failure
- `_extract_json()` — handles code blocks, trailing commas, comments, control chars, unescaped raw_reasoning
  - Added regex-based partial extraction as last resort (extracts position, confidence, key_arguments individually)
  - Better error recovery chain with 5 fallback levels
- `_clean_price()` — handles "$160", "$171.03 (support level)", percentages
- `_clean_string_list()` — converts dicts to strings for concessions
- `_parse_position()` — maps old HOLD/SELL to new WAIT/AVOID via `_POSITION_MAP`
- `_format_others_positions()` — handles both dict and Pydantic Argument objects for key_arguments; includes raw reasoning snippet when agent has no key_arguments (fallback display)

### Business Intelligence Data (in FundamentalsCollector)
- `business_description` — company overview from yfinance (truncated to 600 chars)
- `quarterly_earnings` — last 8 quarters EPS actual vs estimate with beat/miss and surprise %
- `analyst_actions` — last 15 analyst upgrades/downgrades from yfinance
- `top_institutional_holders` — top 10 institutional holders with % and shares
- `competitor_tickers` — same-industry peers via `yf.Industry()`
- `earnings_news` — Google News RSS for recent earnings call headlines
- `dividend_history_summary` — payment history and annual total

### Employee Sentiment (in EmployeeSentimentCollector)
- Searches 6 career subreddits + 9 Google News RSS queries per company
- Relevance scoring filters out posts that don't mention the company
- Recurring issue detection: cross-references Reddit + News for themes (layoffs, management, culture, etc.)
- 10 theme categories with keyword detection

### Analysis Persistence
- SQLite database at `data/analyses.db` (auto-created)
- Every analysis saved automatically after completion
- History dropdown on main dashboard loads past analyses
- Comparison view on Analysis History page (2-4 side-by-side)

## Environment Variables
See `.env.example`. For Anthropic (default, recommended): set `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=your_key`, `ANTHROPIC_MODEL=claude-haiku-4-5-20251001`. For Groq (free tier): set `LLM_PROVIDER=groq`, `GROQ_API_KEY=your_key`. For Ollama (free, local): set `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen2.5:32b`.
