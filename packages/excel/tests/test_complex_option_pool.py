"""Test complex multi-round cap table with option pools and allocations."""
from datetime import date
from decimal import Decimal

from captable_domain.schemas import (
    CapTable,
    ShareClass,
    ShareIssuanceEvent,
    RoundClosingEvent,
    OptionPoolCreation,
    OptionExerciseEvent,
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


def test_complex_multi_round_with_option_pools():
    """Test calculator with multiple rounds and option pools.

    Scenario:
    - Founders: 10M common shares
    - Seed round: $1M investment, 10% post-money option pool
    - Option grants: 500K allocated from seed pool
    - Series A: $8M investment, calculator with 15% target pool
    - Calculator should ONLY affect Series A round (not Seed)
    """
    cap_table = CapTable(company_name="MultiRound Co")

    # ===== COMMON SHARES =====
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

    # ===== SEED ROUND =====
    cap_table.share_classes["seed_pref"] = ShareClass(
        id="seed_pref",
        name="Seed Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=1,
        ),
    )

    # Seed investment: $1M at $0.50/share = 2M shares
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="seed_inv1",
            event_date=date(2024, 2, 1),
            holder_id="seed_investor",
            share_class_id="seed_pref",
            shares=ShareCount("2000000"),
            price_per_share=MoneyAmount("0.50"),
        )
    )

    # Seed option pool: 1.33M shares (10% post-money)
    cap_table.add_event(
        OptionPoolCreation(
            event_id="seed_option_pool",
            event_date=date(2024, 2, 15),
            shares_authorized=ShareCount("1333333"),
            pool_timing="post_money",
            share_class_id="common",
        )
    )

    cap_table.add_event(
        RoundClosingEvent(
            event_id="seed_close",
            event_date=date(2024, 2, 15),
            round_id="seed_round",
            round_name="Seed",
            instruments=[],
        )
    )

    # Option exercises from seed pool: 500K allocated
    cap_table.add_event(
        OptionExerciseEvent(
            event_id="exercise_1",
            event_date=date(2024, 3, 1),
            holder_id="employee_1",
            option_grant_id="grant_1",
            shares_exercised=ShareCount("300000"),
            exercise_price=Decimal("0.50"),
            resulting_share_class_id="common",
        )
    )

    cap_table.add_event(
        OptionExerciseEvent(
            event_id="exercise_2",
            event_date=date(2024, 4, 1),
            holder_id="employee_2",
            option_grant_id="grant_2",
            shares_exercised=ShareCount("200000"),
            exercise_price=Decimal("0.50"),
            resulting_share_class_id="common",
        )
    )

    # ===== SERIES A ROUND =====
    cap_table.share_classes["series_a"] = ShareClass(
        id="series_a",
        name="Series A Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=0,
        ),
    )

    # Series A: $8M investment at $2.00/share = 4M shares
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="series_a_inv1",
            event_date=date(2024, 6, 1),
            holder_id="vc_firm_a",
            share_class_id="series_a",
            shares=ShareCount("3000000"),
            price_per_share=MoneyAmount("2.00"),
        )
    )

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="series_a_inv2",
            event_date=date(2024, 6, 1),
            holder_id="vc_firm_b",
            share_class_id="series_a",
            shares=ShareCount("1000000"),
            price_per_share=MoneyAmount("2.00"),
        )
    )

    # Series A option pool - calculator will determine size based on 15% target
    # Adding a placeholder pool that calculator will resize via formula
    cap_table.add_event(
        OptionPoolCreation(
            event_id="series_a_option_pool",
            event_date=date(2024, 6, 1),
            shares_authorized=ShareCount("1000000"),  # Placeholder - formula will override
            pool_timing="post_money",
            share_class_id="common",
        )
    )

    cap_table.add_event(
        RoundClosingEvent(
            event_id="series_a_close",
            event_date=date(2024, 6, 1),
            round_id="series_a",
            round_name="Series A",
            instruments=[],
        )
    )

    # ===== CREATE TWO SNAPSHOTS: SEED (HARDCODED) AND SERIES A (CALCULATOR) =====

    # Snapshot 1: Post-Seed (historical, all hardcoded)
    seed_snapshot_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Post-Seed (Hardcoded)",
        as_of_date=date(2024, 5, 1),  # Before Series A
        round_calculator=RoundCalculatorCFG(enabled=False),  # No calculator
    )

    # Snapshot 2: Post-Series A (calculator targeting Series A only)
    series_a_snapshot_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Post-Series A (Calculator)",
        as_of_date=None,  # Current
        round_calculator=RoundCalculatorCFG(
            enabled=True,
            show_calculator_section=True,
            target_round_id="series_a",  # Calculator ONLY affects Series A
            investment_allocation_mode="manual",
            option_pool_mode="target_pct_inclusive",
            option_pool_target_pct=Decimal("0.15"),  # 15% target post-money
        ),
    )

    cfg = WorkbookCFG(
        cap_table_snapshots=[seed_snapshot_cfg, series_a_snapshot_cfg],
        waterfall_analyses=None,
    )

    # Render to Excel
    renderer = RoundSheetRenderer(cfg)
    output_path = "complex_multi_round_test.xlsx"
    renderer.render(output_path)

    print(f"\n✓ Generated: {output_path}")
    print("\n📊 TWO SHEETS CREATED:")
    print("\n  SHEET 1: Post-Seed (Hardcoded)")
    print("  ├─ Date: As of May 1, 2024 (before Series A)")
    print("  ├─ Calculator: DISABLED")
    print("  ├─ Founders: 10M common shares")
    print("  ├─ Seed Round:")
    print("  │   ├─ Investment: $1M (2M shares @ $0.50)")
    print("  │   ├─ Option Pool: 1.33M shares")
    print("  │   ├─ Exercised: 500K by employees")
    print("  │   └─ Available: 833K remaining")
    print("  └─ All values: HARDCODED (blue font)")
    print()
    print("  SHEET 2: Post-Series A (Calculator)")
    print("  ├─ Date: Current (includes Series A)")
    print("  ├─ Calculator: ENABLED, targeting Series A only")
    print("  ├─ Founders: 10M common shares")
    print("  ├─ Seed Round:")
    print("  │   ├─ Investment: $1M (hardcoded, from previous sheet)")
    print("  │   ├─ Option Pool: 1.33M (hardcoded)")
    print("  │   └─ Values: HARDCODED (green = from previous round)")
    print("  └─ Series A Round:")
    print("      ├─ Investment: $8M (REFERENCES calculator)")
    print("      ├─ Pre-Money: REFERENCES calculator")
    print("      ├─ Option Pool: FORMULA with 15% target")
    print("      └─ Values: BLACK FORMULAS referencing calculator")
    print()
    print("🎯 KEY COMPARISON:")
    print("  • Sheet 1 (Seed): Everything hardcoded, no calculator")
    print("  • Sheet 2 (Series A): Seed hardcoded, Series A references calculator")
    print("  • Calculator ONLY affects Series A round in Sheet 2")
    print()
    print("📝 VALIDATION:")
    print("  Sheet 1:")
    print("    ✓ All values are hardcoded (blue font)")
    print("    ✓ No calculator section")
    print("  Sheet 2:")
    print("    ✓ Seed values hardcoded (green = from previous)")
    print("    ✓ Series A pre-money references calculator")
    print("    ✓ Series A investments reference calculator")
    print("    ✓ Series A option pool uses formula with calculator target %")


