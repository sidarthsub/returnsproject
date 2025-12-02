"""Instrument types using discriminated unions for type safety.

Instruments represent different ways of investing in or participating in a company's cap table:
- SAFEs: Convert to equity in next priced round
- Priced rounds: Direct equity purchase at specific price
- Convertible notes: Debt that converts to equity
- Warrants: Rights to purchase shares at a strike price

Using discriminated unions ensures type safety and prevents invalid instrument configurations.
"""

from typing import Annotated, Union, Literal, Optional
from decimal import Decimal
from datetime import date
from pydantic import Field, model_validator

from .base import DomainModel, ShareClassId, MoneyAmount, Percentage, ShareCount


# =============================================================================
# SAFE Instrument
# =============================================================================

class SAFEInstrument(DomainModel):
    """Simple Agreement for Future Equity (SAFE).

    A SAFE is a contract between an investor and company that grants the investor
    the right to receive equity in a future priced round, based on the terms of
    the SAFE (valuation cap and/or discount rate).

    SAFEs were popularized by Y Combinator as a simpler alternative to convertible
    notes (no interest rate, no maturity date, no debt on balance sheet).

    Key mechanics:
        - Investment converts in next "equity financing" (priced round)
        - Conversion price based on:
          * Valuation cap (if any): effective_valuation = min(cap, round_valuation)
          * Discount rate (if any): price = round_price * (1 - discount)
          * If both cap AND discount: investor gets whichever gives them more shares (better deal)

    Types:
        - Post-money SAFE: More common, cap refers to post-money valuation
        - Pre-money SAFE: Less common, cap refers to pre-money valuation

    Example with both cap and discount:
        SAFE: $100K investment, $5M cap, 20% discount
        Series A: $10M pre-money, $1.00/share

        Via cap: $100K / ($5M / shares_outstanding) = more shares
        Via discount: $100K / ($1.00 * 0.8) = $100K / $0.80 = 125K shares

        Investor gets whichever calculation gives MORE shares.
    """

    type: Literal["SAFE"] = "SAFE"

    investment_amount: MoneyAmount = Field(
        description="Amount invested via SAFE"
    )

    valuation_cap: Optional[MoneyAmount] = Field(
        default=None,
        description="Valuation cap for conversion. If actual valuation > cap, investor benefits."
    )

    discount_rate: Optional[Percentage] = Field(
        default=None,
        description="Discount rate for conversion (e.g., 0.20 = 20% discount). "
                    "SAFE holder pays 20% less than Series A investor."
    )

    safe_type: Literal["pre_money", "post_money"] = Field(
        default="post_money",
        description="Pre-money or post-money SAFE (post-money is more common post-2018)"
    )

    # Note: MFN and pro-rata side letters removed for MVP (edge cases)

    @model_validator(mode='after')
    def validate_cap_or_discount(self):
        """SAFE must have valuation cap and/or discount rate (can have both)."""
        if self.valuation_cap is None and self.discount_rate is None:
            raise ValueError("SAFE must have at least one of: valuation_cap or discount_rate (can have both)")
        return self


# =============================================================================
# Priced Round Instrument
# =============================================================================

class PricedRoundInstrument(DomainModel):
    """Priced equity round (Seed, Series A, Series B, etc.).

    In a priced round, the company and investors agree on:
        1. Valuation (pre-money)
        2. Investment amount
        3. Price per share (derived from valuation / shares outstanding)
        4. Number of shares issued

    Math: post_money_valuation = pre_money_valuation + investment_amount

    Example:
        Company has 10M shares outstanding (all common).
        Series A: $20M pre-money valuation, $5M investment.
        Price per share: $20M / 10M = $2.00
        Shares issued: $5M / $2.00 = 2.5M shares
        Post-money: $25M
        Series A ownership: 2.5M / 12.5M = 20%
    """

    type: Literal["priced"] = "priced"

    investment_amount: MoneyAmount = Field(
        description="Total amount raised in this round"
    )

    pre_money_valuation: MoneyAmount = Field(
        description="Company valuation before this investment"
    )

    price_per_share: Decimal = Field(
        gt=0,
        description="Price per share for this round"
    )

    shares_issued: ShareCount = Field(
        description="Number of shares issued to investors in this round"
    )

    # Note: Warrant coverage removed for MVP - warrants should be separate WarrantIssuance events

    @model_validator(mode='after')
    def validate_math(self):
        """Validate that investment = price * shares (allowing for small rounding errors)."""
        calculated_investment = self.price_per_share * self.shares_issued

        # Allow 1% tolerance for rounding differences
        diff = abs(calculated_investment - self.investment_amount)
        tolerance = self.investment_amount * Decimal("0.01")

        if diff > tolerance:
            raise ValueError(
                f"Inconsistent math: price_per_share ({self.price_per_share}) * "
                f"shares_issued ({self.shares_issued}) = {calculated_investment}, "
                f"but investment_amount is {self.investment_amount}. "
                f"Difference ({diff}) exceeds tolerance ({tolerance})."
            )

        return self


# =============================================================================
# Convertible Note Instrument
# =============================================================================

class ConvertibleNoteInstrument(DomainModel):
    """Convertible note (debt that converts to equity).

    A convertible note is a loan that converts to equity in a future financing round.
    Unlike a SAFE, it's actual debt with:
        - Principal amount (loan amount)
        - Interest rate (typically 2-8% annually)
        - Maturity date (when the note is due if not converted)

    Interest mechanics:
        - Simple interest: Interest = Principal * Rate * Time
        - Compound interest: Amount = Principal * (1 + Rate)^Time

        - Accruing: Interest accumulates and converts with principal
        - Paid: Interest is paid out periodically (quarterly/annually)

    Conversion mechanics (similar to SAFE):
        - Valuation cap: Maximum valuation for conversion calculation
        - Discount rate: Discount on price per share vs. new investors
        - If both cap AND discount: investor gets whichever gives more shares

    Example:
        $500K note, 5% simple interest, issued Jan 1, 2023.
        Converts in Series A on Jan 1, 2025 (2 years later).
        Accrued amount: $500K + ($500K * 0.05 * 2) = $550K converts to equity.

    PIK Interest (Payment In Kind):
        When interest_type="compound" and interest_payment="accruing",
        the note effectively has PIK interest - interest compounds and
        converts to equity rather than being paid in cash.
    """

    type: Literal["convertible_note"] = "convertible_note"

    principal_amount: MoneyAmount = Field(
        description="Principal amount of the note (initial loan)"
    )

    interest_rate: Percentage = Field(
        description="Annual interest rate (e.g., 0.05 = 5% per year)"
    )

    interest_type: Literal["simple", "compound"] = Field(
        default="simple",
        description="Simple interest (linear) or compound interest (exponential). Most notes use simple."
    )

    # Note: Interest payment timing simplified for MVP - always accruing (not paid out)

    issue_date: date = Field(
        description="Date note was issued"
    )

    maturity_date: date = Field(
        description="Date note matures (becomes due for repayment if not converted)"
    )

    valuation_cap: Optional[MoneyAmount] = Field(
        default=None,
        description="Valuation cap for conversion (same as SAFE cap)"
    )

    discount_rate: Optional[Percentage] = Field(
        default=None,
        description="Discount rate for conversion (same as SAFE discount)"
    )

    @model_validator(mode='after')
    def validate_dates(self):
        """Maturity date must be after issue date."""
        if self.maturity_date <= self.issue_date:
            raise ValueError("maturity_date must be after issue_date")
        return self

    @model_validator(mode='after')
    def validate_cap_or_discount(self):
        """Convertible note should have valuation cap and/or discount rate (can have both)."""
        if self.valuation_cap is None and self.discount_rate is None:
            raise ValueError(
                "Convertible note should have at least one of: valuation_cap or discount_rate (can have both)"
            )
        return self

    def calculate_accrued_amount(self, as_of_date: date) -> Decimal:
        """Calculate principal + accrued interest as of a specific date.

        Args:
            as_of_date: Date to calculate accrued amount

        Returns:
            Total amount (principal + interest) as of the date

        Note:
            Interest always accrues (simplified for MVP - paid interest removed).
        """
        # Calculate time elapsed
        days = (as_of_date - self.issue_date).days
        years = Decimal(days) / Decimal("365.25")

        if self.interest_type == "simple":
            # Simple interest: I = P * r * t
            interest = self.principal_amount * self.interest_rate * years
        else:  # compound
            # Compound interest (annually): A = P(1 + r)^t
            interest = self.principal_amount * (
                (Decimal("1") + self.interest_rate) ** years - Decimal("1")
            )

        return self.principal_amount + interest


# =============================================================================
# Warrant Instrument
# =============================================================================

class WarrantInstrument(DomainModel):
    """Warrant to purchase shares.

    A warrant gives the holder the right (but not obligation) to purchase a
    specific number of shares at a predetermined price (exercise/strike price).

    Common uses:
        - Issued with debt financing (warrant coverage)
        - Issued to service providers as compensation
        - Issued to strategic partners

    Example:
        Company issues warrant for 100K shares at $1.00/share.
        If company exits at $10/share, holder can:
        - Exercise: Pay $100K, get shares worth $1M → $900K gain
        - Net exercise: Get ~90K shares (net of exercise cost)

    Warrant coverage:
        Often expressed as percentage of investment.
        "$5M investment with 10% warrant coverage" = warrant to purchase
        $500K worth of shares at the round price.
    """

    type: Literal["warrant"] = "warrant"

    shares_purchasable: ShareCount = Field(
        description="Number of shares that can be purchased upon exercise"
    )

    exercise_price: Decimal = Field(
        gt=0,
        description="Price per share to exercise warrant (strike price)"
    )

    share_class_id: ShareClassId = Field(
        description="Share class the warrant grants rights to purchase"
    )

    issue_date: date = Field(
        description="Date warrant was issued"
    )

    expiration_date: Optional[date] = Field(
        default=None,
        description="Date warrant expires (if any). None = no expiration."
    )

    @model_validator(mode='after')
    def validate_dates(self):
        """Expiration date must be after issue date."""
        if self.expiration_date and self.expiration_date <= self.issue_date:
            raise ValueError("expiration_date must be after issue_date")
        return self


# =============================================================================
# Discriminated Union
# =============================================================================

Instrument = Annotated[
    Union[
        SAFEInstrument,
        PricedRoundInstrument,
        ConvertibleNoteInstrument,
        WarrantInstrument
    ],
    Field(discriminator='type')
]
"""Discriminated union of all instrument types.

The 'type' field serves as the discriminator, allowing Pydantic to:
1. Validate the correct instrument schema based on type
2. Provide proper type narrowing in static analysis
3. Prevent invalid instrument configurations

Usage:
    # Valid - type determines which fields are allowed
    safe = SAFEInstrument(
        type="SAFE",
        investment_amount=Decimal("100000"),
        valuation_cap=Decimal("5000000"),
        discount_rate=Decimal("0.20"),  # Can have both cap and discount
        safe_type="post_money"
    )

    # Invalid - caught by Pydantic validation
    invalid = SAFEInstrument(
        type="SAFE",
        principal_amount=Decimal("100000")  # Error: SAFEs don't have principal_amount
    )
"""
