import logging
from abc import ABC, abstractmethod
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Abstract base class for all data collectors.

    Provides in-memory TTL caching. Subclasses implement _fetch_raw() and _transform().
    """

    def __init__(self, cache_ttl: int = 900, cache_maxsize: int = 100):
        self._cache = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl)

    def _cache_key(self, symbol: str) -> str:
        return f"{self.__class__.__name__}:{symbol}"

    async def collect(self, symbol: str) -> Any:
        """Collect data for a symbol, using cache if available."""
        key = self._cache_key(symbol)
        if key in self._cache:
            logger.debug(f"Cache hit: {key}")
            return self._cache[key]

        try:
            raw = await self._fetch_raw(symbol)
            result = self._transform(symbol, raw)
            self._cache[key] = result
            return result
        except Exception as e:
            logger.error(f"{self.__class__.__name__} failed for {symbol}: {e}")
            raise

    @abstractmethod
    async def _fetch_raw(self, symbol: str) -> Any:
        """Fetch raw data from external source."""
        ...

    @abstractmethod
    def _transform(self, symbol: str, raw: Any) -> Any:
        """Transform raw data into a structured model."""
        ...
