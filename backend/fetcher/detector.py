"""URL type detector and fetcher dispatcher."""

import json
import logging
import re
import httpx
from typing import Any, Optional
from urllib.parse import urlparse
from .base import FetchResult
from .postman import PostmanFetcher

logger = logging.getLogger(__name__)

# Matches markdown headings: captures hashes and title text
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


class FetcherDetector:
    """Detects URL type and dispatches to appropriate fetcher."""

    def __init__(self):
        self.postman_fetcher = PostmanFetcher()

    async def fetch(
        self,
        url: str,
        timeout: int = 30,
        sections: Optional[list[str]] = None,
    ) -> FetchResult:
        """Detect URL type, fetch, and optionally filter to specific sections.

        Args:
            url: The URL to fetch.
            timeout: Request timeout in seconds.
            sections: Optional list of section names to include. Matched
                      case-insensitively against top-level headings in the
                      rendered markdown. Works for any content type — Postman
                      collections, OpenAPI specs, webpages, PDFs, etc.
        """
        parsed = urlparse(url)

        if self._is_postman_url(url, parsed):
            logger.info(f"Detected Postman collection: {url}")
            try:
                result = await self.postman_fetcher.fetch(url, timeout)
            except (ValueError, IOError) as e:
                logger.warning(f"Postman fetch failed ({e}), falling back to raw fetch...")
                result = await self._fetch_raw(url, timeout)
        else:
            logger.info(f"Fetching as raw text: {url}")
            result = await self._fetch_raw(url, timeout)

        if sections:
            result = self._apply_sections_filter(result, sections)

        return result

    # ------------------------------------------------------------------
    # Section filtering — generic post-processing on FetchResult
    # ------------------------------------------------------------------

    def _apply_sections_filter(self, result: FetchResult, sections: list[str]) -> FetchResult:
        """Filter a FetchResult to only include the requested sections.

        Works on any content type by scanning ``raw_text`` for markdown headings
        and extracting the matching blocks.  For Postman collections,
        ``structured_data["item"]`` is also pruned to stay consistent with the
        filtered text.
        """
        lower_sections = {s.lower() for s in sections}

        filtered_text = _filter_markdown_sections(result.raw_text, lower_sections)

        # Keep structured_data in sync for Postman collections
        filtered_data = result.structured_data
        if (
            result.content_type == "postman"
            and filtered_data
            and "item" in filtered_data
        ):
            filtered_data = {
                **filtered_data,
                "item": [
                    item for item in filtered_data["item"]
                    if item.get("name", "").lower() in lower_sections
                ],
            }
            logger.info(f"Filtered Postman collection to sections: {sections}")

        return FetchResult(
            content_type=result.content_type,
            raw_text=filtered_text,
            structured_data=filtered_data,
        )

    # ------------------------------------------------------------------
    # Raw fallback fetch
    # ------------------------------------------------------------------

    async def _fetch_raw(self, url: str, timeout: int) -> FetchResult:
        """Generic fallback: fetch URL and return raw text content."""
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            text = response.text
            try:
                data = json.loads(text)
                return FetchResult(content_type="openapi", raw_text=text, structured_data=data)
            except (json.JSONDecodeError, ValueError):
                pass
            return FetchResult(content_type="webpage", raw_text=text, structured_data=None)

    def _is_postman_url(self, url: str, parsed: Any) -> bool:
        """Check if URL is a Postman collection (documenter page or direct JSON export)."""
        lower = url.lower()
        if "documenter.getpostman.com/view/" in lower:
            return True
        if lower.endswith(".postman_collection.json"):
            return True
        if "postman" in lower and lower.endswith(".json"):
            return True
        return False


def _filter_markdown_sections(text: str, lower_sections: set[str]) -> str:
    """Extract sections from markdown text whose headings match ``lower_sections``.

    Algorithm:
    - Lines before the first matching heading are treated as preamble and kept.
    - A section starts at a heading whose stripped, lowercased title is in
      ``lower_sections`` and ends just before the next heading at the same or
      shallower depth, or end-of-text.
    - Sections not in ``lower_sections`` are dropped.

    This is content-type agnostic: any fetcher that emits markdown headings
    benefits from this filter automatically.
    """
    lines = text.split("\n")
    output: list[str] = []
    preamble_done = False   # True once we've passed the first heading of any kind
    in_target = False
    target_depth: int = 0

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            depth = len(m.group(1))
            title = m.group(2).strip().lower()

            if title in lower_sections:
                # Start of a matching section
                in_target = True
                target_depth = depth
                preamble_done = True
                output.append(line)
            elif in_target and depth <= target_depth:
                # Heading at same/higher level ends the current section
                in_target = False
            elif not in_target:
                # Non-matching heading outside a target section — skip, but
                # mark preamble as done so we stop emitting preamble lines
                preamble_done = True
        else:
            if in_target:
                output.append(line)
            elif not preamble_done:
                # Still in preamble — keep these lines (title, description, etc.)
                output.append(line)

    return "\n".join(output).strip()
