"""
Defines Pydantic models for API request/response validation and serialization.

These models are used throughout the FastAPI application to ensure data consistency
and provide clear API documentation for request bodies and response payloads.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Pydantic Models for API responses ────────────────────────────────────────
class Entity(BaseModel):
    """Represents the state and metadata of a monitored RV-C entity."""

    entity_id: str
    value: Dict[str, str]
    raw: Dict[str, int]
    state: str
    timestamp: float
    suggested_area: Optional[str] = "Unknown"
    device_type: Optional[str] = "unknown"
    capabilities: Optional[List[str]] = []
    friendly_name: Optional[str] = None
    groups: Optional[List[str]] = Field(default_factory=list)


class ControlCommand(BaseModel):
    """Defines the structure for sending control commands to an entity, typically a light."""

    command: str
    state: Optional[str] = Field(
        None, description="Target state: 'on' or 'off'. Required only for 'set' command."
    )
    brightness: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description=(
            "Brightness percent (0–100). Only used when command is 'set' and state is 'on'."
        ),
    )


class SuggestedMapping(BaseModel):
    """
    Provides a suggested mapping for an unmapped device instance
    based on existing configurations.
    """

    instance: str
    name: str
    suggested_area: Optional[str] = None


class UnmappedEntryModel(BaseModel):
    """Represents an RV-C message that could not be mapped to a configured entity."""

    pgn_hex: str
    pgn_name: Optional[str] = Field(
        None,
        description=(
            "The human-readable name of the PGN (from arbitration ID), if known from the spec."
        ),
    )
    dgn_hex: str
    dgn_name: Optional[str] = Field(
        None, description="The human-readable name of the DGN, if known from the spec."
    )
    instance: str
    last_data_hex: str
    decoded_signals: Optional[Dict[str, Any]] = None
    first_seen_timestamp: float
    last_seen_timestamp: float
    count: int
    suggestions: Optional[List[SuggestedMapping]] = None
    spec_entry: Optional[Dict[str, Any]] = Field(
        None,
        description=("The raw rvc.json spec entry used for decoding, if PGN was known."),
    )


class UnknownPGNEntry(BaseModel):
    """Represents a CAN message whose PGN (from arbitration ID) is not in the rvc.json spec."""

    arbitration_id_hex: str
    first_seen_timestamp: float
    last_seen_timestamp: float
    count: int
    last_data_hex: str


class BulkLightControlResponse(BaseModel):
    """Response model for bulk light control operations, summarizing the outcome."""

    status: str
    message: str  # Added message field
    action: str
    group: Optional[str] = None  # Added group field
    lights_processed: int
    lights_commanded: int
    errors: List[Dict[str, str]] = Field(default_factory=list)  # Changed type from List[str]
    details: List[Dict[str, Any]] = Field(default_factory=list)  # Added details field


class ControlEntityResponse(BaseModel):
    """Response model for individual entity control commands, confirming the action taken."""

    status: str
    entity_id: str
    command: str
    brightness: int
    action: str


class CANInterfaceStats(BaseModel):
    name: str
    state: Optional[str] = None
    restart_ms: Optional[int] = None
    bitrate: Optional[int] = None
    sample_point: Optional[float] = None
    tq: Optional[int] = None  # Time quantum in nanoseconds
    prop_seg: Optional[int] = None
    phase_seg1: Optional[int] = None
    phase_seg2: Optional[int] = None
    sjw: Optional[int] = None  # Synchronization Jump Width
    brp: Optional[int] = None  # Bitrate Prescaler
    # Shortened line:
    clock_freq: Optional[int] = Field(default=None, alias="clock")  # Clock frequency Hz

    # From ip -s link show
    tx_packets: Optional[int] = None
    rx_packets: Optional[int] = None
    tx_bytes: Optional[int] = None
    rx_bytes: Optional[int] = None
    tx_errors: Optional[int] = None
    rx_errors: Optional[int] = None
    bus_errors: Optional[int] = None  # General bus errors
    restarts: Optional[int] = None  # Controller restarts

    # Additional details from ip -details link show
    link_type: Optional[str] = Field(default=None, alias="link/can")
    promiscuity: Optional[int] = None
    allmulti: Optional[int] = None
    minmtu: Optional[int] = None
    maxmtu: Optional[int] = None
    parentbus: Optional[str] = None
    parentdev: Optional[str] = None

    # Specific error counters if available (these might vary by controller)
    error_warning: Optional[int] = None  # Entered error warning state count
    error_passive: Optional[int] = None  # Entered error passive state count
    bus_off: Optional[int] = None  # Entered bus off state count

    # Raw details string for any unparsed info, if needed for debugging
    raw_details: Optional[str] = None


class AllCANStats(BaseModel):
    interfaces: Dict[str, CANInterfaceStats]
