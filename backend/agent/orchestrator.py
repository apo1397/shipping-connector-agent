"""Orchestrator - coordinates the entire pipeline."""

import json
import logging
from typing import AsyncGenerator
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
        )
        self.analyzer = APIDiscoveryAnalyzer(self.llm)

    async def run(
        self,
        session_id: str,
        url: str,
        provider_hint: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Run the full pipeline, yielding SSE events."""
        context = AgentContext(session_id=session_id, source_url=url, provider_name_hint=provider_hint)
        
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
            # Pipeline would pause here in real implementation
            yield await self._emit_step_complete(PipelineStep.AWAIT_USER_REVIEW)
            
            # TODO: Remaining steps (code generation, validation)
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            yield await self._emit_step_error(PipelineStep(context.session_id[:10]), str(e))

    async def _step_fetch(self, context: AgentContext) -> None:
        """Step 1: Fetch and parse the URL."""
        try:
            result = await self.fetcher.fetch(context.source_url, timeout=self.settings.fetcher_timeout)
            context.raw_content = result.raw_text
            context.content_type = result.content_type
            context.structured_spec = result.structured_data
            logger.info(f"Fetched {context.content_type} from {context.source_url}")
        except Exception as e:
            raise ValueError(f"Failed to fetch URL: {e}")

    async def _step_discover_apis(self, context: AgentContext) -> None:
        """Step 2: Discover tracking and auth APIs."""
        try:
            context.tracking_api = await self.analyzer.discover_tracking_api(
                context.raw_content,
                context.provider_name_hint or "",
            )
            logger.info(f"Discovered tracking API: {context.tracking_api.name}")
            
            context.auth_api = await self.analyzer.discover_auth_api(
                context.raw_content,
                context.provider_name_hint or "",
            )
            if context.auth_api:
                logger.info(f"Discovered auth API: {context.auth_api.name}")
                context.auth_mechanism = context.auth_api.auth_type
            else:
                context.auth_mechanism = "none"
        except Exception as e:
            raise ValueError(f"Failed to discover APIs: {e}")

    async def _step_extract_statuses(self, context: AgentContext) -> None:
        """Step 3: Extract provider shipment statuses."""
        # TODO: Implement status extraction
        context.provider_statuses = ["in_transit", "delivered", "out_for_delivery", "cancelled"]
        logger.info(f"Extracted {len(context.provider_statuses)} statuses")

    async def _step_suggest_mappings(self, context: AgentContext) -> None:
        """Step 4: Suggest status mappings."""
        # TODO: Implement mapping suggestion
        context.suggested_mappings = {
            status: "in_transit" for status in context.provider_statuses
        }
        logger.info(f"Suggested mappings for {len(context.suggested_mappings)} statuses")

    async def _emit_step_start(self, step: PipelineStep) -> str:
        """Emit a step start event."""
        event = {
            "type": "step_start",
            "step": step.value,
        }
        return json.dumps(event)

    async def _emit_step_complete(self, step: PipelineStep) -> str:
        """Emit a step complete event."""
        event = {
            "type": "step_complete",
            "step": step.value,
        }
        return json.dumps(event)

    async def _emit_step_error(self, step: PipelineStep, error: str) -> str:
        """Emit a step error event."""
        event = {
            "type": "step_error",
            "step": step.value,
            "error": error,
        }
        return json.dumps(event)
