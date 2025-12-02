"""Waterfall computation block.

Computes liquidation preference waterfall for exit scenarios.

The waterfall implements the distribution of exit proceeds according to:
1. Liquidation preferences (by seniority)
2. Participation rights (if applicable)
3. Remaining proceeds to common on as-converted basis
"""

from typing import List, Dict
from decimal import Decimal
import pandas as pd

from .base import Block, BlockContext
from ..schemas import CapTableSnapshot, ExitScenario, ShareClass


class WaterfallBlock(Block):
    """Computes liquidation preference waterfall for an exit scenario.

    Inputs (from context):
        - cap_table_snapshot: CapTableSnapshot with ownership positions
        - exit_scenario: ExitScenario with exit value and parameters

    Outputs (to context):
        - waterfall_steps: DataFrame showing each step of waterfall distribution:
            * step: Step number (1, 2, 3, ...)
            * step_name: Description of step ("Liquidation Preference - Series A", "Participation", etc.)
            * share_class_id: Share class receiving distribution in this step
            * amount_available: Total amount available for distribution in this step
            * amount_distributed: Amount actually distributed in this step
            * amount_remaining: Amount remaining after this step

        - waterfall_by_holder: DataFrame showing final distribution by holder:
            * holder_id: Holder identifier
            * share_class_id: Share class
            * shares: Number of shares
            * ownership_pct: Ownership percentage
            * liquidation_preference_amount: Amount from liquidation preference
            * participation_amount: Amount from participation
            * common_distribution_amount: Amount from common distribution
            * total_distribution: Total amount received
            * distribution_pct: Percentage of total exit proceeds

        - waterfall_by_class: DataFrame showing distribution by share class:
            * share_class_id: Share class identifier
            * share_class_name: Share class name
            * total_distribution: Total distributed to class
            * distribution_pct: Percentage of total exit proceeds

    Example:
        snapshot = cap_table.get_snapshot()
        scenario = ExitScenario(exit_value=50_000_000, exit_type="M&A", ...)

        context = BlockContext()
        context.set("cap_table_snapshot", snapshot)
        context.set("exit_scenario", scenario)

        block = WaterfallBlock()
        block.execute(context)

        waterfall_df = context.get("waterfall_steps")
        by_holder_df = context.get("waterfall_by_holder")
    """

    def __init__(
        self,
        snapshot_key: str = "cap_table_snapshot",
        scenario_key: str = "exit_scenario",
    ):
        """Initialize WaterfallBlock.

        Args:
            snapshot_key: Context key for CapTableSnapshot input
            scenario_key: Context key for ExitScenario input
        """
        self.snapshot_key = snapshot_key
        self.scenario_key = scenario_key

    def inputs(self) -> List[str]:
        return [self.snapshot_key, self.scenario_key]

    def outputs(self) -> List[str]:
        return [
            "waterfall_steps",
            "waterfall_by_holder",
            "waterfall_by_class",
        ]

    def execute(self, context: BlockContext) -> None:
        """Execute waterfall computation.

        Args:
            context: BlockContext with snapshot and scenario
        """
        snapshot: CapTableSnapshot = context.get(self.snapshot_key)
        scenario: ExitScenario = context.get(self.scenario_key)

        # Calculate net proceeds after transaction costs
        net_proceeds = scenario.calculate_net_proceeds()

        # Initialize distribution tracking
        distributions: Dict[str, Dict[str, Decimal]] = {}  # holder_id -> {step_name -> amount}
        for position in snapshot.positions:
            distributions[position.holder_id] = {}

        # Track waterfall steps
        waterfall_steps = []
        remaining_proceeds = net_proceeds
        step_number = 1

        # Step 1: Pay liquidation preferences by seniority
        remaining_proceeds, step_number = self._distribute_liquidation_preferences(
            snapshot, remaining_proceeds, distributions, waterfall_steps, step_number
        )

        # Step 2: Participation (if applicable)
        remaining_proceeds, step_number = self._distribute_participation(
            snapshot, remaining_proceeds, distributions, waterfall_steps, step_number
        )

        # Step 3: Remaining proceeds to common (as-converted)
        remaining_proceeds, step_number = self._distribute_to_common(
            snapshot, remaining_proceeds, distributions, waterfall_steps, step_number
        )

        # Convert to DataFrames
        steps_df = pd.DataFrame(waterfall_steps)
        by_holder_df = self._compute_by_holder(snapshot, distributions, scenario)
        by_class_df = self._compute_by_class(by_holder_df)

        context.set("waterfall_steps", steps_df)
        context.set("waterfall_by_holder", by_holder_df)
        context.set("waterfall_by_class", by_class_df)

    def _distribute_liquidation_preferences(
        self,
        snapshot: CapTableSnapshot,
        remaining: Decimal,
        distributions: Dict[str, Dict[str, Decimal]],
        steps: List[Dict],
        step_number: int,
    ) -> tuple[Decimal, int]:
        """Distribute liquidation preferences by seniority.

        Args:
            snapshot: CapTableSnapshot
            remaining: Remaining proceeds to distribute
            distributions: Distribution tracking dict (mutated)
            steps: Waterfall steps list (mutated)
            step_number: Current step number

        Returns:
            (remaining_proceeds, next_step_number)
        """
        # Group positions by seniority rank
        by_seniority: Dict[int, List] = {}
        for position in snapshot.positions:
            share_class = snapshot.share_classes.get(position.share_class_id)
            if not share_class or not share_class.liquidation_preference:
                continue

            rank = share_class.liquidation_preference.seniority_rank
            if rank not in by_seniority:
                by_seniority[rank] = []
            by_seniority[rank].append((position, share_class))

        # Distribute by seniority (lowest rank = highest priority)
        for rank in sorted(by_seniority.keys()):
            positions_at_rank = by_seniority[rank]

            # Calculate total liquidation preference at this rank
            total_liq_pref = Decimal("0")
            for position, share_class in positions_at_rank:
                # liq_pref = shares * original_price * multiple
                # For MVP: we don't have original_price, so just use multiple as placeholder
                # In production, would track investment_amount or price_per_share
                liq_pref_multiple = share_class.liquidation_preference.multiple
                total_liq_pref += position.shares * liq_pref_multiple

            # Distribute available proceeds pro-rata at this seniority level
            amount_to_distribute = min(remaining, total_liq_pref)

            for position, share_class in positions_at_rank:
                liq_pref_multiple = share_class.liquidation_preference.multiple
                position_liq_pref = position.shares * liq_pref_multiple

                # Pro-rata share of distribution
                if total_liq_pref > 0:
                    position_distribution = amount_to_distribute * (position_liq_pref / total_liq_pref)
                else:
                    position_distribution = Decimal("0")

                step_name = f"liquidation_preference_{share_class.id}"
                distributions[position.holder_id][step_name] = position_distribution

            # Record step
            share_class_name = positions_at_rank[0][1].name if positions_at_rank else "Unknown"
            steps.append({
                "step": step_number,
                "step_name": f"Liquidation Preference - {share_class_name} (Rank {rank})",
                "share_class_id": positions_at_rank[0][1].id if positions_at_rank else None,
                "amount_available": float(remaining),
                "amount_distributed": float(amount_to_distribute),
                "amount_remaining": float(remaining - amount_to_distribute),
            })

            remaining -= amount_to_distribute
            step_number += 1

            if remaining <= 0:
                break

        return remaining, step_number

    def _distribute_participation(
        self,
        snapshot: CapTableSnapshot,
        remaining: Decimal,
        distributions: Dict[str, Dict[str, Decimal]],
        steps: List[Dict],
        step_number: int,
    ) -> tuple[Decimal, int]:
        """Distribute participation rights (participating preferred).

        Args:
            snapshot: CapTableSnapshot
            remaining: Remaining proceeds
            distributions: Distribution tracking dict (mutated)
            steps: Waterfall steps list (mutated)
            step_number: Current step number

        Returns:
            (remaining_proceeds, next_step_number)
        """
        # For MVP: simplified participation
        # Full participation: preferred shares participate pro-rata with common
        # This would require tracking as-converted shares and participation caps

        # Placeholder for future implementation
        # In production: distribute to participating preferred pro-rata with common
        # up to participation cap (if any)

        return remaining, step_number

    def _distribute_to_common(
        self,
        snapshot: CapTableSnapshot,
        remaining: Decimal,
        distributions: Dict[str, Dict[str, Decimal]],
        steps: List[Dict],
        step_number: int,
    ) -> tuple[Decimal, int]:
        """Distribute remaining proceeds to common (as-converted).

        Args:
            snapshot: CapTableSnapshot
            remaining: Remaining proceeds
            distributions: Distribution tracking dict (mutated)
            steps: Waterfall steps list (mutated)
            step_number: Current step number

        Returns:
            (remaining_proceeds, next_step_number)
        """
        if remaining <= 0:
            return remaining, step_number

        # All shares convert to common and participate pro-rata
        total_as_converted_shares = snapshot.fully_diluted_shares

        if total_as_converted_shares > 0:
            for position in snapshot.positions:
                # For MVP: assume 1:1 conversion ratio
                # In production: use ConversionRights.current_conversion_ratio
                as_converted_shares = position.shares

                position_distribution = remaining * (as_converted_shares / total_as_converted_shares)
                distributions[position.holder_id]["common_distribution"] = position_distribution

        # Record step
        steps.append({
            "step": step_number,
            "step_name": "Distribution to Common (As-Converted)",
            "share_class_id": "common",
            "amount_available": float(remaining),
            "amount_distributed": float(remaining),
            "amount_remaining": 0.0,
        })

        return Decimal("0"), step_number + 1

    def _compute_by_holder(
        self,
        snapshot: CapTableSnapshot,
        distributions: Dict[str, Dict[str, Decimal]],
        scenario: ExitScenario,
    ) -> pd.DataFrame:
        """Compute final distribution by holder.

        Args:
            snapshot: CapTableSnapshot
            distributions: Distribution tracking dict
            scenario: ExitScenario for percentage calculations

        Returns:
            DataFrame with distribution by holder
        """
        rows = []
        net_proceeds = scenario.calculate_net_proceeds()

        for position in snapshot.positions:
            holder_distributions = distributions.get(position.holder_id, {})

            # Sum up distributions by category
            liq_pref_amount = sum(
                amount for key, amount in holder_distributions.items()
                if key.startswith("liquidation_preference_")
            )
            participation_amount = holder_distributions.get("participation", Decimal("0"))
            common_amount = holder_distributions.get("common_distribution", Decimal("0"))

            total_distribution = liq_pref_amount + participation_amount + common_amount

            ownership_pct = (
                float(position.shares / snapshot.fully_diluted_shares * 100)
                if snapshot.fully_diluted_shares > 0
                else 0.0
            )

            distribution_pct = (
                float(total_distribution / net_proceeds * 100)
                if net_proceeds > 0
                else 0.0
            )

            rows.append({
                "holder_id": position.holder_id,
                "share_class_id": position.share_class_id,
                "shares": float(position.shares),
                "ownership_pct": ownership_pct,
                "liquidation_preference_amount": float(liq_pref_amount),
                "participation_amount": float(participation_amount),
                "common_distribution_amount": float(common_amount),
                "total_distribution": float(total_distribution),
                "distribution_pct": distribution_pct,
            })

        df = pd.DataFrame(rows)

        # Sort by total distribution descending
        if not df.empty:
            df = df.sort_values("total_distribution", ascending=False)

        return df

    def _compute_by_class(self, by_holder_df: pd.DataFrame) -> pd.DataFrame:
        """Compute distribution aggregated by share class.

        Args:
            by_holder_df: Distribution by holder DataFrame

        Returns:
            DataFrame with distribution by share class
        """
        if by_holder_df.empty:
            return pd.DataFrame(columns=[
                "share_class_id",
                "total_distribution",
                "distribution_pct",
            ])

        by_class = by_holder_df.groupby("share_class_id").agg({
            "total_distribution": "sum",
            "distribution_pct": "sum",
        }).reset_index()

        by_class = by_class.sort_values("total_distribution", ascending=False)

        return by_class
