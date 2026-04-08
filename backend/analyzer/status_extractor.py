"""Status extraction and mapping suggestion via LLM."""

import json
import logging
from typing import List
from pydantic import BaseModel
from backend.models import ProviderStatus, GoKwikShipmentStatus
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

_MAX_DOC_CHARS = 12_000

# Pre-compute the valid GoKwik status values for validation
_VALID_GOKWIK_STATUSES = {s.value for s in GoKwikShipmentStatus}


class _StatusListResponse(BaseModel):
    """Wrapper for LLM response containing a list of statuses."""
    statuses: List[ProviderStatus]


class _MappingEntry(BaseModel):
    code: str
    suggested_mapping: str


class _MappingListResponse(BaseModel):
    mappings: List[_MappingEntry]


class StatusExtractor:
    """Extracts provider statuses from docs and suggests GoKwik mappings."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def _truncate(self, text: str) -> str:
        if len(text) > _MAX_DOC_CHARS:
            return text[:_MAX_DOC_CHARS] + "\n\n[... truncated ...]"
        return text

    async def extract_statuses(
        self, documentation: str, provider_hint: str = ""
    ) -> List[ProviderStatus]:
        """Extract all shipment statuses from API documentation."""
        logger.info(f"Extracting statuses | provider={provider_hint!r} doc_chars={len(documentation)}")
        documentation = self._truncate(documentation)

        system = (
            "You are an API documentation expert for shipping and logistics providers.\n"
            "Extract ALL shipment/tracking status codes from the documentation.\n"
            "Include status codes, descriptions, and whether each is a terminal state "
            "(delivered, cancelled, lost, RTO delivered are terminal).\n"
            "Return a JSON object with a 'statuses' array."
        )
        hint = f"Provider: {provider_hint}\n\n" if provider_hint else ""
        user = f"{hint}API Documentation:\n\n{documentation}"

        try:
            result = await self.llm.complete(
                system=system, user=user, response_format=_StatusListResponse
            )
            if isinstance(result, _StatusListResponse):
                logger.info(f"Extracted {len(result.statuses)} statuses")
                return result.statuses

            # Fallback: try parsing as raw JSON
            logger.warning("LLM returned non-structured response for statuses")
            return []
        except Exception as e:
            logger.error(f"Status extraction failed: {type(e).__name__}: {e}")
            raise

    async def suggest_mappings(
        self, statuses: List[ProviderStatus]
    ) -> List[ProviderStatus]:
        """Use LLM to suggest GoKwik status mappings for each provider status."""
        if not statuses:
            return statuses

        logger.info(f"Suggesting mappings for {len(statuses)} statuses")

        gokwik_statuses_desc = "\n".join(
            f"- {s.value}" for s in GoKwikShipmentStatus
        )

        statuses_desc = "\n".join(
            f"- code={s.code!r}, description={s.description!r}, is_terminal={s.is_terminal}"
            for s in statuses
        )

        system = (
            "You are a shipping logistics expert.\n"
            "Map each provider shipment status to the closest GoKwik internal status.\n\n"
            f"Available GoKwik statuses:\n{gokwik_statuses_desc}\n\n"
            "Return a JSON object with a 'mappings' array where each entry has "
            "'code' (the provider status code) and 'suggested_mapping' (the GoKwik status value)."
        )
        user = f"Provider statuses to map:\n{statuses_desc}"

        try:
            result = await self.llm.complete(
                system=system, user=user, response_format=_MappingListResponse
            )
            if isinstance(result, _MappingListResponse):
                mapping_dict = {m.code: m.suggested_mapping for m in result.mappings}
                for status in statuses:
                    suggested = mapping_dict.get(status.code, "unknown")
                    # Validate it's a real GoKwik status
                    if suggested in _VALID_GOKWIK_STATUSES:
                        status.suggested_mapping = suggested
                    else:
                        logger.warning(f"Invalid mapping {suggested!r} for {status.code!r}, defaulting to unknown")
                        status.suggested_mapping = "unknown"
                logger.info(f"Mappings suggested for {len(statuses)} statuses")
            return statuses
        except Exception as e:
            logger.error(f"Mapping suggestion failed: {type(e).__name__}: {e}")
            # Return statuses with default "unknown" mapping rather than crashing
            return statuses
