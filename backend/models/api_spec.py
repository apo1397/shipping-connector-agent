"""Models for discovered API specifications."""

from typing import Optional, List
from pydantic import BaseModel


class ResponseFieldMapping(BaseModel):
    """Dotted-path pointers into the tracking API response JSON.

    Use bracket notation for arrays: e.g. ``records[0].shipment_details[0].status``
    """
    current_status: str = ""
    awb_number: str = ""
    timestamp: str = ""
    origin_city: str = ""
    destination_city: str = ""
    weight_grams: str = ""
    scan_history: str = ""       # path to the array of scan/event objects
    scan_status: str = ""        # field name *within* each scan object
    scan_timestamp: str = ""
    scan_location: str = ""
    scan_remarks: str = ""


class ProviderStatus(BaseModel):
    """A shipment status discovered from provider documentation."""
    code: str
    description: str
    is_terminal: bool = False
    suggested_mapping: str = "unknown"


class EndpointCandidate(BaseModel):
    """A candidate endpoint when the LLM finds multiple options."""
    name: str = ""
    description: str = ""   # e.g. "B2C Tracking — for consumer shipments"
    method: str = ""
    url: str = ""


class DiscoveredEndpoint(BaseModel):
    """An API endpoint discovered from documentation."""
    name: str
    method: str
    url: str
    base_url: str = ""
    path: str = ""
    headers: dict = {}
    auth_type: str = "none"          # none | api_key_header | bearer_token | login_flow | basic | oauth2
    request_body: Optional[dict] = None
    query_params: Optional[dict] = None
    awb_field_name: str = ""
    awb_location: str = ""           # "path" | "query" | "body"
    response_schema: Optional[dict] = None
    response_field_mapping: Optional[ResponseFieldMapping] = None
    # Auth-endpoint-specific fields
    token_response_field: str = ""   # dotted path to token in login response
    token_prefix: str = "Bearer"
    token_expiry_seconds: Optional[int] = None
    credentials_required: List[str] = []
    inject_header: str = "Authorization"
    inject_header_format: str = "Bearer {token}"
    how_to_get_credentials: str = ""  # Human-readable steps extracted from docs
    confidence: float = 0.5
    reasoning: str = ""
    # Body-level error detection (providers that return HTTP 200 for errors)
    error_indicator_field: str = ""     # e.g. "success", "status", "code"
    error_success_value: str = ""       # e.g. "true", "SUCCESS", "0"
    error_message_field: str = ""       # e.g. "message", "error.description"
    # Rate limiting (extracted from docs)
    rate_limit_rpm: Optional[int] = None
    rate_limit_note: str = ""
    # Clarification — populated when LLM finds multiple candidate endpoints
    needs_clarification: bool = False
    clarification_question: str = ""
    candidates: List[EndpointCandidate] = []


class ParsedAPISpec(BaseModel):
    """Complete parsed API specification."""
    provider_name: str
    tracking_endpoint: DiscoveredEndpoint
    auth_endpoint: Optional[DiscoveredEndpoint] = None
    auth_mechanism: str
    provider_statuses: List[ProviderStatus] = []
    raw_content: str = ""
    content_type: str = ""
