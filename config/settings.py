from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = Path(__file__).parent / "prompts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Provider
    llm_provider: str = Field(default="gemini", description="gemini or ollama")

    # Google Gemini
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_agent_model: str = Field(
        default="gemini-2.5-flash", description="Model for agent reasoning"
    )
    gemini_summarizer_model: str = Field(
        default="gemini-2.0-flash", description="Model for data summarization"
    )

    # Ollama
    ollama_host: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1:70b")

    # Reddit
    reddit_client_id: str = Field(default="")
    reddit_client_secret: str = Field(default="")
    reddit_user_agent: str = Field(default="stock_analyzer/0.1")

    # NewsAPI
    newsapi_key: str = Field(default="")

    # FRED
    fred_api_key: str = Field(default="")

    # Token budget (Gemini free tier limits)
    max_requests_per_minute: int = Field(default=15)
    max_tokens_per_day: int = Field(default=1_000_000)

    # Cache TTL (seconds)
    price_cache_ttl: int = Field(default=900, description="15 minutes")
    fundamentals_cache_ttl: int = Field(default=86400, description="24 hours")
    news_cache_ttl: int = Field(default=1800, description="30 minutes")
    sentiment_cache_ttl: int = Field(default=3600, description="1 hour")

    # Default watchlist
    default_watchlist: list[str] = Field(
        default=["NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "JETS", "WIX"]
    )

    # Stock filters
    min_market_cap: float = Field(
        default=2_000_000_000, description="Minimum market cap ($2B) to filter penny stocks"
    )


settings = Settings()
