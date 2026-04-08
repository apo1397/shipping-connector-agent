"""Orchestrator - coordinates the entire pipeline with pause/resume."""

import json
import time
import logging
from typing import AsyncGenerator, Optional
from backend.config import Settings
from backend.agent.context import AgentContext
from backend.agent.steps import PipelineStep
from backend.fetcher import FetcherDetector
from backend.analyzer import LLMClient, APIDiscoveryAnalyzer, StatusExtractor
from backend.generator import CodeGenerator, CodeValidator, save_connector

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Main orchestrator that runs the pipeline with pause/resume support."""

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
        self.status_extractor = StatusExtractor(self.llm)
        self.code_generator = CodeGenerator(self.llm)
        self.code_validator = CodeValidator()

        # Session registry for pause/resume
        self.sessions: dict[str, AgentContext] = {}

    def resume_after_review(self, session_id: str, confirmed_mappings: dict) -> bool:
        """Called by PUT /mappings to resume the pipeline."""
        ctx = self.sessions.get(session_id)
        if not ctx:
            logger.warning(f"[{session_id}] resume_after_review: session not found")
            return False
        ctx.confirmed_mappings = confirmed_mappings
        ctx.review_event.set()
        logger.info(f"[{session_id}] Pipeline resumed with {len(confirmed_mappings)} confirmed mappings")
        return True

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
        self.sessions[session_id] = context

        logger.info(f"[{session_id}] Pipeline start | url={url}")
        pipeline_start = time.perf_counter()

        # Step 1: FETCH
        try:
            yield self._emit("step_start", step="fetch", message="Fetching documentation...")
            await self._step_fetch(context)
            endpoint_count = 0
            if context.structured_spec and "item" in context.structured_spec:
                endpoint_count = len(context.structured_spec.get("item", []))
            yield self._emit("step_complete", step="fetch", data={
                "endpoint_count": endpoint_count,
                "content_type": context.content_type,
                "doc_length": len(context.raw_content),
            })
        except Exception as e:
            yield self._emit("step_error", step="fetch", error=str(e))
            return

        # Step 2: DISCOVER APIS
        try:
            yield self._emit("step_start", step="discover_apis", message="Discovering tracking & auth APIs...")
            await self._step_discover_apis(context)
            yield self._emit("step_complete", step="discover_apis", data={
                "tracking_api": context.tracking_api.dict() if context.tracking_api else None,
                "auth_api": context.auth_api.dict() if context.auth_api else None,
                "auth_mechanism": context.auth_mechanism,
            })
        except Exception as e:
            yield self._emit("step_error", step="discover_apis", error=str(e))
            return

        # Step 3: EXTRACT STATUSES
        try:
            yield self._emit("step_start", step="extract_statuses", message="Extracting provider statuses...")
            await self._step_extract_statuses(context)
            yield self._emit("step_complete", step="extract_statuses", data={
                "statuses": [s.dict() for s in context.provider_statuses],
                "count": len(context.provider_statuses),
            })
        except Exception as e:
            yield self._emit("step_error", step="extract_statuses", error=str(e))
            return

        # Step 4: SUGGEST MAPPINGS
        try:
            yield self._emit("step_start", step="suggest_mappings", message="Suggesting status mappings...")
            await self._step_suggest_mappings(context)
            yield self._emit("step_complete", step="suggest_mappings", data={
                "mappings": [s.dict() for s in context.provider_statuses],
            })
        except Exception as e:
            yield self._emit("step_error", step="suggest_mappings", error=str(e))
            return

        # Emit mapping_review event and pause
        yield self._emit("mapping_review", mappings=[s.dict() for s in context.provider_statuses])

        # Step 5: AWAIT USER REVIEW — pause here
        yield self._emit("step_start", step="await_user_review", message="Waiting for mapping confirmation...")
        await context.review_event.wait()
        yield self._emit("step_complete", step="await_user_review", data={
            "confirmed_count": len(context.confirmed_mappings),
        })

        # Step 6: GENERATE CODE
        try:
            yield self._emit("step_start", step="generate_code", message="Generating connector code...")
            await self._step_generate_code(context)
            yield self._emit("step_complete", step="generate_code", data={
                "files": context.generated_files,
                "provider_name": context.provider_name_hint or "connector",
                "validation_errors": context.validation_errors,
            })
        except Exception as e:
            yield self._emit("step_error", step="generate_code", error=str(e))
            return

        # Emit test_ready
        yield self._emit("test_ready")

        elapsed = time.perf_counter() - pipeline_start
        logger.info(f"[{session_id}] Pipeline complete | elapsed={elapsed:.2f}s")

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    async def _step_fetch(self, context: AgentContext) -> None:
        sid = context.session_id
        logger.info(f"[{sid}] Fetching URL: {context.source_url}")
        try:
            result = await self.fetcher.fetch(
                context.source_url,
                timeout=self.settings.fetcher_timeout,
                sections=["Track Order", "Authentication API"],
            )
            context.raw_content = result.raw_text
            context.content_type = result.content_type
            context.structured_spec = result.structured_data
            logger.info(f"[{sid}] Fetch complete | type={result.content_type} chars={len(result.raw_text)}")
        except Exception as e:
            logger.error(f"[{sid}] Fetch failed: {e}")
            raise ValueError(f"Failed to fetch URL: {e}")

    async def _step_discover_apis(self, context: AgentContext) -> None:
        sid = context.session_id
        hint = context.provider_name_hint or ""

        context.tracking_api = await self.analyzer.discover_tracking_api(context.raw_content, hint)
        logger.info(f"[{sid}] Tracking API: {context.tracking_api.name} {context.tracking_api.method} {context.tracking_api.url}")

        context.auth_api = await self.analyzer.discover_auth_api(context.raw_content, hint)
        context.auth_mechanism = context.auth_api.auth_type if context.auth_api else "none"
        logger.info(f"[{sid}] Auth: {context.auth_mechanism}")

    async def _step_extract_statuses(self, context: AgentContext) -> None:
        sid = context.session_id
        context.provider_statuses = await self.status_extractor.extract_statuses(
            context.raw_content, context.provider_name_hint or ""
        )
        logger.info(f"[{sid}] Extracted {len(context.provider_statuses)} statuses")

    async def _step_suggest_mappings(self, context: AgentContext) -> None:
        sid = context.session_id
        context.provider_statuses = await self.status_extractor.suggest_mappings(
            context.provider_statuses
        )
        logger.info(f"[{sid}] Mappings suggested for {len(context.provider_statuses)} statuses")

    async def _step_generate_code(self, context: AgentContext) -> None:
        sid = context.session_id
        provider_name = context.provider_name_hint or "connector"

        tracking_dict = context.tracking_api.dict() if context.tracking_api else {}
        auth_dict = context.auth_api.dict() if context.auth_api else {}

        context.generated_files = await self.code_generator.generate(
            provider_name=provider_name,
            tracking_api=tracking_dict,
            auth_api=auth_dict,
            confirmed_mappings=context.confirmed_mappings,
            documentation=context.raw_content,
        )

        # Validate connector.py
        connector_code = context.generated_files.get("connector.py", "")
        context.validation_errors = self.code_validator.validate(connector_code)

        # Save to disk
        save_connector(provider_name, context.generated_files)
        logger.info(f"[{sid}] Code generated and saved for {provider_name}")

    # ------------------------------------------------------------------
    # SSE helpers
    # ------------------------------------------------------------------

    def _emit(self, event_type: str, **kwargs) -> str:
        return json.dumps({"type": event_type, **kwargs})
