"""Postman collection fetcher and parser."""

import json
import logging
import re
import httpx
from typing import Any
from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)

# Matches both:
#   https://documenter.getpostman.com/view/27749698/2s93mBwyZ1
#   https://documenter.getpostman.com/view/27749698/2s93mBwyZ1#anchor
_DOCUMENTER_RE = re.compile(
    r"documenter\.getpostman\.com/view/(\d+)/([A-Za-z0-9]+)"
)


class PostmanFetcher(BaseFetcher):
    """Fetches and parses Postman collection JSON.

    Handles two kinds of Postman URLs:
      1. Documenter share pages — https://documenter.getpostman.com/view/{uid}/{pubId}
         These are SPA HTML pages; the real JSON lives on the gw.postman.com gateway.
      2. Direct JSON exports — any URL that returns Postman collection JSON directly.
    """

    async def fetch(self, url: str, timeout: int = 30) -> FetchResult:
        m = _DOCUMENTER_RE.search(url)
        if m:
            return await self._fetch_from_documenter(m.group(1), m.group(2), timeout)
        return await self._fetch_direct_json(url, timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_from_documenter(
        self, owner_id: str, published_id: str, timeout: int
    ) -> FetchResult:
        """Use the Postman gateway API to get the raw collection JSON."""
        api_url = (
            f"https://documenter.gw.postman.com/api/collections"
            f"/{owner_id}/{published_id}"
        )
        params = {"segregateAuth": "true", "versionTag": "latest"}
        headers = {
            "Origin": "https://documenter.getpostman.com",
            "Referer": "https://documenter.getpostman.com/",
        }
        logger.info(f"Fetching Postman collection via gateway: {api_url}")
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(api_url, params=params, headers=headers)
                response.raise_for_status()
                collection = response.json()
        except httpx.HTTPError as e:
            raise IOError(f"Failed to fetch Postman collection via gateway: {e}")
        except json.JSONDecodeError:
            raise ValueError("Gateway response is not valid JSON")

        return self._parse_collection(collection)

    async def _fetch_direct_json(self, url: str, timeout: int) -> FetchResult:
        """Fetch a direct Postman collection JSON export URL."""
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                collection = response.json()
        except httpx.HTTPError as e:
            raise IOError(f"Failed to fetch Postman collection: {e}")
        except json.JSONDecodeError:
            raise ValueError("Response is not valid JSON")

        return self._parse_collection(collection)

    def _parse_collection(self, collection: dict[str, Any]) -> FetchResult:
        if "info" not in collection or "item" not in collection:
            raise ValueError("Not a valid Postman collection")
        markdown = self._collection_to_markdown(collection)
        return FetchResult(content_type="postman", raw_text=markdown, structured_data=collection)

    # ------------------------------------------------------------------
    # Markdown conversion
    # ------------------------------------------------------------------

    def _collection_to_markdown(self, collection: dict[str, Any]) -> str:
        lines: list[str] = []
        info = collection.get("info", {})
        lines.append(f"# {info.get('name', 'API Collection')}")
        if info.get("description"):
            lines.append(f"\n{info['description']}\n")

        # Collection-level auth
        auth = collection.get("auth")
        if auth:
            lines.append(f"\n## Collection-level Auth\nType: {auth.get('type', 'unknown')}")
            for key, val in auth.items():
                if key != "type":
                    lines.append(f"- {key}: {json.dumps(val)}")

        lines.append("\n## Endpoints\n")
        self._process_items(collection.get("item", []), lines)
        return "\n".join(lines)

    def _process_items(self, items: list[dict], lines: list[str], depth: int = 1) -> None:
        for item in items:
            if "item" in item:
                # Folder
                lines.append(f"{'#' * (depth + 1)} {item['name']}\n")
                folder_auth = item.get("auth")
                if folder_auth:
                    lines.append(f"Auth: {folder_auth.get('type', 'unknown')}")
                self._process_items(item["item"], lines, depth + 1)
            elif "request" in item:
                req = item["request"]
                method = req.get("method", "GET")
                url = self._get_url(req.get("url"))
                desc = item.get("description", "") or req.get("description", "")

                lines.append(f"### {item['name']}")
                lines.append(f"- **Method**: {method}")
                lines.append(f"- **URL**: {url}")
                if desc:
                    lines.append(f"- **Description**: {desc}")

                # Headers
                for h in req.get("header", []):
                    if lines[-1] != "- **Headers**:":
                        lines.append("- **Headers**:")
                    lines.append(f"  - {h.get('key')}: {h.get('value')}")

                # Per-request auth
                req_auth = req.get("auth")
                if req_auth:
                    lines.append(f"- **Auth**: {req_auth.get('type', 'unknown')}")

                # Query params
                url_obj = req.get("url", {})
                if isinstance(url_obj, dict):
                    for q in url_obj.get("query", []):
                        if lines[-1] != "- **Query Params**:":
                            lines.append("- **Query Params**:")
                        lines.append(
                            f"  - {q.get('key')}: {q.get('value', '')} "
                            f"({q.get('description', '')})"
                        )

                # Request body
                body = req.get("body")
                if body and body.get("mode") == "raw":
                    lines.append("- **Request Body**:")
                    lines.append("  ```json")
                    lines.append(f"  {body.get('raw', '')}")
                    lines.append("  ```")

                lines.append("")

    def _get_url(self, url_obj: Any) -> str:
        if isinstance(url_obj, str):
            return url_obj
        if isinstance(url_obj, dict):
            if "raw" in url_obj:
                return url_obj["raw"]
            protocol = url_obj.get("protocol", "https")
            host = url_obj.get("host", [])
            host_str = ".".join(host) if isinstance(host, list) else host
            path = url_obj.get("path", [])
            path_str = "/" + "/".join(p for p in path if p) if path else ""
            return f"{protocol}://{host_str}{path_str}"
        return ""
