"""Staging-vs-prod URL detection and host-only rewrite.

Heuristic detection only — not exhaustive. Looks at the URL's host for common
staging/test indicators. If matched, the agent pauses and asks the requestor
to confirm a production base URL. The host is then rewritten while preserving
path, query, headers, and body template.

Per PRD v2 §7 — this is called out explicitly because many shipping providers
(Delhivery, Shiprocket, BlueDart) document staging URLs in their examples.
"""

from __future__ import annotations
import logging
import re
from urllib.parse import urlparse, urlunparse
from typing import Optional

logger = logging.getLogger(__name__)

# Heuristic indicators — host substrings that suggest non-prod environment.
_STAGING_INDICATORS = (
    "staging",
    "sandbox",
    "uat",
    "qa",
    "staging-api",
    "test.",
    ".test",
    "dev.",
    ".dev",
    "preprod",
    "pre-prod",
)


def is_staging_url(url: str) -> bool:
    """Return True if the URL's host matches any staging indicator."""
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    if not host:
        return False
    for ind in _STAGING_INDICATORS:
        # Match as a substring of the host or as a hyphen-bounded segment
        if ind in host:
            logger.info(f"Staging URL detected | host={host!r} matched={ind!r}")
            return True
    return False


def rewrite_host(url: str, prod_base_url: str) -> str:
    """Replace the host portion of `url` with the host of `prod_base_url`.

    Preserves path, query, fragment from `url`. Preserves scheme from `prod_base_url`
    if specified (else falls back to original scheme).

    Examples
    --------
    >>> rewrite_host("https://staging.api.x.com/v1/track/{awb}", "https://api.x.com")
    'https://api.x.com/v1/track/{awb}'
    >>> rewrite_host("https://sandbox.foo.io/track?awb=123", "https://api.foo.io")
    'https://api.foo.io/track?awb=123'
    """
    if not url or not prod_base_url:
        return url
    try:
        original = urlparse(url)
        prod = urlparse(prod_base_url if "://" in prod_base_url else f"https://{prod_base_url}")
    except Exception:
        logger.warning(f"URL rewrite failed: parse error url={url!r} prod={prod_base_url!r}")
        return url

    new_scheme = prod.scheme or original.scheme or "https"
    new_netloc = prod.netloc or prod.path  # if user pasted just the host without scheme
    # If prod_base_url itself includes a path prefix, prepend it; rare but possible.
    prod_path_prefix = prod.path if prod.netloc else ""
    new_path = (prod_path_prefix.rstrip("/") + original.path) if prod_path_prefix else original.path

    rewritten = urlunparse(
        (new_scheme, new_netloc, new_path, original.params, original.query, original.fragment)
    )
    logger.info(f"URL rewritten | from={url!r} to={rewritten!r}")
    return rewritten


def extract_host(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None
