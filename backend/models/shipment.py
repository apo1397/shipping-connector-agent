"""Standardized shipment tracking result model."""

from datetime import datetime
from typing import Any, Optional, Union
from pydantic import BaseModel
from .status_mapping import GoKwikShipmentStatus


class ScanEvent(BaseModel):
    """A shipment scan/update event."""

    timestamp: datetime
    status: GoKwikShipmentStatus
    status_raw: str  # Original provider status string
    location: Optional[str] = None
    remarks: Optional[str] = None


class ShipmentTrackingResult(BaseModel):
    """Standardized shipment tracking result returned by connectors."""

    awb_number: str
    provider_name: str
    current_status: GoKwikShipmentStatus
    current_status_raw: str  # Original provider status string
    current_status_timestamp: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    origin_city: Optional[str] = None
    destination_city: Optional[str] = None
    destination_pincode: Optional[str] = None
    weight_grams: Optional[float] = None
    scan_history: list[ScanEvent] = []
    raw_response: dict[str, Any] = {}
