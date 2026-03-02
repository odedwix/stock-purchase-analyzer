# Stock Purchase Analyzer

AI-powered multi-agent stock analysis system. Uses specialist AI agents that debate each other to produce investment recommendations.

## How It Works

Five AI agents — Stock Analyst, Sentiment Specialist, Risk Manager, Macro Economist, and Technical Analyst — independently analyze a stock, then debate their positions across multiple rounds. A Moderator synthesizes the debate into a final recommendation with entry/exit points, risk/reward assessment, and confidence level.

## Quick Start

### 1. Install

```bash
# Clone and install
cd stock_purchase_analyzer
uv pip install -e ".[dev]"

# Copy env template and add your Gemini API key
cp .env.example .env
# Edit .env and set GEMINI_API_KEY (free at https://aistudio.google.com)
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

- **Multi-agent debate**: 5 specialist agents + moderator
- **Zero cost**: Uses Google Gemini free tier (15 req/min, 1M tokens/day)
- **Ollama fallback**: Run local models on your Mac if rate limited
- **Data sources**: yfinance (prices, fundamentals), pandas-ta (technical indicators)
- **CSV import**: Import your purchase history
- **Streamlit dashboard**: Visual recommendations with debate transcripts

## Default Watchlist

NVDA, AAPL, MSFT, GOOGL, META, AMZN, JETS, WIX

## API Keys

| Service | Required | Cost | Get it at |
|---------|----------|------|-----------|
| Google Gemini | Yes | Free | [aistudio.google.com](https://aistudio.google.com) |
| Reddit (PRAW) | No | Free | [reddit.com/prefs/apps](https://reddit.com/prefs/apps) |
| NewsAPI | No | Free | [newsapi.org](https://newsapi.org) |
| FRED | No | Free | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
