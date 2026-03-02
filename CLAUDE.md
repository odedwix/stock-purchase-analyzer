# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent AI stock analysis system. Uses Google Gemini (free tier) to run 5 specialist AI agents that debate and produce investment recommendations based on fundamentals, sentiment, technicals, macro, and risk analysis.

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
User selects stock → DataAggregator (parallel collectors) → StockDataPackage
→ DebateEngine (Phase 1: independent analysis, Phase 2: debate, Phase 3: synthesis)
→ Recommendation (entry/exit/stop-loss, bull/bear case, confidence)
```

### Key Layers

- **`src/data_collectors/`** — Fetch stock data from external APIs. All inherit `BaseCollector` (Template Method pattern with TTL caching). `aggregator.py` runs all collectors in parallel via `asyncio.gather`.

- **`src/agents/`** — Multi-agent debate system. Each agent inherits `BaseAgent`, has a specialized system prompt (`config/prompts/*.md`), and receives only its relevant data slice. `debate_engine.py` orchestrates the 3-phase debate. `llm_provider.py` abstracts Gemini/Ollama.

- **`src/models/`** — Pydantic data models. `StockDataPackage` carries all collected data. `AgentAnalysis` / `DebateResponse` / `Recommendation` structure agent outputs. Agents return structured JSON parsed into these models.

- **`src/services/`** — `AnalysisService` is the top-level orchestrator. `PortfolioService` handles CSV import.

- **`streamlit_app/`** — Streamlit dashboard with pages for analysis, portfolio, sentiment.

- **`config/settings.py`** — All configuration via Pydantic Settings / env vars. Single source of truth for API keys, model selection, cache TTLs, watchlist.

### LLM Provider Abstraction
`src/agents/llm_provider.py` — `LLMProvider` ABC with `GeminiProvider` and `OllamaProvider`. Agents don't import LLM SDKs directly. Switch providers via `LLM_PROVIDER` env var.

### Agent Debate Protocol
- Phase 1: Each agent calls `analyze()` independently (parallel)
- Phase 2: Each agent calls `debate_respond()` seeing others' positions (1-2 rounds)
- Phase 3: `ModeratorAgent.synthesize()` produces final `Recommendation`
- All outputs are structured JSON matching Pydantic models
- `TokenBudget` tracks usage to stay within Gemini free tier limits

## Environment Variables
See `.env.example`. Required: `GEMINI_API_KEY`. Everything else is optional.
