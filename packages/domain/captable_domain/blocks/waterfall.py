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

        # For non-participating preferred, we need to determine optimal choice
        # Calculate what as-converted distribution would be
        as_converted_per_share = net_proceeds / snapshot.fully_diluted_shares if snapshot.fully_diluted_shares > 0 else Decimal("0")

        # Categorize positions by participation type
        participating_positions = []
        non_participating_positions = []
        common_positions = []

        for position in snapshot.positions:
            share_class = snapshot.share_classes.get(position.share_class_id)
            if not share_class:
                continue

            if share_class.participation_rights:
                if share_class.participation_rights.participation_type in ("participating", "capped_participating"):
                    participating_positions.append((position, share_class))
                elif share_class.participation_rights.participation_type == "non_participating":
                    # Determine optimal choice for non-participating
                    # Use cost_basis if available, otherwise shares * multiple
                    if share_class.liquidation_preference:
                        if position.cost_basis is not None:
                            liq_pref_amount = position.cost_basis * share_class.liquidation_preference.multiple
                        else:
                            liq_pref_amount = position.shares * share_class.liquidation_preference.multiple
                    else:
                        liq_pref_amount = Decimal("0")

                    as_converted_amount = position.shares * as_converted_per_share

                    if liq_pref_amount > as_converted_amount:
                        # Take liquidation preference
                        non_participating_positions.append((position, share_class, "preference"))
                    else:
                        # Convert to common
                        non_participating_positions.append((position, share_class, "convert"))
            elif share_class.liquidation_preference:
                # Has liquidation preference but no participation rights specified
                # Treat as non-participating
                if position.cost_basis is not None:
                    liq_pref_amount = position.cost_basis * share_class.liquidation_preference.multiple
                else:
                    liq_pref_amount = position.shares * share_class.liquidation_preference.multiple

                as_converted_amount = position.shares * as_converted_per_share

                if liq_pref_amount > as_converted_amount:
                    non_participating_positions.append((position, share_class, "preference"))
                else:
                    non_participating_positions.append((position, share_class, "convert"))
            else:
                # Common or other share classes
                common_positions.append((position, share_class))

        # Initialize distribution tracking
        distributions: Dict[str, Dict[str, Decimal]] = {}  # holder_id -> {step_name -> amount}
        for position in snapshot.positions:
            distributions[position.holder_id] = {}

        # Track waterfall steps
        waterfall_steps = []
        remaining_proceeds = net_proceeds
        step_number = 1

        # Step 1: Pay liquidation preferences by seniority (participating + non-participating taking preference)
        remaining_proceeds, step_number = self._distribute_liquidation_preferences(
            snapshot, remaining_proceeds, distributions, waterfall_steps, step_number,
            non_participating_positions
        )

        # Step 2: Participation (participating preferred only)
        remaining_proceeds, step_number = self._distribute_participation(
            snapshot, remaining_proceeds, distributions, waterfall_steps, step_number
        )

        # Step 3: Remaining proceeds to common (as-converted)
        # This includes: common shares + non-participating that chose to convert
        remaining_proceeds, step_number = self._distribute_to_common(
            snapshot, remaining_proceeds, distributions, waterfall_steps, step_number,
            non_participating_positions
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
        non_participating_positions: List,
    ) -> tuple[Decimal, int]:
        """Distribute liquidation preferences by seniority.

        Only distributes to:
        - Participating preferred (will also get participation later)
        - Capped participating preferred (will also get participation later)
        - Non-participating preferred that chose preference over conversion

        Args:
            snapshot: CapTableSnapshot
            remaining: Remaining proceeds to distribute
            distributions: Distribution tracking dict (mutated)
            steps: Waterfall steps list (mutated)
            step_number: Current step number
            non_participating_positions: List of (position, share_class, choice) tuples

        Returns:
            (remaining_proceeds, next_step_number)
        """
        # Build set of non-participating holders taking conversion (skip their liquidation preference)
        converting_holders = set()
        for position, share_class, choice in non_participating_positions:
            if choice == "convert":
                converting_holders.add((position.holder_id, position.share_class_id))

        # Group positions by seniority rank
        by_seniority: Dict[int, List] = {}
        for position in snapshot.positions:
            share_class = snapshot.share_classes.get(position.share_class_id)
            if not share_class or not share_class.liquidation_preference:
                continue

            # Skip if this is non-participating choosing to convert
            if (position.holder_id, position.share_class_id) in converting_holders:
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
                # liq_pref = cost_basis * multiple
                # Use cost_basis if available (actual investment), otherwise shares * multiple
                liq_pref_multiple = share_class.liquidation_preference.multiple
                if position.cost_basis is not None:
                    # Use actual investment amount * multiple
                    position_liq_pref = position.cost_basis * liq_pref_multiple
                else:
                    # Fallback for positions without cost_basis (founder shares, etc.)
                    position_liq_pref = position.shares * liq_pref_multiple
                total_liq_pref += position_liq_pref

            # Distribute available proceeds pro-rata at this seniority level
            amount_to_distribute = min(remaining, total_liq_pref)

            for position, share_class in positions_at_rank:
                liq_pref_multiple = share_class.liquidation_preference.multiple

                # Calculate this position's liquidation preference
                if position.cost_basis is not None:
                    position_liq_pref = position.cost_basis * liq_pref_multiple
                else:
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

        Handles three types of participation:
        1. participating: Double dip - gets liquidation preference AND pro-rata share
        2. capped_participating: Same as participating but capped at cap_multiple
        3. non_participating: Gets BETTER of liquidation preference OR as-converted

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

        # Identify participating preferred positions
        participating_positions = []
        for position in snapshot.positions:
            share_class = snapshot.share_classes.get(position.share_class_id)
            if not share_class:
                continue

            # Check if this class has participating rights
            if share_class.participation_rights and \
               share_class.participation_rights.participation_type in ("participating", "capped_participating"):
                participating_positions.append((position, share_class))

        if not participating_positions:
            return remaining, step_number

        # Calculate total as-converted shares (all shares participate)
        total_as_converted = snapshot.fully_diluted_shares

        # Distribute participation pro-rata with all shares
        amount_distributed_this_step = Decimal("0")

        for position, share_class in participating_positions:
            # Calculate pro-rata share based on as-converted shares
            # For MVP: assume 1:1 conversion ratio
            as_converted_shares = position.shares

            if total_as_converted > 0:
                pro_rata_share = remaining * (as_converted_shares / total_as_converted)

                # Check for cap (capped_participating only)
                if share_class.participation_rights.participation_type == "capped_participating":
                    cap_multiple = share_class.participation_rights.cap_multiple

                    # Calculate total already received from liquidation preference
                    liq_pref_received = sum(
                        amount for key, amount in distributions[position.holder_id].items()
                        if key.startswith("liquidation_preference_")
                    )

                    # Calculate original investment
                    # Use cost_basis if available, otherwise shares * multiple
                    if position.cost_basis is not None:
                        original_investment = position.cost_basis
                    else:
                        original_investment = position.shares * share_class.liquidation_preference.multiple if share_class.liquidation_preference else position.shares

                    # Calculate cap: cap_multiple * original_investment
                    cap_amount = cap_multiple * original_investment if cap_multiple else Decimal("0")

                    # Total can't exceed cap
                    max_additional = max(Decimal("0"), cap_amount - liq_pref_received)
                    participation_amount = min(pro_rata_share, max_additional)
                else:
                    # Unlimited participation
                    participation_amount = pro_rata_share

                distributions[position.holder_id]["participation"] = participation_amount
                amount_distributed_this_step += participation_amount

        # Record step
        if amount_distributed_this_step > 0:
            steps.append({
                "step": step_number,
                "step_name": "Participation Rights (Participating Preferred)",
                "share_class_id": None,  # Multiple classes may participate
                "amount_available": float(remaining),
                "amount_distributed": float(amount_distributed_this_step),
                "amount_remaining": float(remaining - amount_distributed_this_step),
            })

            remaining -= amount_distributed_this_step
            step_number += 1

        return remaining, step_number

    def _distribute_to_common(
        self,
        snapshot: CapTableSnapshot,
        remaining: Decimal,
        distributions: Dict[str, Dict[str, Decimal]],
        steps: List[Dict],
        step_number: int,
        non_participating_positions: List,
    ) -> tuple[Decimal, int]:
        """Distribute remaining proceeds to common (as-converted).

        Distributes to:
        - Common shares
        - Non-participating preferred that chose to convert
        - Already-participating preferred do NOT participate here (they got it in participation step)

        Args:
            snapshot: CapTableSnapshot
            remaining: Remaining proceeds
            distributions: Distribution tracking dict (mutated)
            steps: Waterfall steps list (mutated)
            step_number: Current step number
            non_participating_positions: List of (position, share_class, choice) tuples

        Returns:
            (remaining_proceeds, next_step_number)
        """
        if remaining <= 0:
            return remaining, step_number

        # Build set of non-participating holders that took preference (don't participate in common)
        took_preference = set()
        for position, share_class, choice in non_participating_positions:
            if choice == "preference":
                took_preference.add((position.holder_id, position.share_class_id))

        # Identify positions that participate in common distribution
        # Exclude:
        # 1. Participating preferred (they already got their share in participation step)
        # 2. Non-participating preferred that took preference (they already got liquidation pref)
        participating_in_common = set()

        for position in snapshot.positions:
            share_class = snapshot.share_classes.get(position.share_class_id)
            if not share_class:
                continue

            # Skip if this is participating/capped_participating (they got participation already)
            if share_class.participation_rights and \
               share_class.participation_rights.participation_type in ("participating", "capped_participating"):
                continue

            # Skip if this is non-participating that took preference
            if (position.holder_id, position.share_class_id) in took_preference:
                continue

            # Include everyone else (common, non-participating taking conversion, etc.)
            participating_in_common.add((position.holder_id, position.share_class_id))

        # Calculate total shares participating in common distribution
        total_participating_shares = Decimal("0")
        for position in snapshot.positions:
            if (position.holder_id, position.share_class_id) in participating_in_common:
                total_participating_shares += position.shares

        # Distribute pro-rata among participating shares
        if total_participating_shares > 0:
            for position in snapshot.positions:
                if (position.holder_id, position.share_class_id) not in participating_in_common:
                    continue

                # For MVP: assume 1:1 conversion ratio
                # In production: use ConversionRights.current_conversion_ratio
                as_converted_shares = position.shares

                position_distribution = remaining * (as_converted_shares / total_participating_shares)
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
