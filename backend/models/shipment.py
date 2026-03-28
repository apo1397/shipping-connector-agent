"""Standardized shipment tracking result model."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel
from .status_mapping import GoKwikShipmentStatus


class ScanEvent(BaseModel):
    """A shipment scan/update event."""

    timestamp: datetime
    status: GoKwikShipmentStatus
    status_raw: str  # Original provider status string
    location: str | None = None
    remarks: str | None = None


class ShipmentTrackingResult(BaseModel):
    """Standardized shipment tracking result returned by connectors."""

    awb_number: str
    provider_name: str
    current_status: GoKwikShipmentStatus
    current_status_raw: str  # Original provider status string
    current_status_timestamp: datetime | None = None
    estimated_delivery: datetime | None = None
    origin_city: str | None = None
    destination_city: str | None = None
    destination_pincode: str | None = None
    weight_grams: float | None = None
    scan_history: list[ScanEvent] = []
    raw_response: dict[str, Any] = {}
