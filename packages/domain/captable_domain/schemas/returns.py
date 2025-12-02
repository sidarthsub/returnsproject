"""Returns and waterfall analysis models.

Exit scenarios model different outcomes (M&A, IPO, secondary sales) and calculate
distributions through the liquidation preference waterfall.

This module handles:
- Exit scenario modeling (valuation, type, costs)
- Transaction costs and fees
- Management carveouts and bonus pools
- IPO-specific considerations (float, lockups)
- Returns analysis configuration
"""

from typing import List, Literal, Optional, Dict
from decimal import Decimal
from datetime import date
from pydantic import Field, model_validator

from .base import DomainModel, MoneyAmount, Percentage


# =============================================================================
# Exit Scenario
# =============================================================================

class ExitScenario(DomainModel):
    """Exit scenario for returns analysis.

    Models different exit outcomes to analyze distributions to shareholders.
    Each scenario specifies:
        - Exit value (enterprise value or proceeds)
        - Exit type (M&A, IPO, secondary sale)
        - Transaction costs (legal, banking fees)
        - Management incentives (carveouts, bonus pools)
        - IPO-specific details (float, lockups)

    Common scenarios:
        - Base case: Realistic valuation
        - Upside case: Optimistic valuation
        - Downside case: Conservative valuation
        - Liquidation: Distressed sale

    Example:
        M&A Exit:
            exit_value: $50M
            transaction_costs: 3% ($1.5M for bankers, lawyers)
            management_carveout: 5% ($2.5M bonus pool for executives)
            Net proceeds to distribute: $46M through waterfall

        IPO Exit:
            exit_value: $500M post-IPO valuation
            float_percentage: 20% (20% of shares sold in IPO)
            lockup_period: 180 days
            transaction_costs: 7% (underwriting fees)
    """

    id: str = Field(
        description="Unique identifier for this scenario (e.g., 'base_case', 'upside')"
    )

    label: str = Field(
        description="Human-readable label (e.g., 'Base Case', 'Bullish Case', 'Liquidation')"
    )

    exit_value: MoneyAmount = Field(
        description="Total exit proceeds or valuation before costs/deductions"
    )

    exit_type: Literal["M&A", "IPO", "secondary"] = Field(
        description="Type of exit event"
    )

    exit_date: Optional[date] = Field(
        default=None,
        description="Expected or actual exit date (used for IRR calculation)"
    )

    # Transaction costs and fees (simplified)
    transaction_costs_percentage: Optional[Percentage] = Field(
        default=Decimal("0.03"),
        description="Transaction costs as % of exit value (default 3% for M&A, 7% for IPO)"
    )

    # Management incentives (simplified)
    management_carveout_percentage: Optional[Percentage] = Field(
        default=None,
        description="Management carveout as % of exit proceeds (bonus pool for executives)"
    )

    # IPO-specific fields (simplified)
    float_percentage: Optional[Percentage] = Field(
        default=None,
        description="Percentage of shares sold in IPO (public float). Required for IPO exits."
    )

    lockup_period_days: Optional[int] = Field(
        default=180,
        description="Lockup period for existing shareholders (default 180 days)"
    )

    # Note: Removed for MVP simplification:
    # - Fixed transaction costs (use percentage only)
    # - Management carveout recipients (tracking allocations too detailed)
    # - Greenshoe/over-allotment (IPO edge case)
    # - Escrow holdback (M&A edge case)
    # - Earnout provisions (M&A edge case)

    @model_validator(mode='after')
    def validate_exit_type_fields(self):
        """Validate that exit-type-specific fields are set correctly."""
        if self.exit_type == "IPO":
            if self.float_percentage is None:
                raise ValueError("IPO exit requires float_percentage")

        if self.exit_type == "M&A":
            # M&A exits commonly have escrow and management carveouts
            # But these are optional, so no hard validation
            pass

        return self

    def calculate_net_proceeds(self) -> Decimal:
        """Calculate net proceeds available for distribution through waterfall.

        Deductions (in order):
            1. Transaction costs (percentage of exit value)
            2. Management carveout (percentage of proceeds after transaction costs)

        Returns:
            Net amount to distribute to shareholders

        Example:
            Exit value: $50M
            Transaction costs: 3% = $1.5M
            Management carveout: 5% = $2.425M
            Net proceeds: $46.075M
        """
        proceeds = self.exit_value

        # Deduct transaction costs
        if self.transaction_costs_percentage:
            proceeds -= self.exit_value * self.transaction_costs_percentage

        # Deduct management carveout (calculated on proceeds after transaction costs)
        if self.management_carveout_percentage:
            proceeds -= proceeds * self.management_carveout_percentage

        return proceeds

    def calculate_ipo_offering_size(self) -> Optional[Decimal]:
        """Calculate IPO offering size (value of shares sold to public).

        Returns:
            Offering size in currency, or None if not an IPO

        Example:
            Post-IPO valuation: $500M
            Float: 20%
            Offering size: $100M raised from public
        """
        if self.exit_type != "IPO" or self.float_percentage is None:
            return None

        return self.exit_value * self.float_percentage


# =============================================================================
# Returns Configuration
# =============================================================================

class ReturnsCFG(DomainModel):
    """Configuration for returns and waterfall analysis.

    Specifies which scenarios to model and which metrics to calculate.

    Metrics:
        - MOIC (Multiple on Invested Capital): proceeds / investment
        - IRR (Internal Rate of Return): annualized return accounting for time
        - Cash-on-cash return: actual cash distributions
        - Unrealized gains: paper value of remaining holdings (post-IPO)

    Example:
        ReturnsCFG(
            scenarios=[
                ExitScenario(id="conservative", exit_value=25_000_000, ...),
                ExitScenario(id="base_case", exit_value=50_000_000, ...),
                ExitScenario(id="upside", exit_value=100_000_000, ...),
            ],
            include_irr=True,
            include_moic=True,
            include_unrealized_gains=True,  # For IPO scenarios
        )
    """

    scenarios: List[ExitScenario] = Field(
        description="Exit scenarios to model (base case, upside, downside, etc.)"
    )

    # Metrics to calculate
    include_irr: bool = Field(
        default=False,
        description="Calculate IRR (requires investment dates in cap table)"
    )

    include_moic: bool = Field(
        default=True,
        description="Calculate MOIC (Multiple on Invested Capital)"
    )

    # Display options
    show_by_holder: bool = Field(
        default=True,
        description="Show returns broken down by holder"
    )

    show_by_share_class: bool = Field(
        default=True,
        description="Show returns broken down by share class"
    )

    show_waterfall_steps: bool = Field(
        default=True,
        description="Show detailed waterfall calculation steps"
    )

    # Note: Removed for MVP simplification:
    # - include_unrealized_gains (IPO edge case)
    # - Sensitivity analysis (run multiple scenarios instead)
