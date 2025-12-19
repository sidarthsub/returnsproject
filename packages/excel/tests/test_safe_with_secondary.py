"""Test complex SAFE scenario with multiple rounds and secondary transactions.

Scenario (with clean round numbers):
- Founders: 8M common shares
- Initial Pool: 2M shares (10M total)
- Seed-1: SAFE with $5M cap, $500K investment → 1M shares @ $0.50
- Seed-2: SAFE with 20% discount, $500K investment → 250K shares @ $2.00
- Series A: $25M pre-money, $5M investment → 2M shares @ $2.50 (SAFEs convert here)
- Series B: $55M pre-money, $10M investment → 2.5M shares @ $4.00
  - Secondary: 50% of SAFE investors' shares convert to Series B via alchemy
"""
from datetime import date
from decimal import Decimal

from captable_domain.schemas import (
    CapTable,
    ShareClass,
    ShareIssuanceEvent,
    ShareTransferEvent,
    RoundClosingEvent,
    SAFEConversionEvent,
    OptionPoolCreation,
    ShareCount,
    MoneyAmount,
    LiquidationPreference,
)
from captable_domain.schemas.instruments import SAFEInstrument
from captable_excel.round_sheet_renderer import RoundSheetRenderer
from captable_domain.schemas.workbook import (
    WorkbookCFG,
    CapTableSnapshotCFG,
    RoundCalculatorCFG,
)


def test_safe_with_secondary():
    """Test SAFE conversion and secondary transactions with clean round numbers."""
    cap_table = CapTable(company_name="SAFE Secondary Co")

    # =========================================================================
    # FOUNDING - Common Shares
    # =========================================================================
    cap_table.share_classes["common"] = ShareClass(
        id="common",
        name="Common Stock",
        share_type="common",
    )

    # Founders: 8M shares at nominal price
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

    # Initial option pool: 2M shares (20% of founding shares)
    # Total pre-SAFE: 10M shares
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
    # SEED-1: SAFE with $5M cap, $500K investment
    # Cap price = $5M / 10M shares = $0.50/share
    # Shares = $500K / $0.50 = 1,000,000 shares
    # =========================================================================
    seed1_safe = SAFEInstrument(
        type="SAFE",
        investment_amount=MoneyAmount("500000"),
        valuation_cap=MoneyAmount("5000000"),
        safe_type="post_money",
    )

    # =========================================================================
    # SEED-2: SAFE with 20% discount, $500K investment
    # Series A PPS = $2.50, Discount price = $2.50 * 0.80 = $2.00/share
    # Shares = $500K / $2.00 = 250,000 shares
    # =========================================================================
    seed2_safe = SAFEInstrument(
        type="SAFE",
        investment_amount=MoneyAmount("500000"),
        discount_rate=Decimal("0.20"),  # 20% discount off Series A price
        safe_type="post_money",
    )

    # =========================================================================
    # SERIES A: $25M pre-money, $5M investment
    # PPS = $25M / 10M = $2.50/share
    # New money shares = $5M / $2.50 = 2,000,000 shares
    # =========================================================================

    # Seed-1 converts into its own preferred class
    cap_table.share_classes["seed1_pref"] = ShareClass(
        id="seed1_pref",
        name="Seed-1 Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=2,  # Junior to Series A
        ),
        has_pro_rata_rights=True,  # SAFE investors get pro rata rights
    )

    # Seed-2 converts into its own preferred class
    cap_table.share_classes["seed2_pref"] = ShareClass(
        id="seed2_pref",
        name="Seed-2 Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=2,  # Same seniority as Seed-1 (pari passu)
        ),
        has_pro_rata_rights=True,  # SAFE investors get pro rata rights
    )

    # Series A new money
    cap_table.share_classes["series_a"] = ShareClass(
        id="series_a",
        name="Series A Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=1,  # Senior to Seeds
        ),
        has_pro_rata_rights=True,  # Series A investors get pro rata rights
    )

    # Pre-Series A: 10M shares (8M founders + 2M pool)
    pre_series_a_shares = Decimal("10000000")

    # Series A price per share
    series_a_pps = Decimal("2.50")  # $25M / 10M = $2.50

    # Seed-1 conversion (cap-based): $5M cap / 10M shares = $0.50/share
    seed1_cap_price = Decimal("0.50")
    seed1_shares = Decimal("1000000")  # $500K / $0.50 = 1M shares

    seed1_conversion = SAFEConversionEvent(
        event_id="seed1_convert",
        event_date=date(2024, 3, 1),
        safe_holder_id="seed1_investor",
        safe_instrument=seed1_safe,
        conversion_price=seed1_cap_price,
        shares_issued=ShareCount("1000000"),
        resulting_share_class_id="seed1_pref",
    )

    # Seed-2 conversion (discount-based): $2.50 * 0.80 = $2.00/share
    seed2_discount_price = Decimal("2.00")
    seed2_shares = Decimal("250000")  # $500K / $2.00 = 250K shares

    seed2_conversion = SAFEConversionEvent(
        event_id="seed2_convert",
        event_date=date(2024, 3, 1),
        safe_holder_id="seed2_investor",
        safe_instrument=seed2_safe,
        conversion_price=seed2_discount_price,
        shares_issued=ShareCount("250000"),
        resulting_share_class_id="seed2_pref",
    )

    # Series A new money: $5M / $2.50 = 2M shares
    series_a_shares = Decimal("2000000")

    series_a_issuance = ShareIssuanceEvent(
        event_id="series_a_lead",
        event_date=date(2024, 3, 1),
        holder_id="series_a_lead",
        share_class_id="series_a",
        shares=ShareCount("2000000"),
        price_per_share=series_a_pps,
    )

    # Series A option pool expansion: 500K more shares
    series_a_pool = OptionPoolCreation(
        event_id="series_a_pool",
        event_date=date(2024, 3, 1),
        shares_authorized=ShareCount("500000"),
        pool_timing="post_money",
        share_class_id="common",
    )

    # Series A Round Closing
    cap_table.add_event(
        RoundClosingEvent(
            event_id="series_a_close",
            event_date=date(2024, 3, 1),
            round_id="series_a",
            round_name="Series A",
            instruments=[seed1_safe, seed2_safe],
            safe_conversions=[seed1_conversion, seed2_conversion],
            share_issuances=[series_a_issuance],
            option_pool_created=series_a_pool,
        )
    )

    # =========================================================================
    # SERIES B: $55M pre-money, $10M investment
    # Post-Series A: 8M + 2.5M + 1M + 250K + 2M = 13.75M shares
    # PPS = $55M / 13.75M = $4.00/share
    # New money shares = $10M / $4.00 = 2.5M shares
    # =========================================================================
    cap_table.share_classes["series_b"] = ShareClass(
        id="series_b",
        name="Series B Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"),
            seniority_rank=0,  # Senior to Series A
        ),
        has_pro_rata_rights=True,  # Series B investors get pro rata rights
    )

    # Post-Series A shares: 13.75M
    post_series_a_shares = Decimal("13750000")  # 8M + 2.5M + 1M + 250K + 2M

    # Series B price per share
    series_b_pps = Decimal("4.00")  # $55M / 13.75M = $4.00

    # Primary: $10M / $4.00 = 2.5M shares
    series_b_primary_shares = Decimal("2500000")

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="series_b_primary",
            event_date=date(2025, 1, 15),
            holder_id="series_b_lead",
            share_class_id="series_b",
            shares=ShareCount("2500000"),
            price_per_share=series_b_pps,
        )
    )

    # Secondary with ALCHEMY: 50% of SAFE investors' shares sold to Series B investor
    # The buyer receives Series B preferred (alchemy converts the share class)
    # Seed-1 sells 50%: 500K shares
    # Seed-2 sells 50%: 125K shares

    seed1_secondary_shares = Decimal("500000")  # 50% of 1M
    seed2_secondary_shares = Decimal("125000")  # 50% of 250K

    # Seed-1 secondary with alchemy: seller gives up seed1_pref, buyer gets series_b
    cap_table.add_event(
        ShareTransferEvent(
            event_id="seed1_secondary",
            event_date=date(2025, 1, 15),
            from_holder_id="seed1_investor",
            to_holder_id="series_b_lead",
            share_class_id="seed1_pref",  # Seller's class (what they're giving up)
            shares=ShareCount("500000"),
            price_per_share=series_b_pps,  # At Series B price
            resulting_share_class_id="series_b",  # ALCHEMY: buyer gets Series B
        )
    )

    # Seed-2 secondary with alchemy: seller gives up seed2_pref, buyer gets series_b
    cap_table.add_event(
        ShareTransferEvent(
            event_id="seed2_secondary",
            event_date=date(2025, 1, 15),
            from_holder_id="seed2_investor",
            to_holder_id="series_b_lead",
            share_class_id="seed2_pref",  # Seller's class (what they're giving up)
            shares=ShareCount("125000"),
            price_per_share=series_b_pps,
            resulting_share_class_id="series_b",  # ALCHEMY: buyer gets Series B
        )
    )

    cap_table.add_event(
        RoundClosingEvent(
            event_id="series_b_close",
            event_date=date(2025, 1, 15),
            round_id="series_b",
            round_name="Series B",
            instruments=[],
        )
    )

    # =========================================================================
    # CREATE SNAPSHOTS
    # =========================================================================

    # Snapshot 1: Post-Founding (before any SAFEs)
    founding_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Founding",
        as_of_date=date(2023, 6, 1),
        round_calculator=RoundCalculatorCFG(enabled=False),
    )

    # Snapshot 2: Post-Series A (after SAFE conversion)
    series_a_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Post-Series A",
        as_of_date=date(2024, 6, 1),
        round_calculator=RoundCalculatorCFG(enabled=False),
    )

    # Snapshot 3: Post-Series B (after secondary)
    series_b_cfg = CapTableSnapshotCFG(
        cap_table=cap_table,
        label="Post-Series B",
        as_of_date=None,  # Current
        round_calculator=RoundCalculatorCFG(enabled=False),
    )

    cfg = WorkbookCFG(
        cap_table_snapshots=[founding_cfg, series_a_cfg, series_b_cfg],
        waterfall_analyses=None,
    )

    # Render
    renderer = RoundSheetRenderer(cfg)
    output_path = "safe_with_secondary_test.xlsx"
    renderer.render(output_path)

    # Print summary
    print(f"\n{'='*70}")
    print(f"SAFE WITH SECONDARY TEST (Clean Numbers)")
    print(f"{'='*70}")

    print(f"\nSCENARIO (all clean multiples):")
    print(f"  Founders: 8M common shares")
    print(f"  Initial Pool: 2M shares")
    print(f"  Pre-SAFE Total: 10M shares")
    print()
    print(f"  Seed-1 SAFE: $500K @ $5M cap")
    print(f"    Cap price = $5M / 10M = $0.50/share")
    print(f"    Shares = $500K / $0.50 = 1,000,000 shares")
    print()
    print(f"  Seed-2 SAFE: $500K @ 20% discount")
    print(f"    Discount price = $2.50 * 0.80 = $2.00/share")
    print(f"    Shares = $500K / $2.00 = 250,000 shares")
    print()
    print(f"  Series A: $25M pre-money, $5M investment")
    print(f"    PPS = $25M / 10M = $2.50/share")
    print(f"    New shares = $5M / $2.50 = 2,000,000 shares")
    print(f"    Pool expansion: 500,000 shares")
    print()
    print(f"  Post-Series A: 13.75M shares")
    print(f"    8M founders + 2.5M pool + 1M seed1 + 250K seed2 + 2M series_a")
    print()
    print(f"  Series B: $55M pre-money, $10M primary + secondary WITH ALCHEMY")
    print(f"    PPS = $55M / 13.75M = $4.00/share")
    print(f"    Primary = $10M / $4.00 = 2,500,000 shares")
    print(f"    Seed-1 sells 50%: 500,000 seed1_pref -> series_b (alchemy)")
    print(f"    Seed-2 sells 50%: 125,000 seed2_pref -> series_b (alchemy)")
    print()
    print(f"Generated: {output_path}")
    print()
    print(f"SHEETS CREATED:")
    print(f"  1. Founding - Just founders + pool (10M shares)")
    print(f"  2. Post-Series A - SAFE conversions + new money (13.75M shares)")
    print(f"  3. Post-Series B - Primary + secondary with alchemy (16.25M shares)")
    print()

    # Verify the math
    final_snapshot = cap_table.current_snapshot()
    print(f"FINAL CAP TABLE:")
    for pos in sorted(final_snapshot.positions, key=lambda p: -p.shares):
        pct = pos.shares / final_snapshot.total_shares_outstanding * 100
        print(f"  {pos.holder_id}: {int(pos.shares):,} shares ({pct:.1f}%) - {pos.share_class_id}")

    print(f"\n  Total: {int(final_snapshot.total_shares_outstanding):,} shares")
