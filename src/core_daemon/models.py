from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Pydantic Models for API responses ────────────────────────────────────────
class Entity(BaseModel):
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
    instance: str
    name: str
    suggested_area: Optional[str] = None


class UnmappedEntryModel(BaseModel):
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


class BulkLightControlResponse(BaseModel):
    status: str
    action: str
    lights_processed: int
    lights_commanded: int
    errors: List[str] = []


class ControlEntityResponse(BaseModel):
    status: str
    entity_id: str
    command: str
    brightness: int
    action: str
