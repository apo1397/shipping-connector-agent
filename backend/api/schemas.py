"""API request and response schemas."""

from pydantic import BaseModel
from datetime import datetime
from typing import Any


class CreateSessionRequest(BaseModel):
    """Request to create a new generation session."""

    url: str
    provider_name_hint: str | None = None


class CreateSessionResponse(BaseModel):
    """Response with session ID."""

    session_id: str


class StepStatus(BaseModel):
    """Status of a pipeline step."""

    step: str
    status: str  # pending, running, complete, error
    progress_percent: int = 0
    error_message: str | None = None
    details: dict[str, Any] = {}


class SessionStatusResponse(BaseModel):
    """Current session status."""

    session_id: str
    current_step: str
    steps_completed: list[StepStatus]
    mappings: dict[str, str] = {}


class StatusMapping(BaseModel):
    """Provider status to GoKwik status mapping."""

    provider_status: str
    gokwik_status: str


class UpdateMappingsRequest(BaseModel):
    """Request to confirm status mappings."""

    mappings: dict[str, str]  # provider_status -> gokwik_status


class CodeResponse(BaseModel):
    """Generated code files."""

    files: dict[str, str]  # filename -> content


class LiveTestRequest(BaseModel):
    """Request to live test a connector."""

    credentials: dict[str, str]
    awb_number: str


class LiveTestResponse(BaseModel):
    """Result of live test."""

    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
