"""GoKwik internal shipment status mappings."""

from enum import Enum


class GoKwikShipmentStatus(str, Enum):
    """Canonical GoKwik shipment statuses that all providers map to."""

    ORDER_PLACED = "order_placed"
    PICKUP_PENDING = "pickup_pending"
    PICKUP_SCHEDULED = "pickup_scheduled"
    OUT_FOR_PICKUP = "out_for_pickup"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    REACHED_DESTINATION_HUB = "reached_destination_hub"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    DELIVERY_FAILED_CUSTOMER_UNAVAILABLE = "delivery_failed_customer_unavailable"
    DELIVERY_FAILED_ADDRESS_ISSUE = "delivery_failed_address_issue"
    DELIVERY_FAILED_REFUSED = "delivery_failed_refused"
    RTO_INITIATED = "rto_initiated"
    RTO_IN_TRANSIT = "rto_in_transit"
    RTO_DELIVERED = "rto_delivered"
    CANCELLED = "cancelled"
    LOST = "lost"
    DAMAGED = "damaged"
    ON_HOLD = "on_hold"
    UNKNOWN = "unknown"
