"""Test Pro Rata editor functionality.

Scenario (clean numbers):
- Founders: 8M common shares
- Initial Pool: 2M shares (10M total)
- Seed: $1M investment @ $10M pre-money → 1M shares @ $1.00
- Series A: $5M total round with pro rata
  - Founders (80%): $4M pro rata allocation
  - Seed investor (10%): $500K pro rata allocation
  - New lead gets remainder

The Pro Rata editor box shows:
- Total Round Size (input)
- For each existing investor: Current %, Pro Rata $, Participating %, Investment
- New Lead row showing remainder
"""
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


def test_pro_rata_editor():
    """Test Pro Rata editor box in priced rounds."""
    cap_table = CapTable(company_name="Pro Rata Test Co")

    # =========================================================================
    # FOUNDING - Common Shares
    # =========================================================================
    cap_table.share_classes["common"] = ShareClass(
        id="common",
        name="Common Stock",
        share_type="common",
    )

    # Founders: 8M shares
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="founders",
            event_date=date(2023, 1, 1),
            holder_id="founders",
            share_class_id="common",
            shares=ShareCount("8000000"),
            price_per_share=MoneyAmount("0.001"),
        )
    )

    # Initial option pool: 2M shares
    cap_table.add_event(
        OptionPoolCreation(
            event_id="initial_pool",
            event_date=date(2023, 1, 1),
            shares_authorized=ShareCount("2000000"),
            pool_timing="post_money",
            share_class_id="common",
        )
    )

    # =========================================================================
    # SEED: $1M @ $10M pre-money = 1M shares @ $1.00
    # =========================================================================
    cap_table.share_classes["seed"] = ShareClass(
        id="seed",
        name="Seed Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=1,
        ),
        has_pro_rata_rights=True,  # Preferred investors get pro rata rights
    )

    # Seed investment: $1M at $1.00/share = 1M shares
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="seed_investor",
            event_date=date(2024, 1, 1),
            holder_id="seed_investor",
            share_class_id="seed",
            shares=ShareCount("1000000"),
            price_per_share=MoneyAmount("1.00"),
        )
    )

    cap_table.add_event(
        RoundClosingEvent(
            event_id="seed_close",
            event_date=date(2024, 1, 1),
            round_id="seed",
            round_name="Seed",
            instruments=[],
        )
    )

    # =========================================================================
    # SERIES A: $5M @ $22M pre-money = 2M shares @ $2.00
    # Post-Seed: 8M + 2M + 1M = 11M shares
    # PPS = $22M / 11M = $2.00
    # New shares = $5M / $2.00 = 2.5M
    # =========================================================================
    cap_table.share_classes["series_a"] = ShareClass(
        id="series_a",
        name="Series A Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=0,
        ),
        has_pro_rata_rights=True,  # Series A investors get pro rata rights
    )

    # Series A: Founders participate via pro rata + new lead
    # For this test, let's say:
    # - Total round: $5M
    # - Founders (8M/11M = 72.7%): $3.64M pro rata, let's say they invest $2M
    # - Seed investor (1M/11M = 9.1%): $455K pro rata, they invest full $455K
    # - New lead: $2.545M (remainder)

    # Simplified: founders invest $2M, seed $500K, lead $2.5M = $5M total
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="founders_series_a",
            event_date=date(2024, 6, 1),
            holder_id="founders",
            share_class_id="series_a",
            shares=ShareCount("1000000"),  # $2M / $2.00 = 1M
            price_per_share=MoneyAmount("2.00"),
        )
    )

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="seed_series_a",
            event_date=date(2024, 6, 1),
            holder_id="seed_investor",
            share_class_id="series_a",
            shares=ShareCount("250000"),  # $500K / $2.00 = 250K
            price_per_share=MoneyAmount("2.00"),
        )
    )

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="series_a_lead",
            event_date=date(2024, 6, 1),
            holder_id="series_a_lead",
            share_class_id="series_a",
            shares=ShareCount("1250000"),  # $2.5M / $2.00 = 1.25M
            price_per_share=MoneyAmount("2.00"),
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

    # =========================================================================
    # CREATE SNAPSHOTS
    # =========================================================================

    # Snapshot 1: Post-Founding
    founding_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Founding",
        as_of_date=date(2023, 6, 1),
        round_calculator=RoundCalculatorCFG(enabled=False),
    )

    # Snapshot 2: Post-Seed
    seed_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Post-Seed",
        as_of_date=date(2024, 3, 1),
        round_calculator=RoundCalculatorCFG(enabled=False),
    )

    # Snapshot 3: Post-Series A (this should show Pro Rata editor)
    series_a_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Post-Series A",
        as_of_date=None,  # Current
        round_calculator=RoundCalculatorCFG(enabled=False),
    )

    cfg = WorkbookCFG(
        cap_table_snapshots=[founding_cfg, seed_cfg, series_a_cfg],
        waterfall_analyses=None,
    )

    # Render
    renderer = RoundSheetRenderer(cfg)
    output_path = "pro_rata_test.xlsx"
    renderer.render(output_path)

    # Print summary
    print(f"\n{'='*70}")
    print(f"PRO RATA TEST")
    print(f"{'='*70}")

    print(f"\nSCENARIO:")
    print(f"  Founders: 8M common shares")
    print(f"  Initial Pool: 2M shares")
    print(f"  Total: 10M shares")
    print()
    print(f"  Seed: $1M @ $10M pre-money")
    print(f"    PPS = $10M / 10M = $1.00/share")
    print(f"    Shares = $1M / $1.00 = 1,000,000 shares")
    print()
    print(f"  Post-Seed: 11M shares")
    print(f"    Founders: 8M (72.7%)")
    print(f"    Pool: 2M (18.2%)")
    print(f"    Seed Investor: 1M (9.1%)")
    print()
    print(f"  Series A: $5M @ $22M pre-money")
    print(f"    PPS = $22M / 11M = $2.00/share")
    print(f"    Total new shares = $5M / $2.00 = 2,500,000 shares")
    print()
    print(f"    PRO RATA RIGHTS (only preferred with has_pro_rata_rights=True):")
    print(f"    - Seed Investor (9.1%): has pro rata rights")
    print(f"    - Founders: NO pro rata (common stock, has_pro_rata_rights=False)")
    print(f"    - Pool: NO pro rata (not an investor)")
    print()
    print(f"    ACTUAL INVESTMENTS:")
    print(f"    - Founders: $2M (1M shares) - not via pro rata")
    print(f"    - Seed Investor: $500K (250K shares) - via pro rata")
    print(f"    - New Lead: $2.5M (1.25M shares)")
    print()
    print(f"Generated: {output_path}")
    print()
    print(f"SHEETS CREATED:")
    print(f"  1. Founding - Just founders + pool")
    print(f"  2. Post-Seed - Seed round added (NO pro rata editor - first priced round)")
    print(f"  3. Post-Series A - WITH Pro Rata editor for existing investors")
    print()
    print(f"PRO RATA EDITOR (on Post-Series A sheet):")
    print(f"  Shows investors with pro rata rights from Post-Seed snapshot")
    print(f"  (Only share classes with has_pro_rata_rights=True)")
    print(f"  - Total Round Size: [INPUT]")
    print(f"  - seed_investor: 9.1% current → Pro Rata $ formula → Participation % → Investment")
    print(f"  - (New Lead): Remainder after pro rata")
    print(f"  Note: Founders NOT shown (common stock has_pro_rata_rights=False)")
    print()

    # Verify the math
    final_snapshot = cap_table.current_snapshot()
    print(f"FINAL CAP TABLE:")
    for pos in sorted(final_snapshot.positions, key=lambda p: -p.shares):
        pct = pos.shares / final_snapshot.total_shares_outstanding * 100
        print(f"  {pos.holder_id}: {int(pos.shares):,} shares ({pct:.1f}%) - {pos.share_class_id}")

    print(f"\n  Total: {int(final_snapshot.total_shares_outstanding):,} shares")
