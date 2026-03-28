"""API discovery - identifies tracking and auth endpoints from documentation."""

import logging
import json
from pydantic import BaseModel
from backend.models import DiscoveredEndpoint, ParsedAPISpec
from .llm_client import LLMClient

logger = logging.getLogger(__name__)


class DiscoveryRequest(BaseModel):
    """Request for API discovery."""

    endpoint_type: str  # "tracking" or "auth"
    documentation: str
    provider_hint: str = ""


class DiscoveryResponse(BaseModel):
    """Response from API discovery."""

    endpoints: list[DiscoveredEndpoint]
    selected_endpoint: DiscoveredEndpoint
    reasoning: str


class APIDiscoveryAnalyzer:
    """Analyzes documentation to discover tracking and auth APIs."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def discover_tracking_api(self, documentation: str, provider_hint: str = "") -> DiscoveredEndpoint:
        """Discover the tracking API endpoint."""
        system = self._get_tracking_prompt_system()
        user = self._get_tracking_prompt_user(documentation, provider_hint)
        
        try:
            result = await self.llm.complete(
                system=system,
                user=user,
                response_format=DiscoveredEndpoint,
            )
            if isinstance(result, DiscoveredEndpoint):
                return result
            else:
                raise ValueError("Expected DiscoveredEndpoint response")
        except Exception as e:
            logger.error(f"Failed to discover tracking API: {e}")
            raise

    async def discover_auth_api(self, documentation: str, provider_hint: str = "") -> DiscoveredEndpoint | None:
        """Discover the authentication API endpoint if one exists."""
        system = self._get_auth_prompt_system()
        user = self._get_auth_prompt_user(documentation, provider_hint)
        
        try:
            # For auth, we ask the LLM to return null/none if no auth endpoint exists
            response = await self.llm.complete(system=system, user=user)
            if isinstance(response, str):
                if response.lower() in ["none", "null", "no auth"]:
                    return None
                # Try to parse as JSON
                try:
                    data = json.loads(response)
                    return DiscoveredEndpoint(**data)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse auth endpoint response: {response}")
                    return None
        except Exception as e:
            logger.warning(f"Failed to discover auth API, assuming no auth: {e}")
            return None

    def _get_tracking_prompt_system(self) -> str:
        return """You are an API documentation expert specializing in shipping and logistics providers.
Your task is to identify the shipment tracking API endpoint from documentation.

Return a JSON object with these fields:
- name: string, name of the endpoint
- method: string, HTTP method (GET or POST)
- url: string, the endpoint URL or path
- headers: object, required headers
- auth_type: string (bearer_token, api_key_header, basic, oauth2, or none)
- request_body: object or null, expected request body if POST
- query_params: object or null, expected query parameters if GET
- awb_field_name: string, which parameter/field contains the AWB number
- response_schema: object or null, sample response structure
- confidence: number between 0 and 1
- reasoning: string, why you selected this endpoint"""

    def _get_tracking_prompt_user(self, documentation: str, provider_hint: str) -> str:
        hint_text = f"Provider: {provider_hint}\n" if provider_hint else ""
        return f"""{hint_text}Here is the API documentation:

---
{documentation}
---

Identify the shipment tracking API endpoint. It should:
1. Accept an AWB (Air Waybill) number as input
2. Return shipment status, location, and delivery information
3. Be distinct from order creation, manifest, or pickup APIs

Return ONLY valid JSON with the endpoint details."""

    def _get_auth_prompt_system(self) -> str:
        return """You are an API documentation expert.
Your task is to identify the authentication API endpoint if one exists.

If authentication is required, return a JSON object with endpoint details.
If no separate auth endpoint exists or authentication is handled via headers/queries, return "no auth"."""

    def _get_auth_prompt_user(self, documentation: str, provider_hint: str) -> str:
        hint_text = f"Provider: {provider_hint}\n" if provider_hint else ""
        return f"""{hint_text}Here is the API documentation:

---
{documentation}
---

Does this API require a separate authentication endpoint (like login/token)?
If yes, provide endpoint details. If not, respond with "no auth"."""
