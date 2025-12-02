"""Base classes and type system for cap table domain models.

This module provides the foundational types, validators, and base classes
used throughout the cap table schema system.
"""

from decimal import Decimal
from datetime import date
from typing import Annotated
from pydantic import BaseModel, Field, ConfigDict

# =============================================================================
# Base Model
# =============================================================================

class DomainModel(BaseModel):
    """Base class for all domain models.

    Provides common configuration for all Pydantic models in the domain layer:
    - Validation on assignment for runtime safety
    - Support for Decimal and date types
    - Enum value serialization
    """

    model_config = ConfigDict(
        frozen=False,  # Allow mutation for computed fields
        validate_assignment=True,  # Validate on field assignment
        use_enum_values=True,  # Use enum values in JSON
        arbitrary_types_allowed=True,  # Allow Decimal, date, etc.
    )


# =============================================================================
# Type Aliases - Numeric
# =============================================================================

ShareCount = Annotated[
    Decimal,
    Field(ge=0, description="Number of shares (non-negative)")
]

MoneyAmount = Annotated[
    Decimal,
    Field(ge=0, description="Currency amount (non-negative)")
]

Percentage = Annotated[
    Decimal,
    Field(ge=0, le=1, description="Percentage as decimal (0.0 to 1.0)")
]

Multiple = Annotated[
    Decimal,
    Field(ge=0, description="Multiplier value (e.g., 2x = 2.0)")
]


# =============================================================================
# ID Conventions
# =============================================================================

ShareClassId = Annotated[
    str,
    Field(
        pattern=r'^[a-z][a-z0-9_]*$',
        description="Snake_case identifier for share classes (e.g., 'common', 'series_a_preferred')"
    )
]

HolderId = Annotated[
    str,
    Field(
        pattern=r'^[a-z][a-z0-9_]*$',
        description="Snake_case identifier for shareholders (e.g., 'founder_alice', 'acme_vc')"
    )
]

EventId = Annotated[
    str,
    Field(
        description="Unique event identifier (UUID or user-defined)"
    )
]

RoundId = Annotated[
    str,
    Field(
        pattern=r'^[a-z][a-z0-9_]*$',
        description="Snake_case identifier for funding rounds (e.g., 'seed', 'series_a')"
    )
]


# =============================================================================
# ID Examples and Conventions
# =============================================================================
#
# Share Class IDs:
#   - "common" - Common stock
#   - "series_a_preferred" - Series A Preferred
#   - "seed_safe" - SAFE from seed round
#
# Holder IDs:
#   - "founder_alice" - Founder Alice
#   - "acme_vc" - Acme Ventures VC firm
#   - "employee_1234" - Employee option holder
#
# Round IDs:
#   - "seed" - Seed round
#   - "series_a" - Series A round
#   - "series_b" - Series B round
#
# Event IDs:
#   - Can be UUIDs: "550e8400-e29b-41d4-a716-446655440000"
#   - Or descriptive: "seed_round_closing", "founder_vesting_grant"
#
# =============================================================================
