"""URL type detector and fetcher dispatcher."""

import logging
from urllib.parse import urlparse
from .base import BaseFetcher, FetchResult
from .postman import PostmanFetcher

logger = logging.getLogger(__name__)


class FetcherDetector:
    """Detects URL type and dispatches to appropriate fetcher."""

    def __init__(self):
        self.postman_fetcher = PostmanFetcher()

    async def fetch(self, url: str, timeout: int = 30) -> FetchResult:
        """Detect URL type and fetch."""
        parsed = urlparse(url)
        
        # Check for Postman collection
        if self._is_postman_url(url, parsed):
            logger.info(f"Detected Postman collection: {url}")
            return await self.postman_fetcher.fetch(url, timeout)
        
        # Fallback to Postman (most common format)
        # In Phase 3, we'll add OpenAPI, webpage, and PDF fetchers
        logger.warning(f"No fetcher matched for {url}, attempting Postman...")
        return await self.postman_fetcher.fetch(url, timeout)

    def _is_postman_url(self, url: str, parsed: Any) -> bool:
        """Check if URL is likely a Postman collection."""
        if url.endswith(".json"):
            return True
        if "postman" in url.lower():
            return True
        if "api-collection" in parsed.path.lower():
            return True
        return False
