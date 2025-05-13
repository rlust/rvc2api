"""
common.models

Shared Pydantic models for use across rvc2api modules.

CoachInfo:
    Represents coach/model metadata parsed from the mapping YAML or filename, including year, make,
    model, trim, filename, and notes.

UserCoachInfo:
    Represents user-supplied coach information (VIN, serial numbers, owner, etc),
    with common fields and support for arbitrary extra fields.
"""

from typing import Optional

from pydantic import BaseModel


class CoachInfo(BaseModel):
    """
    CoachInfo

    Represents coach/model metadata parsed from the mapping YAML or filename.

    Attributes:
        year (Optional[str]): Model year (e.g., '2021').
        make (Optional[str]): Manufacturer (e.g., 'Entegra').
        model (Optional[str]): Model name (e.g., 'Aspire').
        trim (Optional[str]): Trim level or submodel (e.g., '44R').
        filename (Optional[str]): Mapping filename in use.
        notes (Optional[str]): Additional notes or parsing status.
    """

    year: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    filename: Optional[str] = None
    notes: Optional[str] = None


class UserCoachInfo(BaseModel):
    """
    UserCoachInfo

    Represents user-supplied coach information (VIN, serial numbers, owner, etc).
    Common fields are optional; arbitrary extra fields are allowed.

    Attributes:
        vin (Optional[str]): Vehicle Identification Number (optional).
        chassis_serial_number (Optional[str]): Chassis serial number (optional).
        owner (Optional[str]): Owner name (optional).
        custom_notes (Optional[str]): Freeform notes (optional).
        ...any other user-supplied fields are accepted as extra keys.
    """

    vin: Optional[str] = None
    chassis_serial_number: Optional[str] = None
    owner: Optional[str] = None
    custom_notes: Optional[str] = None

    class Config:
        extra = "allow"
