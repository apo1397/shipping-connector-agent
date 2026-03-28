"""Postman collection fetcher and parser."""

import json
import logging
import httpx
from typing import Any
from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class PostmanFetcher(BaseFetcher):
    """Fetches and parses Postman collection JSON."""

    async def fetch(self, url: str, timeout: int = 30) -> FetchResult:
        """Fetch a Postman collection."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                collection = response.json()
                
                # Validate Postman collection structure
                if "info" not in collection or "item" not in collection:
                    raise ValueError("Not a valid Postman collection")
                
                # Extract endpoints into markdown format
                markdown = self._collection_to_markdown(collection)
                
                return FetchResult(
                    content_type="postman",
                    raw_text=markdown,
                    structured_data=collection,
                )
        except httpx.HTTPError as e:
            raise IOError(f"Failed to fetch Postman collection: {e}")
        except json.JSONDecodeError:
            raise ValueError("Response is not valid JSON")

    def _collection_to_markdown(self, collection: dict[str, Any]) -> str:
        """Convert Postman collection to markdown."""
        lines = []
        info = collection.get("info", {})
        
        lines.append(f"# {info.get('name', 'API Collection')}")
        if info.get("description"):
            lines.append(f"\n{info['description']}\n")
        
        lines.append("\n## Endpoints\n")
        
        self._process_items(collection.get("item", []), lines)
        
        return "\n".join(lines)

    def _process_items(self, items: list[dict], lines: list[str], depth: int = 1) -> None:
        """Recursively process Postman items (folders and requests)."""
        for item in items:
            if "item" in item:
                # It's a folder
                lines.append(f"{'#' * (depth + 1)} {item['name']}\n")
                self._process_items(item["item"], lines, depth + 1)
            elif "request" in item:
                # It's a request
                req = item["request"]
                method = req.get("method", "GET")
                url = self._get_url(req.get("url"))
                desc = item.get("description", "")
                
                lines.append(f"### {item['name']}")
                lines.append(f"- **Method**: {method}")
                lines.append(f"- **URL**: {url}")
                if desc:
                    lines.append(f"- **Description**: {desc}")
                
                # Add request body if present
                body = req.get("body")
                if body and body.get("mode") == "raw":
                    lines.append("- **Request Body**:")
                    lines.append(f"  ```json")
                    lines.append(f"  {body.get('raw', '')}")
                    lines.append(f"  ```")
                
                lines.append("")

    def _get_url(self, url_obj: Any) -> str:
        """Extract URL from Postman URL object."""
        if isinstance(url_obj, str):
            return url_obj
        elif isinstance(url_obj, dict):
            if "raw" in url_obj:
                return url_obj["raw"]
            elif "host" in url_obj:
                protocol = url_obj.get("protocol", "https")
                host = ".".join(url_obj["host"]) if isinstance(url_obj["host"], list) else url_obj["host"]
                path = "/" + "/".join(url_obj.get("path", [])) if url_obj.get("path") else ""
                return f"{protocol}://{host}{path}"
        return ""
