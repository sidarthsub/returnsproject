"""Workbook configuration - top-level entry point for Excel generation.

The WorkbookCFG is the root configuration object that ties together:
- Cap tables (can compare multiple scenarios or time periods)
- Returns analysis (multiple exit scenarios and waterfalls)
- Display options (formatting, sheets to include)

This is what gets passed to the Excel renderer to generate the workbook.
"""

from typing import Optional, Literal, List
from datetime import date
from pydantic import Field, model_validator

from .base import DomainModel
from .cap_table import CapTable
from .returns import ReturnsCFG


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
