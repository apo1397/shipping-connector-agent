"""API routes for the connector agent."""

import io
import uuid
import zipfile
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse
from .schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    UpdateMappingsRequest,
    CodeResponse,
    LiveTestRequest,
    LiveTestResponse,
    LiveTestResultItem,
    SessionStatusResponse,
)
from backend.agent.orchestrator import AgentOrchestrator
from backend.tester.live_test import ConnectorTester
from backend.config import Settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings) -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(title="GoKwik Connector Agent")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve frontend
    frontend_dir = Path(__file__).parent.parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        @app.get("/")
        async def serve_index():
            return FileResponse(str(frontend_dir / "index.html"))

    orchestrator = AgentOrchestrator(settings)
    tester = ConnectorTester()
    sessions: dict[str, dict] = {}

    @app.post("/api/v1/sessions", response_model=CreateSessionResponse)
    async def create_session(request: CreateSessionRequest) -> CreateSessionResponse:
        session_id = str(uuid.uuid4())
        sessions[session_id] = {
            "url": request.url,
            "provider_name_hint": request.provider_name_hint,
            "status": "created",
        }
        logger.info(f"Session created | id={session_id} url={request.url}")
        return CreateSessionResponse(session_id=session_id)

    @app.get("/api/v1/sessions/{session_id}/stream")
    async def stream_progress(session_id: str):
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")

        async def event_generator():
            session_data = sessions[session_id]
            async for event in orchestrator.run(
                session_id=session_id,
                url=session_data["url"],
                provider_hint=session_data.get("provider_name_hint"),
            ):
                yield {"data": event}

        return EventSourceResponse(event_generator())

    @app.get("/api/v1/sessions/{session_id}/status")
    async def get_status(session_id: str):
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        ctx = orchestrator.sessions.get(session_id)
        return {
            "session_id": session_id,
            "has_context": ctx is not None,
            "has_generated_files": bool(ctx and ctx.generated_files),
        }

    @app.get("/api/v1/sessions/{session_id}/mappings")
    async def get_mappings(session_id: str):
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx:
            return {"provider_statuses": [], "suggested_mappings": {}}
        return {
            "provider_statuses": [s.dict() for s in ctx.provider_statuses],
            "suggested_mappings": {s.code: s.suggested_mapping for s in ctx.provider_statuses},
        }

    @app.put("/api/v1/sessions/{session_id}/mappings")
    async def update_mappings(session_id: str, request: UpdateMappingsRequest):
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")

        success = orchestrator.resume_after_review(session_id, request.mappings)
        if not success:
            raise HTTPException(status_code=400, detail="Session not in review state")

        logger.info(f"Mappings confirmed for {session_id}: {len(request.mappings)} mappings")
        return {"status": "confirmed", "count": len(request.mappings)}

    @app.get("/api/v1/sessions/{session_id}/code", response_model=CodeResponse)
    async def get_code(session_id: str):
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx or not ctx.generated_files:
            raise HTTPException(status_code=400, detail="No code generated yet")
        return CodeResponse(files=ctx.generated_files)

    @app.get("/api/v1/sessions/{session_id}/download")
    async def download_code(session_id: str):
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx or not ctx.generated_files:
            raise HTTPException(status_code=400, detail="No code generated yet")

        # Create in-memory ZIP
        buffer = io.BytesIO()
        provider_name = ctx.provider_name_hint or "connector"
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in ctx.generated_files.items():
                zf.writestr(f"{provider_name}/{filename}", content)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={provider_name}_connector.zip"},
        )

    @app.post("/api/v1/sessions/{session_id}/test", response_model=LiveTestResponse)
    async def live_test(session_id: str, request: LiveTestRequest):
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        ctx = orchestrator.sessions.get(session_id)
        if not ctx or not ctx.generated_files:
            raise HTTPException(status_code=400, detail="No code generated yet")

        connector_code = ctx.generated_files.get("connector.py", "")
        if not connector_code:
            raise HTTPException(status_code=400, detail="No connector.py found")

        results = await tester.test(
            connector_code=connector_code,
            credentials=request.credentials,
            awb_numbers=request.awb_numbers,
        )

        ctx.test_results = results
        return LiveTestResponse(
            results=[LiveTestResultItem(**r) for r in results]
        )

    return app
