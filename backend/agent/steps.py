"""Pipeline step definitions."""

from enum import Enum


class PipelineStep(str, Enum):
    """Enum of all pipeline steps."""

    FETCH = "fetch"
    DISCOVER_APIS = "discover_apis"
    EXTRACT_STATUSES = "extract_statuses"
    SUGGEST_MAPPINGS = "suggest_mappings"
    AWAIT_USER_REVIEW = "await_user_review"
    GENERATE_CODE = "generate_code"
    VALIDATE_CODE = "validate_code"
