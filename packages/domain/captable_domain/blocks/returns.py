"""Returns computation block.

Computes return metrics (MOIC, IRR) from waterfall distributions.

Metrics:
- MOIC (Multiple on Invested Capital): total_distribution / investment_amount
- IRR (Internal Rate of Return): annualized return accounting for time
- Cash-on-cash return: actual cash distributions
"""

from typing import List, Optional
from decimal import Decimal
from datetime import date
import pandas as pd

from .base import Block, BlockContext
from ..schemas import CapTableSnapshot, ExitScenario, ReturnsCFG


class ReturnsBlock(Block):
    """Computes return metrics from waterfall distributions.

    Inputs (from context):
        - waterfall_by_holder: DataFrame with distribution by holder (from WaterfallBlock)
        - exit_scenario: ExitScenario with exit details
        - returns_cfg: ReturnsCFG specifying which metrics to calculate

    Outputs (to context):
        - returns_by_holder: DataFrame with return metrics by holder:
            * holder_id: Holder identifier
            * investment_amount: Original investment (for MOIC calculation)
            * total_distribution: Total proceeds from waterfall
            * moic: Multiple on Invested Capital (if include_moic=True)
            * irr: Internal Rate of Return (if include_irr=True)
            * cash_on_cash_return: Cash-on-cash return percentage

        - returns_by_class: DataFrame with return metrics by share class:
            * share_class_id: Share class identifier
            * total_investment: Total invested in class
            * total_distribution: Total distributed to class
            * moic: Average MOIC for class
            * irr: Average IRR for class (if include_irr=True)

        - returns_summary: DataFrame with single row of aggregate metrics:
            * total_investment: Total capital invested
            * total_distribution: Total proceeds distributed
            * aggregate_moic: Overall MOIC
            * aggregate_irr: Overall IRR (if include_irr=True)

    Example:
        # After running CapTableBlock and WaterfallBlock
        context.set("returns_cfg", ReturnsCFG(
            scenarios=[scenario],
            include_moic=True,
            include_irr=False
        ))

        block = ReturnsBlock()
        block.execute(context)

        returns_df = context.get("returns_by_holder")
    """

    def __init__(
        self,
        waterfall_key: str = "waterfall_by_holder",
        scenario_key: str = "exit_scenario",
        config_key: str = "returns_cfg",
    ):
        """Initialize ReturnsBlock.

        Args:
            waterfall_key: Context key for waterfall_by_holder DataFrame
            scenario_key: Context key for ExitScenario
            config_key: Context key for ReturnsCFG
        """
        self.waterfall_key = waterfall_key
        self.scenario_key = scenario_key
        self.config_key = config_key

    def inputs(self) -> List[str]:
        return [self.waterfall_key, self.scenario_key, self.config_key]

    def outputs(self) -> List[str]:
        return [
            "returns_by_holder",
            "returns_by_class",
            "returns_summary",
        ]

    def execute(self, context: BlockContext) -> None:
        """Execute returns computation.

        Args:
            context: BlockContext with waterfall and config
        """
        waterfall_df: pd.DataFrame = context.get(self.waterfall_key)
        scenario: ExitScenario = context.get(self.scenario_key)
        config: ReturnsCFG = context.get(self.config_key)

        # Compute returns by holder
        by_holder_df = self._compute_by_holder(waterfall_df, scenario, config)
        context.set("returns_by_holder", by_holder_df)

        # Compute returns by class
        by_class_df = self._compute_by_class(by_holder_df)
        context.set("returns_by_class", by_class_df)

        # Compute summary metrics
        summary_df = self._compute_summary(by_holder_df, config)
        context.set("returns_summary", summary_df)

    def _compute_by_holder(
        self,
        waterfall_df: pd.DataFrame,
        scenario: ExitScenario,
        config: ReturnsCFG,
    ) -> pd.DataFrame:
        """Compute return metrics by holder.

        Args:
            waterfall_df: Waterfall distribution DataFrame
            scenario: ExitScenario for dates
            config: ReturnsCFG for metric selection

        Returns:
            DataFrame with return metrics by holder
        """
        if waterfall_df.empty:
            return pd.DataFrame(columns=[
                "holder_id",
                "investment_amount",
                "total_distribution",
                "moic",
                "irr",
                "cash_on_cash_return",
            ])

        rows = []

        for _, row in waterfall_df.iterrows():
            holder_id = row["holder_id"]
            total_distribution = Decimal(str(row["total_distribution"]))

            # For MVP: we don't track investment_amount per holder yet
            # Would need to track this from ShareIssuanceEvent.price_per_share
            # For now, use placeholder based on ownership
            # TODO: Track actual investment amounts in future
            investment_amount = Decimal("0")  # Placeholder

            # Calculate MOIC
            moic = None
            if config.include_moic and investment_amount > 0:
                moic = float(total_distribution / investment_amount)

            # Calculate IRR
            irr = None
            if config.include_irr and scenario.exit_date:
                # IRR calculation requires:
                # 1. Investment date (from ShareIssuanceEvent)
                # 2. Investment amount
                # 3. Exit date
                # 4. Exit proceeds
                # For MVP: not implemented
                # In production: use numpy.irr or scipy optimization
                pass

            # Cash-on-cash return
            cash_on_cash = (
                float((total_distribution / investment_amount - 1) * 100)
                if investment_amount > 0
                else 0.0
            )

            rows.append({
                "holder_id": holder_id,
                "share_class_id": row["share_class_id"],
                "investment_amount": float(investment_amount),
                "total_distribution": float(total_distribution),
                "moic": moic,
                "irr": irr,
                "cash_on_cash_return": cash_on_cash,
            })

        return pd.DataFrame(rows)

    def _compute_by_class(self, by_holder_df: pd.DataFrame) -> pd.DataFrame:
        """Compute return metrics aggregated by share class.

        Args:
            by_holder_df: Returns by holder DataFrame

        Returns:
            DataFrame with return metrics by share class
        """
        if by_holder_df.empty:
            return pd.DataFrame(columns=[
                "share_class_id",
                "total_investment",
                "total_distribution",
                "moic",
                "irr",
            ])

        by_class = by_holder_df.groupby("share_class_id").agg({
            "investment_amount": "sum",
            "total_distribution": "sum",
            "moic": "mean",  # Average MOIC across holders in class
            "irr": "mean",   # Average IRR across holders in class
        }).reset_index()

        by_class = by_class.rename(columns={
            "investment_amount": "total_investment",
        })

        # Recalculate aggregate MOIC for class
        by_class["aggregate_moic"] = by_class.apply(
            lambda row: (
                row["total_distribution"] / row["total_investment"]
                if row["total_investment"] > 0
                else None
            ),
            axis=1,
        )

        by_class = by_class.sort_values("total_distribution", ascending=False)

        return by_class

    def _compute_summary(
        self, by_holder_df: pd.DataFrame, config: ReturnsCFG
    ) -> pd.DataFrame:
        """Compute summary return metrics.

        Args:
            by_holder_df: Returns by holder DataFrame
            config: ReturnsCFG for metric selection

        Returns:
            DataFrame with single row of summary metrics
        """
        if by_holder_df.empty:
            return pd.DataFrame([{
                "total_investment": 0.0,
                "total_distribution": 0.0,
                "aggregate_moic": None,
                "aggregate_irr": None,
            }])

        total_investment = by_holder_df["investment_amount"].sum()
        total_distribution = by_holder_df["total_distribution"].sum()

        aggregate_moic = None
        if config.include_moic and total_investment > 0:
            aggregate_moic = total_distribution / total_investment

        aggregate_irr = None
        if config.include_irr:
            # Would calculate portfolio IRR here
            # Requires investment dates and amounts for all holders
            pass

        summary = pd.DataFrame([{
            "total_investment": total_investment,
            "total_distribution": total_distribution,
            "aggregate_moic": aggregate_moic,
            "aggregate_irr": aggregate_irr,
        }])

        return summary
