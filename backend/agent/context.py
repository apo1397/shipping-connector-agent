"""Agent context - mutable state passed through the pipeline."""

from dataclasses import dataclass, field
from typing import Any, Optional, Union
from backend.models import DiscoveredEndpoint, ParsedAPISpec


@dataclass
class AgentContext:
    """Mutable state container passed through each pipeline step."""

    session_id: str
    source_url: str
    provider_name_hint: Optional[str] = None

    # Populated by fetcher
    raw_content: str = ""  # Markdown/text of the docs
    content_type: str = ""  # "postman" | "openapi" | "webpage" | "pdf"
    structured_spec: Optional[dict] = None  # Parsed Postman/OpenAPI

    # Populated by analyzer
    tracking_api: Optional[DiscoveredEndpoint] = None
    auth_api: Optional[DiscoveredEndpoint] = None
    auth_mechanism: str = ""  # bearer_token, api_key_header, basic, oauth2, none
    provider_statuses: list[str] = field(default_factory=list)
    suggested_mappings: dict[str, str] = field(default_factory=dict)

    # Set by user confirmation
    confirmed_mappings: dict[str, str] = field(default_factory=dict)

    # Populated by generator
    generated_files: dict[str, str] = field(default_factory=dict)  # filename -> code
    validation_errors: list[str] = field(default_factory=list)
