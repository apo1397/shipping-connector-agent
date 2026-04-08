"""Orchestrator - coordinates the entire pipeline."""

import json
import time
import logging
from typing import AsyncGenerator, Optional
from backend.config import Settings
from backend.agent.context import AgentContext
from backend.agent.steps import PipelineStep
from backend.fetcher import FetcherDetector
from backend.analyzer import LLMClient, APIDiscoveryAnalyzer

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Main orchestrator that runs the pipeline."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fetcher = FetcherDetector()
        self.llm = LLMClient(
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )
        self.analyzer = APIDiscoveryAnalyzer(self.llm)

    async def run(
        self,
        session_id: str,
        url: str,
        provider_hint: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Run the full pipeline, yielding SSE events."""
        context = AgentContext(
            session_id=session_id,
            source_url=url,
            provider_name_hint=provider_hint,
        )

        logger.info(
            f"[{session_id}] Pipeline start | url={url} provider_hint={provider_hint!r}"
        )
        pipeline_start = time.perf_counter()

        try:
            # Step 1: FETCH
            yield await self._emit_step_start(PipelineStep.FETCH)
            await self._step_fetch(context)
            yield await self._emit_step_complete(PipelineStep.FETCH)

            # Step 2: DISCOVER_APIS
            yield await self._emit_step_start(PipelineStep.DISCOVER_APIS)
            await self._step_discover_apis(context)
            yield await self._emit_step_complete(PipelineStep.DISCOVER_APIS)

            # Step 3: EXTRACT_STATUSES
            yield await self._emit_step_start(PipelineStep.EXTRACT_STATUSES)
            await self._step_extract_statuses(context)
            yield await self._emit_step_complete(PipelineStep.EXTRACT_STATUSES)

            # Step 4: SUGGEST_MAPPINGS
            yield await self._emit_step_start(PipelineStep.SUGGEST_MAPPINGS)
            await self._step_suggest_mappings(context)
            yield await self._emit_step_complete(PipelineStep.SUGGEST_MAPPINGS)

            # Step 5: AWAIT_USER_REVIEW
            yield await self._emit_step_start(PipelineStep.AWAIT_USER_REVIEW)
            yield await self._emit_step_complete(PipelineStep.AWAIT_USER_REVIEW)

            elapsed = time.perf_counter() - pipeline_start
            logger.info(f"[{session_id}] Pipeline complete | total_elapsed={elapsed:.2f}s")

        except Exception as e:
            elapsed = time.perf_counter() - pipeline_start
            logger.error(
                f"[{session_id}] Pipeline failed | elapsed={elapsed:.2f}s | "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            yield await self._emit_step_error(PipelineStep.FETCH, str(e))

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    async def _step_fetch(self, context: AgentContext) -> None:
        """Step 1: Fetch and parse the URL."""
        sid = context.session_id
        logger.info(f"[{sid}] Fetching URL: {context.source_url}")
        t0 = time.perf_counter()
        try:
            result = await self.fetcher.fetch(
                context.source_url,
                timeout=self.settings.fetcher_timeout,
                sections=["Track Order", "Authentication API"],
            )
            context.raw_content = result.raw_text
            context.content_type = result.content_type
            context.structured_spec = result.structured_data

            elapsed = time.perf_counter() - t0
            logger.info(
                f"[{sid}] Fetch complete | content_type={result.content_type} "
                f"raw_chars={len(result.raw_text)} elapsed={elapsed:.2f}s"
            )
            if result.structured_data and "item" in result.structured_data:
                section_names = [i.get("name") for i in result.structured_data["item"]]
                logger.info(f"[{sid}] Postman sections fetched: {section_names}")

        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(
                f"[{sid}] Fetch failed | elapsed={elapsed:.2f}s | {type(e).__name__}: {e}"
            )
            raise ValueError(f"Failed to fetch URL: {e}")

    async def _step_discover_apis(self, context: AgentContext) -> None:
        """Step 2: Discover tracking and auth APIs."""
        sid = context.session_id
        logger.info(
            f"[{sid}] Discovering APIs | content_type={context.content_type} "
            f"doc_chars={len(context.raw_content)}"
        )
        t0 = time.perf_counter()
        try:
            context.tracking_api = await self.analyzer.discover_tracking_api(
                context.raw_content,
                context.provider_name_hint or "",
            )
            logger.info(
                f"[{sid}] Tracking API found | name={context.tracking_api.name!r} "
                f"method={context.tracking_api.method} url={context.tracking_api.url}"
            )

            context.auth_api = await self.analyzer.discover_auth_api(
                context.raw_content,
                context.provider_name_hint or "",
            )
            if context.auth_api:
                context.auth_mechanism = context.auth_api.auth_type
                logger.info(
                    f"[{sid}] Auth API found | name={context.auth_api.name!r} "
                    f"method={context.auth_api.method} url={context.auth_api.url} "
                    f"auth_type={context.auth_api.auth_type!r}"
                )
            else:
                context.auth_mechanism = "none"
                logger.info(f"[{sid}] Auth API → none (static key or no dedicated endpoint)")

            elapsed = time.perf_counter() - t0
            logger.info(f"[{sid}] API discovery complete | elapsed={elapsed:.2f}s")

        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(
                f"[{sid}] API discovery failed | elapsed={elapsed:.2f}s | "
                f"{type(e).__name__}: {e}"
            )
            raise ValueError(f"Failed to discover APIs: {e}")

    async def _step_extract_statuses(self, context: AgentContext) -> None:
        """Step 3: Extract provider shipment statuses."""
        sid = context.session_id
        # TODO: Implement LLM-based status extraction
        context.provider_statuses = [
            "in_transit", "delivered", "out_for_delivery", "cancelled"
        ]
        logger.info(
            f"[{sid}] Statuses extracted (stub) | count={len(context.provider_statuses)} "
            f"statuses={context.provider_statuses}"
        )

    async def _step_suggest_mappings(self, context: AgentContext) -> None:
        """Step 4: Suggest status mappings."""
        sid = context.session_id
        # TODO: Implement LLM-based mapping suggestion
        context.suggested_mappings = {
            status: "in_transit" for status in context.provider_statuses
        }
        logger.info(
            f"[{sid}] Mappings suggested (stub) | count={len(context.suggested_mappings)} "
            f"mappings={context.suggested_mappings}"
        )

    # ------------------------------------------------------------------
    # SSE event helpers
    # ------------------------------------------------------------------

    async def _emit_step_start(self, step: PipelineStep) -> str:
        logger.debug(f"SSE → step_start:{step.value}")
        return json.dumps({"type": "step_start", "step": step.value})

    async def _emit_step_complete(self, step: PipelineStep) -> str:
        logger.debug(f"SSE → step_complete:{step.value}")
        return json.dumps({"type": "step_complete", "step": step.value})

    async def _emit_step_error(self, step: PipelineStep, error: str) -> str:
        logger.debug(f"SSE → step_error:{step.value} error={error!r}")
        return json.dumps({"type": "step_error", "step": step.value, "error": error})
