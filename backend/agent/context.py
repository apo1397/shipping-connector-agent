"""Agent context — mutable state threaded through every pipeline step."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional, List
from backend.models import DiscoveredEndpoint, ProviderStatus


@dataclass
class AgentContext:
    """Single source of truth for one session's pipeline state."""

    session_id: str
    source_url: str
    provider_name_hint: Optional[str] = None
    requestor: str = "requestor"  # Who initiated; used in notifications

    # ── Fetcher output ───────────────────────────────────────────────────────
    raw_content: str = ""
    content_type: str = ""
    structured_spec: Optional[dict] = None

    # ── Analyzer output ──────────────────────────────────────────────────────
    tracking_api: Optional[DiscoveredEndpoint] = None
    auth_api: Optional[DiscoveredEndpoint] = None
    auth_mechanism: str = ""
    provider_statuses: List[ProviderStatus] = field(default_factory=list)

    # ── Clarification pause/resume ───────────────────────────────────────────
    clarification_event: asyncio.Event = field(default_factory=asyncio.Event)
    clarification_focus_hint: str = ""

    # ── Staging-vs-prod URL pause/resume (NEW v2) ────────────────────────────
    staging_url_event: asyncio.Event = field(default_factory=asyncio.Event)
    staging_url_detected: bool = False
    discovered_host_original: Optional[str] = None  # The host before rewrite
    prod_base_url: Optional[str] = None             # User-provided prod base URL
    host_rewritten: bool = False

    # ── Credential test ──────────────────────────────────────────────────────
    test_credentials: dict = field(default_factory=dict)
    test_awb: str = ""
    live_test_result: Optional[dict] = None
    live_test_classification: Optional[dict] = None  # {classification, reason, action}
    live_test_attempts: int = 0
    live_test_event: asyncio.Event = field(default_factory=asyncio.Event)

    # ── Mapping confirmation pause/resume ─────────────────────────────────────
    review_event: asyncio.Event = field(default_factory=asyncio.Event)
    confirmed_mappings: dict = field(default_factory=dict)

    # ── Final approval pause/resume (NEW v2) ─────────────────────────────────
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_decision: Optional[str] = None  # "approve" | "reject"
    approval_comment: Optional[str] = None
    approver: Optional[str] = None

    # ── JIRA (simulated in dev — ticket id assigned post-validation) ─────────
    jira_ticket_id: Optional[str] = None

    # ── Generator output ──────────────────────────────────────────────────────
    connector_config: Optional[dict] = None
    implementation_hints: List[str] = field(default_factory=list)

    # ── Notification feed (PRD §9.1) — list of dicts shown in the UI ─────────
    notifications: List[dict] = field(default_factory=list)

    # ── Legacy (unused, kept for import compat) ───────────────────────────────
    generated_files: dict = field(default_factory=dict)
    validation_errors: List[str] = field(default_factory=list)
