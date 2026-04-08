from typing import Optional, Union, Any
"""Models for discovered API specifications."""

from pydantic import BaseModel


class DiscoveredEndpoint(BaseModel):
    """An API endpoint discovered from documentation."""

    name: str  # e.g., "Track Shipment"
    method: str  # GET or POST
    url: str  # Full URL or path template
    headers: dict[str, str]  # Required headers
    auth_type: str  # bearer_token, api_key_header, basic, oauth2, none
    request_body: Optional[dict] = None  # JSON body template if POST
    query_params: Optional[dict] = None  # Query params if GET
    awb_field_name: str = ""  # Which field holds the AWB number
    response_schema: Optional[dict] = None  # Expected response structure
    confidence: float = 0.5  # 0–1 confidence level
    reasoning: str = ""  # Why this endpoint was chosen


class ParsedAPISpec(BaseModel):
    """Complete parsed API specification."""

    provider_name: str
    tracking_endpoint: DiscoveredEndpoint
    auth_endpoint: Optional[DiscoveredEndpoint] = None
    auth_mechanism: str  # bearer_token, api_key_header, basic, oauth2, none
    provider_statuses: list[str]  # All statuses found in docs
    raw_content: str  # Full documentation text
    content_type: str  # postman, openapi, webpage, pdf
