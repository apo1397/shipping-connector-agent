"""Live-test failure classification per PRD v2 §5 (US-5).

Maps the EndpointTester's stage-based output to four named buckets the
requestor sees in the UI:

  auth_failure   — credentials wrong / expired
  awb_not_found  — provider says shipment doesn't exist
  wrong_domain   — DNS / persistent host failure (covers staging-URL slip)
  unknown        — anything else (5xx, response-shape mismatch, malformed body)

Response-shape mismatch is intentionally NOT a stop reason — it falls into
`unknown` so the requestor sees the raw issue, but the agent's downstream
LLM-remap path (config error_handling.6_unexpected_response_shape) handles
recovery without aborting the pipeline.
"""

from __future__ import annotations
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Strings inside provider response bodies that suggest each cause.
_AUTH_PATTERNS = re.compile(
    r"(unauthori[sz]ed|invalid[\s_-]+token|invalid[\s_-]+key|forbidden|access[\s_-]+denied|401|403)",
    re.IGNORECASE,
)
_AWB_PATTERNS = re.compile(
    r"(awb[\s_-]+not[\s_-]+found|invalid[\s_-]+awb|shipment[\s_-]+not[\s_-]+found|does[\s_-]+not[\s_-]+exist|no[\s_-]+record|tracking[\s_-]+not[\s_-]+found|404)",
    re.IGNORECASE,
)
_DNS_PATTERNS = re.compile(
    r"(name[\s_-]+or[\s_-]+service[\s_-]+not[\s_-]+known|nodename.*nor[\s_-]+servname|getaddrinfo|dns[\s_-]+resolution|connection[\s_-]+refused|no[\s_-]+address[\s_-]+associated|temporary[\s_-]+failure[\s_-]+in[\s_-]+name[\s_-]+resolution|connecterror|httpx\.connecterror)",
    re.IGNORECASE,
)


def classify(test_result: dict) -> dict:
    """Return {classification, reason, requestor_action} for a test result.

    Always returns a dict — never raises. Pure function.
    """
    success = bool(test_result.get("success"))
    stage = (test_result.get("stage") or "").lower()
    error = test_result.get("error") or ""
    current_status = test_result.get("current_status")

    if success and current_status:
        return {
            "classification": "passed",
            "reason": f"Live test passed — extracted status: {current_status!r}",
            "requestor_action": None,
        }

    # Success=true but no current_status — response-shape mismatch (per PRD: NOT a stop)
    if success and not current_status:
        return {
            "classification": "unknown",
            "reason": (
                "Provider returned 2xx but the response shape didn't match the discovered "
                "field paths. The agent will re-derive paths and retry on a future run "
                "(no action needed)."
            ),
            "requestor_action": None,
        }

    # ── Stage = auth → auth_failure ─────────────────────────────────────────
    if stage == "auth":
        return {
            "classification": "auth_failure",
            "reason": _short(error) or "Authentication step failed",
            "requestor_action": (
                "Credentials are likely wrong or expired. Regenerate from the "
                "provider's dashboard and try again."
            ),
        }

    # ── Stage = tracking → could be 401/403/404/DNS/other ───────────────────
    if stage == "tracking":
        if _DNS_PATTERNS.search(error):
            return {
                "classification": "wrong_domain",
                "reason": _short(error),
                "requestor_action": (
                    "The host doesn't resolve. The doc may have shown a staging URL. "
                    "Enter the production base URL manually."
                ),
            }
        if _AUTH_PATTERNS.search(error):
            return {
                "classification": "auth_failure",
                "reason": _short(error),
                "requestor_action": (
                    "Provider rejected the credentials. Regenerate from their dashboard."
                ),
            }
        if _AWB_PATTERNS.search(error):
            return {
                "classification": "awb_not_found",
                "reason": _short(error),
                "requestor_action": (
                    "Provider says the AWB doesn't exist or isn't manifested yet. "
                    "Try a different AWB known to be in transit."
                ),
            }
        return {
            "classification": "unknown",
            "reason": _short(error),
            "requestor_action": (
                "Inspect the raw response. Could be a transient 5xx, rate-limit, or "
                "a response shape the agent didn't handle."
            ),
        }

    return {
        "classification": "unknown",
        "reason": _short(error) or f"Unclassified failure at stage={stage!r}",
        "requestor_action": "Inspect the raw response and retry.",
    }


def _short(s: str, n: int = 200) -> str:
    if not s:
        return ""
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "..."
