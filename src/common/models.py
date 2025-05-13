"""
common.models

Shared Pydantic models for use across rvc2api modules.

CoachInfo:
    Represents coach/model metadata parsed from the mapping YAML or filename, including year, make,
    model, trim, filename, and notes.
"""

from typing import Optional

from pydantic import BaseModel


class CoachInfo(BaseModel):
    """
    Represents coach/model metadata parsed from the mapping YAML or filename.

    Fields:
        year: Model year (e.g., '2021')
        make: Manufacturer (e.g., 'Entegra')
        model: Model name (e.g., 'Aspire')
        trim: Trim level or submodel (e.g., '44R')
        filename: Mapping filename in use
        notes: Additional notes or parsing status
    """

    year: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    filename: Optional[str] = None
    notes: Optional[str] = None
