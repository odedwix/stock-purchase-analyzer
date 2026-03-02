# Stock Purchase Analyzer

AI-powered multi-agent stock analysis system. Uses specialist AI agents that debate each other to produce investment opportunity recommendations.

## How It Works

Five AI agents — Stock Analyst, Sentiment Specialist, Risk Manager, Macro Economist, and Technical Analyst — independently analyze a stock in parallel, then debate their positions across multiple rounds. A Sector Analyst maps world events to sectors/ETFs. A Moderator synthesizes the debate into a final recommendation with entry/exit strategy, risk/reward assessment, and confidence level.

## Quick Start

### 1. Install

```bash
# Clone and install
cd stock_purchase_analyzer
uv pip install -e ".[dev,sentiment,economic,ollama]"

# Copy env template and configure your LLM provider
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY for fastest results, or use Ollama for free local inference
```

### 2. Run

**Dashboard:**
```bash
streamlit run streamlit_app/app.py
```

**CLI:**
```bash
python scripts/run_analysis.py NVDA
```

## Features

- **Multi-agent debate**: 5 specialist agents + sector analyst + moderator
- **Parallel execution**: All agents run concurrently (~15-25s with Anthropic API)
- **Live progress UI**: Real-time status updates showing each analysis phase
- **Multiple LLM providers**: Anthropic Claude (recommended), Ollama (free local), Groq, Gemini
- **10 data collectors**: Price, fundamentals, technicals, news, Reddit, Twitter/X, world news, Fear & Greed, economic indicators, insider trading
- **Free data sources**: VIX, Treasury yields, S&P 500, Dollar Index, SEC insider trades — no API keys needed
- **CSV import**: Import your purchase history
- **Streamlit dashboard**: Visual recommendations with entry/exit strategy, debate transcripts, sector analysis

## Default Watchlist

NVDA, AAPL, MSFT, GOOGL, META, AMZN, JETS, WIX

## API Keys

| Service | Required | Cost | Get it at |
|---------|----------|------|-----------|
| Anthropic Claude | Recommended | ~$0.01/analysis | [console.anthropic.com](https://console.anthropic.com) |
| Ollama (local) | Alternative | Free | [ollama.com](https://ollama.com) |
| Groq | Alternative | Free tier | [console.groq.com](https://console.groq.com/keys) |
| Google Gemini | Alternative | Free tier | [aistudio.google.com](https://aistudio.google.com) |
| Reddit (PRAW) | No | Free | [reddit.com/prefs/apps](https://reddit.com/prefs/apps) |
| NewsAPI | No | Free | [newsapi.org](https://newsapi.org) |
| FRED | No | Free | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
