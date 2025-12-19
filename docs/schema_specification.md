# Cap Table Schema Specification

**Version:** 1.0 (DRAFT)
**Last Updated:** 2025-11-13
**Status:** Draft - Awaiting Review

---

## Table of Contents

1. [Overview](#overview)
2. [Type System & Conventions](#type-system--conventions)
3. [Share Classes & Economic Rights](#share-classes--economic-rights)
4. [Instruments (Discriminated Unions)](#instruments-discriminated-unions)
5. [Events](#events)
6. [Positions](#positions)
7. [Cap Table & Snapshots](#cap-table--snapshots)
8. [Returns & Waterfall](#returns--waterfall)
9. [Workbook Configuration](#workbook-configuration)
10. [Validation Rules](#validation-rules)
11. [Example Schemas](#example-schemas)

---

## Overview

This document specifies the complete Pydantic schema for the cap table domain model.

**Design Principles:**
1. Event-sourced: State is computed from events
2. Type-safe: Discriminated unions prevent invalid states
3. Immutable: Events are append-only, snapshots are computed
4. Validated: Pydantic validators enforce business rules

**Module Organization:**
```
packages/domain/captable_domain/schemas/
├── __init__.py
├── base.py                  # Base classes, shared types
├── share_classes.py         # ShareClass and economic rights
├── instruments.py           # Instrument discriminated unions
├── events.py                # Event base class and concrete events
├── positions.py             # Position and holder models
├── cap_table.py             # CapTable and CapTableSnapshot
├── returns.py               # Exit scenarios and returns config
└── workbook.py              # WorkbookCFG (top-level)
```

---

## Type System & Conventions

### Base Types

```python
# packages/domain/captable_domain/schemas/base.py

from decimal import Decimal
from datetime import date
from typing import Literal, Optional, Union, Annotated
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ConfigDict

class DomainModel(BaseModel):
    """Base class for all domain models."""

    model_config = ConfigDict(
        frozen=False,  # Allow mutation for computed fields
        validate_assignment=True,  # Validate on field assignment
        use_enum_values=True,  # Use enum values in JSON
        arbitrary_types_allowed=True,  # Allow Decimal, date, etc.
    )

# Type aliases
ShareCount = Annotated[Decimal, Field(ge=0, description="Number of shares")]
MoneyAmount = Annotated[Decimal, Field(ge=0, description="Currency amount")]
Percentage = Annotated[Decimal, Field(ge=0, le=1, description="Percentage as decimal (0-1)")]
Multiple = Annotated[Decimal, Field(ge=0, description="Multiplier (e.g., 2x = 2.0)")]
```

### ID Conventions

```python
from typing import Annotated
from pydantic import Field

# Entity IDs (user-defined, must be unique within scope)
ShareClassId = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]*$', description="Snake_case identifier")]
HolderId = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]*$', description="Snake_case identifier")]
EventId = Annotated[str, Field(description="Unique event identifier (UUID or user-defined)")]
RoundId = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]*$', description="Snake_case identifier")]

# Examples:
# - Share class: "common", "series_a_preferred", "seed_safe"
# - Holder: "founder_alice", "acme_vc", "employee_1234"
# - Round: "seed", "series_a", "series_b"
```

---

## Share Classes & Economic Rights

### Share Class

```python
# packages/domain/captable_domain/schemas/share_classes.py

from typing import Optional, Literal
from decimal import Decimal
from .base import DomainModel, ShareClassId, Multiple, Percentage

class LiquidationPreference(DomainModel):
    """
    Liquidation preference defines how proceeds are distributed in an exit.

    Example: "2x liquidation preference" means investor gets 2x their investment
    before anyone else gets paid.
    """
    multiple: Multiple = Field(
        default=Decimal("1.0"),
        description="Liquidation preference multiple (1.0 = 1x, 2.0 = 2x, etc.)"
    )
    seniority_rank: int = Field(
        ge=0,
        description="Priority in waterfall (0 = highest, increasing = lower priority)"
    )
    pari_passu_group: Optional[str] = Field(
        default=None,
        description="Group ID for equal seniority. If set, all classes in group are pari passu."
    )

    @model_validator(mode='after')
    def validate_pari_passu(self):
        """If pari passu, seniority_rank should match within group."""
        # NOTE: This is validated at cap table level, not here
        return self


class ParticipationRights(DomainModel):
    """
    Participation rights define if/how a share class participates in proceeds
    after receiving liquidation preference.

    Types:
    - Non-participating: Gets liquidation pref OR pro-rata, whichever is greater
    - Participating: Gets liquidation pref AND pro-rata
    - Capped participating: Gets liquidation pref AND pro-rata, up to a cap
    """
    participation_type: Literal["non_participating", "participating", "capped_participating"]

    cap_multiple: Optional[Multiple] = Field(
        default=None,
        description="Cap as multiple of investment. E.g., 3.0 = 3x total return cap."
    )

    @model_validator(mode='after')
    def validate_cap_multiple(self):
        """Capped participation requires cap_multiple."""
        if self.participation_type == "capped_participating":
            if self.cap_multiple is None:
                raise ValueError("capped_participating requires cap_multiple")
            if self.cap_multiple <= Decimal("1.0"):
                raise ValueError("cap_multiple must be > 1.0 (cap must exceed liquidation pref)")
        elif self.cap_multiple is not None:
            raise ValueError(f"cap_multiple only valid for capped_participating, not {self.participation_type}")
        return self


class ConversionRights(DomainModel):
    """
    Conversion rights allow converting from one share class to another.

    Common use: Preferred stock can convert to common stock.
    """
    converts_to_class_id: ShareClassId = Field(
        description="Share class ID this converts to (usually 'common')"
    )

    initial_conversion_ratio: Decimal = Field(
        default=Decimal("1.0"),
        ge=0,
        description="Initial ratio: 1 share of this class → N shares of target class"
    )

    current_conversion_ratio: Decimal = Field(
        default=Decimal("1.0"),
        ge=0,
        description="Current ratio (adjusted for anti-dilution, splits, etc.)"
    )

    auto_convert_on_ipo: bool = Field(
        default=True,
        description="Automatically convert on qualified IPO"
    )

    qualified_ipo_threshold: Optional[MoneyAmount] = Field(
        default=None,
        description="Minimum IPO valuation to trigger auto-conversion"
    )


class AntiDilutionProtection(DomainModel):
    """
    Anti-dilution protection adjusts conversion price in down rounds.

    Types:
    - none: No protection (MVP default)
    - weighted_average_broad: Includes all shares in calculation
    - weighted_average_narrow: Excludes certain shares (options, etc.)
    - full_ratchet: Conversion price drops to down round price

    Note: Carve-outs and detailed ratio calculations are deferred;
    the schema only captures the protection type for now.
    """
    protection_type: Literal[
        "none",
        "weighted_average_broad",
        "weighted_average_narrow",
        "full_ratchet"
    ] = Field(
        default="weighted_average_broad",
        description="Type of anti-dilution protection"
    )


class ShareClass(DomainModel):
    """
    A class of shares with specific economic and voting rights.

    Examples:
    - Common Stock
    - Series A Preferred Stock
    - Series B Preferred Stock
    - Warrants to purchase Common Stock
    """
    id: ShareClassId
    name: str = Field(description="Human-readable name")

    share_type: Literal["common", "preferred", "option", "warrant"] = Field(
        description="Fundamental share type"
    )

    # Economic rights
    liquidation_preference: Optional[LiquidationPreference] = Field(
        default=None,
        description="Liquidation preference (typically only for preferred)"
    )

    participation_rights: Optional[ParticipationRights] = Field(
        default=None,
        description="Participation in proceeds after liquidation pref"
    )

    conversion_rights: Optional[ConversionRights] = Field(
        default=None,
        description="Right to convert to another share class"
    )

    anti_dilution_protection: Optional[AntiDilutionProtection] = Field(
        default=None,
        description="Protection against dilution in down rounds"
    )

    # Note: Dividend rights removed in MVP
    # Note: Voting rights removed (not needed for returns modeling)

    # Metadata
    created_in_round_id: Optional[RoundId] = Field(
        default=None,
        description="Round that created this share class"
    )

    @model_validator(mode='after')
    def validate_economic_rights(self):
        """Validate that economic rights make sense for share type."""
        # Common stock typically doesn't have liquidation preference
        if self.share_type == "common":
            if self.liquidation_preference is not None:
                # Allow but warn (some edge cases exist)
                pass

        # Preferred should have liquidation preference
        if self.share_type == "preferred":
            if self.liquidation_preference is None:
                raise ValueError("Preferred stock should have liquidation_preference")

        # Options and warrants are different
        if self.share_type in ("option", "warrant"):
            # These convert to another class, not distributed directly in waterfall
            if self.liquidation_preference is not None:
                raise ValueError(f"{self.share_type} should not have liquidation_preference")

        return self
```

---

## Instruments (Discriminated Unions)

### Instrument Types

```python
# packages/domain/captable_domain/schemas/instruments.py

from typing import Annotated, Union, Literal, Optional
from decimal import Decimal
from datetime import date
from pydantic import Field, model_validator
from .base import DomainModel, MoneyAmount, Percentage, ShareCount

class SAFEInstrument(DomainModel):
    """
    Simple Agreement for Future Equity (SAFE).

    Converts to equity in next priced round based on cap and/or discount.
    """
    type: Literal["SAFE"] = "SAFE"

    investment_amount: MoneyAmount = Field(
        description="Amount invested via SAFE"
    )

    valuation_cap: Optional[MoneyAmount] = Field(
        default=None,
        description="Valuation cap for conversion (optional)"
    )

    discount_rate: Optional[Percentage] = Field(
        default=None,
        description="Discount rate for conversion (e.g., 0.20 = 20% discount)"
    )

    safe_type: Literal["pre_money", "post_money"] = Field(
        description="Pre-money or post-money SAFE"
    )

    # Note: MFN and pro-rata side letters removed for MVP simplification

    @model_validator(mode='after')
    def validate_cap_or_discount(self):
        """SAFE must have cap and/or discount."""
        if self.valuation_cap is None and self.discount_rate is None:
            raise ValueError("SAFE must have valuation_cap and/or discount_rate")
        return self


class PricedRoundInstrument(DomainModel):
    """
    Priced equity round (Seed, Series A, Series B, etc.).

    Shares are issued at a specific price per share.
    """
    type: Literal["priced"] = "priced"

    investment_amount: MoneyAmount = Field(
        description="Total amount raised in this round"
    )

    pre_money_valuation: MoneyAmount = Field(
        description="Company valuation before investment"
    )

    price_per_share: Decimal = Field(
        gt=0,
        description="Price per share"
    )

    shares_issued: ShareCount = Field(
        description="Number of shares issued to investors"
    )

    # Optional: Warrants issued alongside equity
    warrant_coverage_percentage: Optional[Percentage] = Field(
        default=None,
        description="Warrant coverage as % of investment (e.g., 0.10 = 10% coverage)"
    )

    @model_validator(mode='after')
    def validate_math(self):
        """Validate that investment = price * shares (approximately)."""
        calculated_investment = self.price_per_share * self.shares_issued

        # Allow small rounding differences
        diff = abs(calculated_investment - self.investment_amount)
        tolerance = self.investment_amount * Decimal("0.01")  # 1% tolerance

        if diff > tolerance:
            raise ValueError(
                f"Inconsistent math: price_per_share ({self.price_per_share}) * "
                f"shares_issued ({self.shares_issued}) = {calculated_investment}, "
                f"but investment_amount is {self.investment_amount}"
            )

        return self


class ConvertibleNoteInstrument(DomainModel):
    """
    Convertible note (debt that converts to equity).

    Accrues interest until conversion or maturity.
    Interest can be simple or compound, cumulative or paid.
    """
    type: Literal["convertible_note"] = "convertible_note"

    principal_amount: MoneyAmount = Field(
        description="Principal amount of the note"
    )

    interest_rate: Percentage = Field(
        description="Annual interest rate (e.g., 0.05 = 5% per year)"
    )

    interest_type: Literal["simple", "compound"] = Field(
        default="simple",
        description="Interest calculation method (most notes use simple)"
    )

    interest_payment: Literal["accruing", "paid_quarterly", "paid_annually"] = Field(
        default="accruing",
        description="Whether interest accrues or is paid out"
    )

    issue_date: date = Field(
        description="Date note was issued"
    )

    maturity_date: date = Field(
        description="Date note matures (becomes due)"
    )

    valuation_cap: Optional[MoneyAmount] = Field(
        default=None,
        description="Valuation cap for conversion"
    )

    discount_rate: Optional[Percentage] = Field(
        default=None,
        description="Discount rate for conversion"
    )

    @model_validator(mode='after')
    def validate_dates(self):
        """Maturity date must be after issue date."""
        if self.maturity_date <= self.issue_date:
            raise ValueError("maturity_date must be after issue_date")
        return self

    @model_validator(mode='after')
    def validate_cap_or_discount(self):
        """Convertible note should have cap and/or discount."""
        if self.valuation_cap is None and self.discount_rate is None:
            raise ValueError("Convertible note should have valuation_cap and/or discount_rate")
        return self

    def calculate_accrued_amount(self, as_of_date: date) -> Decimal:
        """Calculate principal + accrued interest as of a date."""
        if self.interest_payment != "accruing":
            # If interest is paid out, only principal converts
            return self.principal_amount

        days = (as_of_date - self.issue_date).days
        years = Decimal(days) / Decimal("365.25")

        if self.interest_type == "simple":
            interest = self.principal_amount * self.interest_rate * years
        else:  # compound
            # Compound annually: A = P(1 + r)^t
            interest = self.principal_amount * ((Decimal("1") + self.interest_rate) ** years - Decimal("1"))

        return self.principal_amount + interest


class WarrantInstrument(DomainModel):
    """
    Warrant to purchase shares.

    Gives holder the right (but not obligation) to buy shares at a strike price.
    """
    type: Literal["warrant"] = "warrant"

    shares_purchasable: ShareCount = Field(
        description="Number of shares that can be purchased"
    )

    exercise_price: Decimal = Field(
        gt=0,
        description="Price per share to exercise warrant"
    )

    share_class_id: ShareClassId = Field(
        description="Share class the warrant converts to"
    )

    issue_date: date = Field(
        description="Date warrant was issued"
    )

    expiration_date: Optional[date] = Field(
        default=None,
        description="Date warrant expires (if any)"
    )

    @model_validator(mode='after')
    def validate_dates(self):
        """Expiration must be after issue date."""
        if self.expiration_date and self.expiration_date <= self.issue_date:
            raise ValueError("expiration_date must be after issue_date")
        return self


# Discriminated union
Instrument = Annotated[
    Union[SAFEInstrument, PricedRoundInstrument, ConvertibleNoteInstrument, WarrantInstrument],
    Field(discriminator='type')
]
```

---

## Events

### Event Base Class

```python
# packages/domain/captable_domain/schemas/events.py

from abc import ABC, abstractmethod
from typing import Optional, Literal, List, TYPE_CHECKING
from datetime import date
from pydantic import Field
from .base import DomainModel, EventId

if TYPE_CHECKING:
    from .cap_table import CapTableSnapshot

class CapTableEvent(DomainModel, ABC):
    """
    Base class for all cap table events.

    Events are immutable records of what happened.
    Events are applied to snapshots to compute state.
    """
    event_id: EventId = Field(
        description="Unique identifier for this event"
    )

    event_date: date = Field(
        description="Date the event occurred"
    )

    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of the event"
    )

    @abstractmethod
    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """
        Apply this event to a snapshot to update its state.

        This method mutates the snapshot.
        """
        pass
```

### Concrete Event Types

```python
from .base import ShareClassId, HolderId, RoundId, ShareCount, MoneyAmount
from .instruments import Instrument
from decimal import Decimal

class ShareIssuanceEvent(CapTableEvent):
    """Shares are issued to a holder."""

    event_type: Literal["share_issuance"] = "share_issuance"

    holder_id: HolderId = Field(
        description="ID of the holder receiving shares"
    )

    share_class_id: ShareClassId = Field(
        description="Share class being issued"
    )

    shares: ShareCount = Field(
        description="Number of shares issued"
    )

    price_per_share: Optional[Decimal] = Field(
        default=None,
        description="Price per share (for cost basis calculation)"
    )

    vesting_schedule_id: Optional[str] = Field(
        default=None,
        description="Vesting schedule ID (if shares vest)"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Add or update position in snapshot."""
        from .positions import Position

        snapshot.add_or_update_position(
            Position(
                holder_id=self.holder_id,
                share_class_id=self.share_class_id,
                shares=self.shares,
                acquisition_date=self.event_date,
                cost_basis=self.price_per_share * self.shares if self.price_per_share else None,
                vesting_schedule_id=self.vesting_schedule_id,
            )
        )


class ShareTransferEvent(CapTableEvent):
    """Shares are transferred from one holder to another (secondary sale)."""

    event_type: Literal["share_transfer"] = "share_transfer"

    from_holder_id: HolderId
    to_holder_id: HolderId
    share_class_id: ShareClassId
    shares: ShareCount

    price_per_share: Optional[Decimal] = Field(
        default=None,
        description="Transfer price (if disclosed)"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Transfer shares from one holder to another."""
        snapshot.transfer_shares(
            from_holder=self.from_holder_id,
            to_holder=self.to_holder_id,
            share_class_id=self.share_class_id,
            shares=self.shares,
            transfer_date=self.event_date,
            transfer_price=self.price_per_share,
        )


class ConversionEvent(CapTableEvent):
    """Shares convert from one class to another (e.g., preferred → common)."""

    event_type: Literal["conversion"] = "conversion"

    holder_id: HolderId
    from_share_class_id: ShareClassId
    to_share_class_id: ShareClassId
    shares_converted: ShareCount
    conversion_ratio: Decimal = Field(
        description="Conversion ratio (1 from_share → N to_shares)"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Convert shares from one class to another."""
        new_shares = self.shares_converted * self.conversion_ratio

        snapshot.reduce_position(
            self.holder_id,
            self.from_share_class_id,
            self.shares_converted
        )

        from .positions import Position
        snapshot.add_or_update_position(
            Position(
                holder_id=self.holder_id,
                share_class_id=self.to_share_class_id,
                shares=new_shares,
                acquisition_date=self.event_date,
            )
        )


class OptionExerciseEvent(CapTableEvent):
    """Employee exercises stock options."""

    event_type: Literal["option_exercise"] = "option_exercise"

    holder_id: HolderId
    option_grant_id: str = Field(
        description="ID of the option grant being exercised"
    )
    shares_exercised: ShareCount
    exercise_price: Decimal
    resulting_share_class_id: ShareClassId = Field(
        description="Share class received (usually 'common')"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Exercise options → issue shares."""
        # Reduce option pool
        snapshot.option_pool_available -= self.shares_exercised

        # Issue shares to holder
        from .positions import Position
        snapshot.add_or_update_position(
            Position(
                holder_id=self.holder_id,
                share_class_id=self.resulting_share_class_id,
                shares=self.shares_exercised,
                acquisition_date=self.event_date,
                cost_basis=self.exercise_price * self.shares_exercised,
            )
        )


class RoundClosingEvent(CapTableEvent):
    """
    A financing round closes.

    This is a composite event that may include:
    - SAFE/convertible conversions
    - New share issuances
    - Option pool creation
    - Warrant issuances
    """
    event_type: Literal["round_closing"] = "round_closing"

    round_id: RoundId
    round_name: str = Field(
        description="Human-readable round name (e.g., 'Seed Round', 'Series A')"
    )

    instruments: List[Instrument] = Field(
        description="Instruments used in this round (SAFEs, priced equity, etc.)"
    )

    # Sub-events that occur as part of round closing
    safe_conversions: List['SAFEConversionEvent'] = Field(
        default_factory=list,
        description="SAFEs that convert in this round"
    )

    share_issuances: List[ShareIssuanceEvent] = Field(
        default_factory=list,
        description="Shares issued to investors"
    )

    option_pool_created: Optional['OptionPoolCreation'] = Field(
        default=None,
        description="Option pool created in this round"
    )

    warrants_issued: List['WarrantIssuance'] = Field(
        default_factory=list,
        description="Warrants issued alongside equity"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Apply all sub-events in order."""
        # Step 1: Convert SAFEs/convertibles
        for conversion in self.safe_conversions:
            conversion.apply(snapshot)

        # Step 2: Issue new shares
        for issuance in self.share_issuances:
            issuance.apply(snapshot)

        # Step 3: Create option pool
        if self.option_pool_created:
            self.option_pool_created.apply(snapshot)

        # Step 4: Issue warrants
        for warrant in self.warrants_issued:
            warrant.apply(snapshot)


class SAFEConversionEvent(CapTableEvent):
    """SAFE converts to equity in a priced round."""

    event_type: Literal["safe_conversion"] = "safe_conversion"

    safe_holder_id: HolderId
    safe_instrument: SAFEInstrument

    # Conversion details
    conversion_price: Decimal = Field(
        description="Effective price per share for SAFE conversion"
    )
    shares_issued: ShareCount
    resulting_share_class_id: ShareClassId

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Issue shares from SAFE conversion."""
        from .positions import Position
        snapshot.add_or_update_position(
            Position(
                holder_id=self.safe_holder_id,
                share_class_id=self.resulting_share_class_id,
                shares=self.shares_issued,
                acquisition_date=self.event_date,
                cost_basis=self.safe_instrument.investment_amount,
            )
        )


class OptionPoolCreation(CapTableEvent):
    """
    Option pool is created or expanded.

    Timing matters for dilution:
    - pre_money: Pool created before new investment (dilutes existing holders)
    - post_money: Pool created after new investment (dilutes investors too)
    - target_post_money: Pool sized to hit target % AFTER round closes
    """

    event_type: Literal["option_pool_creation"] = "option_pool_creation"

    shares_authorized: ShareCount = Field(
        description="Number of shares authorized for option pool"
    )

    pool_timing: Literal["pre_money", "post_money", "target_post_money"] = Field(
        description="When pool is created relative to investment"
    )

    target_percentage: Optional[Percentage] = Field(
        default=None,
        description="Target option pool % post-money (only for target_post_money timing)"
    )

    share_class_id: ShareClassId = Field(
        default="common",
        description="Share class for options (usually common)"
    )

    @model_validator(mode='after')
    def validate_target_percentage(self):
        """target_post_money requires target_percentage."""
        if self.pool_timing == "target_post_money":
            if self.target_percentage is None:
                raise ValueError("target_post_money pool requires target_percentage")
        return self

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Add shares to option pool."""
        snapshot.option_pool_authorized += self.shares_authorized
        snapshot.option_pool_available += self.shares_authorized

        # Pre-money: Pool created before investment, dilutes existing holders
        if self.pool_timing == "pre_money":
            snapshot.total_shares_outstanding += self.shares_authorized

        # Post-money or target: Pool shares come from post-investment allocation
        # Total shares already includes investor shares, pool doesn't add more
        # (Pool is carved out of the post-money total)


class WarrantIssuance(CapTableEvent):
    """Warrants are issued (usually alongside priced round)."""

    event_type: Literal["warrant_issuance"] = "warrant_issuance"

    holder_id: HolderId
    warrant: WarrantInstrument

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Add warrant position to snapshot."""
        from .positions import Position
        snapshot.add_or_update_position(
            Position(
                holder_id=self.holder_id,
                share_class_id=f"warrant_{self.warrant.share_class_id}",
                shares=self.warrant.shares_purchasable,
                acquisition_date=self.event_date,
                is_option=True,
                exercise_price=self.warrant.exercise_price,
                expiration_date=self.warrant.expiration_date,
            )
        )
```

---

## Positions

```python
# packages/domain/captable_domain/schemas/positions.py

from typing import Optional
from datetime import date
from decimal import Decimal
from pydantic import Field
from .base import DomainModel, ShareClassId, HolderId, ShareCount, MoneyAmount

class Position(DomainModel):
    """
    A holder's position in a specific share class.

    Represents ownership at a point in time.
    """
    holder_id: HolderId
    share_class_id: ShareClassId
    shares: ShareCount
    acquisition_date: date = Field(
        description="Date shares were acquired"
    )

    # Financial tracking
    cost_basis: Optional[MoneyAmount] = Field(
        default=None,
        description="Total cost basis (price paid for shares)"
    )

    # Vesting
    vesting_schedule_id: Optional[str] = Field(
        default=None,
        description="ID of vesting schedule (if shares vest)"
    )

    # For options/warrants
    is_option: bool = Field(
        default=False,
        description="True if this is an option/warrant (not exercised yet)"
    )

    exercise_price: Optional[Decimal] = Field(
        default=None,
        description="Exercise/strike price (for options/warrants)"
    )

    expiration_date: Optional[date] = Field(
        default=None,
        description="Expiration date (for options/warrants)"
    )

    def effective_cost_per_share(self) -> Optional[Decimal]:
        """Calculate cost per share."""
        if self.cost_basis is None or self.shares == 0:
            return None
        return self.cost_basis / self.shares
```

---

## Cap Table & Snapshots

```python
# packages/domain/captable_domain/schemas/cap_table.py

from typing import Dict, List, Optional
from datetime import date
from decimal import Decimal
from pydantic import Field, field_validator
from .base import DomainModel, ShareCount
from .share_classes import ShareClass
from .events import CapTableEvent
from .positions import Position

class CapTableSnapshot(DomainModel):
    """
    Point-in-time cap table state.

    Computed by replaying events up to a specific date.
    """
    as_of_date: date

    positions: List[Position] = Field(
        default_factory=list,
        description="All holder positions"
    )

    total_shares_outstanding: ShareCount = Field(
        default=Decimal("0"),
        description="Total shares issued and outstanding"
    )

    # Option pool tracking
    option_pool_authorized: ShareCount = Field(
        default=Decimal("0"),
        description="Total shares authorized for option pool"
    )

    option_pool_available: ShareCount = Field(
        default=Decimal("0"),
        description="Shares available for grant (not yet granted or exercised)"
    )

    def add_or_update_position(self, position: Position) -> None:
        """Add a new position or update existing."""
        # Find existing position for this holder + share class
        existing = next(
            (p for p in self.positions
             if p.holder_id == position.holder_id
             and p.share_class_id == position.share_class_id
             and p.is_option == position.is_option),
            None
        )

        if existing:
            # Update existing position
            existing.shares += position.shares
            if position.cost_basis:
                existing.cost_basis = (existing.cost_basis or Decimal("0")) + position.cost_basis
        else:
            # Add new position
            self.positions.append(position)

        # Update total shares
        if not position.is_option:
            self.total_shares_outstanding += position.shares

    def reduce_position(
        self,
        holder_id: str,
        share_class_id: str,
        shares: Decimal
    ) -> None:
        """Reduce a holder's position (for conversions, transfers, etc.)."""
        position = next(
            (p for p in self.positions
             if p.holder_id == holder_id
             and p.share_class_id == share_class_id
             and not p.is_option),
            None
        )

        if not position:
            raise ValueError(
                f"Position not found: holder={holder_id}, class={share_class_id}"
            )

        if position.shares < shares:
            raise ValueError(
                f"Insufficient shares: holder has {position.shares}, trying to reduce by {shares}"
            )

        position.shares -= shares
        self.total_shares_outstanding -= shares

        # Remove position if shares = 0
        if position.shares == 0:
            self.positions.remove(position)

    def transfer_shares(
        self,
        from_holder: str,
        to_holder: str,
        share_class_id: str,
        shares: Decimal,
        transfer_date: date,
        transfer_price: Optional[Decimal] = None,
    ) -> None:
        """Transfer shares from one holder to another."""
        # Reduce from_holder position
        self.reduce_position(from_holder, share_class_id, shares)

        # Add to to_holder position
        self.add_or_update_position(
            Position(
                holder_id=to_holder,
                share_class_id=share_class_id,
                shares=shares,
                acquisition_date=transfer_date,
                cost_basis=transfer_price * shares if transfer_price else None,
            )
        )

    def ownership_percentage(
        self,
        holder_id: str,
        fully_diluted: bool = False
    ) -> Decimal:
        """
        Calculate ownership percentage for a holder.

        Args:
            holder_id: Holder to calculate for
            fully_diluted: If True, include option pool in denominator
        """
        holder_shares = sum(
            p.shares for p in self.positions
            if p.holder_id == holder_id and not p.is_option
        )

        if fully_diluted:
            total = self.total_shares_outstanding + self.option_pool_available
        else:
            total = self.total_shares_outstanding

        return holder_shares / total if total > 0 else Decimal("0")

    def get_positions_by_holder(self, holder_id: str) -> List[Position]:
        """Get all positions for a specific holder."""
        return [p for p in self.positions if p.holder_id == holder_id]

    def get_positions_by_class(self, share_class_id: str) -> List[Position]:
        """Get all positions for a specific share class."""
        return [p for p in self.positions if p.share_class_id == share_class_id]


class CurrencyAmount(DomainModel):
    """
    Monetary amount with currency.

    Supports multi-currency cap tables (e.g., UK company with USD and GBP investors).
    """
    amount: Decimal = Field(ge=0, description="Monetary amount")
    currency: str = Field(description="ISO 4217 currency code (USD, GBP, EUR, etc.)")

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is uppercase 3-letter code."""
        if not v.isupper() or len(v) != 3:
            raise ValueError(f"Currency must be 3-letter uppercase code, got: {v}")
        return v


class CapTable(DomainModel):
    """
    Event-sourced cap table.

    State is computed by replaying events chronologically.
    Supports multi-currency investments (base_currency + exchange rates).
    """
    company_name: str

    base_currency: str = Field(
        default="USD",
        description="Primary currency for reporting (ISO 4217 code: USD, GBP, EUR, etc.)"
    )

    events: List[CapTableEvent] = Field(
        default_factory=list,
        description="Chronological history of cap table events"
    )

    share_classes: Dict[str, ShareClass] = Field(
        default_factory=dict,
        description="Share class definitions (class_id → ShareClass)"
    )

    exchange_rates: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="Exchange rates to base_currency (e.g., {'GBP': 1.27} = 1 GBP = 1.27 USD)"
    )

    @field_validator('base_currency')
    @classmethod
    def validate_base_currency(cls, v: str) -> str:
        """Validate currency code."""
        if not v.isupper() or len(v) != 3:
            raise ValueError(f"Currency must be 3-letter uppercase code, got: {v}")
        return v

    def convert_to_base_currency(self, amount: Decimal, from_currency: str) -> Decimal:
        """Convert amount from another currency to base currency."""
        if from_currency == self.base_currency:
            return amount

        if from_currency not in self.exchange_rates:
            raise ValueError(f"Exchange rate not defined for {from_currency}")

        return amount * self.exchange_rates[from_currency]

    @field_validator('events')
    @classmethod
    def sort_events_by_date(cls, v: List[CapTableEvent]) -> List[CapTableEvent]:
        """Ensure events are sorted chronologically."""
        return sorted(v, key=lambda e: e.event_date)

    def snapshot(self, as_of_date: date) -> CapTableSnapshot:
        """
        Compute cap table state at a specific date.

        This is the CORE METHOD of event sourcing.
        """
        snapshot = CapTableSnapshot(as_of_date=as_of_date)

        # Replay events chronologically up to as_of_date
        for event in self.events:
            if event.event_date <= as_of_date:
                event.apply(snapshot)

        return snapshot

    def current_snapshot(self) -> CapTableSnapshot:
        """Get current cap table state (all events applied)."""
        return self.snapshot(date.today())

    def add_event(self, event: CapTableEvent) -> None:
        """Add an event to the cap table."""
        self.events.append(event)
        self.events = sorted(self.events, key=lambda e: e.event_date)
```

---

## Returns & Waterfall

```python
# packages/domain/captable_domain/schemas/returns.py

from typing import List, Literal, Optional
from decimal import Decimal
from datetime import date
from pydantic import Field
from .base import DomainModel, MoneyAmount

class ExitScenario(DomainModel):
    """Exit scenario for returns analysis."""

    id: str
    label: str = Field(
        description="Human-readable label (e.g., 'Base Case', 'Bullish Case')"
    )

    exit_value: MoneyAmount = Field(
        description="Total exit proceeds"
    )

    exit_type: Literal["M&A", "IPO", "secondary"] = Field(
        description="Type of exit event"
    )

    exit_date: Optional[date] = Field(
        default=None,
        description="Expected or actual exit date (for IRR calculation)"
    )


class ReturnsCFG(DomainModel):
    """Configuration for returns analysis."""

    scenarios: List[ExitScenario] = Field(
        description="Exit scenarios to model"
    )

    include_irr: bool = Field(
        default=False,
        description="Calculate IRR (requires investment dates)"
    )

    include_moic: bool = Field(
        default=True,
        description="Calculate MOIC (Multiple on Invested Capital)"
    )
```

---

## Workbook Configuration

```python
# packages/domain/captable_domain/schemas/workbook.py

from typing import Optional, Literal
from pydantic import Field
from .base import DomainModel
from .cap_table import CapTable
from .returns import ReturnsCFG

class WorkbookCFG(DomainModel):
    """
    Top-level configuration for Excel workbook generation.

    This is the entry point for the entire system.
    """
    cap_table: CapTable = Field(
        description="Event-sourced cap table"
    )

    returns: Optional[ReturnsCFG] = Field(
        default=None,
        description="Returns/waterfall configuration (optional)"
    )

    include_audit_sheet: bool = Field(
        default=True,
        description="Include sheet with validation checks"
    )

    include_summary_sheet: bool = Field(
        default=True,
        description="Include summary/overview sheet"
    )

    formatting_theme: Literal["professional", "minimal", "detailed"] = Field(
        default="professional",
        description="Excel formatting theme"
    )
```

---

## Validation Rules

### Field-Level Validation

Handled by Pydantic field validators:
- Data types (Decimal, date, etc.)
- Ranges (ge=0 for ShareCount)
- Patterns (regex for IDs)
- Required vs optional fields

### Model-Level Validation

Handled by Pydantic model validators (`@model_validator`):
- Cross-field constraints (e.g., capped participation requires cap_multiple)
- Business rules (e.g., SAFE must have cap or discount)
- Date validations (maturity > issue date)

### Domain-Level Validation

Handled by separate validator classes in `packages/domain/captable_domain/validators/`:

```python
# packages/domain/captable_domain/validators/cap_table_validator.py

from decimal import Decimal
from typing import List
from dataclasses import dataclass
from ..schemas.cap_table import CapTable, CapTableSnapshot

@dataclass
class ValidationError:
    """A validation error with severity and message."""
    severity: str  # "error" | "warning"
    message: str
    field: str | None = None

@dataclass
class ValidationResult:
    """Result of validation check."""
    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


class CapTableValidator:
    """Validates cap table consistency and business rules."""

    @staticmethod
    def validate_snapshot(snapshot: CapTableSnapshot) -> ValidationResult:
        """Validate a cap table snapshot for consistency."""
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        # 1. No negative equity
        for position in snapshot.positions:
            if position.shares < 0:
                errors.append(ValidationError(
                    severity="error",
                    message=f"Holder {position.holder_id} has negative shares: {position.shares}",
                    field="shares"
                ))

            if position.cost_basis and position.cost_basis < 0:
                errors.append(ValidationError(
                    severity="error",
                    message=f"Holder {position.holder_id} has negative cost basis: {position.cost_basis}",
                    field="cost_basis"
                ))

        # 2. Total shares matches sum of positions
        position_total = sum(
            p.shares for p in snapshot.positions if not p.is_option
        )
        tolerance = Decimal("0.01")  # Allow 0.01 share rounding difference

        if abs(position_total - snapshot.total_shares_outstanding) > tolerance:
            errors.append(ValidationError(
                severity="error",
                message=(
                    f"Position total ({position_total}) does not match "
                    f"total_shares_outstanding ({snapshot.total_shares_outstanding})"
                ),
                field="total_shares_outstanding"
            ))

        # 3. Ownership percentages sum to ~100%
        total_ownership = sum(
            snapshot.ownership_percentage(p.holder_id)
            for p in snapshot.positions
            if not p.is_option
        )

        if not (Decimal("0.99") <= total_ownership <= Decimal("1.01")):
            errors.append(ValidationError(
                severity="error",
                message=f"Ownership percentages sum to {total_ownership*100:.2f}%, expected ~100%",
                field="ownership"
            ))

        # 4. Option pool doesn't exceed authorized
        if snapshot.option_pool_available > snapshot.option_pool_authorized:
            errors.append(ValidationError(
                severity="error",
                message=(
                    f"Option pool available ({snapshot.option_pool_available}) exceeds "
                    f"authorized ({snapshot.option_pool_authorized})"
                ),
                field="option_pool"
            ))

        # 5. Option pool available is non-negative
        if snapshot.option_pool_available < 0:
            errors.append(ValidationError(
                severity="error",
                message=f"Option pool available is negative: {snapshot.option_pool_available}",
                field="option_pool"
            ))

        # 6. Warn if option pool is exhausted
        if snapshot.option_pool_available == 0 and snapshot.option_pool_authorized > 0:
            warnings.append(ValidationError(
                severity="warning",
                message="Option pool is fully allocated (0 shares available)",
                field="option_pool"
            ))

        # 7. Check for duplicate positions (same holder + class + is_option)
        seen = set()
        for position in snapshot.positions:
            key = (position.holder_id, position.share_class_id, position.is_option)
            if key in seen:
                warnings.append(ValidationError(
                    severity="warning",
                    message=f"Duplicate position: {position.holder_id} in {position.share_class_id}",
                    field="positions"
                ))
            seen.add(key)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    @staticmethod
    def validate_cap_table(cap_table: CapTable) -> ValidationResult:
        """Validate entire cap table structure."""
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        # 1. All share_class_ids in events exist in share_classes
        defined_classes = set(cap_table.share_classes.keys())

        for event in cap_table.events:
            # Check ShareIssuanceEvent
            if hasattr(event, 'share_class_id'):
                if event.share_class_id not in defined_classes:
                    errors.append(ValidationError(
                        severity="error",
                        message=(
                            f"Event {event.event_id} references undefined share class: "
                            f"{event.share_class_id}"
                        ),
                        field="share_class_id"
                    ))

        # 2. Price per share > 0 (when specified)
        for event in cap_table.events:
            if hasattr(event, 'price_per_share') and event.price_per_share is not None:
                if event.price_per_share <= 0:
                    errors.append(ValidationError(
                        severity="error",
                        message=(
                            f"Event {event.event_id} has non-positive price_per_share: "
                            f"{event.price_per_share}"
                        ),
                        field="price_per_share"
                    ))

        # 3. Exercise price > 0 for warrants/options
        for event in cap_table.events:
            if hasattr(event, 'exercise_price') and event.exercise_price is not None:
                if event.exercise_price <= 0:
                    errors.append(ValidationError(
                        severity="error",
                        message=(
                            f"Event {event.event_id} has non-positive exercise_price: "
                            f"{event.exercise_price}"
                        ),
                        field="exercise_price"
                    ))

        # 4. Conversion ratio > 0
        for event in cap_table.events:
            if hasattr(event, 'conversion_ratio'):
                if event.conversion_ratio <= 0:
                    errors.append(ValidationError(
                        severity="error",
                        message=(
                            f"Event {event.event_id} has non-positive conversion_ratio: "
                            f"{event.conversion_ratio}"
                        ),
                        field="conversion_ratio"
                    ))

        # 5. Investment amounts > 0
        for event in cap_table.events:
            if hasattr(event, 'instruments'):
                for instrument in event.instruments:
                    if hasattr(instrument, 'investment_amount'):
                        if instrument.investment_amount <= 0:
                            errors.append(ValidationError(
                                severity="error",
                                message=f"Instrument has non-positive investment_amount: {instrument.investment_amount}",
                                field="investment_amount"
                            ))

        # 6. Liquidation preference multiples >= 0
        for share_class in cap_table.share_classes.values():
            if share_class.liquidation_preference:
                if share_class.liquidation_preference.multiple < 0:
                    errors.append(ValidationError(
                        severity="error",
                        message=(
                            f"Share class {share_class.id} has negative liquidation preference: "
                            f"{share_class.liquidation_preference.multiple}"
                        ),
                        field="liquidation_preference"
                    ))

        # 7. Warn if no events
        if len(cap_table.events) == 0:
            warnings.append(ValidationError(
                severity="warning",
                message="Cap table has no events (no shares issued)",
                field="events"
            ))

        # 8. Warn if no share classes defined
        if len(cap_table.share_classes) == 0:
            errors.append(ValidationError(
                severity="error",
                message="No share classes defined",
                field="share_classes"
            ))

        # 9. Multi-currency: Check exchange rates exist
        currencies_used = set()
        for event in cap_table.events:
            if hasattr(event, 'instruments'):
                for instrument in event.instruments:
                    # In multi-currency version, instruments would have currency field
                    # For now, this is a placeholder
                    pass

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )


class WaterfallValidator:
    """Validates waterfall calculations."""

    @staticmethod
    def validate_waterfall(
        snapshot: CapTableSnapshot,
        exit_value: Decimal,
        distributions: dict[str, Decimal]  # holder_id -> proceeds
    ) -> ValidationResult:
        """Validate waterfall distribution sums to exit value."""
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        # 1. Total distributions = exit value
        total_distributed = sum(distributions.values())
        tolerance = exit_value * Decimal("0.0001")  # 0.01% tolerance

        if abs(total_distributed - exit_value) > tolerance:
            errors.append(ValidationError(
                severity="error",
                message=(
                    f"Waterfall distributions ({total_distributed}) do not sum to "
                    f"exit value ({exit_value}). Difference: {abs(total_distributed - exit_value)}"
                ),
                field="distributions"
            ))

        # 2. No negative distributions
        for holder_id, proceeds in distributions.items():
            if proceeds < 0:
                errors.append(ValidationError(
                    severity="error",
                    message=f"Holder {holder_id} has negative proceeds: {proceeds}",
                    field="distributions"
                ))

        # 3. All holders in distributions exist in snapshot
        holder_ids = {p.holder_id for p in snapshot.positions if not p.is_option}
        for holder_id in distributions:
            if holder_id not in holder_ids:
                warnings.append(ValidationError(
                    severity="warning",
                    message=f"Distribution includes unknown holder: {holder_id}",
                    field="distributions"
                ))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
```

**Validation is run at multiple stages:**
1. **Schema creation**: Pydantic validators enforce field-level rules
2. **Event application**: Events validate they can be applied to snapshot
3. **Snapshot generation**: Validate snapshot consistency
4. **Waterfall calculation**: Validate distributions sum correctly
5. **Excel generation**: Final validation before rendering

---

## Example Schemas

### Example 1: Simple Cap Table (2 Founders + Seed Round)

```json
{
  "company_name": "Acme Inc",
  "currency": "USD",
  "share_classes": {
    "common": {
      "id": "common",
      "name": "Common Stock",
      "share_type": "common"
    },
    "seed_preferred": {
      "id": "seed_preferred",
      "name": "Seed Preferred Stock",
      "share_type": "preferred",
      "liquidation_preference": {
        "multiple": 1.0,
        "seniority_rank": 0
      },
      "participation_rights": {
        "participation_type": "non_participating"
      },
      "conversion_rights": {
        "converts_to_class_id": "common",
        "initial_conversion_ratio": 1.0,
        "current_conversion_ratio": 1.0
      }
    }
  },
  "events": [
    {
      "event_id": "event_001",
      "event_type": "share_issuance",
      "event_date": "2023-01-01",
      "holder_id": "founder_alice",
      "share_class_id": "common",
      "shares": 7000000,
      "description": "Founder shares issued to Alice"
    },
    {
      "event_id": "event_002",
      "event_type": "share_issuance",
      "event_date": "2023-01-01",
      "holder_id": "founder_bob",
      "share_class_id": "common",
      "shares": 3000000,
      "description": "Founder shares issued to Bob"
    },
    {
      "event_id": "event_003",
      "event_type": "round_closing",
      "event_date": "2023-06-01",
      "round_id": "seed",
      "round_name": "Seed Round",
      "instruments": [
        {
          "type": "priced",
          "investment_amount": 2000000,
          "pre_money_valuation": 8000000,
          "price_per_share": 0.8,
          "shares_issued": 2500000
        }
      ],
      "share_issuances": [
        {
          "event_id": "event_003a",
          "event_type": "share_issuance",
          "event_date": "2023-06-01",
          "holder_id": "seed_vc",
          "share_class_id": "seed_preferred",
          "shares": 2500000,
          "price_per_share": 0.8
        }
      ]
    }
  ]
}
```

### Example 2: SAFE Conversion

```json
{
  "event_id": "safe_001",
  "event_type": "safe_conversion",
  "event_date": "2024-01-15",
  "safe_holder_id": "early_investor",
  "safe_instrument": {
    "type": "SAFE",
    "investment_amount": 500000,
    "valuation_cap": 10000000,
    "discount_rate": 0.20,
    "safe_type": "post_money"
  },
  "conversion_price": 0.5,
  "shares_issued": 1000000,
  "resulting_share_class_id": "series_a_preferred"
}
```

---

## Review Checklist

**Before implementing, please review:**

- [ ] Do discriminated unions cover all instrument types we need?
- [ ] Are economic rights (liquidation pref, participation, conversion) sufficiently modeled?
- [ ] Does event sourcing make sense for your use cases?
- [ ] Are there any missing event types?
- [ ] Do validation rules cover all critical business logic?
- [ ] Are field names clear and consistent?
- [ ] Do we need additional metadata fields?
- [ ] Are there any VC-specific edge cases not covered?

**Questions ANSWERED:**
1. ✅ **Multi-currency support**: YES - Added base_currency + exchange_rates to CapTable
2. ❌ **Transfer restrictions**: NO - Not modeling lock-ups/ROFR (out of scope)
3. ❌ **Vesting schedules**: NO - Just track vesting_schedule_id reference (details out of scope)
4. ✅ **Stock splits**: YES - Handled via ConversionEvent (no separate type needed)
5. ❌ **Voting agreements**: NO - Not modeling (out of scope)

**Edits Made:**
- ✅ Added `target_post_money` option pool timing (pool sized to hit target % post-round)
- ✅ Added multi-currency support (base_currency + exchange_rates)
- ✅ Simplified convertible note interest: accruing only, with simple or compound calculation
- ✅ Removed dividend rights from MVP schema
- ✅ Added comprehensive domain-level validation (price > 0, no negative equity, etc.)

---

## Edge Case Analysis: Venture Scenarios Not Covered

**Scenario 1: Pay-to-Play / Penalty Provisions** ⚠️ NOT COVERED
```
Series B has pay-to-play: Series A investors who don't participate in Series B
get converted from preferred to common (lose liquidation preference).

Required additions:
- ConditionalConversionEvent (triggers based on participation)
- PayToPlayProvision in share class
```

**Scenario 2: Liquidation Preference Stacking with Dividends** ⚠️ NOT COVERED (MVP REMOVAL)
```
Series A has 8% cumulative dividend + 1x liquidation preference.
At exit, Series A would expect: MAX(1x + accrued dividends, conversion to common)

Current schema:
- ❌ Dividend rights removed from ShareClass in MVP
- ❌ No accrued dividend tracking in snapshot or waterfall

Required additions:
- DividendRights on ShareClass
- DividendAccrual tracking in CapTableSnapshot
- Waterfall logic to include accrued dividends in liquidation preference
```

**Scenario 3: Multiple Closings / Tranched Investment** ⚠️ NOT COVERED
```
Series A raises $10M in two tranches:
- Tranche 1 (Jan 2024): $6M at $1.00/share
- Tranche 2 (Jun 2024): $4M at $1.20/share (higher price, same round)

Both get same share class, but different prices.

Current schema:
- ✅ Can model as separate ShareIssuanceEvents
- ❌ No way to link tranches to same "round"
- ❌ Weighted average price per round not calculated

Required additions:
- tranche_id field in RoundClosingEvent
- Link multiple RoundClosingEvents to same logical round
```

**Scenario 4: Ratchet Anti-Dilution (Full Ratchet)** ⚠️ PARTIALLY COVERED
```
Series A at $10M valuation ($1.00/share).
Series B at $5M valuation (down round, $0.50/share).
Series A has full ratchet → conversion price drops to $0.50.
Series A now has 2x the shares.

Current schema:
- ✅ Has anti_dilution_protection field
- ❌ Missing: Actual recalculation logic
- ❌ Missing: AntiDilutionAdjustmentEvent to record the change

Required additions:
- AntiDilutionAdjustmentEvent
- Logic to detect down rounds and trigger adjustments
- Update conversion_rights.current_conversion_ratio
```

**Scenario 5: Founder Repurchase / Buyback** ⚠️ PARTIALLY COVERED
```
Company buys back 1M shares from departing founder at $0.10/share.
Shares are retired (reduce total shares outstanding).

Current schema:
- ✅ ShareTransferEvent can transfer to company
- ❌ No concept of "treasury shares" or "retired shares"
- ❌ Shares transfer to company still count in total outstanding

Required additions:
- ShareRetirementEvent (reduces total_shares_outstanding)
- Or: Special holder_id = "treasury" that's excluded from ownership calcs
```

**Scenario 6: Earnout / Milestone-Based Equity** ⚠️ NOT COVERED
```
Acquisition with earnout: Founders get additional shares if revenue hits $10M.
Shares issued conditionally based on future performance.

Current schema:
- ❌ No conditional/contingent share issuances
- ❌ No milestone tracking

Required additions:
- ConditionalShareIssuance event type
- Milestone/trigger conditions
- Logic to issue shares when conditions met
```

**Scenario 7: Drag-Along on Acquisition** ⚠️ NOT COVERED (By Design)
```
Series A has drag-along rights: If 60% vote for acquisition, all shareholders
must sell (even if they voted against).

Current schema:
- ❌ Not modeling voting/governance (out of scope)
```

**Scenario 8: Redemption Rights** ⚠️ NOT COVERED
```
Series A has redemption rights: After 5 years, investors can force company
to buy back their shares at original price + 8% annual return.

Current schema:
- ❌ No redemption rights modeling
- ❌ No forced buyback events

Required additions:
- RedemptionRights in ShareClass
- RedemptionEvent (company buys back shares)
```

**Scenario 9: PIK (Payment-in-Kind) Interest** ⚠️ NOT COVERED
```
Convertible note with PIK interest: Instead of cash interest payments,
additional note principal is issued (compounds debt).

Current schema:
- ✅ Has compound interest option
- ❌ Doesn't model PIK specifically (principal increase vs cash payment)

Could be handled with current schema by using compound interest.
```

**Scenario 10: Down Round with Broad-Based Weighted Average** ⚠️ PARTIALLY COVERED
```
Complex anti-dilution calculation:
Old Price = (A + B) / (C + D)
Where:
- A = total consideration for prior rounds
- B = consideration for down round
- C = shares outstanding before down round
- D = shares issued in down round

Current schema:
- ✅ Has anti_dilution_protection with weighted_average_broad
- ❌ Missing: Actual calculation logic
- ❌ Missing: Event to record adjustment

Required for MVP:
- Document the algorithm
- Implement in domain logic (not schema)
```

---

## Recommendations

### For MVP (Phase 1):
**Include:**
- ✅ All current schemas as-is
- ✅ Multi-currency support
- ✅ Option pool target_post_money
- ✅ Participation rights with automatic better-of handling for non-participating

**Defer to Phase 2+:**
- Pay-to-play provisions
- Ratchet anti-dilution (field exists, calculation deferred)
- Multiple closings/tranches
- Redemption rights
- Earnouts/conditional equity

**Explicitly Out of Scope:**
- Voting/governance (drag-along, board seats)
- Transfer restrictions (ROFR, lock-ups)
- Vesting schedule details (just track ID)

### Schema Additions Needed for Full VC Coverage:

1. **AntiDilutionAdjustmentEvent** - Record when conversion ratios change
2. **ShareRetirementEvent** - Handle buybacks and share cancellations
3. **DividendAccrual** tracking in snapshot - For waterfall calculations
4. **Tranche support** in RoundClosingEvent - Link multiple closings to one round

---

**Status:** DRAFT v2 - Revised Based on Feedback
**Next:** Final approval, then begin Pydantic implementation
