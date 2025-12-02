"""Cap table and snapshot models for event-sourced architecture.

The CapTable stores the event history and share class definitions.
CapTableSnapshots represent the computed state at a specific point in time.
"""

from typing import Dict, List, Optional
from datetime import date
from decimal import Decimal
from pydantic import Field, field_validator

from .base import DomainModel, ShareCount
from .share_classes import ShareClass
from .events import CapTableEvent
from .positions import Position


# =============================================================================
# Cap Table Snapshot
# =============================================================================

class CapTableSnapshot(DomainModel):
    """Point-in-time cap table state.

    A snapshot represents the computed state of the cap table at a specific date.
    It's computed by replaying all events up to that date chronologically.

    Key properties:
        - Immutable once computed (events drive changes, not direct mutation)
        - Reproducible (same events → same snapshot)
        - Time-travel enabled (snapshot at any historical date)

    Usage:
        # Get cap table state as of specific date
        snapshot = cap_table.snapshot(as_of_date=date(2024, 1, 1))

        # Get current state
        current = cap_table.current_snapshot()

        # Query ownership
        alice_ownership = snapshot.ownership_percentage("founder_alice")
    """

    as_of_date: date = Field(
        description="Date of this snapshot"
    )

    positions: List[Position] = Field(
        default_factory=list,
        description="All holder positions (shares, options, warrants)"
    )

    total_shares_outstanding: ShareCount = Field(
        default=Decimal("0"),
        description="Total shares issued and outstanding (excludes unexercised options)"
    )

    # Option pool tracking
    option_pool_authorized: ShareCount = Field(
        default=Decimal("0"),
        description="Total shares authorized for option pool"
    )

    option_pool_available: ShareCount = Field(
        default=Decimal("0"),
        description="Shares available for new grants (authorized - granted - exercised)"
    )

    # Share class definitions (reference from parent CapTable)
    share_classes: Dict[str, ShareClass] = Field(
        default_factory=dict,
        description="Share class definitions (copied from CapTable for snapshot access)"
    )

    @property
    def fully_diluted_shares(self) -> ShareCount:
        """Calculate fully diluted share count.

        Fully diluted = outstanding shares + available option pool
        (assumes all ungranted options will be granted and exercised)

        Returns:
            Total fully diluted shares
        """
        return self.total_shares_outstanding + self.option_pool_available

    @property
    def total_voting_shares(self) -> ShareCount:
        """Calculate total voting shares across all positions.

        Each share class may have different votes_per_share.
        Total voting power = sum(position.shares * share_class.votes_per_share)

        Returns:
            Total voting shares
        """
        total_votes = Decimal("0")
        for position in self.positions:
            share_class = self.share_classes.get(position.share_class_id)
            if share_class:
                votes = position.shares * share_class.votes_per_share
                total_votes += votes
        return total_votes

    def add_or_update_position(self, position: Position) -> None:
        """Add a new position or update existing position for same holder + share class.

        Args:
            position: Position to add/update

        Note:
            If a position already exists for this holder + share class + is_option combination,
            the shares and cost basis are added together. Otherwise, a new position is created.
        """
        # Find existing position for this holder + share class + option status
        existing = next(
            (p for p in self.positions
             if p.holder_id == position.holder_id
             and p.share_class_id == position.share_class_id
             and p.is_option == position.is_option),
            None
        )

        if existing:
            # Update existing position (accumulate shares and cost basis)
            existing.shares += position.shares
            if position.cost_basis:
                existing.cost_basis = (existing.cost_basis or Decimal("0")) + position.cost_basis
        else:
            # Add new position
            self.positions.append(position)

        # Update total shares outstanding (only for actual shares, not options)
        if not position.is_option:
            self.total_shares_outstanding += position.shares

    def reduce_position(
        self,
        holder_id: str,
        share_class_id: str,
        shares: Decimal
    ) -> None:
        """Reduce a holder's position (for conversions, transfers, etc.).

        Args:
            holder_id: ID of holder whose position to reduce
            share_class_id: Share class to reduce
            shares: Number of shares to reduce

        Raises:
            ValueError: If position not found or insufficient shares

        Note:
            If shares are reduced to zero, the position is removed entirely.
        """
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

        # Remove position if shares reduced to zero
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
        """Transfer shares from one holder to another.

        Args:
            from_holder: ID of holder transferring shares
            to_holder: ID of holder receiving shares
            share_class_id: Share class being transferred
            shares: Number of shares to transfer
            transfer_date: Date of transfer
            transfer_price: Price per share (if any)

        Note:
            Total shares outstanding doesn't change - just ownership.
        """
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
        """Calculate ownership percentage for a holder.

        Args:
            holder_id: Holder to calculate ownership for
            fully_diluted: If True, include option pool in denominator
                          (assumes all options will be granted and exercised)

        Returns:
            Ownership percentage as decimal (0.25 = 25%)

        Example:
            Alice owns 5M shares out of 20M outstanding = 25%
            Fully diluted (with 4M option pool) = 5M / 24M = 20.8%
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
        """Get all positions for a specific holder.

        Args:
            holder_id: Holder to query

        Returns:
            List of positions (may include shares, options, warrants)
        """
        return [p for p in self.positions if p.holder_id == holder_id]

    def get_positions_by_class(self, share_class_id: str) -> List[Position]:
        """Get all positions for a specific share class.

        Args:
            share_class_id: Share class to query

        Returns:
            List of positions in that share class
        """
        return [p for p in self.positions if p.share_class_id == share_class_id]


# =============================================================================
# Currency Amount
# =============================================================================

class CurrencyAmount(DomainModel):
    """Monetary amount with currency code.

    Supports multi-currency cap tables where investors invest in different currencies.

    Example:
        USD investment: CurrencyAmount(amount=5_000_000, currency="USD")
        GBP investment: CurrencyAmount(amount=2_000_000, currency="GBP")

    The CapTable tracks exchange rates to convert everything to base_currency for reporting.
    """

    amount: Decimal = Field(
        ge=0,
        description="Monetary amount (non-negative)"
    )

    currency: str = Field(
        description="ISO 4217 currency code (USD, GBP, EUR, JPY, etc.)"
    )

    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Validate currency code is uppercase 3-letter ISO 4217 code."""
        if not v.isupper() or len(v) != 3:
            raise ValueError(f"Currency must be 3-letter uppercase ISO 4217 code, got: {v}")
        return v


# =============================================================================
# Cap Table
# =============================================================================

class CapTable(DomainModel):
    """Event-sourced cap table.

    The CapTable is the source of truth for ownership. It stores:
        1. Event history (what happened, when)
        2. Share class definitions (economic rights, voting rights)
        3. Exchange rates (for multi-currency support)

    State is NOT stored directly - it's computed by replaying events.

    Key methods:
        - snapshot(date): Compute state as of specific date
        - current_snapshot(): Compute current state
        - add_event(event): Append new event to history

    Event-sourcing benefits:
        - Complete audit trail (immutable history)
        - Time travel (query state at any date)
        - Reproducibility (replay events → same state)
        - Debugging (replay subset of events to isolate issues)
        - Compliance (prove ownership at any point in time)

    Multi-currency support:
        Company operates in USD but has GBP and EUR investors.
        Exchange rates convert everything to base_currency for reporting.

    Example:
        cap_table = CapTable(company_name="Acme Corp", base_currency="USD")

        # Add share classes
        cap_table.share_classes["common"] = ShareClass(...)

        # Add events
        cap_table.add_event(ShareIssuanceEvent(...))
        cap_table.add_event(RoundClosingEvent(...))

        # Query state
        snapshot = cap_table.current_snapshot()
        alice_ownership = snapshot.ownership_percentage("founder_alice")
    """

    company_name: str = Field(
        description="Company legal name"
    )

    base_currency: str = Field(
        default="USD",
        description="Primary currency for reporting (ISO 4217 code)"
    )

    events: List[CapTableEvent] = Field(
        default_factory=list,
        description="Chronological history of cap table events (append-only)"
    )

    share_classes: Dict[str, ShareClass] = Field(
        default_factory=dict,
        description="Share class definitions (share_class_id → ShareClass)"
    )

    exchange_rates: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="Exchange rates to base_currency (e.g., {'GBP': 1.27} = 1 GBP = 1.27 USD)"
    )

    @field_validator('base_currency')
    @classmethod
    def validate_base_currency(cls, v: str) -> str:
        """Validate base currency is uppercase 3-letter ISO 4217 code."""
        if not v.isupper() or len(v) != 3:
            raise ValueError(f"Currency must be 3-letter uppercase ISO 4217 code, got: {v}")
        return v

    def convert_to_base_currency(self, amount: Decimal, from_currency: str) -> Decimal:
        """Convert amount from another currency to base currency.

        Args:
            amount: Amount in from_currency
            from_currency: Currency code to convert from

        Returns:
            Amount in base_currency

        Raises:
            ValueError: If exchange rate not defined for from_currency

        Example:
            cap_table.base_currency = "USD"
            cap_table.exchange_rates = {"GBP": Decimal("1.27")}
            usd_amount = cap_table.convert_to_base_currency(Decimal("1000"), "GBP")
            # Returns 1270.00 (1000 GBP * 1.27 = 1270 USD)
        """
        if from_currency == self.base_currency:
            return amount

        if from_currency not in self.exchange_rates:
            raise ValueError(
                f"Exchange rate not defined for {from_currency}. "
                f"Add to cap_table.exchange_rates['{from_currency}']"
            )

        return amount * self.exchange_rates[from_currency]

    @field_validator('events')
    @classmethod
    def sort_events_by_date(cls, v: List[CapTableEvent]) -> List[CapTableEvent]:
        """Ensure events are sorted chronologically by event_date.

        This is critical for event sourcing - events must be replayed in order.
        """
        return sorted(v, key=lambda e: e.event_date)

    def snapshot(self, as_of_date: date) -> CapTableSnapshot:
        """Compute cap table state at a specific date.

        This is the CORE METHOD of event sourcing.

        Args:
            as_of_date: Date to compute state for

        Returns:
            CapTableSnapshot with state as of that date

        How it works:
            1. Create empty snapshot
            2. Replay all events chronologically up to as_of_date
            3. Each event applies its changes to the snapshot
            4. Return final snapshot

        Example:
            # Cap table state as of Series A closing
            series_a_snapshot = cap_table.snapshot(date(2023, 6, 15))

            # Cap table state one year ago
            year_ago = cap_table.snapshot(date.today() - timedelta(days=365))
        """
        snapshot = CapTableSnapshot(
            as_of_date=as_of_date,
            share_classes=self.share_classes  # Pass share classes to snapshot
        )

        # Replay events chronologically up to as_of_date
        for event in self.events:
            if event.event_date <= as_of_date:
                event.apply(snapshot)

        return snapshot

    def current_snapshot(self) -> CapTableSnapshot:
        """Get current cap table state (all events applied).

        Returns:
            CapTableSnapshot with latest state

        Equivalent to:
            cap_table.snapshot(date.today())
        """
        return self.snapshot(date.today())

    def add_event(self, event: CapTableEvent) -> None:
        """Add an event to the cap table.

        Args:
            event: Event to append to history

        Note:
            Events are automatically sorted by date after adding.
            This ensures chronological replay always works correctly.

        Example:
            cap_table.add_event(
                ShareIssuanceEvent(
                    event_id="founder_grant_001",
                    event_date=date(2023, 1, 1),
                    holder_id="founder_alice",
                    share_class_id="common",
                    shares=Decimal("5000000"),
                )
            )
        """
        self.events.append(event)
        # Re-sort to maintain chronological order
        self.events = sorted(self.events, key=lambda e: e.event_date)
