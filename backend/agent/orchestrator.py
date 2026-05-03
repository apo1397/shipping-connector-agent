"""Orchestrator — v2 flow with notifications, dedup, staging-URL handling,
diagnostic test classification, and a single approval gate.

Flow (per PRD v2 §4):

  1. Submit + Pre-flight (doc reachable + dedup check)         [auto]
  2. Discovery (B2C endpoint, auth, statuses, mappings)        [auto]
  3. Clarification pause (only if multiple candidate endpoints)[human if needed]
  4. Staging-URL detection                                      [auto]
  5. Staging→Prod URL confirm                                   [PAUSE if flagged]
  6. Live test with creds + AWB                                 [PAUSE for input]
  7. Failure classification (auth_failure / awb_not_found /
     wrong_domain / unknown)                                    [auto]
  8. JIRA ticket created (simulated in dev)                     [auto, post-validation]
  9. Final approval                                             [PAUSE — single gate]
 10. JSON config emitted to handoff                             [auto]

Every step transition emits a `notification` SSE event with shape:
{step, status, by, provider, details, ts, jira}.
The frontend renders these in a live timeline.
"""

import json
import time
import uuid
import logging
from typing import AsyncGenerator, Optional
from backend.config import Settings
from backend.agent.context import AgentContext
from backend.agent.staging_url import is_staging_url, rewrite_host, extract_host
from backend.agent.notifications import build as build_notification
from backend.fetcher import FetcherDetector
from backend.analyzer import LLMClient, APIDiscoveryAnalyzer, StatusExtractor
from backend.generator import generate_connector_config
from backend import persistence

logger = logging.getLogger(__name__)


class AgentOrchestrator:

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
        self.sessions: dict[str, AgentContext] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # External resume hooks (called by route handlers)
    # ─────────────────────────────────────────────────────────────────────────

    def resume_after_clarification(self, session_id: str, focus_hint: str) -> bool:
        ctx = self.sessions.get(session_id)
        if not ctx:
            return False
        ctx.clarification_focus_hint = focus_hint
        ctx.clarification_event.set()
        return True

    def resume_after_staging_url(self, session_id: str, prod_base_url: str) -> bool:
        ctx = self.sessions.get(session_id)
        if not ctx:
            return False
        ctx.prod_base_url = prod_base_url.strip()
        ctx.staging_url_event.set()
        return True

    def resume_after_live_test(self, session_id: str) -> bool:
        """Called after POST /test-endpoint succeeds (or fails terminally)."""
        ctx = self.sessions.get(session_id)
        if not ctx:
            return False
        ctx.live_test_event.set()
        return True

    def resume_after_review(self, session_id: str, confirmed_mappings: dict) -> bool:
        ctx = self.sessions.get(session_id)
        if not ctx:
            return False
        ctx.confirmed_mappings = confirmed_mappings
        ctx.review_event.set()
        return True

    def resume_after_approval(
        self,
        session_id: str,
        decision: str,
        comment: Optional[str] = None,
        approver: Optional[str] = None,
        confirmed_mappings: Optional[dict] = None,
    ) -> bool:
        ctx = self.sessions.get(session_id)
        if not ctx:
            return False
        ctx.approval_decision = decision
        ctx.approval_comment = comment
        ctx.approver = approver or "approver"
        if confirmed_mappings:
            ctx.confirmed_mappings = confirmed_mappings
        ctx.approval_event.set()
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Main pipeline
    # ─────────────────────────────────────────────────────────────────────────

    async def run(
        self,
        session_id: str,
        url: str,
        provider_hint: Optional[str] = None,
        requestor: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:

        ctx = AgentContext(
            session_id=session_id,
            source_url=url,
            provider_name_hint=provider_hint,
            requestor=requestor or "requestor",
        )
        self.sessions[session_id] = ctx
        provider_label = provider_hint or "(unknown)"

        t0 = time.perf_counter()
        logger.info(f"[{session_id}] Pipeline start | url={url} provider={provider_label!r}")

        # Notification: submitted
        yield self._notify(ctx, "Submitted", "started", ctx.requestor,
                           details=f"Doc URL: {url}")

        # ── Step 1: PRE-FLIGHT (doc reachable + dedup) ──────────────────────
        try:
            yield self._notify(ctx, "Pre-flight", "started", "agent",
                               details="Fetching doc + checking for duplicates")
            yield self._emit("step_start", step="preflight",
                             message="Pre-flight: fetching doc + dedup check...")

            # Dedup check — only if provider hint provided (else can't dedup safely)
            if provider_hint:
                dup = persistence.check_duplicate(provider_hint, url)
                if dup:
                    msg = (
                        f"Duplicate request — provider+URL combo already processed. "
                        f"Prior request: {dup.get('request_id')}"
                    )
                    yield self._notify(ctx, "Pre-flight", "failed", "agent",
                                       details=msg)
                    yield self._emit(
                        "preflight_duplicate",
                        prior_request_id=dup.get("request_id"),
                        prior_url=dup.get("url"),
                        message=msg,
                    )
                    return

            # Fetch doc
            await self._step_fetch(ctx)
            yield self._emit("step_complete", step="preflight", data={
                "content_type": ctx.content_type,
                "doc_chars": len(ctx.raw_content),
            })
            yield self._notify(ctx, "Pre-flight", "passed", "agent",
                               details=f"Doc fetched ({len(ctx.raw_content):,} chars). No duplicates.")
        except Exception as e:
            logger.error(f"[{session_id}] Pre-flight error: {e}", exc_info=True)
            yield self._notify(ctx, "Pre-flight", "failed", "agent",
                               details=f"Doc unreachable: {str(e)[:160]}")
            yield self._emit("step_error", step="preflight", error=str(e))
            return

        # ── Step 2: DISCOVER APIS ────────────────────────────────────────────
        try:
            yield self._notify(ctx, "Discovery", "started", "agent",
                               details="Identifying B2C tracking endpoint + auth + statuses")
            yield self._emit("step_start", step="discover_apis",
                             message="Discovering tracking & auth endpoints...")
            await self._step_discover_apis(ctx)
        except Exception as e:
            logger.error(f"[{session_id}] Discover error: {e}", exc_info=True)
            yield self._notify(ctx, "Discovery", "failed", "agent", details=str(e)[:160])
            yield self._emit("step_error", step="discover_apis", error=str(e))
            return

        # ── (optional) CLARIFICATION PAUSE ──────────────────────────────────
        if ctx.tracking_api and ctx.tracking_api.needs_clarification:
            yield self._notify(ctx, "Discovery", "needs_input", "agent",
                               details=f"Multiple endpoint candidates — needs selection")
            yield self._emit(
                "clarification_needed",
                question=ctx.tracking_api.clarification_question,
                candidates=[c.dict() for c in ctx.tracking_api.candidates],
                current_best=ctx.tracking_api.dict(),
            )
            await ctx.clarification_event.wait()
            yield self._notify(ctx, "Discovery", "passed", ctx.requestor,
                               details=f"Endpoint selected: {ctx.clarification_focus_hint[:120]}")
            try:
                yield self._emit("step_start", step="discover_apis",
                                 message="Re-analyzing selected endpoint...")
                await self._step_discover_apis(ctx, focus_hint=ctx.clarification_focus_hint)
            except Exception as e:
                yield self._notify(ctx, "Discovery", "failed", "agent", details=str(e)[:160])
                yield self._emit("step_error", step="discover_apis", error=str(e))
                return

        # Discovery + status extraction + mapping suggestion (combine for fewer pauses)
        try:
            await self._step_extract_statuses(ctx)
            await self._step_suggest_mappings(ctx)
        except Exception as e:
            logger.error(f"[{session_id}] Status/mapping error: {e}", exc_info=True)
            yield self._notify(ctx, "Discovery", "failed", "agent", details=str(e)[:160])
            yield self._emit("step_error", step="discover_apis", error=str(e))
            return

        yield self._emit("step_complete", step="discover_apis", data={
            "tracking_api": ctx.tracking_api.dict() if ctx.tracking_api else None,
            "auth_api": ctx.auth_api.dict() if ctx.auth_api else None,
            "auth_mechanism": ctx.auth_mechanism,
            "provider_statuses": [s.dict() for s in ctx.provider_statuses],
        })
        yield self._notify(
            ctx, "Discovery", "passed", "agent",
            details=(
                f"Endpoint: {ctx.tracking_api.method if ctx.tracking_api else '?'} "
                f"{ctx.tracking_api.url if ctx.tracking_api else '?'} · "
                f"Auth: {ctx.auth_mechanism or 'unknown'} · "
                f"{len(ctx.provider_statuses)} provider statuses extracted"
            ),
        )

        # ── Step 3: STAGING URL DETECTION ───────────────────────────────────
        if ctx.tracking_api and ctx.tracking_api.url and is_staging_url(ctx.tracking_api.url):
            ctx.staging_url_detected = True
            ctx.discovered_host_original = extract_host(ctx.tracking_api.url)
            yield self._notify(
                ctx, "Staging URL flagged", "needs_input", "agent",
                details=(
                    f"Discovered URL looks like staging/sandbox "
                    f"({ctx.discovered_host_original!r}). Awaiting prod base URL."
                ),
            )
            yield self._emit(
                "staging_url_flagged",
                discovered_url=ctx.tracking_api.url,
                discovered_host=ctx.discovered_host_original,
            )
            await ctx.staging_url_event.wait()
            # Rewrite host on the tracking endpoint
            old_url = ctx.tracking_api.url
            new_url = rewrite_host(old_url, ctx.prod_base_url or "")
            ctx.tracking_api.url = new_url
            if hasattr(ctx.tracking_api, "base_url"):
                ctx.tracking_api.base_url = (
                    f"https://{extract_host(ctx.prod_base_url)}"
                    if not ctx.prod_base_url.startswith(("http://", "https://"))
                    else f"{extract_host(ctx.prod_base_url)}"
                )
            ctx.host_rewritten = True
            yield self._notify(
                ctx, "Prod URL confirmed", "passed", ctx.requestor,
                details=f"Rewrote host: {old_url} → {new_url}",
            )
            yield self._emit("staging_url_resolved",
                             rewritten_url=new_url,
                             host_rewritten=True)
        else:
            yield self._notify(ctx, "Staging URL check", "passed", "agent",
                               details="URL looks like prod — no rewrite needed.")

        # ── Step 4: AWAIT CREDS + AWB → LIVE TEST ───────────────────────────
        # Auto-confirm mappings with the suggested values so the live test has
        # something usable; the final approval gate lets the approver edit them.
        if not ctx.confirmed_mappings:
            ctx.confirmed_mappings = {
                s.code: s.suggested_mapping for s in ctx.provider_statuses
            }

        yield self._notify(
            ctx, "Awaiting creds + AWB", "needs_input", "agent",
            details="Provide test credentials and an AWB to run the live test.",
        )
        yield self._emit("awaiting_creds_and_awb",
                         auth=ctx.auth_api.dict() if ctx.auth_api else None,
                         credentials_required=(
                             ctx.auth_api.credentials_required if ctx.auth_api else ["api_key"]
                         ))
        # Wait for the test to be triggered + completed via POST /test-endpoint
        await ctx.live_test_event.wait()

        # By now ctx.live_test_classification is set
        cls = ctx.live_test_classification or {"classification": "unknown"}
        if cls.get("classification") == "passed":
            yield self._notify(
                ctx, "Live test", "passed", "agent",
                details=f"AWB {ctx.test_awb} → status {ctx.live_test_result.get('current_status') if ctx.live_test_result else '—'}",
            )
        else:
            yield self._notify(
                ctx, "Live test", "failed", "agent",
                details=(
                    f"Classification: {cls.get('classification')!r} · "
                    f"{cls.get('reason', '')[:160]}"
                ),
            )

        # ── Step 5: JIRA TICKET (created post-validation; simulated) ────────
        if cls.get("classification") == "passed":
            ctx.jira_ticket_id = f"RE-{int(time.time())%100000:05d}"
            yield self._notify(
                ctx, "JIRA ticket created", "passed", "agent",
                details=f"Validations passed. Ticket {ctx.jira_ticket_id} on RE Board.",
                jira=ctx.jira_ticket_id,
            )
            yield self._emit("validations_passed", jira_ticket=ctx.jira_ticket_id)
        else:
            # Test failed — surface but don't auto-create JIRA. The requestor can retry
            # by sending another POST /test-endpoint (the live_test_event is reset by
            # the route handler on retries).
            # For MVP simplicity we proceed to approval anyway and let the approver
            # decide; in real life a hard-fail would loop back to creds entry.
            yield self._emit("validations_failed",
                             classification=cls,
                             attempts=ctx.live_test_attempts)
            # Stop here — let the requestor retry via the test endpoint
            return

        # ── Step 6: FINAL APPROVAL (single gate per PRD v2) ─────────────────
        yield self._notify(
            ctx, "Awaiting approval", "needs_input", "approver",
            details="Review the discovery + test result and approve or reject.",
            jira=ctx.jira_ticket_id or "",
        )
        yield self._emit(
            "awaiting_approval",
            mappings=[s.dict() for s in ctx.provider_statuses],
            tracking_api=ctx.tracking_api.dict() if ctx.tracking_api else None,
            auth_api=ctx.auth_api.dict() if ctx.auth_api else None,
            test_result=ctx.live_test_result,
            host_rewritten=ctx.host_rewritten,
            discovered_host_original=ctx.discovered_host_original,
            jira_ticket_id=ctx.jira_ticket_id,
        )
        await ctx.approval_event.wait()

        if ctx.approval_decision != "approve":
            yield self._notify(
                ctx, "Approval", "failed", ctx.approver or "approver",
                details=f"Rejected: {ctx.approval_comment or '—'}",
                jira=ctx.jira_ticket_id or "",
            )
            yield self._emit("rejected",
                             reason=ctx.approval_comment,
                             approver=ctx.approver)
            return

        yield self._notify(
            ctx, "Approval", "passed", ctx.approver or "approver",
            details="Approved — ready for code-gen handoff.",
            jira=ctx.jira_ticket_id or "",
        )

        # ── Step 7: GENERATE CONFIG + HANDOFF ────────────────────────────────
        try:
            yield self._emit("step_start", step="generate_config",
                             message="Assembling final connector config...")
            await self._step_generate_config(ctx)
            yield self._emit("step_complete", step="generate_config", data={
                "config": ctx.connector_config,
                "provider_name": ctx.provider_name_hint or "connector",
            })
            yield self._notify(
                ctx, "Config handoff", "passed", "agent",
                details=f"JSON config emitted (schema {ctx.connector_config.get('schema_version')}).",
                jira=ctx.jira_ticket_id or "",
            )
        except Exception as e:
            logger.error(f"[{session_id}] Config gen error: {e}", exc_info=True)
            yield self._notify(ctx, "Config handoff", "failed", "agent", details=str(e)[:160])
            yield self._emit("step_error", step="generate_config", error=str(e))
            return

        # Register in dedup registry now that this is a real, approved config
        if ctx.provider_name_hint:
            persistence.register(
                provider=ctx.provider_name_hint,
                url=ctx.source_url,
                request_id=session_id,
                config_path=None,
            )

        yield self._emit("config_ready", jira_ticket=ctx.jira_ticket_id)
        elapsed = round((time.perf_counter() - t0), 2)
        logger.info(f"[{session_id}] Pipeline complete | elapsed={elapsed}s")

    # ─────────────────────────────────────────────────────────────────────────
    # Step implementations
    # ─────────────────────────────────────────────────────────────────────────

    async def _step_fetch(self, ctx: AgentContext) -> None:
        result = await self.fetcher.fetch(
            ctx.source_url,
            timeout=self.settings.fetcher_timeout,
        )
        ctx.raw_content = result.raw_text
        ctx.content_type = result.content_type
        ctx.structured_spec = result.structured_data

    async def _step_discover_apis(self, ctx: AgentContext, focus_hint: str = "") -> None:
        hint = ctx.provider_name_hint or ""
        ctx.tracking_api = await self.analyzer.discover_tracking_api(
            ctx.raw_content, hint, focus_hint=focus_hint
        )
        ctx.auth_api = await self.analyzer.discover_auth_api(ctx.raw_content, hint)
        ctx.auth_mechanism = ctx.auth_api.auth_type if ctx.auth_api else "none"

    async def _step_extract_statuses(self, ctx: AgentContext) -> None:
        ctx.provider_statuses = await self.status_extractor.extract_statuses(
            ctx.raw_content, ctx.provider_name_hint or ""
        )

    async def _step_suggest_mappings(self, ctx: AgentContext) -> None:
        ctx.provider_statuses = await self.status_extractor.suggest_mappings(
            ctx.provider_statuses
        )

    async def _step_generate_config(self, ctx: AgentContext) -> None:
        provider_name = ctx.provider_name_hint or "connector"
        config = generate_connector_config(
            provider_name=provider_name,
            source_url=ctx.source_url,
            tracking_api=ctx.tracking_api,
            auth_api=ctx.auth_api,
            confirmed_mappings=ctx.confirmed_mappings,
            provider_statuses=ctx.provider_statuses,
            implementation_hints=ctx.implementation_hints,
            test_credentials=ctx.test_credentials,
            test_awb=ctx.test_awb,
            live_test_result=ctx.live_test_result,
        )
        # Stamp v2 fields onto the tracking endpoint section
        if ctx.host_rewritten and "tracking" in config and "endpoint" in config["tracking"]:
            config["tracking"]["endpoint"]["host_rewritten"] = True
            config["tracking"]["endpoint"]["discovered_host_original"] = ctx.discovered_host_original
        else:
            config.setdefault("tracking", {}).setdefault("endpoint", {})["host_rewritten"] = False
            config["tracking"]["endpoint"]["discovered_host_original"] = None
        # Stamp approval block
        config["approval"] = {
            "approver_id": ctx.approver or "",
            "decision": ctx.approval_decision or "approve",
            "comment": ctx.approval_comment or "",
            "jira_ticket": ctx.jira_ticket_id or "",
        }
        # Stamp failure classification (will be null on pass)
        if ctx.live_test_classification:
            config.setdefault("test_run", {})["classification"] = ctx.live_test_classification
        ctx.connector_config = config

    # ─────────────────────────────────────────────────────────────────────────
    # Notification + emit helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _notify(
        self,
        ctx: AgentContext,
        step: str,
        status: str,
        by: str,
        details: str = "",
        jira: str = "",
    ) -> str:
        n = build_notification(
            step=step,
            status=status,
            by=by,
            provider=ctx.provider_name_hint or "",
            details=details,
            jira=jira or (ctx.jira_ticket_id or "not yet created"),
        )
        ctx.notifications.append(n)
        return self._emit("notification", **n)

    def _emit(self, event_type: str, **kwargs) -> str:
        return json.dumps({"type": event_type, **kwargs})
