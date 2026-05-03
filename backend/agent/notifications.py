"""Notification builder — produces structured events shown in the in-UI feed.

Per PRD v2 §9.1, every step transition emits one notification with shape:

    {
      "step": "<name>",
      "status": "started|passed|failed|needs_input",
      "by": "@<requestor|agent|approver>",
      "provider": "<name or empty>",
      "details": "<one-line context>",
      "ts": "<ISO timestamp>",
      "jira": "<ticket_id or 'not yet created'>",
    }

The frontend renders these as a Slack-like timeline. We're surfacing them in
the UI directly because we don't have a real Slack integration in dev.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional


def build(
    step: str,
    status: str,
    by: str,
    provider: str = "",
    details: str = "",
    jira: str = "not yet created",
) -> dict:
    """Build one notification record. Pure function."""
    return {
        "step": step,
        "status": status,
        "by": by,
        "provider": provider or "",
        "details": details or "",
        "ts": datetime.utcnow().isoformat() + "Z",
        "jira": jira,
    }
