"""Base fetcher interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class FetchResult:
    """Result of fetching a URL."""

    content_type: str  # "postman" | "openapi" | "webpage" | "pdf"
    raw_text: str  # Extracted text content
    structured_data: Optional[dict] = None  # Parsed JSON/YAML if applicable


class BaseFetcher(ABC):
    """Abstract base for URL fetchers."""

    @abstractmethod
    async def fetch(self, url: str, timeout: int = 30) -> FetchResult:
        """Fetch and parse a URL."""
        ...
