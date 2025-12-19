"""Share classes and economic rights models.

This module defines the economic and voting rights attached to different classes
of shares in a cap table. Preferred stock, common stock, and derivative securities
have different rights that affect distributions in exit scenarios.
"""

from typing import Optional, Literal
from decimal import Decimal
from pydantic import Field, model_validator

from .base import (
    DomainModel,
    ShareClassId,
    RoundId,
    Multiple,
    Percentage,
    MoneyAmount,
    ShareCount,
)


# =============================================================================
# Liquidation Preference
# =============================================================================

class LiquidationPreference(DomainModel):
    """Liquidation preference defines how proceeds are distributed in an exit.

    In a liquidation event (acquisition, IPO, or dissolution), shareholders with
    liquidation preferences get paid before others. The multiple determines how much
    they receive relative to their investment.

    Example:
        2x liquidation preference means investor gets 2x their investment
        before common shareholders get anything.

    Seniority:
        - Rank 0 = highest priority (gets paid first)
        - Higher ranks get paid after lower ranks
        - Pari passu groups share proceeds equally at the same rank
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
        """Validate pari passu configuration.

        Note: Full validation of pari passu groups happens at cap table level,
        where we can verify all classes in a group have matching seniority ranks.
        """
        return self


# =============================================================================
# Participation Rights
# =============================================================================

class ParticipationRights(DomainModel):
    """Participation rights define if/how a share class participates in proceeds
    after receiving liquidation preference.

    Types:
        - Non-participating: Gets liquidation pref OR pro-rata, whichever is greater.
          This is the "better of" choice - investor chooses optimal path.

        - Participating: Gets liquidation pref AND pro-rata.
          Also called "double dipping" - investor gets preference then shares in remaining proceeds.

        - Capped participating: Gets liquidation pref AND pro-rata, up to a total cap.
          E.g., "1x pref with 3x cap" means investor gets 1x + pro-rata up to 3x total.

    Example:
        Series A invests $5M for 25% of company.
        Company exits for $100M.

        Non-participating:
            - Liquidation pref: $5M
            - Pro-rata: $25M
            - Takes $25M (better of the two)

        Participating:
            - Liquidation pref: $5M
            - Pro-rata of remaining $95M: 0.25 * $95M = $23.75M
            - Total: $28.75M

        Capped participating (3x cap):
            - Same as participating but capped at 3 * $5M = $15M
    """

    participation_type: Literal["non_participating", "participating", "capped_participating"]

    cap_multiple: Optional[Multiple] = Field(
        default=None,
        description="Cap as multiple of investment. E.g., 3.0 = 3x total return cap."
    )

    @model_validator(mode='after')
    def validate_cap_multiple(self):
        """Validate that cap_multiple is set correctly for participation type."""
        if self.participation_type == "capped_participating":
            if self.cap_multiple is None:
                raise ValueError("capped_participating requires cap_multiple")
            if self.cap_multiple <= Decimal("1.0"):
                raise ValueError("cap_multiple must be > 1.0 (cap must exceed liquidation pref)")
        elif self.cap_multiple is not None:
            raise ValueError(
                f"cap_multiple only valid for capped_participating, not {self.participation_type}"
            )
        return self


# =============================================================================
# Conversion Rights
# =============================================================================

class ConversionRights(DomainModel):
    """Conversion rights allow converting from one share class to another.

    Common use case: Preferred stock converts to common stock at IPO or at
    holder's option if common is more valuable than the liquidation preference.

    Conversion ratio mechanics:
        - initial_conversion_ratio: Set at issuance (usually 1:1)
        - current_conversion_ratio: Adjusted for anti-dilution, stock splits, etc.

    Example:
        Series A Preferred with 1:1 conversion ratio.
        After a down round with weighted average anti-dilution,
        ratio might adjust to 1:1.2 (1 preferred → 1.2 common).
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


# =============================================================================
# Anti-Dilution Protection
# =============================================================================

class AntiDilutionProtection(DomainModel):
    """Anti-dilution protection adjusts conversion price/ratio in down rounds.

    When a company raises money at a lower valuation than previous rounds,
    early investors with anti-dilution protection get compensated by adjusting
    their conversion ratio to receive more shares.

    Types:
        - None: No protection

        - Weighted average (broad-based): Most common and founder-friendly.
          Includes all outstanding shares (common + preferred + options) in calculation.
          Results in smaller adjustment.

        - Weighted average (narrow-based): Less common and less founder-friendly.
          Only includes common + preferred in calculation (excludes options).
          Results in larger adjustment.

        - Full ratchet: Most investor-friendly (harsh on founders).
          Conversion price drops to the down round price, regardless of amount raised.
          Can cause massive dilution to founders.

    Example:
        Series A invests at $2/share.
        Series B invests at $1/share (down round).

        Weighted average: Series A conversion ratio adjusts from 1:1 to ~1:1.4
        Full ratchet: Series A conversion ratio adjusts from 1:1 to 1:2

    Note: Carve-outs (excluding certain shares from calculation) are not modeled
    in MVP but can be added in Phase 2 if needed.
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


# =============================================================================
# Share Class
# =============================================================================

class ShareClass(DomainModel):
    """A class of shares with specific economic and voting rights.

    Share classes define the "type" of shares that can be held. Each share class
    has economic rights (liquidation preference, participation, conversion, etc.)
    and voting rights.

    Examples:
        - Common Stock: Standard equity, no preference, 1 vote per share
        - Series A Preferred: 1x liquidation preference, converts to common, 1 vote per share
        - Series B Preferred: 1x liquidation preference senior to A, participating, converts to common
        - Founder Preferred: 10x voting rights (supervoting), otherwise same as common

    Key distinction:
        Rounds ≠ Share Classes
        - A round (e.g., "Series A") may create one or more share classes
        - Multiple rounds can invest in the same share class
        - Share classes outlive rounds (they persist until converted/retired)

    Economic rights hierarchy:
        1. Liquidation preference (with seniority)
        2. Participation rights (if any)
        3. Conversion rights (if any)
        4. Anti-dilution protection (if any)
        5. Dividend rights (if any)
    """

    id: ShareClassId
    name: str = Field(description="Human-readable name (e.g., 'Series A Preferred Stock')")

    share_type: Literal["common", "preferred", "option", "warrant"] = Field(
        description="Fundamental share type category"
    )

    # Economic rights (most apply to preferred stock)
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
        description="Right to convert to another share class (typically preferred → common)"
    )

    anti_dilution_protection: Optional[AntiDilutionProtection] = Field(
        default=None,
        description="Protection against dilution in down rounds"
    )

    # Pro rata rights
    has_pro_rata_rights: bool = Field(
        default=False,
        description="Whether holders of this class have pro rata rights to invest "
                    "in future rounds to maintain ownership percentage. "
                    "Typically True for preferred stock, False for common/options."
    )

    # Note: Dividend rights removed for MVP (rare for VC-backed startups)
    # Note: Voting rights removed (not needed for returns modeling)

    # Metadata
    created_in_round_id: Optional[RoundId] = Field(
        default=None,
        description="Round that created this share class (if applicable)"
    )

    @model_validator(mode='after')
    def validate_economic_rights(self):
        """Validate that economic rights make sense for share type.

        Common stock: Usually no liquidation preference (some edge cases exist)
        Preferred stock: Must have liquidation preference
        Options/Warrants: No liquidation preference (they convert to underlying shares)
        """
        if self.share_type == "common":
            # Common with liquidation preference is unusual but allowed
            # (Some companies have "participating common" in specific scenarios)
            pass

        if self.share_type == "preferred":
            if self.liquidation_preference is None:
                raise ValueError("Preferred stock must have liquidation_preference")

        if self.share_type in ("option", "warrant"):
            # Options and warrants are not distributed in waterfall
            # They must be exercised/converted first
            if self.liquidation_preference is not None:
                raise ValueError(f"{self.share_type} cannot have liquidation_preference")

        return self
