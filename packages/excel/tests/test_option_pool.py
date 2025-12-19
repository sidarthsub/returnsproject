"""Test option pool calculator with existing pools."""
from datetime import date
from decimal import Decimal

from captable_domain.schemas import (
    CapTable,
    ShareClass,
    ShareIssuanceEvent,
    RoundClosingEvent,
    OptionPoolCreation,
    ShareCount,
    MoneyAmount,
    LiquidationPreference,
)
from captable_excel.round_sheet_renderer import RoundSheetRenderer
from captable_domain.schemas.workbook import (
    WorkbookCFG,
    CapTableSnapshotCFG,
    RoundCalculatorCFG,
)


def test_option_pool_with_existing_pool():
    """Test option pool calculator with pre-existing option pool from previous round."""
    # Create cap table
    cap_table = CapTable(company_name="TestCo")

    # Common shares
    cap_table.share_classes["common"] = ShareClass(
        id="common",
        name="Common Stock",
        share_type="common",
    )

    # Founders: 10M shares
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="founders",
            event_date=date(2024, 1, 1),
            holder_id="founders",
            share_class_id="common",
            shares=ShareCount("10000000"),
            price_per_share=MoneyAmount("0.001"),
        )
    )

    # Seed round option pool: 1.11M shares (created post-Seed)
    cap_table.add_event(
        OptionPoolCreation(
            event_id="seed_option_pool",
            event_date=date(2024, 2, 1),
            shares_authorized=ShareCount("1111111"),
            pool_timing="post_money",
            share_class_id="common",
        )
    )

    # Series A preferred shares
    cap_table.share_classes["series_a"] = ShareClass(
        id="series_a",
        name="Series A Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=0,
        ),
    )

    # Series A: $8M investment
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="series_a_inv1",
            event_date=date(2024, 3, 1),
            holder_id="vc_firm",
            share_class_id="series_a",
            shares=ShareCount("4000000"),
            price_per_share=MoneyAmount("2.00"),
        )
    )

    cap_table.add_event(
        RoundClosingEvent(
            event_id="series_a_close",
            event_date=date(2024, 3, 1),
            round_id="series_a",
            round_name="Series A",
            instruments=[],
        )
    )

    # Create workbook with option pool target (15% post-money inclusive)
    snapshot_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Series A Option Pool Target",  # 31 chars exactly
        as_of_date=None,
        round_calculator=RoundCalculatorCFG(
            enabled=True,
            show_calculator_section=True,
            investment_allocation_mode="manual",
            option_pool_mode="target_pct_inclusive",
            option_pool_target_pct=Decimal("0.15"),  # 15% target post-money
        ),
    )

    cfg = WorkbookCFG(
        cap_table_snapshots=[snapshot_cfg],
        waterfall_analyses=None,
    )

    # Render to Excel
    renderer = RoundSheetRenderer(cfg)
    output_path = "option_pool_target_test.xlsx"
    renderer.render(output_path)

    print(f"\n✓ Generated: {output_path}")
    print("  - 10M founder shares")
    print("  - 1.11M existing option pool (from Seed)")
    print("  - $8M Series A investment")
    print("  - 15% post-money option pool target (inclusive)")
    print("  - Calculator will show NEW shares needed to reach target")


if __name__ == "__main__":
    test_option_pool_with_existing_pool()
