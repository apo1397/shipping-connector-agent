"""API request and response schemas."""

from pydantic import BaseModel
from typing import Any, Optional, List


class CreateSessionRequest(BaseModel):
    url: str
    provider_name_hint: Optional[str] = None


class CreateSessionResponse(BaseModel):
    session_id: str


class StepStatus(BaseModel):
    step: str
    status: str
    progress_percent: int = 0
    error_message: Optional[str] = None
    details: dict = {}


class SessionStatusResponse(BaseModel):
    session_id: str
    current_step: str
    steps_completed: List[StepStatus] = []
    mappings: dict = {}


class UpdateMappingsRequest(BaseModel):
    mappings: dict  # {provider_status: gokwik_status}


class CodeResponse(BaseModel):
    files: dict  # {filename: content}


class LiveTestRequest(BaseModel):
    credentials: dict
    awb_numbers: List[str]


class LiveTestResultItem(BaseModel):
    awb: str
    success: bool
    result: Optional[dict] = None
    raw_response: Optional[Any] = None
    error: Optional[str] = None


class LiveTestResponse(BaseModel):
    results: List[LiveTestResultItem]
