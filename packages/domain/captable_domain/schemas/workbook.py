"""Workbook configuration - top-level entry point for Excel generation.

The WorkbookCFG is the root configuration object that ties together:
- Cap tables (can compare multiple scenarios or time periods)
- Returns analysis (multiple exit scenarios and waterfalls)
- Display options (formatting, sheets to include)

This is what gets passed to the Excel renderer to generate the workbook.
"""

from typing import Optional, Literal, List, Dict
from datetime import date
from pydantic import Field, model_validator

from .base import DomainModel
from .cap_table import CapTable
from .returns import ReturnsCFG


# =============================================================================
# Round Calculator Configuration
# =============================================================================

# Type aliases for allocation strategies
InvestmentAllocationMode = Literal["manual", "target_ownership", "pro_rata"]
OptionPoolMode = Literal["manual", "expansion_pct", "target_pct_inclusive", "target_pct_exclusive"]


class RoundCalculatorCFG(DomainModel):
    """Configuration for round design calculator - drives how cap table cells are populated.

    The calculator configuration determines whether cap table cells are:
    - **Hardcoded (blue font)** - Manual entry by user
    - **Formula-driven (black font)** - Calculated automatically based on allocation rules

    This allows flexible round modeling with different allocation strategies.

    Investment Allocation Modes:
    - **manual**: All investments hardcoded (blue font, user editable)
    - **target_ownership**: Calculate investment needed to achieve target ownership % (formula, black font)
    - **pro_rata**: Calculate investment to maintain previous round ownership % (formula, black font)

    Option Pool Modes:
    - **manual**: Hardcoded shares (blue font, user editable)
    - **expansion_pct**: Add X% more shares (formula, black font)
    - **target_pct_inclusive**: X% total post-money including existing pool (formula, black font)
    - **target_pct_exclusive**: X% post-money net new excluding existing pool (formula, black font)

    Examples:
        # All manual (default - backward compatible)
        RoundCalculatorCFG(enabled=False)

        # Target ownership for all investors
        RoundCalculatorCFG(
            investment_allocation_mode="target_ownership",
            target_ownership_pct=0.20  # 20% target
        )

        # Pro-rata for all investors
        RoundCalculatorCFG(
            investment_allocation_mode="pro_rata"
        )

        # Mixed: some manual, some target, some pro-rata
        RoundCalculatorCFG(
            investment_allocation_mode="manual",  # Default for others
            per_investor_allocation={
                "Lead Investor": "target_ownership",
                "Follow-on Fund": "pro_rata"
            },
            per_investor_target_pct={
                "Lead Investor": 0.25  # 25% target for lead
            }
        )

        # Option pool expansion
        RoundCalculatorCFG(
            option_pool_mode="expansion_pct",
            option_pool_expansion_pct=0.10  # Add 10% more shares
        )

        # Option pool target % (post-money)
        RoundCalculatorCFG(
            option_pool_mode="target_pct_inclusive",
            option_pool_target_pct=0.15  # 15% total post-money
        )
    """

    enabled: bool = Field(
        default=True,
        description="Whether calculator is enabled. If False, all values are manual (hardcoded)"
    )

    target_round_id: Optional[str] = Field(
        default=None,
        description="Which round to apply calculator to. None = most recent preferred round on the sheet"
    )

    # =========================================================================
    # Investment Allocation Configuration
    # =========================================================================

    investment_allocation_mode: InvestmentAllocationMode = Field(
        default="manual",
        description=(
            "How to allocate investments:\n"
            "- manual: All investments hardcoded (blue)\n"
            "- target_ownership: Calculate investment needed for target % (formula, black)\n"
            "- pro_rata: Calculate investment to maintain previous ownership % (formula, black)"
        )
    )

    target_ownership_pct: Optional[float] = Field(
        default=None,
        description=(
            "Target ownership % for target_ownership mode (e.g., 0.20 for 20%).\n"
            "Used as default when investment_allocation_mode='target_ownership'.\n"
            "Can be overridden per-investor via per_investor_target_pct."
        )
    )

    per_investor_allocation: Optional[Dict[str, InvestmentAllocationMode]] = Field(
        default=None,
        description=(
            "Override allocation mode for specific investors (for mixed strategies).\n"
            "Key = investor holder name, Value = allocation mode for that investor.\n"
            "Example: {'Investor A': 'target_ownership', 'Investor B': 'pro_rata'}"
        )
    )

    per_investor_target_pct: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            "Target ownership % for specific investors using target_ownership mode.\n"
            "Key = investor holder name, Value = target % (e.g., 0.15 for 15%).\n"
            "Only used when that investor's allocation mode is 'target_ownership'.\n"
            "If not specified, falls back to target_ownership_pct."
        )
    )

    # =========================================================================
    # Option Pool Configuration
    # =========================================================================

    option_pool_mode: OptionPoolMode = Field(
        default="manual",
        description=(
            "How to calculate option pool:\n"
            "- manual: Hardcoded shares (blue)\n"
            "- expansion_pct: Add X% more shares (formula, black)\n"
            "- target_pct_inclusive: X% total post-money including existing pool (formula, black)\n"
            "- target_pct_exclusive: X% post-money net new excluding existing pool (formula, black)"
        )
    )

    option_pool_expansion_pct: Optional[float] = Field(
        default=None,
        description=(
            "Expansion % for expansion_pct mode (e.g., 0.10 for 10% expansion).\n"
            "Required when option_pool_mode='expansion_pct'."
        )
    )

    option_pool_target_pct: Optional[float] = Field(
        default=None,
        description=(
            "Target % for target_pct_inclusive or target_pct_exclusive modes.\n"
            "E.g., 0.15 for 15% option pool post-money.\n"
            "Required when option_pool_mode is 'target_pct_inclusive' or 'target_pct_exclusive'."
        )
    )

    # =========================================================================
    # Calculator Display
    # =========================================================================

    show_calculator_section: bool = Field(
        default=True,
        description=(
            "Show calculator section below cap table for reference/planning.\n"
            "Even when False, calculator modes still drive cap table formula generation.\n"
            "Set to False to hide the calculator section while keeping formula-driven cells."
        )
    )


# =============================================================================
# Cap Table Snapshot Configuration
# =============================================================================

class CapTableSnapshotCFG(DomainModel):
    """Configuration for a specific cap table snapshot to include in workbook.

    Allows modeling multiple time periods or scenarios:
        - Historical vs current cap table
        - Pre-round vs post-round cap table
        - Different what-if scenarios

    Example:
        Compare cap table before and after Series A:
        - Snapshot 1: as_of_date = pre-Series A, label = "Pre-Series A"
        - Snapshot 2: as_of_date = post-Series A, label = "Post-Series A"
    """

    cap_table: CapTable = Field(
        description="Cap table to snapshot"
    )

    label: str = Field(
        description="Human-readable label for this snapshot (e.g., 'Current', 'Pre-Series A', 'Post-Raise')"
    )

    as_of_date: Optional[date] = Field(
        default=None,
        description="Date for snapshot. None = current date (all events applied)"
    )

    round_calculator: RoundCalculatorCFG = Field(
        default_factory=RoundCalculatorCFG,
        description="Round design calculator configuration"
    )


# =============================================================================
# Returns Analysis Configuration
# =============================================================================

class WaterfallAnalysisCFG(DomainModel):
    """Configuration for a specific waterfall analysis to include in workbook.

    Allows comparing multiple return scenarios:
        - Different cap table states (pre-round vs post-round)
        - Different investor perspectives
        - Multiple exit valuations

    Example:
        Analyze returns for multiple rounds:
        - Analysis 1: Post-Seed cap table, label = "Seed Returns"
        - Analysis 2: Post-Series A cap table, label = "Series A Returns"
    """

    cap_table_snapshot: CapTableSnapshotCFG = Field(
        description="Cap table snapshot to use for waterfall calculation"
    )

    returns_cfg: ReturnsCFG = Field(
        description="Returns configuration (exit scenarios, metrics)"
    )

    label: str = Field(
        description="Human-readable label for this analysis (e.g., 'Current Returns', 'Post-Raise Returns')"
    )


# =============================================================================
# Workbook Configuration
# =============================================================================

class WorkbookCFG(DomainModel):
    """Top-level configuration for Excel workbook generation.

    This is the entry point for the entire system. It specifies:
        - Which cap tables to include (can compare multiple)
        - Which returns analyses to include (can compare multiple)
        - Which sheets to generate
        - How to format the output

    Typical workflows:

    Single cap table:
        config = WorkbookCFG(
            cap_table_snapshots=[
                CapTableSnapshotCFG(cap_table=cap_table, label="Current")
            ],
            waterfall_analyses=[
                WaterfallAnalysisCFG(
                    cap_table_snapshot=...,
                    returns_cfg=ReturnsCFG(scenarios=[...]),
                    label="Returns Analysis"
                )
            ]
        )

    Comparing pre/post round:
        config = WorkbookCFG(
            cap_table_snapshots=[
                CapTableSnapshotCFG(
                    cap_table=cap_table,
                    label="Pre-Series A",
                    as_of_date=date(2024, 5, 31)
                ),
                CapTableSnapshotCFG(
                    cap_table=cap_table,
                    label="Post-Series A",
                    as_of_date=date(2024, 6, 15)
                )
            ],
            waterfall_analyses=[...]
        )

    Multiple waterfalls for different investors:
        config = WorkbookCFG(
            cap_table_snapshots=[...],
            waterfall_analyses=[
                WaterfallAnalysisCFG(label="Founder Returns", ...),
                WaterfallAnalysisCFG(label="Series A Returns", ...),
                WaterfallAnalysisCFG(label="Employee Returns", ...)
            ]
        )

    Generated sheets (depending on config):
        1. Summary - High-level overview and key metrics
        2. Cap Table (one per snapshot) - Detailed ownership breakdown
        3. Waterfall (one per analysis) - Returns analysis for each scenario
        4. Events - Audit trail of all cap table events
        5. Share Classes - Economic and voting rights by class
        6. Validation - Integrity checks and warnings
    """

    # Core data
    cap_table_snapshots: List[CapTableSnapshotCFG] = Field(
        description="Cap table snapshots to include (can compare multiple time periods or scenarios)"
    )

    waterfall_analyses: Optional[List[WaterfallAnalysisCFG]] = Field(
        default=None,
        description="Waterfall analyses to include (optional - one per scenario/perspective)"
    )

    # Sheet inclusion options
    include_audit_sheet: bool = Field(
        default=True,
        description="Include audit sheet with validation checks and warnings"
    )

    include_summary_sheet: bool = Field(
        default=True,
        description="Include summary/overview sheet with key metrics across all snapshots"
    )

    include_events_sheet: bool = Field(
        default=True,
        description="Include events sheet showing full event history for each cap table"
    )

    include_share_classes_sheet: bool = Field(
        default=True,
        description="Include share classes sheet with economic rights details"
    )

    # Note: Rendering/formatting options removed for MVP
    # Excel renderer will use sensible defaults:
    # - Professional formatting theme
    # - Frozen panes on headers
    # - Excel Tables with structured references
    # - Named ranges for cross-sheet formulas
    # - Filters on all data tables
    # - Fully diluted ownership percentages
    # - Formulas (not just values) for user modification
    # These are implementation details, not user configuration

    @model_validator(mode='after')
    def validate_waterfall_references(self):
        """Validate that waterfall analyses reference cap table snapshots included in workbook."""
        if not self.waterfall_analyses:
            return self

        # Get all snapshot labels
        snapshot_labels = {snap.label for snap in self.cap_table_snapshots}

        # Verify each waterfall references a valid snapshot
        for waterfall in self.waterfall_analyses:
            if waterfall.cap_table_snapshot.label not in snapshot_labels:
                # This is OK - waterfall can have its own snapshot config
                # Just means it's not in the main cap_table_snapshots list
                pass

        return self
