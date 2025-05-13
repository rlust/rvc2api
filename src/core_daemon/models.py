"""
Defines Pydantic models for API request/response validation and serialization.

These models are used throughout the FastAPI application to ensure data consistency
and provide clear API documentation for request bodies and response payloads.

Models:
    - Entity: State and metadata of a monitored RV-C entity
    - ControlCommand: Structure for sending control commands to an entity
    - SuggestedMapping: Suggested mapping for an unmapped device instance
    - UnmappedEntryModel: RV-C message not mapped to a configured entity
    - UnknownPGNEntry: CAN message with unknown PGN
    - BulkLightControlResponse: Response for bulk light control operations
    - ControlEntityResponse: Response for individual entity control commands
    - CANInterfaceStats: Statistics for a CAN interface
    - AllCANStats: Statistics for all CAN interfaces
    - GitHubReleaseAsset: Downloadable asset attached to a GitHub release
    - GitHubReleaseInfo: Metadata about a GitHub release
    - GitHubUpdateStatus: Status and metadata of the latest GitHub release
    - CoachInfo: (re-exported from common.models)
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
    state: str
    brightness: int
    action: str


class CANInterfaceStats(BaseModel):
    """Statistics for a CAN interface."""

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
    """Statistics for all CAN interfaces."""

    interfaces: Dict[str, CANInterfaceStats]


class GitHubReleaseAsset(BaseModel):
    """Represents a downloadable asset attached to a GitHub release."""

    name: str
    browser_download_url: str
    size: Optional[int] = None
    download_count: Optional[int] = None


class GitHubReleaseInfo(BaseModel):
    """Represents metadata about a GitHub release for update checking."""

    tag_name: Optional[str] = None
    name: Optional[str] = None
    body: Optional[str] = None
    html_url: Optional[str] = None
    published_at: Optional[str] = None
    created_at: Optional[str] = None
    assets: Optional[List[GitHubReleaseAsset]] = None
    tarball_url: Optional[str] = None
    zipball_url: Optional[str] = None
    prerelease: Optional[bool] = None
    draft: Optional[bool] = None
    author: Optional[dict] = None  # login, html_url
    discussion_url: Optional[str] = None


class GitHubUpdateStatus(BaseModel):
    """Represents the status and metadata of the latest GitHub release as cached by the server."""

    latest_version: Optional[str] = None
    last_checked: Optional[float] = None
    last_success: Optional[float] = None
    error: Optional[str] = None
    latest_release_info: Optional[GitHubReleaseInfo] = None
    repo: Optional[str] = None
    api_url: Optional[str] = None


# CoachInfo model has been moved to src/common/models.py
# Remove the class definition here.
