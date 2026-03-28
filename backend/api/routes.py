"""API routes for the connector agent."""

import uuid
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from .schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    UpdateMappingsRequest,
    CodeResponse,
    LiveTestRequest,
    LiveTestResponse,
    SessionStatusResponse,
)
from backend.agent.orchestrator import AgentOrchestrator
from backend.config import Settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings) -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(title="GoKwik Connector Agent")
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize orchestrator
    orchestrator = AgentOrchestrator(settings)
    
    # Sessions storage (in-memory)
    sessions: dict[str, dict] = {}
    
    @app.post("/api/v1/sessions", response_model=CreateSessionResponse)
    async def create_session(request: CreateSessionRequest) -> CreateSessionResponse:
        """Create a new generation session."""
        session_id = str(uuid.uuid4())
        sessions[session_id] = {
            "url": request.url,
            "provider_name_hint": request.provider_name_hint,
            "status": "created",
        }
        logger.info(f"Created session {session_id} for URL {request.url}")
        return CreateSessionResponse(session_id=session_id)
    
    @app.get("/api/v1/sessions/{session_id}/stream")
    async def stream_progress(session_id: str):
        """SSE stream of pipeline progress."""
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        async def event_generator():
            session_data = sessions[session_id]
            
            # Run the orchestrator
            async for event in orchestrator.run(
                session_id=session_id,
                url=session_data["url"],
                provider_hint=session_data.get("provider_name_hint"),
            ):
                yield f"data: {event}\n\n"
        
        return EventSourceResponse(event_generator())
    
    @app.get("/api/v1/sessions/{session_id}/status", response_model=SessionStatusResponse)
    async def get_status(session_id: str):
        """Get current session status."""
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session_data = sessions[session_id]
        return SessionStatusResponse(
            session_id=session_id,
            current_step=session_data.get("current_step", ""),
            steps_completed=[],
            mappings=session_data.get("mappings", {}),
        )
    
    @app.get("/api/v1/sessions/{session_id}/mappings")
    async def get_mappings(session_id: str):
        """Get discovered statuses and suggested mappings."""
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session_data = sessions[session_id]
        return {
            "provider_statuses": session_data.get("provider_statuses", []),
            "suggested_mappings": session_data.get("suggested_mappings", {}),
        }
    
    @app.put("/api/v1/sessions/{session_id}/mappings")
    async def update_mappings(session_id: str, request: UpdateMappingsRequest):
        """Confirm and update status mappings."""
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        sessions[session_id]["confirmed_mappings"] = request.mappings
        sessions[session_id]["mappings_confirmed"] = True
        logger.info(f"Mappings confirmed for session {session_id}")
        return {"status": "confirmed"}
    
    @app.get("/api/v1/sessions/{session_id}/code", response_model=CodeResponse)
    async def get_code(session_id: str):
        """Get generated code files."""
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session_data = sessions[session_id]
        files = session_data.get("generated_files", {})
        
        if not files:
            raise HTTPException(status_code=400, detail="No code generated yet")
        
        return CodeResponse(files=files)
    
    @app.get("/api/v1/sessions/{session_id}/download")
    async def download_code(session_id: str):
        """Download generated code as ZIP."""
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # TODO: Implement ZIP download
        raise HTTPException(status_code=501, detail="Not implemented yet")
    
    @app.post("/api/v1/sessions/{session_id}/test", response_model=LiveTestResponse)
    async def live_test(session_id: str, request: LiveTestRequest):
        """Live test the generated connector."""
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # TODO: Implement live testing
        raise HTTPException(status_code=501, detail="Not implemented yet")
    
    return app
