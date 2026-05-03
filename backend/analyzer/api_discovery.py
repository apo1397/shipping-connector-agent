"""API discovery — identifies tracking and auth endpoints from documentation.

Improvements over v1
---------------------
- Ambiguity detection: if multiple tracking endpoints exist (B2C/B2B, v1/v2, etc.)
  the LLM returns candidates[] + needs_clarification=true so the user can pick.
- Response field mapping: extracts dotted paths into the JSON response.
- Credential hints: auth discovery captures how_to_get_credentials from docs.
"""

from typing import Optional, List
import logging
from pydantic import BaseModel
from backend.models import DiscoveredEndpoint, ResponseFieldMapping, EndpointCandidate
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

_MAX_DOC_CHARS = 20_000


# ─────────────────────────────────────────────────────────────────────────────
# Internal LLM response schemas (not exposed outside this module)
# ─────────────────────────────────────────────────────────────────────────────

class _ResponseMapping(BaseModel):
    current_status: str = ""
    awb_number: str = ""
    timestamp: str = ""
    origin_city: str = ""
    destination_city: str = ""
    weight_grams: str = ""
    scan_history: str = ""
    scan_status: str = ""
    scan_timestamp: str = ""
    scan_location: str = ""
    scan_remarks: str = ""


class _Candidate(BaseModel):
    name: str = ""
    description: str = ""
    method: str = ""
    url: str = ""


class _TrackingSpec(BaseModel):
    name: str = "tracking"
    method: str = "POST"
    url: str = ""
    base_url: str = ""
    path: str = ""
    headers: dict = {}
    auth_type: str = "none"
    request_body: Optional[dict] = None
    query_params: Optional[dict] = None
    awb_field_name: str = ""
    awb_location: str = ""
    response_schema: Optional[dict] = None
    response_field_mapping: _ResponseMapping = _ResponseMapping()
    confidence: float = 0.5
    reasoning: str = ""
    # Body-level error detection
    error_indicator_field: str = ""
    error_success_value: str = ""
    error_message_field: str = ""
    # Rate limiting
    rate_limit_rpm: Optional[int] = None
    rate_limit_note: str = ""
    # Ambiguity
    needs_clarification: bool = False
    clarification_question: str = ""
    candidates: List[_Candidate] = []


class _AuthSpec(BaseModel):
    name: str = "no_auth"
    method: str = "POST"
    url: str = "none"
    base_url: str = ""
    path: str = ""
    headers: dict = {}
    auth_type: str = "none"
    request_body: Optional[dict] = None
    token_response_field: str = ""
    token_prefix: str = "Bearer"
    token_expiry_seconds: Optional[int] = None
    credentials_required: List[str] = []
    inject_header: str = "Authorization"
    inject_header_format: str = "Bearer {token}"
    how_to_get_credentials: str = ""
    reasoning: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Analyzer
# ─────────────────────────────────────────────────────────────────────────────

class APIDiscoveryAnalyzer:
    """Analyzes documentation to discover tracking and auth APIs."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def _truncate(self, documentation: str) -> str:
        if len(documentation) > _MAX_DOC_CHARS:
            logger.warning(
                f"Documentation truncated: {len(documentation)} → {_MAX_DOC_CHARS} chars"
            )
            return documentation[:_MAX_DOC_CHARS] + "\n\n[... truncated ...]"
        return documentation

    async def discover_tracking_api(
        self,
        documentation: str,
        provider_hint: str = "",
        focus_hint: str = "",
    ) -> DiscoveredEndpoint:
        """
        Discover the tracking endpoint.

        Parameters
        ----------
        focus_hint : optional string injected at the top of the user prompt
                     when re-running after a clarification (e.g. "Use the B2C endpoint at …")
        """
        doc = self._truncate(documentation)
        logger.info(
            f"Discovering tracking API | provider={provider_hint!r} "
            f"focus={focus_hint!r} doc_chars={len(doc)}"
        )

        system = (
            "You are an API documentation expert for shipping and logistics.\n\n"
            "Extract the shipment TRACKING endpoint. This accepts an AWB/tracking "
            "number and returns shipment status. Ignore order-creation, manifest, "
            "pickup, or label APIs.\n\n"

            "AMBIGUITY RULE: If you find multiple candidate tracking endpoints "
            "(e.g. B2C vs B2B, v1 vs v2, forward vs return), you MUST:\n"
            "  - Set needs_clarification=true\n"
            "  - List ALL candidates in the candidates[] array with name, description, method, url\n"
            "  - Set clarification_question to a short human-readable question\n"
            "  - Still pick your best guess as the main endpoint (lower confidence)\n\n"

            "RESPONSE FIELD MAPPING: populate response_field_mapping with exact dotted "
            "paths (use bracket notation for arrays) — e.g. "
            "'records[0].shipment_details[0].current_tracking_status_code'.\n\n"

            "BODY-LEVEL ERROR DETECTION: Many providers return HTTP 200 for errors. "
            "Look for a field that indicates success or failure in the response, e.g.:\n"
            "  - A boolean field: 'success', 'ok', 'status'\n"
            "  - A numeric code: 'code', 'errorCode', 'statusCode' where non-zero = error\n"
            "  - A string: 'status' with values like 'SUCCESS'/'ERROR'\n"
            "Set error_indicator_field to that field path (e.g. 'success').\n"
            "Set error_success_value to the value it has on success (e.g. 'true', '0', 'SUCCESS').\n"
            "Set error_message_field to the path of the human-readable error message (e.g. 'message', 'error.description').\n"
            "Leave all three empty if the docs show no such pattern.\n\n"

            "RATE LIMITS: If the documentation mentions rate limits, set "
            "rate_limit_rpm to the numeric requests-per-minute limit and "
            "rate_limit_note to a verbatim or paraphrased quote from the docs. "
            "Leave both empty if not documented.\n\n"

            "awb_location must be one of: 'path', 'query', 'body'.\n"
            "base_url = scheme+host only (e.g. https://api.rapidshyp.com).\n"
            "path = path only (e.g. /rapidshyp/apis/v1/track_order)."
        )

        focus = f"IMPORTANT: {focus_hint}\n\n" if focus_hint else ""
        hint = f"Provider: {provider_hint}\n\n" if provider_hint else ""
        user = f"{focus}{hint}=== DOCUMENTATION ===\n\n{doc}"

        result = await self.llm.complete(system=system, user=user, response_format=_TrackingSpec)

        if not isinstance(result, _TrackingSpec):
            raise ValueError(f"Unexpected LLM return type: {type(result)}")

        rfm = ResponseFieldMapping(**result.response_field_mapping.model_dump())
        candidates = [
            EndpointCandidate(
                name=c.name, description=c.description,
                method=c.method, url=c.url,
            )
            for c in result.candidates
        ]

        endpoint = DiscoveredEndpoint(
            name=result.name,
            method=result.method,
            url=result.url,
            base_url=result.base_url,
            path=result.path,
            headers=result.headers,
            auth_type=result.auth_type,
            request_body=result.request_body,
            query_params=result.query_params,
            awb_field_name=result.awb_field_name,
            awb_location=result.awb_location,
            response_schema=result.response_schema,
            response_field_mapping=rfm,
            confidence=result.confidence,
            reasoning=result.reasoning,
            error_indicator_field=result.error_indicator_field,
            error_success_value=result.error_success_value,
            error_message_field=result.error_message_field,
            rate_limit_rpm=result.rate_limit_rpm,
            rate_limit_note=result.rate_limit_note,
            needs_clarification=result.needs_clarification,
            clarification_question=result.clarification_question,
            candidates=candidates,
        )

        logger.info(
            f"Tracking API discovered | method={endpoint.method} url={endpoint.url} "
            f"awb_loc={endpoint.awb_location!r} confidence={endpoint.confidence:.2f} "
            f"error_field={endpoint.error_indicator_field!r} "
            f"rate_limit_rpm={endpoint.rate_limit_rpm} "
            f"needs_clarification={endpoint.needs_clarification} "
            f"candidates={len(candidates)}"
        )
        return endpoint

    async def discover_auth_api(
        self, documentation: str, provider_hint: str = ""
    ) -> Optional[DiscoveredEndpoint]:
        """Discover auth mechanism and how to obtain credentials."""
        doc = self._truncate(documentation)
        logger.info(
            f"Discovering auth | provider={provider_hint!r} doc_chars={len(doc)}"
        )

        system = (
            "You are an API documentation expert.\n\n"
            "Identify the AUTHENTICATION mechanism from the documentation.\n\n"
            "auth_type values:\n"
            "- 'api_key_header': static API key injected as a header. No login endpoint. "
            "Set name='no_auth', url='none'. Fill inject_header (header name), "
            "inject_header_format (e.g. '{api_key}'), credentials_required=['api_key'].\n"
            "- 'login_flow': must POST to a login URL to get a token. Provide url, "
            "request_body template (use {username}/{password} placeholders), "
            "token_response_field (dotted path), inject_header, inject_header_format "
            "(e.g. 'Bearer {token}').\n"
            "- 'basic': HTTP Basic Auth. credentials_required=['username','password'].\n"
            "- 'oauth2': client credentials. credentials_required=['client_id','client_secret'].\n"
            "- 'none': public API, no auth.\n\n"
            "how_to_get_credentials: quote the EXACT steps from the documentation that "
            "explain how a developer gets their API key / credentials (sign-up link, "
            "dashboard path, etc.). Leave empty if not documented."
        )

        hint = f"Provider: {provider_hint}\n\n" if provider_hint else ""
        user = f"{hint}=== DOCUMENTATION ===\n\n{doc}"

        result = await self.llm.complete(system=system, user=user, response_format=_AuthSpec)

        if not isinstance(result, _AuthSpec):
            logger.warning("LLM returned unexpected type for auth spec")
            return None

        logger.info(
            f"Auth discovered | type={result.auth_type} url={result.url!r} "
            f"inject_header={result.inject_header!r} "
            f"creds_required={result.credentials_required} "
            f"has_cred_guide={bool(result.how_to_get_credentials)}"
        )

        endpoint = DiscoveredEndpoint(
            name=result.name,
            method=result.method,
            url=result.url,
            base_url=result.base_url,
            path=result.path,
            headers=result.headers,
            auth_type=result.auth_type,
            request_body=result.request_body,
            token_response_field=result.token_response_field,
            token_prefix=result.token_prefix,
            token_expiry_seconds=result.token_expiry_seconds,
            credentials_required=result.credentials_required,
            inject_header=result.inject_header,
            inject_header_format=result.inject_header_format,
            how_to_get_credentials=result.how_to_get_credentials,
            reasoning=result.reasoning,
        )
        return endpoint
