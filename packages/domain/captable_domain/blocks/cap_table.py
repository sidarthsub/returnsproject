"""Cap table computation block.

Converts CapTableSnapshot into DataFrames for Excel rendering or analysis.

Output DataFrames:
- cap_table_ownership: Per-holder ownership breakdown with fully diluted percentages
- cap_table_by_class: Ownership aggregated by share class
- cap_table_summary: High-level metrics (total shares, valuation, etc.)
"""

from typing import List
from decimal import Decimal
import pandas as pd

from .base import Block, BlockContext
from ..schemas import CapTableSnapshot


class CapTableBlock(Block):
    """Converts CapTableSnapshot to ownership DataFrames.

    Inputs (from context):
        - cap_table_snapshot: CapTableSnapshot to convert

    Outputs (to context):
        - cap_table_ownership: DataFrame with columns:
            * holder_id: Holder identifier
            * holder_name: Human-readable name (same as holder_id for now)
            * share_class_id: Share class identifier
            * share_class_name: Share class name
            * shares: Number of shares owned
            * ownership_pct: Fully diluted ownership percentage
            * liquidation_preference: Total liquidation preference amount (if applicable)
            * votes: Total voting power
            * voting_pct: Voting percentage

        - cap_table_by_class: DataFrame with columns:
            * share_class_id: Share class identifier
            * share_class_name: Share class name
            * shares: Total shares in class
            * ownership_pct: Percentage of fully diluted shares
            * holders_count: Number of holders in class

        - cap_table_summary: DataFrame with single row:
            * total_shares: Total fully diluted shares
            * total_holders: Total number of unique holders
            * total_share_classes: Number of share classes
            * common_shares: Total common shares
            * preferred_shares: Total preferred shares
            * option_pool_shares: Total option pool shares

    Example:
        snapshot = cap_table.get_snapshot()
        context = BlockContext()
        context.set("cap_table_snapshot", snapshot)

        block = CapTableBlock()
        block.execute(context)

        ownership_df = context.get("cap_table_ownership")
        summary_df = context.get("cap_table_summary")
    """

    def __init__(self, snapshot_key: str = "cap_table_snapshot"):
        """Initialize CapTableBlock.

        Args:
            snapshot_key: Context key for CapTableSnapshot input (default: "cap_table_snapshot")
        """
        self.snapshot_key = snapshot_key

    def inputs(self) -> List[str]:
        return [self.snapshot_key]

    def outputs(self) -> List[str]:
        return [
            "cap_table_ownership",
            "cap_table_by_class",
            "cap_table_summary",
        ]

    def execute(self, context: BlockContext) -> None:
        """Execute cap table computation.

        Args:
            context: BlockContext with cap_table_snapshot
        """
        snapshot: CapTableSnapshot = context.get(self.snapshot_key)

        # Compute ownership DataFrame
        ownership_df = self._compute_ownership(snapshot)
        context.set("cap_table_ownership", ownership_df)

        # Compute by-class aggregation
        by_class_df = self._compute_by_class(ownership_df, snapshot)
        context.set("cap_table_by_class", by_class_df)

        # Compute summary metrics
        summary_df = self._compute_summary(snapshot, ownership_df)
        context.set("cap_table_summary", summary_df)

    def _compute_ownership(self, snapshot: CapTableSnapshot) -> pd.DataFrame:
        """Compute per-holder ownership breakdown.

        Args:
            snapshot: CapTableSnapshot to analyze

        Returns:
            DataFrame with ownership details per holder/class combination
        """
        rows = []

        # Total fully diluted shares for percentage calculations
        total_shares = snapshot.fully_diluted_shares

        for position in snapshot.positions:
            # Get share class details
            share_class = snapshot.share_classes.get(position.share_class_id)
            if not share_class:
                # Skip positions with unknown share class (shouldn't happen with valid data)
                continue

            # Calculate ownership percentage
            ownership_pct = (
                float(position.shares / total_shares * 100)
                if total_shares > 0
                else 0.0
            )

            # Calculate liquidation preference
            liquidation_pref = None
            if share_class.liquidation_preference:
                # For preferred: shares * price_per_share * liquidation_multiple
                # But we don't have price_per_share in snapshot yet (MVP)
                # So just store the multiple for now
                liquidation_pref = share_class.liquidation_preference.multiple

            # Calculate voting power
            votes = position.shares * share_class.votes_per_share
            voting_pct = (
                float(votes / snapshot.total_voting_shares * 100)
                if snapshot.total_voting_shares > 0
                else 0.0
            )

            rows.append({
                "holder_id": position.holder_id,
                "holder_name": position.holder_id,  # TODO: Add holder names to schema in future
                "share_class_id": position.share_class_id,
                "share_class_name": share_class.name,
                "shares": float(position.shares),
                "ownership_pct": ownership_pct,
                "liquidation_preference_multiple": float(liquidation_pref) if liquidation_pref else None,
                "votes": float(votes),
                "voting_pct": voting_pct,
            })

        df = pd.DataFrame(rows)

        # Sort by ownership descending
        if not df.empty:
            df = df.sort_values("ownership_pct", ascending=False)

        return df

    def _compute_by_class(
        self, ownership_df: pd.DataFrame, snapshot: CapTableSnapshot
    ) -> pd.DataFrame:
        """Compute ownership aggregated by share class.

        Args:
            ownership_df: Per-holder ownership DataFrame
            snapshot: CapTableSnapshot for metadata

        Returns:
            DataFrame with ownership by share class
        """
        if ownership_df.empty:
            return pd.DataFrame(columns=[
                "share_class_id",
                "share_class_name",
                "shares",
                "ownership_pct",
                "holders_count",
            ])

        # Aggregate by share class
        by_class = ownership_df.groupby(["share_class_id", "share_class_name"]).agg({
            "shares": "sum",
            "ownership_pct": "sum",
            "holder_id": "nunique",  # Count unique holders
        }).reset_index()

        by_class = by_class.rename(columns={"holder_id": "holders_count"})

        # Sort by ownership descending
        by_class = by_class.sort_values("ownership_pct", ascending=False)

        return by_class

    def _compute_summary(
        self, snapshot: CapTableSnapshot, ownership_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Compute summary metrics for cap table.

        Args:
            snapshot: CapTableSnapshot to summarize
            ownership_df: Per-holder ownership DataFrame

        Returns:
            DataFrame with single row of summary metrics
        """
        # Count shares by type
        common_shares = Decimal("0")
        preferred_shares = Decimal("0")
        option_pool_shares = Decimal("0")

        for position in snapshot.positions:
            share_class = snapshot.share_classes.get(position.share_class_id)
            if not share_class:
                continue

            if share_class.share_type == "common":
                if "option" in position.holder_id.lower() or "pool" in position.holder_id.lower():
                    option_pool_shares += position.shares
                else:
                    common_shares += position.shares
            elif share_class.share_type == "preferred":
                preferred_shares += position.shares

        summary = pd.DataFrame([{
            "total_shares": float(snapshot.fully_diluted_shares),
            "total_holders": ownership_df["holder_id"].nunique() if not ownership_df.empty else 0,
            "total_share_classes": len(snapshot.share_classes),
            "common_shares": float(common_shares),
            "preferred_shares": float(preferred_shares),
            "option_pool_shares": float(option_pool_shares),
        }])

        return summary
