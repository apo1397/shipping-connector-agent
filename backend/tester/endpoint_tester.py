"""E2E endpoint tester — drives real HTTP calls using discovered API config.

Flow
----
1. Auth
   - api_key_header / none  → inject key directly into request header
   - login_flow             → POST to login URL → extract token → build header
2. Tracking call
   - awb_location=path   → substitute AWB into URL template
   - awb_location=query  → pass as query parameter
   - awb_location=body   → set field in JSON body
3. Extract current_status using response_field_mapping dotted path
4. Return structured result with every intermediate value for debugging
"""

from __future__ import annotations
import re
import time
import logging
from typing import Any, Optional
import httpx
from backend.models import DiscoveredEndpoint

logger = logging.getLogger(__name__)

TIMEOUT = 30


class EndpointTester:
    """Tests a discovered tracking endpoint end-to-end with real credentials."""

    async def run(
        self,
        tracking_api: DiscoveredEndpoint,
        auth_api: Optional[DiscoveredEndpoint],
        credentials: dict,
        awb_number: str,
    ) -> dict:
        """
        Run the full auth → track flow and return a structured result dict.

        Return keys
        -----------
        success, stage, error, duration_ms,
        auth_result   : summary of auth step
        tracking_response : raw JSON from tracking endpoint (or None)
        current_status    : extracted status string (or None)
        """
        t0 = time.perf_counter()
        logger.info(
            f"E2E test | awb={awb_number!r} "
            f"tracking={tracking_api.method} {tracking_api.url} "
            f"auth_type={auth_api.auth_type if auth_api else 'none'}"
        )

        # ── Step 1: authenticate ────────────────────────────────────────────
        auth_headers, auth_summary, auth_err = await self._authenticate(
            auth_api, credentials
        )
        elapsed_ms = _ms(t0)

        if auth_err:
            logger.error(f"Auth failed ({elapsed_ms}ms): {auth_err}")
            return _result(
                success=False, stage="auth", error=auth_err,
                auth_result=auth_summary, elapsed=elapsed_ms,
            )

        logger.info(
            f"Auth OK ({elapsed_ms}ms) | "
            f"injected headers: {list(auth_headers.keys())}"
        )

        # ── Step 2: call tracking endpoint ───────────────────────────────────
        track_resp, track_err = await self._call_tracking(
            tracking_api, auth_headers, awb_number
        )
        elapsed_ms = _ms(t0)

        if track_err:
            logger.error(f"Tracking call failed ({elapsed_ms}ms): {track_err}")
            return _result(
                success=False, stage="tracking", error=track_err,
                auth_result=auth_summary, elapsed=elapsed_ms,
            )

        # ── Step 3: extract current_status ──────────────────────────────────
        current_status: Optional[str] = None
        if tracking_api.response_field_mapping:
            path = tracking_api.response_field_mapping.current_status
            raw_val = _get_nested(track_resp, path)
            current_status = str(raw_val) if raw_val is not None else None
            logger.info(
                f"Status extraction | path={path!r} "
                f"value={current_status!r} ({elapsed_ms}ms total)"
            )
        else:
            logger.warning("No response_field_mapping — cannot extract current_status")

        logger.info(
            f"E2E complete | awb={awb_number!r} status={current_status!r} "
            f"duration={elapsed_ms}ms"
        )
        return _result(
            success=True, stage="complete", error=None,
            auth_result=auth_summary,
            tracking_response=track_resp,
            current_status=current_status,
            elapsed=elapsed_ms,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Auth helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _authenticate(
        self,
        auth_api: Optional[DiscoveredEndpoint],
        credentials: dict,
    ) -> tuple[dict, dict, Optional[str]]:
        """Return (headers_to_inject, summary_dict, error_string_or_None)."""

        if not auth_api or auth_api.url == "none":
            hdrs = _build_static_headers(auth_api, credentials)
            logger.info(f"Static auth | headers={list(hdrs.keys())}")
            return hdrs, {"type": "static_headers", "keys": list(hdrs.keys())}, None

        if auth_api.auth_type in ("api_key_header", "none"):
            hdrs = _build_static_headers(auth_api, credentials)
            logger.info(
                f"API-key header auth | inject_header={auth_api.inject_header!r} "
                f"creds={list(credentials.keys())}"
            )
            return hdrs, {"type": "api_key_header", "keys": list(hdrs.keys())}, None

        # login_flow / oauth2 / basic — POST to login endpoint
        login_url = auth_api.url
        if login_url and not login_url.startswith(("http://", "https://")):
            base = auth_api.base_url or ""
            login_url = base.rstrip("/") + "/" + login_url.lstrip("/")
            logger.info(f"Auth relative URL resolved to: {login_url}")
        login_method = auth_api.method or "POST"
        body = _fill_template(auth_api.request_body or {}, credentials)

        logger.info(
            f"Login flow | {login_method} {login_url} "
            f"body_keys={list(body.keys())} "
            f"token_path={auth_api.token_response_field!r}"
        )

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.request(
                    method=login_method,
                    url=login_url,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
                logger.info(
                    f"Login response | http={resp.status_code} "
                    f"size={len(resp.content)}B"
                )
                resp.raise_for_status()
                resp_data = resp.json()
        except httpx.HTTPStatusError as e:
            snippet = e.response.text[:400]
            return {}, {}, f"Login returned HTTP {e.response.status_code}: {snippet}"
        except Exception as e:
            return {}, {}, f"Login request failed: {type(e).__name__}: {e}"

        # Extract token from response
        token = _get_nested(resp_data, auth_api.token_response_field) if auth_api.token_response_field else None
        logger.info(
            f"Token extraction | path={auth_api.token_response_field!r} "
            f"found={token is not None} "
            f"resp_keys={list(resp_data.keys()) if isinstance(resp_data, dict) else 'non-dict'}"
        )

        if not token:
            return {}, {"type": "login_flow", "response_keys": list(resp_data.keys()) if isinstance(resp_data, dict) else []}, (
                f"Login succeeded (HTTP 200) but token not found at "
                f"'{auth_api.token_response_field}'. "
                f"Response top-level keys: "
                f"{list(resp_data.keys()) if isinstance(resp_data, dict) else str(resp_data)[:200]}"
            )

        inject = auth_api.inject_header or "Authorization"
        fmt = auth_api.inject_header_format or "Bearer {token}"
        try:
            header_val = fmt.format(token=token, prefix=auth_api.token_prefix or "Bearer")
        except KeyError:
            header_val = f"{auth_api.token_prefix or 'Bearer'} {token}"

        logger.info(f"Auth header built | {inject}: {str(header_val)[:30]}...")
        return (
            {inject: header_val},
            {"type": "login_flow", "token_field": auth_api.token_response_field},
            None,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Tracking call
    # ─────────────────────────────────────────────────────────────────────────

    async def _call_tracking(
        self,
        tracking_api: DiscoveredEndpoint,
        auth_headers: dict,
        awb_number: str,
    ) -> tuple[Optional[dict], Optional[str]]:
        """Issue the tracking request. Returns (json_response, error_or_None)."""
        method = tracking_api.method or "GET"
        url = tracking_api.url
        if url and not url.startswith(("http://", "https://")):
            base = tracking_api.base_url or ""
            url = base.rstrip("/") + "/" + url.lstrip("/")
            logger.info(f"Relative URL resolved to: {url}")
        awb_loc = (tracking_api.awb_location or "body").lower()
        awb_field = tracking_api.awb_field_name or "awb"
        headers = {**auth_headers, "Content-Type": "application/json"}
        params: dict = {}
        body: Optional[dict] = None

        if awb_loc == "path":
            # Replace {awb_field_name}, {awb}, {waybill}, etc.
            url = re.sub(r"\{" + re.escape(awb_field) + r"\}", awb_number, url)
            url = re.sub(r"\{[a-z_]*(awb|waybill|tracking)[a-z_]*\}", awb_number, url, flags=re.I)
            logger.info(f"AWB substituted in path | url={url}")

        elif awb_loc == "query":
            params[awb_field] = awb_number
            logger.info(f"AWB as query param | {awb_field}={awb_number}")

        else:  # body
            body = _fill_template(
                dict(tracking_api.request_body or {}),
                {awb_field: awb_number},
            )
            body[awb_field] = awb_number  # ensure it's set even if template fill missed it
            logger.info(f"AWB in body | field={awb_field!r} body_keys={list(body.keys())}")

        logger.info(
            f"Tracking request | {method} {url} "
            f"params={params or None} "
            f"body_keys={list(body.keys()) if body else None} "
            f"auth_headers={list(auth_headers.keys())}"
        )

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params or None,
                    json=body,
                )
                logger.info(
                    f"Tracking response | http={resp.status_code} size={len(resp.content)}B"
                )
                resp.raise_for_status()
                data = resp.json()
            return data, None
        except httpx.HTTPStatusError as e:
            snippet = e.response.text[:400]
            return None, f"Tracking returned HTTP {e.response.status_code}: {snippet}"
        except Exception as e:
            return None, f"Tracking request failed: {type(e).__name__}: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_static_headers(
    auth_api: Optional[DiscoveredEndpoint], credentials: dict
) -> dict:
    headers: dict = {}
    if not auth_api:
        return headers
    inject = auth_api.inject_header
    fmt = auth_api.inject_header_format
    if inject:
        if fmt:
            try:
                val = fmt.format(**credentials)
            except KeyError:
                # Use first credential value as fallback
                val = next(iter(credentials.values()), "")
        else:
            val = next(iter(credentials.values()), "")
        headers[inject] = val
    for k, v in (auth_api.headers or {}).items():
        if k not in headers:
            headers[k] = v
    return headers


def _get_nested(data: Any, path: str) -> Any:
    """Resolve a dotted/bracketed path into nested JSON.

    e.g. ``records[0].shipment_details[0].current_tracking_status_code``
    """
    if not path or data is None:
        return None
    parts = re.split(r"[\.\[\]]+", path)
    cur = data
    for part in parts:
        if not part:
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (IndexError, ValueError, TypeError):
                logger.debug(f"_get_nested: index {part!r} out of range on list len={len(cur)}")
                return None
        elif isinstance(cur, dict):
            keys = list(cur.keys())
            cur = cur.get(part)
            if cur is None:
                logger.debug(f"_get_nested: key {part!r} not found in {keys}")
        else:
            return None
    return cur


def _fill_template(template: dict, values: dict) -> dict:
    """Replace ``{key}`` placeholders in string values of a dict."""
    result: dict = {}
    for k, v in template.items():
        if isinstance(v, str):
            try:
                v = v.format(**values)
            except (KeyError, ValueError):
                v = re.sub(r"\{[^}]+\}", "", v)
        result[k] = v
    return result


def _ms(t0: float) -> int:
    return round((time.perf_counter() - t0) * 1000)


def _result(
    *,
    success: bool,
    stage: str,
    error: Optional[str],
    auth_result: dict = {},
    tracking_response: Optional[dict] = None,
    current_status: Optional[str] = None,
    elapsed: int = 0,
) -> dict:
    return {
        "success": success,
        "stage": stage,
        "error": error,
        "auth_result": auth_result,
        "tracking_response": tracking_response,
        "current_status": current_status,
        "duration_ms": elapsed,
    }
