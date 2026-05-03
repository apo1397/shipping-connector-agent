"""Connector config generator — assembles the exhaustive JSON config file.

No LLM calls here — pure deterministic assembly from what the analyzer extracted.

OUTPUT SCHEMA (v2.0)
--------------------
{
  schema_version, generated_at,
  provider        : name, documentation_url, base_url
  authentication  : type-specific block (see _build_auth_config)
  tracking        : endpoint + response_mapping + raw_response_schema
  error_handling  : per-scenario detection patterns + recommended actions
  status_map      : ARRAY of {provider_code, label, gokwik_status, is_terminal}
  implementation_guide : ordered steps for a coding agent
  test_run        : credentials used + live result (or skip note)
}

AUTH TYPES
----------
  none            — no credentials needed, fire request directly
  api_key_header  — inject a static key into one request header every time
  login_flow      — POST credentials → extract token → inject token each request
  oauth2          — same flow as login_flow but token expiry is explicit
  basic           — HTTP Basic auth (base64 of username:password)
  unknown         — could not determine; manual inspection required

ERROR HANDLING
--------------
Every section in error_handling has:
  indicators : list of signals to detect this error
  action     : what the connector implementation should do

STATUS MAP
----------
Array (not object) so order is preserved and each entry is self-contained.
Each entry: { provider_code, label, gokwik_status, is_terminal }
  provider_code  : the raw code/string the provider returns
  label          : human-readable description
  gokwik_status  : canonical GoKwik status to emit downstream
  is_terminal    : if true, no further status updates will arrive for this AWB
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from backend.models import DiscoveredEndpoint, ProviderStatus

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "2.0"


def generate_connector_config(
    provider_name: str,
    source_url: str,
    tracking_api: DiscoveredEndpoint,
    auth_api: Optional[DiscoveredEndpoint],
    confirmed_mappings: dict,
    provider_statuses: List[ProviderStatus],
    implementation_hints: List[str] = [],
    test_credentials: Optional[dict] = None,
    test_awb: Optional[str] = None,
    live_test_result: Optional[dict] = None,
) -> dict:
    auth_block = _build_auth_config(tracking_api, auth_api)
    tracking_block = _build_tracking_config(tracking_api)
    status_list = _build_status_map(confirmed_mappings, provider_statuses)

    config = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(),
        "provider": {
            "name": provider_name,
            "documentation_url": source_url,
            "base_url": tracking_api.base_url or _extract_base_url(tracking_api.url),
        },
        "authentication": auth_block,
        "tracking": tracking_block,
        "error_handling": _build_error_handling(auth_block, tracking_block, tracking_api),
        "status_map": status_list,
        "implementation_guide": _build_implementation_guide(auth_block, tracking_block),
        "implementation_hints": implementation_hints or [],
        "test_run": _build_test_section(test_credentials, test_awb, live_test_result),
    }

    logger.info(
        f"Config v{SCHEMA_VERSION} generated | provider={provider_name!r} "
        f"auth={auth_block['type']} statuses={len(status_list)}"
    )
    return config


# ---------------------------------------------------------------------------
# Authentication block
# ---------------------------------------------------------------------------

def _build_auth_config(
    tracking_api: DiscoveredEndpoint,
    auth_api: Optional[DiscoveredEndpoint],
) -> dict:
    """Return a typed auth block.

    The 'type' field drives which other fields are meaningful:
      api_key_header / none  → inject_header + inject_header_format + credentials_required
      login_flow / oauth2    → login_endpoint block + inject_header + inject_header_format
      basic                  → credentials_required=[username, password]; encode per RFC 7617
      unknown                → manual inspection needed; all fields may be empty
    """
    if not auth_api:
        return {
            "_doc": "Auth mechanism could not be determined from documentation. Inspect manually.",
            "type": "unknown",
            "credentials_required": [],
            "inject_header": "",
            "inject_header_format": "",
            "static_headers": {},
            "login_endpoint": None,
            "error_cases": _auth_error_cases("unknown"),
        }

    auth_type = auth_api.auth_type or "none"

    if auth_type in ("api_key_header", "none") or auth_api.url in (None, "", "none"):
        return {
            "_doc": (
                "Static API key injected as a request header on every call. "
                "No login step required. "
                "Build the header value using inject_header_format, substituting credentials."
            ),
            "type": auth_type,
            "credentials_required": auth_api.credentials_required or ["api_key"],
            "inject_header": auth_api.inject_header or "",
            "inject_header_format": auth_api.inject_header_format or "{api_key}",
            "static_headers": auth_api.headers or {},
            "login_endpoint": None,
            "error_cases": _auth_error_cases(auth_type),
        }

    if auth_type == "basic":
        return {
            "_doc": (
                "HTTP Basic authentication. "
                "Encode credentials as Base64(username:password) and set "
                "Authorization: Basic <encoded> on every request."
            ),
            "type": "basic",
            "credentials_required": auth_api.credentials_required or ["username", "password"],
            "inject_header": "Authorization",
            "inject_header_format": "Basic {base64(username:password)}",
            "static_headers": auth_api.headers or {},
            "login_endpoint": None,
            "error_cases": _auth_error_cases("basic"),
        }

    # login_flow / oauth2
    login_block: Optional[dict] = None
    if auth_api.url and auth_api.url not in ("", "none"):
        login_url = auth_api.url
        if not login_url.startswith(("http://", "https://")):
            base = auth_api.base_url or ""
            login_url = base.rstrip("/") + "/" + login_url.lstrip("/")

        login_block = {
            "_doc": (
                "POST credentials to this endpoint to receive an access token. "
                "Extract the token using response_token_field (dotted path). "
                "Inject the token into subsequent requests via the parent inject_header."
            ),
            "method": auth_api.method or "POST",
            "url": login_url,
            "base_url": auth_api.base_url or _extract_base_url(login_url),
            "path": auth_api.path or _extract_path(login_url),
            "request_body_template": auth_api.request_body or {},
            "response_token_field": auth_api.token_response_field or "",
            "token_prefix": auth_api.token_prefix or "Bearer",
            "token_expiry_seconds": auth_api.token_expiry_seconds,
        }

    return {
        "_doc": (
            "Two-step auth: POST credentials to login_endpoint, extract the token "
            "using response_token_field (supports dotted paths e.g. 'data.token'), "
            "then inject it into every tracking request header using inject_header_format."
        ),
        "type": auth_type,
        "credentials_required": auth_api.credentials_required or [],
        "inject_header": auth_api.inject_header or "Authorization",
        "inject_header_format": auth_api.inject_header_format or "Bearer {token}",
        "static_headers": auth_api.headers or {},
        "login_endpoint": login_block,
        "error_cases": _auth_error_cases(auth_type),
    }


def _auth_error_cases(auth_type: str) -> dict:
    """Per-type error cases the connector must handle."""
    base = {
        "invalid_credentials": {
            "indicators": ["HTTP 401", "HTTP 403"],
            "action": "Credentials are wrong or revoked. Surface error to operator — do not retry automatically.",
        },
        "missing_header": {
            "indicators": ["HTTP 400 with auth-related message"],
            "action": "inject_header is absent from the request. Check header name and format.",
        },
    }
    if auth_type in ("login_flow", "oauth2"):
        base["token_expired"] = {
            "indicators": ["HTTP 401 on tracking call after successful login"],
            "action": "Token has expired. Re-authenticate by calling login_endpoint, then retry the tracking call once.",
        }
        base["token_not_found_in_response"] = {
            "indicators": ["Login returns HTTP 200 but token field is absent"],
            "action": (
                "response_token_field path is wrong. "
                "Log the full login response and locate the token manually."
            ),
        }
    return base


# ---------------------------------------------------------------------------
# Tracking block
# ---------------------------------------------------------------------------

def _build_tracking_config(tracking_api: DiscoveredEndpoint) -> dict:
    """Build the tracking endpoint + response mapping section.

    awb_location values:
      path   — substitute AWB directly into the URL path (e.g. /track/{awb})
      query  — pass AWB as a URL query parameter (?awb_field_name=<value>)
      body   — include AWB in the JSON request body under awb_field_name

    response_mapping paths use dot-notation with bracket array indexing:
      e.g.  "data.shipments[0].status"
    """
    rfm = tracking_api.response_field_mapping

    endpoint = {
        "_doc": (
            "Build the HTTP request exactly as described here. "
            "awb_location tells you WHERE to place the AWB number. "
            "request_body_template is the full body with {awb_field_name} as a placeholder."
        ),
        "method": tracking_api.method,
        "url": tracking_api.url,
        "base_url": tracking_api.base_url or _extract_base_url(tracking_api.url),
        "path": tracking_api.path or _extract_path(tracking_api.url),
        "content_type": "application/json",
        "awb_location": tracking_api.awb_location or "body",
        "awb_field_name": tracking_api.awb_field_name,
        "required_headers": tracking_api.headers or {},
        "query_params": tracking_api.query_params or {},
        "request_body_template": tracking_api.request_body,
    }

    response_mapping: dict = {}
    if rfm:
        response_mapping = {
            "_doc": (
                "Dotted paths into the JSON response. "
                "current_status is the only mandatory field. "
                "Empty string means the field was not found in the documentation."
            ),
            "current_status": rfm.current_status,
            "awb_number": rfm.awb_number,
            "timestamp": rfm.timestamp,
            "origin_city": rfm.origin_city,
            "destination_city": rfm.destination_city,
            "weight_grams": rfm.weight_grams,
            "scan_history": {
                "_doc": "Array of tracking events. Navigate to the array, then read item_fields from each element.",
                "field": rfm.scan_history,
                "item_fields": {
                    "status": rfm.scan_status,
                    "timestamp": rfm.scan_timestamp,
                    "location": rfm.scan_location,
                    "remarks": rfm.scan_remarks,
                },
            },
        }

    return {
        "endpoint": endpoint,
        "response_mapping": response_mapping,
        "raw_response_schema": tracking_api.response_schema,
    }


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def _build_error_handling(
    auth_block: dict,
    tracking_block: dict,
    tracking_api: DiscoveredEndpoint,
) -> dict:
    """Comprehensive error detection guide for the connector implementer.

    Scenarios are numbered 0-7 — evaluate IN ORDER, stop at first match.
    Scenario 0 is body-level and must run even when HTTP status is 200.
    """
    auth_type = auth_block.get("type", "unknown")
    awb_loc = tracking_block["endpoint"].get("awb_location", "body")
    awb_field = tracking_block["endpoint"].get("awb_field_name", "awb")
    status_path = tracking_block.get("response_mapping", {}).get("current_status", "")

    result: dict = {
        "_doc": (
            "Evaluate these scenarios IN ORDER after every API call. "
            "Scenario 0 must be checked even when HTTP status is 200 — "
            "many shipping providers return 200 for application-level errors."
        ),
    }

    # ── Scenario 0: body-level error (HTTP 200 but error in body) ────────────
    if tracking_api.error_indicator_field:
        result["0_body_level_error"] = {
            "_doc": (
                "This provider returns HTTP 200 even for errors. "
                "Check this field BEFORE reading any data fields."
            ),
            "check_field": tracking_api.error_indicator_field,
            "success_value": tracking_api.error_success_value,
            "message_field": tracking_api.error_message_field or "",
            "detection_logic": (
                f"After receiving HTTP 200, read '{tracking_api.error_indicator_field}' "
                f"from the response body. If it is NOT '{tracking_api.error_success_value}', "
                f"the call has failed. Read '{tracking_api.error_message_field}' for the "
                f"human-readable reason." if tracking_api.error_message_field
                else f"After receiving HTTP 200, read '{tracking_api.error_indicator_field}' "
                     f"from the response body. If it is NOT '{tracking_api.error_success_value}', "
                     "the call has failed."
            ),
            "action": (
                "Classify the error from the message field: "
                "if it contains 'not found' / 'invalid awb' / 'does not exist' → treat as awb_not_found. "
                "If it contains 'unauthori' / 'invalid token' / 'invalid key' → treat as auth_failure. "
                "Otherwise → treat as invalid_request and log the full message for inspection."
            ),
        }
    else:
        result["0_body_level_error"] = {
            "_doc": (
                "No explicit success/error field was found in the documentation. "
                "The provider MAY still return HTTP 200 with an error body. "
                "If current_status resolves to null on a valid AWB, inspect the raw response."
            ),
            "check_field": None,
            "detection_logic": (
                f"If HTTP is 200 but '{status_path}' resolves to null, "
                "log the full response body and check for error indicators manually."
            ),
            "action": "Treat as unexpected_response_shape (see scenario 6).",
        }

    # ── Scenario 1: HTTP auth errors ─────────────────────────────────────────
    result["1_auth_failure"] = {
        "_doc": "Credentials are wrong, expired, or the header is missing.",
        "indicators": ["HTTP 401", "HTTP 403"],
        "likely_cause": (
            "Invalid API key" if auth_type == "api_key_header"
            else "Wrong username/password or expired token"
        ),
        "action": (
            "Surface error to operator. Do not auto-retry — "
            "re-authentication with the same credentials will also fail."
            if auth_type in ("api_key_header", "basic", "none")
            else "Re-authenticate via authentication.login_endpoint, then retry once. "
                 "If it fails again, surface to operator."
        ),
    }

    # ── Scenario 2: bad request ───────────────────────────────────────────────
    result["2_invalid_request"] = {
        "_doc": "Request body / parameters are malformed.",
        "indicators": ["HTTP 400"],
        "likely_cause": "AWB field missing, wrong content-type, or extra/missing body keys.",
        "action": (
            f"Verify request matches tracking.endpoint.request_body_template. "
            f"AWB must be in location='{awb_loc}' under field='{awb_field}'."
        ),
    }

    # ── Scenario 3: AWB not found ─────────────────────────────────────────────
    result["3_awb_not_found"] = {
        "_doc": "AWB does not exist in the provider's system yet, or was never created.",
        "indicators": [
            "HTTP 404",
            "HTTP 200 with empty data array",
            "HTTP 200 with error body (see scenario 0) and message contains 'not found' / 'invalid awb'",
        ],
        "action": (
            "Return null status upstream. Do NOT retry immediately — "
            "the shipment may not have been manifested yet. "
            "Poll again after the expected pickup window."
        ),
    }

    # ── Scenario 4: rate limited ──────────────────────────────────────────────
    result["4_rate_limited"] = {
        "_doc": "Too many requests in a short window.",
        "indicators": ["HTTP 429", "HTTP 420"],
        "action": "Retry with exponential backoff: 1s → 2s → 4s → 8s. Respect Retry-After header if present.",
    }

    # ── Scenario 5: server error ──────────────────────────────────────────────
    result["5_server_error"] = {
        "_doc": "Transient provider-side failure.",
        "indicators": ["HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504"],
        "action": "Retry up to 3 times with exponential backoff. Alert on-call if failures persist > 5 min.",
    }

    # ── Scenario 6: unexpected response shape ────────────────────────────────
    result["6_unexpected_response_shape"] = {
        "_doc": "HTTP 200, no body error, but expected fields are absent.",
        "indicators": [
            f"Path '{status_path}' resolves to null" if status_path else "current_status field is null",
        ],
        "action": (
            "Log the raw response body for inspection. "
            "The provider may have changed their response schema. "
            "Update tracking.response_mapping paths accordingly."
        ),
    }

    # ── Rate limiting reference ───────────────────────────────────────────────
    result["rate_limiting"] = {
        "_doc": "Documented rate limit information for this provider.",
        "requests_per_minute": tracking_api.rate_limit_rpm,
        "note": tracking_api.rate_limit_note or "Not documented — apply conservative defaults.",
        "recommended_default": "Max 60 req/min unless documented otherwise.",
        "action": (
            f"Do not exceed {tracking_api.rate_limit_rpm} requests per minute."
            if tracking_api.rate_limit_rpm
            else "Apply a conservative default of 1 request/second until the provider confirms limits."
        ),
    }

    return result


# ---------------------------------------------------------------------------
# Status map  (list, not dict)
# ---------------------------------------------------------------------------

def _build_status_map(
    confirmed_mappings: dict,
    provider_statuses: List[ProviderStatus],
) -> list:
    """Return an ordered list of status entries.

    Each entry:
      provider_code  — raw status code/string from the provider's API response
      label          — human-readable description of that status
      gokwik_status  — canonical GoKwik status to emit; see GOKWIK_STATUS_REFERENCE below
      is_terminal    — true = no further updates will arrive for this AWB

    GOKWIK_STATUS_REFERENCE:
      order_placed, pickup_pending, pickup_scheduled, out_for_pickup, picked_up,
      in_transit, reached_destination_hub, out_for_delivery, delivered,
      delivery_failed, delivery_failed_customer_unavailable,
      delivery_failed_address_issue, delivery_failed_refused,
      rto_initiated, rto_in_transit, rto_delivered,
      cancelled, lost, damaged, on_hold, unknown
    """
    status_index = {s.code: s for s in provider_statuses}
    seen: set = set()
    result: list = []

    for code, gokwik_status in confirmed_mappings.items():
        ps = status_index.get(code)
        result.append({
            "provider_code": code,
            "label": ps.description if ps else code,
            "gokwik_status": gokwik_status,
            "is_terminal": ps.is_terminal if ps else False,
        })
        seen.add(code)

    for code, ps in status_index.items():
        if code not in seen:
            result.append({
                "provider_code": code,
                "label": ps.description,
                "gokwik_status": ps.suggested_mapping,
                "is_terminal": ps.is_terminal,
            })

    return result


# ---------------------------------------------------------------------------
# Implementation guide
# ---------------------------------------------------------------------------

def _build_implementation_guide(auth_block: dict, tracking_block: dict) -> dict:
    """Ordered step-by-step instructions for a coding agent implementing this connector."""
    auth_type = auth_block.get("type", "unknown")
    awb_loc = tracking_block["endpoint"].get("awb_location", "body")
    awb_field = tracking_block["endpoint"].get("awb_field_name", "awb")
    method = tracking_block["endpoint"].get("method", "POST")

    steps = []

    # Step 1 — auth
    if auth_type == "login_flow":
        steps.append({
            "step": 1,
            "title": "Authenticate — obtain token",
            "description": (
                "POST credentials (see authentication.credentials_required) to "
                "authentication.login_endpoint.url using the body template in "
                "login_endpoint.request_body_template. "
                "Extract the token from the response at the path given by "
                "login_endpoint.response_token_field. "
                "Cache the token and refresh when it expires "
                "(login_endpoint.token_expiry_seconds)."
            ),
            "ref": "authentication.login_endpoint",
        })
        steps.append({
            "step": 2,
            "title": "Inject token into request headers",
            "description": (
                "For every tracking request, add header: "
                "authentication.inject_header = authentication.inject_header_format "
                "with {token} replaced by the cached token."
            ),
            "ref": "authentication",
        })
    elif auth_type == "api_key_header":
        steps.append({
            "step": 1,
            "title": "Inject API key into request headers",
            "description": (
                "On every request set: "
                "authentication.inject_header = authentication.inject_header_format "
                "substituting the credential values from authentication.credentials_required. "
                "No login call needed."
            ),
            "ref": "authentication",
        })
    elif auth_type == "basic":
        steps.append({
            "step": 1,
            "title": "Build Basic Auth header",
            "description": (
                "Concatenate username + ':' + password, Base64-encode the result, "
                "and set Authorization: Basic <encoded> on every request."
            ),
            "ref": "authentication",
        })
    else:
        steps.append({
            "step": 1,
            "title": "Review authentication",
            "description": (
                f"Auth type is '{auth_type}'. "
                "Check the documentation_url and populate authentication manually."
            ),
            "ref": "authentication",
        })

    # Step 2/3 — build tracking request
    next_step = len(steps) + 1
    if awb_loc == "path":
        req_desc = (
            f"{method} tracking.endpoint.url with the AWB substituted directly "
            f"into the URL path. Replace the placeholder matching '{awb_field}' "
            "with the actual AWB value."
        )
    elif awb_loc == "query":
        req_desc = (
            f"{method} tracking.endpoint.url with the AWB passed as query parameter "
            f"'{awb_field}=<awb_value>'."
        )
    else:
        req_desc = (
            f"{method} tracking.endpoint.url with Content-Type: application/json. "
            f"Use tracking.endpoint.request_body_template as the body, "
            f"replacing '{awb_field}' with the actual AWB value."
        )

    steps.append({
        "step": next_step,
        "title": "Build and send tracking request",
        "description": req_desc,
        "ref": "tracking.endpoint",
    })

    steps.append({
        "step": next_step + 1,
        "title": "Check for errors",
        "description": (
            "Before parsing the response body, evaluate error_handling scenarios "
            "in order (1→6). Handle each case as described in error_handling[n].action."
        ),
        "ref": "error_handling",
    })

    steps.append({
        "step": next_step + 2,
        "title": "Extract current status",
        "description": (
            "Navigate the JSON response using the dotted path in "
            "tracking.response_mapping.current_status to read the provider's raw status code."
        ),
        "ref": "tracking.response_mapping.current_status",
    })

    steps.append({
        "step": next_step + 3,
        "title": "Map to GoKwik status",
        "description": (
            "Find the entry in status_map where provider_code equals the extracted value. "
            "Emit gokwik_status downstream. "
            "If no match is found, emit 'unknown' and log the unmapped code for review. "
            "If is_terminal is true, stop polling for this AWB."
        ),
        "ref": "status_map",
    })

    return {
        "_doc": (
            "Follow these steps in order to implement the connector. "
            "Each step references a section of this config file."
        ),
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# Test run
# ---------------------------------------------------------------------------

def _build_test_section(
    credentials: Optional[dict],
    awb: Optional[str],
    result: Optional[dict],
) -> dict:
    """Record what was tested and what happened.

    If the test succeeded, the detected status and raw response are included
    so the implementer can cross-check their response_mapping paths.
    If the test failed, the error and the stage at which it failed are recorded
    so the implementer knows where to start debugging.
    """
    if not credentials and not result:
        return {
            "_doc": "No live E2E test was run. Run a test from the UI to populate this section.",
            "skipped": True,
        }

    success = result.get("success") if result else None
    return {
        "_doc": (
            "⚠️  TEST CREDENTIALS — never commit or deploy these values. "
            "This section exists purely for the implementer to verify the connector works."
        ),
        "credentials_used": credentials or {},
        "awb_tested": awb or "",
        "outcome": {
            "success": success,
            "stage_reached": result.get("stage") if result else None,
            "current_status_detected": result.get("current_status") if result else None,
            "duration_ms": result.get("duration_ms") if result else None,
            "error": result.get("error") if result else None,
            "debug_note": (
                "Test passed — cross-check current_status_detected against status_map "
                "to confirm the response_mapping path is correct."
                if success
                else (
                    "Test failed at stage '{}'. See error_handling for likely causes. "
                    "Common causes: wrong credentials (stage=auth), "
                    "relative URL missing base_url (stage=tracking), "
                    "AWB not yet in provider system (stage=tracking with 404/empty response)."
                ).format(result.get("stage", "?") if result else "?")
            ),
        },
        "raw_tracking_response": result.get("tracking_response") if result else None,
    }


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _extract_base_url(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return ""


def _extract_path(url: str) -> str:
    try:
        return urlparse(url).path
    except Exception:
        return ""
