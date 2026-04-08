"""Agent context - mutable state passed through the pipeline."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional, List
from backend.models import DiscoveredEndpoint, ProviderStatus


@dataclass
class AgentContext:
    """Mutable state container passed through each pipeline step."""

    session_id: str
    source_url: str
    provider_name_hint: Optional[str] = None

    # Populated by fetcher
    raw_content: str = ""
    content_type: str = ""
    structured_spec: Optional[dict] = None

    # Populated by analyzer
    tracking_api: Optional[DiscoveredEndpoint] = None
    auth_api: Optional[DiscoveredEndpoint] = None
    auth_mechanism: str = ""
    provider_statuses: List[ProviderStatus] = field(default_factory=list)
    suggested_mappings: dict = field(default_factory=dict)

    # Set by user confirmation
    confirmed_mappings: dict = field(default_factory=dict)

    # Pause/resume for user review
    review_event: asyncio.Event = field(default_factory=asyncio.Event)

    # Populated by generator
    generated_files: dict = field(default_factory=dict)
    validation_errors: List[str] = field(default_factory=list)

    # Test results
    test_results: List[dict] = field(default_factory=list)
