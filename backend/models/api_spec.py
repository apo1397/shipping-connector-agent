"""Models for discovered API specifications."""

from typing import Optional, List
from pydantic import BaseModel


class ProviderStatus(BaseModel):
    """A shipment status discovered from provider documentation."""
    code: str               # e.g. "OFD", "DL", "in_transit"
    description: str        # e.g. "Out for Delivery"
    is_terminal: bool = False
    suggested_mapping: str = "unknown"  # GoKwikShipmentStatus value


class DiscoveredEndpoint(BaseModel):
    """An API endpoint discovered from documentation."""
    name: str
    method: str
    url: str
    headers: dict = {}
    auth_type: str = "none"
    request_body: Optional[dict] = None
    query_params: Optional[dict] = None
    awb_field_name: str = ""
    response_schema: Optional[dict] = None
    confidence: float = 0.5
    reasoning: str = ""


class ParsedAPISpec(BaseModel):
    """Complete parsed API specification."""
    provider_name: str
    tracking_endpoint: DiscoveredEndpoint
    auth_endpoint: Optional[DiscoveredEndpoint] = None
    auth_mechanism: str
    provider_statuses: List[ProviderStatus] = []
    raw_content: str = ""
    content_type: str = ""
