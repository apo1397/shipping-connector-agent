"""API routes — v2 flow."""

import json
import uuid
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from .schemas import (
    CreateSessionRequest, CreateSessionResponse, DuplicateRequestResponse,
    UpdateMappingsRequest, ClarificationRequest,
    ProdUrlRequest, ApprovalRequest,
    EndpointTestRequest, EndpointTestResponse,
    ConfigResponse, SessionStatusResponse, NotificationsResponse,
)
from backend.agent.orchestrator import AgentOrchestrator
from backend.agent.failure_classifier import classify as classify_failure
from backend.tester.endpoint_tester import EndpointTester
from backend.config import Settings
from backend import persistence

logger = logging.getLogger(__name__)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="GoKwik Connector Agent")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    frontend_dir = Path(__file__).parent.parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        @app.get("/")
        async def serve_index():
            return FileResponse(str(frontend_dir / "index.html"))

    orchestrator = AgentOrchestrator(settings)
    tester = EndpointTester()
    sessions: dict[str, dict] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Session creation — runs dedup pre-check synchronously
    # ─────────────────────────────────────────────────────────────────────────

    @app.post("/api/v1/sessions")
    async def create_session(req: CreateSessionRequest):
        # Synchronous dedup check (fail fast before opening the SSE stream)
        if req.provider_name_hint:
            dup = persistence.check_duplicate(req.provider_name_hint, req.url)
            if dup:
                logger.info(
                    f"Submission blocked — duplicate | provider={req.provider_name_hint!r} "
                    f"prior={dup.get('request_id')!r}"
                )
                return JSONResponse(
                    status_code=409,
                    content=DuplicateRequestResponse(
                        prior_request_id=dup.get("request_id", ""),
                        prior_provider=dup.get("provider", ""),
                        prior_url=dup.get("url", ""),
                        message=(
                            f"This provider+URL combo was already processed "
                            f"(prior request {dup.get('request_id')}). "
                            f"Submit a different URL or contact the prior approver."
                        ),
                    ).dict(),
                )
        sid = str(uuid.uuid4())
        sessions[sid] = {
            "url": req.url,
            "provider_name_hint": req.provider_name_hint,
            "requestor": req.requestor or "requestor",
        }
        logger.info(f"Session created | id={sid} url={req.url}")
        return CreateSessionResponse(session_id=sid)

    @app.get("/api/v1/sessions/{session_id}/stream")
    async def stream_progress(session_id: str):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")

        async def _gen():
            s = sessions[session_id]
            async for event in orchestrator.run(
                session_id=session_id,
                url=s["url"],
                provider_hint=s.get("provider_name_hint"),
                requestor=s.get("requestor"),
            ):
                yield {"data": event}

        return EventSourceResponse(_gen())

    @app.get("/api/v1/sessions/{session_id}/status", response_model=SessionStatusResponse)
    async def get_status(session_id: str):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        return SessionStatusResponse(
            session_id=session_id,
            has_context=ctx is not None,
            has_config=bool(ctx and ctx.connector_config),
        )

    @app.get("/api/v1/sessions/{session_id}/notifications", response_model=NotificationsResponse)
    async def get_notifications(session_id: str):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        return NotificationsResponse(notifications=ctx.notifications if ctx else [])

    # ─────────────────────────────────────────────────────────────────────────
    # Pause 1: Clarification
    # ─────────────────────────────────────────────────────────────────────────

    @app.put("/api/v1/sessions/{session_id}/clarification")
    async def resolve_clarification(session_id: str, req: ClarificationRequest):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx:
            raise HTTPException(400, "Session pipeline not started")

        focus_hint = req.focus_hint
        if not focus_hint and req.candidate_index is not None and ctx.tracking_api:
            candidates = ctx.tracking_api.candidates
            if 0 <= req.candidate_index < len(candidates):
                c = candidates[req.candidate_index]
                focus_hint = (
                    f"The user selected the '{c.name}' endpoint. "
                    f"Focus exclusively on: {c.description} at {c.url}"
                )

        ok = orchestrator.resume_after_clarification(session_id, focus_hint)
        if not ok:
            raise HTTPException(400, "Session not awaiting clarification")
        return {"status": "ok", "focus_hint": focus_hint}

    # ─────────────────────────────────────────────────────────────────────────
    # Pause 2: Staging→Prod URL confirm  (NEW v2)
    # ─────────────────────────────────────────────────────────────────────────

    @app.put("/api/v1/sessions/{session_id}/prod-url")
    async def resolve_prod_url(session_id: str, req: ProdUrlRequest):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx:
            raise HTTPException(400, "Session pipeline not started")
        if not ctx.staging_url_detected:
            raise HTTPException(400, "Session not awaiting prod-URL confirmation")
        ok = orchestrator.resume_after_staging_url(session_id, req.prod_base_url)
        if not ok:
            raise HTTPException(400, "Failed to resolve prod-URL pause")
        return {"status": "ok", "prod_base_url": req.prod_base_url}

    # ─────────────────────────────────────────────────────────────────────────
    # E2E endpoint test — also unblocks the pipeline's live_test_event
    # ─────────────────────────────────────────────────────────────────────────

    @app.post("/api/v1/sessions/{session_id}/test-endpoint",
              response_model=EndpointTestResponse)
    async def test_endpoint(session_id: str, req: EndpointTestRequest):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx or not ctx.tracking_api:
            raise HTTPException(400, "Session not ready — wait for discovery to complete")

        ctx.live_test_attempts += 1
        result = await tester.run(
            tracking_api=ctx.tracking_api,
            auth_api=ctx.auth_api,
            credentials=req.credentials,
            awb_number=req.awb_number,
        )

        # Classify the result into v2's 4 buckets
        classification = classify_failure(result)

        ctx.test_credentials = req.credentials
        ctx.test_awb = req.awb_number
        ctx.live_test_result = result
        ctx.live_test_classification = classification

        logger.info(
            f"[{session_id}] Live test result | "
            f"success={result['success']} class={classification['classification']!r} "
            f"attempt={ctx.live_test_attempts}"
        )

        # Unblock the pipeline so it can proceed to JIRA + approval
        # (only if classification == 'passed' OR if attempts >= 3 — caller decides)
        # For MVP: only unblock on pass. Failure means requestor retries.
        if classification["classification"] == "passed":
            orchestrator.resume_after_live_test(session_id)
        # On failure, the pipeline stays paused on live_test_event. The frontend
        # shows the diagnosis and lets the requestor edit creds/AWB and retry.

        response = result.copy()
        response["classification"] = classification
        return EndpointTestResponse(**response)

    # ─────────────────────────────────────────────────────────────────────────
    # Final approval gate (single)  (NEW v2)
    # ─────────────────────────────────────────────────────────────────────────

    @app.put("/api/v1/sessions/{session_id}/approval")
    async def submit_approval(session_id: str, req: ApprovalRequest):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx:
            raise HTTPException(400, "Session pipeline not started")
        if req.decision not in ("approve", "reject"):
            raise HTTPException(400, "decision must be 'approve' or 'reject'")

        ok = orchestrator.resume_after_approval(
            session_id=session_id,
            decision=req.decision,
            comment=req.comment,
            approver=req.approver,
            confirmed_mappings=req.confirmed_mappings,
        )
        if not ok:
            raise HTTPException(400, "Session not awaiting approval")
        return {"status": req.decision, "jira_ticket": ctx.jira_ticket_id}

    # ─────────────────────────────────────────────────────────────────────────
    # Mappings — kept for backward compat / direct edits during approval
    # ─────────────────────────────────────────────────────────────────────────

    @app.get("/api/v1/sessions/{session_id}/mappings")
    async def get_mappings(session_id: str):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx:
            return {"provider_statuses": [], "suggested_mappings": {}}
        return {
            "provider_statuses": [s.dict() for s in ctx.provider_statuses],
            "suggested_mappings": {
                s.code: s.suggested_mapping for s in ctx.provider_statuses
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Config output
    # ─────────────────────────────────────────────────────────────────────────

    @app.get("/api/v1/sessions/{session_id}/config", response_model=ConfigResponse)
    async def get_config(session_id: str):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx or not ctx.connector_config:
            raise HTTPException(400, "Config not yet generated")
        return ConfigResponse(config=ctx.connector_config)

    @app.get("/api/v1/sessions/{session_id}/download")
    async def download_config(session_id: str):
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx or not ctx.connector_config:
            raise HTTPException(400, "Config not yet generated")
        provider = (ctx.provider_name_hint or "connector").lower().replace(" ", "_")
        return JSONResponse(
            content=ctx.connector_config,
            headers={"Content-Disposition": f"attachment; filename={provider}_connector_config.json"},
        )

    return app
