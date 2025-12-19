"""Cap table events for event-sourced architecture.

Events are immutable records of what happened to a cap table over time.
The current state of a cap table is computed by replaying events chronologically.

This event-sourcing pattern provides:
- Complete audit trail (who, what, when)
- Time-travel queries (cap table as of any date)
- Reproducibility (same events → same state)
- Easier debugging and compliance

Note on Exit Events:
    IPO and M&A exits are modeled in returns.py as ExitScenario (for waterfall analysis).
    Actual exit events (if needed) can be added in future versions to record conversions
    and final distributions.
"""

from abc import ABC, abstractmethod
from typing import Optional, Literal, List, TYPE_CHECKING
from datetime import date
from decimal import Decimal
from pydantic import Field, model_validator

from .base import (
    DomainModel,
    EventId,
    ShareClassId,
    HolderId,
    RoundId,
    ShareCount,
    MoneyAmount,
    Percentage,
)
from .instruments import Instrument, SAFEInstrument, WarrantInstrument

# Avoid circular import for type hints
if TYPE_CHECKING:
    from .cap_table import CapTableSnapshot


# =============================================================================
# Event Base Class
# =============================================================================

class CapTableEvent(DomainModel, ABC):
    """Base class for all cap table events.

    Events represent immutable facts about what happened to the cap table.
    Each event has an apply() method that updates a CapTableSnapshot.

    Event-sourcing principles:
        1. Events are append-only (never modified or deleted)
        2. Events are ordered chronologically
        3. State is computed by replaying events in order
        4. Events should capture intent and context (description field)

    Example event timeline:
        1. ShareIssuanceEvent: Founders get 10M shares
        2. OptionPoolCreation: Create 2M share option pool
        3. RoundClosingEvent: Series A closes ($5M)
        4. OptionExerciseEvent: Employee exercises 50K options
        5. ConversionEvent: Series A converts to common at exit
    """

    event_id: EventId = Field(
        description="Unique identifier for this event (UUID or user-defined)"
    )

    event_date: date = Field(
        description="Date the event occurred (for chronological ordering)"
    )

    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of the event for audit trail"
    )

    @abstractmethod
    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Apply this event to a snapshot to update its state.

        This method mutates the snapshot by adding/updating/removing positions,
        adjusting share counts, etc.

        Args:
            snapshot: The CapTableSnapshot to mutate

        Implementation note:
            Subclasses must implement this method to define how the event
            affects cap table state.
        """
        pass


# =============================================================================
# Share Issuance Event
# =============================================================================

class ShareIssuanceEvent(CapTableEvent):
    """Shares are issued to a holder.

    This is the fundamental event for granting equity:
        - Founder shares at incorporation
        - New shares issued to investors
        - Employee equity grants (restricted stock)
        - Advisor grants

    Note: This is different from option grants (use OptionPoolCreation + later OptionExerciseEvent)
    """

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
        description="Price per share paid by holder (None = no cost, e.g., founder shares)"
    )

    vesting_schedule_id: Optional[str] = Field(
        default=None,
        description="Vesting schedule ID if shares vest over time"
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


# =============================================================================
# Share Transfer Event
# =============================================================================

class ShareTransferEvent(CapTableEvent):
    """Shares are transferred from one holder to another (secondary sale).

    Common scenarios:
        - Founder sells shares to another founder
        - Early employee sells vested shares
        - Secondary market transaction
        - Gift or inheritance

    Note: Transfer doesn't change total shares outstanding, just ownership.

    Alchemy (optional):
        If resulting_share_class_id is specified, the buyer receives shares
        of a different class than what the seller gave up. This is common in
        secondary transactions where investors negotiate to receive senior
        preferred stock in exchange for junior preferred shares.
    """

    event_type: Literal["share_transfer"] = "share_transfer"

    from_holder_id: HolderId = Field(
        description="ID of holder transferring shares"
    )

    to_holder_id: HolderId = Field(
        description="ID of holder receiving shares"
    )

    share_class_id: ShareClassId = Field(
        description="Share class being transferred (from seller's perspective)"
    )

    shares: ShareCount = Field(
        description="Number of shares transferred"
    )

    price_per_share: Optional[Decimal] = Field(
        default=None,
        description="Transfer price per share (if disclosed)"
    )

    resulting_share_class_id: Optional[ShareClassId] = Field(
        default=None,
        description="Share class buyer receives (if different from seller's class - 'alchemy'). "
                    "If None, buyer receives same class as seller."
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
            resulting_share_class_id=self.resulting_share_class_id,
        )


# =============================================================================
# Conversion Event
# =============================================================================

class ConversionEvent(CapTableEvent):
    """Shares convert from one class to another.

    Common scenarios:
        - Preferred stock converts to common at IPO/exit
        - Preferred converts voluntarily (if common more valuable)
        - Stock split (e.g., 1 share → 2 shares via 2:1 conversion)
        - Reverse split (e.g., 2 shares → 1 share via 0.5:1 conversion)

    Note: Conversion ratio determines how many new shares result.
    """

    event_type: Literal["conversion"] = "conversion"

    holder_id: HolderId = Field(
        description="ID of holder whose shares are converting"
    )

    from_share_class_id: ShareClassId = Field(
        description="Share class converting from"
    )

    to_share_class_id: ShareClassId = Field(
        description="Share class converting to"
    )

    shares_converted: ShareCount = Field(
        description="Number of shares being converted (in from_share_class)"
    )

    conversion_ratio: Decimal = Field(
        description="Conversion ratio: 1 share of from_class → N shares of to_class"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Convert shares from one class to another."""
        new_shares = self.shares_converted * self.conversion_ratio

        # Reduce position in old share class
        snapshot.reduce_position(
            self.holder_id,
            self.from_share_class_id,
            self.shares_converted
        )

        # Add position in new share class
        from .positions import Position
        snapshot.add_or_update_position(
            Position(
                holder_id=self.holder_id,
                share_class_id=self.to_share_class_id,
                shares=new_shares,
                acquisition_date=self.event_date,
            )
        )


# =============================================================================
# Option Exercise Event
# =============================================================================

class OptionExerciseEvent(CapTableEvent):
    """Employee/advisor exercises stock options.

    When options are exercised:
        1. Option pool available shares decrease
        2. Actual shares are issued to holder
        3. Holder pays exercise price * shares

    Tax implications (not modeled here):
        - ISOs: Potential AMT if hold shares
        - NSOs: Ordinary income on spread at exercise
    """

    event_type: Literal["option_exercise"] = "option_exercise"

    holder_id: HolderId = Field(
        description="ID of holder exercising options"
    )

    option_grant_id: str = Field(
        description="ID of the option grant being exercised"
    )

    shares_exercised: ShareCount = Field(
        description="Number of shares being exercised"
    )

    exercise_price: Decimal = Field(
        description="Exercise price per share (strike price)"
    )

    resulting_share_class_id: ShareClassId = Field(
        description="Share class received upon exercise (usually 'common')"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Exercise options → issue shares, reduce option pool."""
        # Reduce option pool available shares
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


# =============================================================================
# Round Closing Event (Composite Event)
# =============================================================================

class RoundClosingEvent(CapTableEvent):
    """A financing round closes.

    This is a composite event that orchestrates multiple sub-events:
        1. SAFE/convertible conversions (if any)
        2. New share issuances to investors
        3. Option pool creation/expansion (if any)
        4. Warrant issuances (if any)

    This event type captures the entire round in one place for easier
    analysis and reporting (e.g., "Series A Round" as a single unit).

    Example:
        Series A Round:
        - 2 SAFEs convert → 500K shares
        - Lead investor gets 2M shares for $5M
        - Option pool expanded by 1M shares (pre-money)
        - Lead gets 10% warrant coverage → 200K warrants
    """

    event_type: Literal["round_closing"] = "round_closing"

    round_id: RoundId = Field(
        description="Unique identifier for this round"
    )

    round_name: str = Field(
        description="Human-readable round name (e.g., 'Seed Round', 'Series A')"
    )

    instruments: List[Instrument] = Field(
        description="Instruments used in this round (SAFEs, priced equity, notes, warrants)"
    )

    # Sub-events that occur as part of round closing
    safe_conversions: List['SAFEConversionEvent'] = Field(
        default_factory=list,
        description="SAFEs that convert in this round"
    )

    share_issuances: List[ShareIssuanceEvent] = Field(
        default_factory=list,
        description="Shares issued to investors in this round"
    )

    option_pool_created: Optional['OptionPoolCreation'] = Field(
        default=None,
        description="Option pool created/expanded in this round"
    )

    warrants_issued: List['WarrantIssuance'] = Field(
        default_factory=list,
        description="Warrants issued alongside equity"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Apply all sub-events in correct order.

        Order matters:
            1. SAFE conversions first (they convert at pre-money)
            2. New share issuances (investors get shares)
            3. Option pool creation (if pre-money, dilutes everyone; if post-money, includes investors)
            4. Warrants issued (additional upside for investors)
        """
        # Step 1: Convert SAFEs/convertibles
        for conversion in self.safe_conversions:
            conversion.apply(snapshot)

        # Step 2: Issue new shares to investors
        for issuance in self.share_issuances:
            issuance.apply(snapshot)

        # Step 3: Create/expand option pool
        if self.option_pool_created:
            self.option_pool_created.apply(snapshot)

        # Step 4: Issue warrants
        for warrant in self.warrants_issued:
            warrant.apply(snapshot)


# =============================================================================
# SAFE Conversion Event
# =============================================================================

class SAFEConversionEvent(CapTableEvent):
    """SAFE converts to equity in a priced round.

    When a priced round closes, SAFEs convert to equity based on:
        - Valuation cap (if any): Limits valuation used for conversion calculation
        - Discount (if any): Gives SAFE holder discount on price per share
        - If both: SAFE holder gets whichever is more favorable (more shares)

    Conversion calculation:
        shares = investment_amount / effective_price_per_share

        Where effective_price is the better of:
        - Cap-based: investment / (cap / fully_diluted_shares)
        - Discount-based: round_price * (1 - discount)

    Example:
        $100K SAFE with $5M cap and 20% discount.
        Series A: $10M pre-money, $1.00/share.

        Via cap: $100K / ($5M / 10M shares) = $100K / $0.50 = 200K shares
        Via discount: $100K / ($1.00 * 0.8) = 125K shares

        SAFE holder gets 200K shares (better deal).
    """

    event_type: Literal["safe_conversion"] = "safe_conversion"

    safe_holder_id: HolderId = Field(
        description="ID of SAFE holder"
    )

    safe_instrument: SAFEInstrument = Field(
        description="Original SAFE instrument details"
    )

    # Conversion calculation results
    conversion_price: Decimal = Field(
        description="Effective price per share for SAFE conversion"
    )

    shares_issued: ShareCount = Field(
        description="Number of shares issued from SAFE conversion"
    )

    resulting_share_class_id: ShareClassId = Field(
        description="Share class issued (usually same as priced round investors)"
    )

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


# =============================================================================
# Option Pool Creation Event
# =============================================================================

class OptionPoolCreation(CapTableEvent):
    """Option pool is created or expanded.

    Option pools are shares authorized (but not yet issued) for employee options.

    Timing matters for dilution:
        - pre_money: Pool created before investment
          * Dilutes existing shareholders (founders)
          * Does NOT dilute new investors
          * Increases shares outstanding before valuation calculation

        - post_money: Pool created after investment
          * Dilutes everyone (founders + investors)
          * Pool comes out of post-money total

        - target_post_money: Pool sized to hit specific % after round
          * "We want 20% option pool post-Series-A"
          * Pool size calculated backward from target
          * Most investor-friendly (ensures pool for future hires)

    Example:
        10M shares outstanding, Series A wants 20% post-money pool.

        Pre-money pool:
            Pool: 2.5M shares (10M * 0.25 = 2.5M to get 20% of 12.5M)
            New total: 12.5M shares
            Series A invests for 20% → 3.125M more shares
            Final: 15.625M shares, 2.5M pool = 16% pool (diluted by Series A)

        Target post-money pool:
            Target: 20% pool after everything
            Pool size calculated to hit exactly 20% post-investment
    """

    event_type: Literal["option_pool_creation"] = "option_pool_creation"

    shares_authorized: ShareCount = Field(
        description="Number of shares authorized for option pool"
    )

    pool_timing: Literal["pre_money", "post_money", "target_post_money"] = Field(
        description="When pool is created relative to investment (affects dilution)"
    )

    target_percentage: Optional[Percentage] = Field(
        default=None,
        description="Target option pool percentage post-money (only for target_post_money timing)"
    )

    share_class_id: ShareClassId = Field(
        default="common",
        description="Share class for options (usually common stock)"
    )

    @model_validator(mode='after')
    def validate_target_percentage(self):
        """target_post_money timing requires target_percentage to be set."""
        if self.pool_timing == "target_post_money":
            if self.target_percentage is None:
                raise ValueError("target_post_money pool requires target_percentage")
        return self

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Add shares to option pool.

        Note: Option pool shares are tracked separately in option_pool_authorized
        and option_pool_available. They are NOT added to total_shares_outstanding
        because they haven't been issued yet. The fully_diluted_shares property
        adds option_pool_available to get the fully diluted count.
        """
        snapshot.option_pool_authorized += self.shares_authorized
        snapshot.option_pool_available += self.shares_authorized

        # Option pool shares are reserved, not issued, so they don't affect
        # total_shares_outstanding. They only affect fully_diluted_shares.


# =============================================================================
# Warrant Issuance Event
# =============================================================================

class WarrantIssuance(CapTableEvent):
    """Warrants are issued (usually alongside priced round).

    Warrants give the holder the right to purchase shares at a strike price.

    Common uses:
        - Warrant coverage for debt financing (e.g., "5% warrant coverage")
        - Sweetener for investors ("$5M investment + 10% warrant coverage")
        - Compensation for advisors/service providers

    Example:
        Series A: $10M investment with 10% warrant coverage.
        Warrant: Right to purchase $1M worth of shares at Series A price.
        If Series A price = $2.00/share, warrant is for 500K shares.

    Warrants vs Options:
        - Warrants: Issued to investors/outsiders, longer expiration (5-10 years)
        - Options: Issued to employees, shorter expiration (10 years max)
        - Accounting: Warrants affect diluted shares immediately, options only when in-the-money
    """

    event_type: Literal["warrant_issuance"] = "warrant_issuance"

    holder_id: HolderId = Field(
        description="ID of warrant holder"
    )

    warrant: WarrantInstrument = Field(
        description="Warrant instrument details (shares, strike price, expiration)"
    )

    def apply(self, snapshot: 'CapTableSnapshot') -> None:
        """Add warrant position to snapshot.

        Note: Warrants are tracked as positions with is_option=True,
        but distinguished from options by a 'warrant_' prefix on share class.
        """
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
