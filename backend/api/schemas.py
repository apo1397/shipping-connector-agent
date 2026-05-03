"""API request/response schemas."""

from pydantic import BaseModel
from typing import Any, Optional, List


class CreateSessionRequest(BaseModel):
    url: str
    provider_name_hint: Optional[str] = None
    requestor: Optional[str] = None  # Who's submitting; defaults to "requestor"


class CreateSessionResponse(BaseModel):
    session_id: str


class DuplicateRequestResponse(BaseModel):
    """Returned with HTTP 409 when an exact provider+URL match exists."""
    duplicate: bool = True
    prior_request_id: str
    prior_provider: str
    prior_url: str
    message: str


class UpdateMappingsRequest(BaseModel):
    mappings: dict  # {provider_status_code: gokwik_status}


class ClarificationRequest(BaseModel):
    candidate_index: Optional[int] = None
    focus_hint: str = ""


class ProdUrlRequest(BaseModel):
    """Sent when staging URL was flagged and the requestor confirms the prod base URL."""
    prod_base_url: str  # e.g. "https://api.delhivery.com"


class EndpointTestRequest(BaseModel):
    credentials: dict
    awb_number: str


class EndpointTestResponse(BaseModel):
    success: bool
    stage: str
    error: Optional[str] = None
    auth_result: dict = {}
    tracking_response: Optional[Any] = None
    current_status: Optional[str] = None
    duration_ms: int = 0
    classification: Optional[dict] = None  # {classification, reason, requestor_action}


class ApprovalRequest(BaseModel):
    """Sent at the single approval gate."""
    decision: str  # "approve" | "reject"
    comment: Optional[str] = None
    approver: Optional[str] = None
    # Allow the approver to override mappings before approving
    confirmed_mappings: Optional[dict] = None


class ConfigResponse(BaseModel):
    config: dict


class SessionStatusResponse(BaseModel):
    session_id: str
    has_context: bool
    has_config: bool


class NotificationsResponse(BaseModel):
    notifications: List[dict]
