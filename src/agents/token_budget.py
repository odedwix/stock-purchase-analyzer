import logging
import time

logger = logging.getLogger(__name__)


class TokenBudget:
    """Tracks and enforces token spending within a single analysis run.

    Designed to stay within Gemini free tier limits:
    - 15 requests per minute
    - 1M tokens per day
    """

    def __init__(
        self,
        max_requests_per_minute: int = 15,
        max_tokens_per_day: int = 1_000_000,
    ):
        self.max_rpm = max_requests_per_minute
        self.max_daily_tokens = max_tokens_per_day

        # Per-analysis tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.request_count = 0
        self.request_timestamps: list[float] = []

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.request_count += 1
        self.request_timestamps.append(time.time())

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def can_make_request(self) -> bool:
        """Check if we can make another request within rate limits."""
        now = time.time()
        # Count requests in the last 60 seconds
        recent = [t for t in self.request_timestamps if now - t < 60]
        return len(recent) < self.max_rpm

    async def wait_if_needed(self) -> None:
        """Wait if we're at the rate limit."""
        import asyncio

        while not self.can_make_request():
            logger.info("Rate limit approaching, waiting 5s...")
            await asyncio.sleep(5)

    def summary(self) -> dict:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "request_count": self.request_count,
        }
