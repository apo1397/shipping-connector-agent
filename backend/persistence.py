"""File-based dedup registry for connector requests.

Stores: provider_normalized + url_normalized → first request_id seen.

This is a thin MVP layer. In production this would be a DB row keyed on
(provider_normalized, url_normalized) with an index. Here we use a JSON
file at `data/dedup_registry.json` for simplicity.
"""

from __future__ import annotations
import json
import logging
import re
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REGISTRY_LOCK = threading.Lock()
_REGISTRY_PATH = Path(__file__).parent.parent / "data" / "dedup_registry.json"


def _normalize_provider(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def _normalize_url(url: str) -> str:
    """Drop trailing slash + lowercase scheme/host. Keep path/query as-is."""
    url = url.strip()
    return re.sub(r"^(https?://)([^/]+)", lambda m: m.group(1) + m.group(2).lower(), url).rstrip("/")


def _ensure_registry() -> dict:
    if not _REGISTRY_PATH.exists():
        _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _REGISTRY_PATH.write_text("{}")
        return {}
    try:
        return json.loads(_REGISTRY_PATH.read_text() or "{}")
    except json.JSONDecodeError:
        logger.warning("Dedup registry corrupted; resetting")
        _REGISTRY_PATH.write_text("{}")
        return {}


def check_duplicate(provider: str, url: str) -> Optional[dict]:
    """Return existing entry if a prior request matches this provider+URL combo.

    Match logic:
      - Exact: same normalized provider + same normalized URL → returns the entry.
      - None: no match → returns None.

    The caller decides what to do (hard-block vs warn-and-allow).
    """
    if not provider or not url:
        return None
    key_provider = _normalize_provider(provider)
    key_url = _normalize_url(url)
    with _REGISTRY_LOCK:
        registry = _ensure_registry()
    entry = registry.get(f"{key_provider}|{key_url}")
    if entry:
        logger.info(
            f"Dedup hit | provider={key_provider!r} url={key_url!r} "
            f"prior_request={entry.get('request_id')!r}"
        )
    return entry


def check_provider_match(provider: str, url: str) -> Optional[dict]:
    """Return prior entry where provider matches but URL differs (near-duplicate)."""
    if not provider:
        return None
    key_provider = _normalize_provider(provider)
    key_url = _normalize_url(url)
    with _REGISTRY_LOCK:
        registry = _ensure_registry()
    for k, v in registry.items():
        rp, ru = k.split("|", 1)
        if rp == key_provider and ru != key_url:
            logger.info(
                f"Near-duplicate | provider={rp!r} prior_url={ru!r} new_url={key_url!r}"
            )
            return v
    return None


def register(provider: str, url: str, request_id: str, config_path: Optional[str] = None) -> None:
    """Record this provider+URL combo as processed."""
    if not provider or not url:
        return
    key = f"{_normalize_provider(provider)}|{_normalize_url(url)}"
    with _REGISTRY_LOCK:
        registry = _ensure_registry()
        registry[key] = {
            "request_id": request_id,
            "provider": provider,
            "url": url,
            "config_path": config_path,
        }
        _REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    logger.info(f"Dedup registered | key={key} request_id={request_id}")
