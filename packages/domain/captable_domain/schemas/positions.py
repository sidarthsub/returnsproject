"""Position tracking for shareholders and optionholders.

A Position represents a holder's stake in a specific share class at a point in time.
Positions are computed from events in the event-sourced model.
"""

from typing import Optional
from datetime import date
from decimal import Decimal
from pydantic import Field

from .base import DomainModel, ShareClassId, HolderId, ShareCount, MoneyAmount


# =============================================================================
# Position
# =============================================================================

class Position(DomainModel):
    """A holder's position in a specific share class.

    Represents ownership at a point in time. Positions are computed by replaying
    cap table events up to a specific date.

    Key distinction:
        - Position: Current state of ownership (shares held)
        - Event: Historical record of what happened (shares issued/transferred)

    Examples:
        Common stock position:
            holder_id="founder_alice"
            share_class_id="common"
            shares=5_000_000
            cost_basis=None (founder shares, no cost)

        Investor position:
            holder_id="acme_vc"
            share_class_id="series_a_preferred"
            shares=2_500_000
            cost_basis=5_000_000 (paid $5M for these shares)

        Option position (not yet exercised):
            holder_id="employee_123"
            share_class_id="common"
            shares=50_000
            is_option=True
            exercise_price=2.00
    """

    holder_id: HolderId = Field(
        description="ID of the shareholder/optionholder"
    )

    share_class_id: ShareClassId = Field(
        description="Share class being held"
    )

    shares: ShareCount = Field(
        description="Number of shares held (or under option)"
    )

    acquisition_date: date = Field(
        description="Date shares were acquired (or option granted)"
    )

    # Financial tracking
    cost_basis: Optional[MoneyAmount] = Field(
        default=None,
        description="Total cost basis (price paid for shares). None = no cost (founder shares, etc.)"
    )

    # Vesting (simplified - detailed vesting schedules handled elsewhere)
    vesting_schedule_id: Optional[str] = Field(
        default=None,
        description="ID of vesting schedule if shares vest over time"
    )

    # Options and warrants
    is_option: bool = Field(
        default=False,
        description="True if this is an unexercised option/warrant position"
    )

    exercise_price: Optional[Decimal] = Field(
        default=None,
        description="Exercise/strike price per share (for options/warrants)"
    )

    expiration_date: Optional[date] = Field(
        default=None,
        description="Expiration date for options/warrants (None = no expiration)"
    )

    def effective_cost_per_share(self) -> Optional[Decimal]:
        """Calculate the effective cost per share.

        Returns:
            Cost per share if cost_basis is set, otherwise None.

        Note:
            Returns None for founder shares or other zero-cost positions.
        """
        if self.cost_basis is None or self.shares == 0:
            return None
        return self.cost_basis / self.shares

    def total_exercise_cost(self) -> Optional[Decimal]:
        """Calculate total cost to exercise all options/warrants.

        Returns:
            Total cost (exercise_price * shares) for options/warrants, None otherwise.
        """
        if not self.is_option or self.exercise_price is None:
            return None
        return self.exercise_price * self.shares
