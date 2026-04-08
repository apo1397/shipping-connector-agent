"""API discovery - identifies tracking and auth endpoints from documentation."""

from typing import Optional, Union, Any
import logging
from pydantic import BaseModel
from backend.models import DiscoveredEndpoint, ParsedAPISpec
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

# Max chars of documentation to send to the LLM — keeps prompts fast and within context limits
_MAX_DOC_CHARS = 12_000


class APIDiscoveryAnalyzer:
    """Analyzes documentation to discover tracking and auth APIs."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def _truncate(self, documentation: str) -> str:
        """Trim very large docs to avoid slow / over-budget LLM calls."""
        if len(documentation) > _MAX_DOC_CHARS:
            logger.warning(
                f"Documentation truncated {len(documentation)} → {_MAX_DOC_CHARS} chars "
                f"(dropped {len(documentation) - _MAX_DOC_CHARS} chars)"
            )
            return documentation[:_MAX_DOC_CHARS] + "\n\n[... truncated ...]"
        logger.debug(f"Documentation within limit: {len(documentation)} chars")
        return documentation

    async def discover_tracking_api(
        self, documentation: str, provider_hint: str = ""
    ) -> DiscoveredEndpoint:
        """Discover the tracking API endpoint."""
        logger.info(
            f"Discovering tracking API | provider_hint={provider_hint!r} "
            f"doc_chars={len(documentation)}"
        )
        documentation = self._truncate(documentation)

        system = (
            "You are an API documentation expert specializing in shipping and logistics. "
            "Identify the shipment tracking endpoint — the one that accepts an AWB/tracking number "
            "and returns shipment status and location. Exclude order creation, manifest, or pickup APIs."
        )
        hint = f"Provider: {provider_hint}\n\n" if provider_hint else ""
        user = (
            f"{hint}API Documentation:\n\n{documentation}\n\n"
            "Return the tracking endpoint as JSON."
        )

        try:
            result = await self.llm.complete(
                system=system, user=user, response_format=DiscoveredEndpoint
            )
            if isinstance(result, DiscoveredEndpoint):
                logger.info(
                    f"Tracking API discovered | name={result.name!r} "
                    f"method={result.method} url={result.url} "
                    f"auth_type={getattr(result, 'auth_type', 'unknown')!r}"
                )
                return result
            raise ValueError("Expected DiscoveredEndpoint response")
        except Exception as e:
            logger.error(f"Failed to discover tracking API | {type(e).__name__}: {e}")
            raise

    async def discover_auth_api(
        self, documentation: str, provider_hint: str = ""
    ) -> Optional[DiscoveredEndpoint]:
        """Discover the authentication API endpoint if one exists."""
        logger.info(
            f"Discovering auth API | provider_hint={provider_hint!r} "
            f"doc_chars={len(documentation)}"
        )
        documentation = self._truncate(documentation)

        system = (
            "You are an API documentation expert. "
            "Identify the authentication endpoint if one exists (e.g. a login or token endpoint). "
            "If auth is handled via static headers or API keys with no separate endpoint, "
            'set name to "no_auth" and url to "none".'
        )
        hint = f"Provider: {provider_hint}\n\n" if provider_hint else ""
        user = (
            f"{hint}API Documentation:\n\n{documentation}\n\n"
            "Return the auth endpoint as JSON. If there is no auth endpoint, "
            'return JSON with name="no_auth" and url="none".'
        )

        try:
            result = await self.llm.complete(
                system=system, user=user, response_format=DiscoveredEndpoint
            )
            if isinstance(result, DiscoveredEndpoint):
                if result.name == "no_auth":
                    logger.info("Auth API: none (static key / no login endpoint)")
                    return None
                logger.info(
                    f"Auth API discovered | name={result.name!r} "
                    f"method={result.method} url={result.url} "
                    f"auth_type={getattr(result, 'auth_type', 'unknown')!r}"
                )
                return result
            return None
        except Exception as e:
            logger.warning(
                f"Failed to discover auth API, assuming no auth | {type(e).__name__}: {e}"
            )
            return None
