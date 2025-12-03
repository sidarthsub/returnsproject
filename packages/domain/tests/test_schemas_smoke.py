"""Smoke tests for schema validation.

These tests verify that:
1. All schemas can be imported
2. Basic instantiation works
3. Field validation catches obvious errors
4. Discriminated unions work correctly
"""

import pytest
from decimal import Decimal
from datetime import date

from captable_domain.schemas import (
    # Base
    DomainModel,
    ShareCount,
    MoneyAmount,
    # Share classes
    ShareClass,
    LiquidationPreference,
    ParticipationRights,
    ConversionRights,
    # Instruments
    SAFEInstrument,
    PricedRoundInstrument,
    ConvertibleNoteInstrument,
    WarrantInstrument,
    # Events
    ShareIssuanceEvent,
    OptionPoolCreation,
    # Cap table
    CapTable,
    CapTableSnapshot,
    Position,
    # Returns
    ExitScenario,
    ReturnsCFG,
    # Workbook
    WorkbookCFG,
    CapTableSnapshotCFG,
)


class TestBasicInstantiation:
    """Test that basic schema instantiation works."""

    def test_share_class_common(self):
        """Test creating a common stock share class."""
        share_class = ShareClass(
            id="common",
            name="Common Stock",
            share_type="common"
        )
        assert share_class.id == "common"
        assert share_class.share_type == "common"

    def test_share_class_preferred_with_liquidation_pref(self):
        """Test creating preferred stock with liquidation preference."""
        share_class = ShareClass(
            id="series_a_preferred",
            name="Series A Preferred Stock",
            share_type="preferred",
            liquidation_preference=LiquidationPreference(
                multiple=Decimal("1.0"),
                seniority_rank=0
            )
        )
        assert share_class.liquidation_preference is not None
        assert share_class.liquidation_preference.multiple == Decimal("1.0")

    def test_safe_instrument_with_cap(self):
        """Test creating a SAFE with valuation cap."""
        safe = SAFEInstrument(
            type="SAFE",
            investment_amount=Decimal("100000"),
            valuation_cap=Decimal("5000000"),
            safe_type="post_money"
        )
        assert safe.investment_amount == Decimal("100000")
        assert safe.valuation_cap == Decimal("5000000")

    def test_safe_instrument_with_cap_and_discount(self):
        """Test creating a SAFE with both cap and discount."""
        safe = SAFEInstrument(
            type="SAFE",
            investment_amount=Decimal("100000"),
            valuation_cap=Decimal("5000000"),
            discount_rate=Decimal("0.20"),
            safe_type="post_money"
        )
        assert safe.valuation_cap == Decimal("5000000")
        assert safe.discount_rate == Decimal("0.20")

    def test_priced_round_instrument(self):
        """Test creating a priced round instrument."""
        priced = PricedRoundInstrument(
            type="priced",
            investment_amount=Decimal("5000000"),
            pre_money_valuation=Decimal("20000000"),
            price_per_share=Decimal("2.0"),
            shares_issued=Decimal("2500000")
        )
        assert priced.investment_amount == Decimal("5000000")


class TestValidation:
    """Test that validation rules work correctly."""

    def test_safe_requires_cap_or_discount(self):
        """Test that SAFE without cap or discount raises error."""
        with pytest.raises(ValueError, match="must have at least one of"):
            SAFEInstrument(
                type="SAFE",
                investment_amount=Decimal("100000"),
                safe_type="post_money"
            )

    def test_preferred_requires_liquidation_preference(self):
        """Test that preferred stock without liquidation preference raises error."""
        with pytest.raises(ValueError, match="must have liquidation_preference"):
            ShareClass(
                id="series_a",
                name="Series A",
                share_type="preferred"
            )

    def test_capped_participation_requires_cap_multiple(self):
        """Test that capped participation requires cap_multiple."""
        with pytest.raises(ValueError, match="requires cap_multiple"):
            ParticipationRights(
                participation_type="capped_participating"
            )

    def test_option_pool_target_timing_requires_target_percentage(self):
        """Test that target_post_money timing requires target_percentage."""
        with pytest.raises(ValueError, match="requires target_percentage"):
            OptionPoolCreation(
                event_id="pool_001",
                event_date=date(2024, 1, 1),
                shares_authorized=Decimal("1000000"),
                pool_timing="target_post_money"
            )


class TestEventSourcing:
    """Test event-sourced cap table functionality."""

    def test_cap_table_snapshot_empty(self):
        """Test creating an empty cap table snapshot."""
        snapshot = CapTableSnapshot(as_of_date=date(2024, 1, 1))
        assert snapshot.total_shares_outstanding == Decimal("0")
        assert len(snapshot.positions) == 0

    def test_cap_table_snapshot_with_simple_event(self):
        """Test applying a simple share issuance event."""
        cap_table = CapTable(company_name="Acme Corp")

        # Add common stock share class
        cap_table.share_classes["common"] = ShareClass(
            id="common",
            name="Common Stock",
            share_type="common"
        )

        # Add founder share issuance event
        event = ShareIssuanceEvent(
            event_id="founder_grant_001",
            event_date=date(2024, 1, 1),
            holder_id="founder_alice",
            share_class_id="common",
            shares=Decimal("5000000"),
            description="Founder shares for Alice"
        )
        cap_table.add_event(event)

        # Get snapshot
        snapshot = cap_table.current_snapshot()

        assert snapshot.total_shares_outstanding == Decimal("5000000")
        assert len(snapshot.positions) == 1
        assert snapshot.positions[0].holder_id == "founder_alice"
        assert snapshot.positions[0].shares == Decimal("5000000")

    def test_cap_table_time_travel(self):
        """Test querying cap table state at different dates."""
        cap_table = CapTable(company_name="Acme Corp")
        cap_table.share_classes["common"] = ShareClass(
            id="common",
            name="Common Stock",
            share_type="common"
        )

        # Event 1: Jan 1
        cap_table.add_event(ShareIssuanceEvent(
            event_id="event_001",
            event_date=date(2024, 1, 1),
            holder_id="founder_alice",
            share_class_id="common",
            shares=Decimal("5000000")
        ))

        # Event 2: Feb 1
        cap_table.add_event(ShareIssuanceEvent(
            event_id="event_002",
            event_date=date(2024, 2, 1),
            holder_id="founder_bob",
            share_class_id="common",
            shares=Decimal("5000000")
        ))

        # Snapshot as of Jan 15 (only Alice has shares)
        jan_snapshot = cap_table.snapshot(date(2024, 1, 15))
        assert jan_snapshot.total_shares_outstanding == Decimal("5000000")
        assert len(jan_snapshot.positions) == 1

        # Snapshot as of Feb 15 (both founders have shares)
        feb_snapshot = cap_table.snapshot(date(2024, 2, 15))
        assert feb_snapshot.total_shares_outstanding == Decimal("10000000")
        assert len(feb_snapshot.positions) == 2


class TestExitScenarios:
    """Test exit scenario and returns analysis."""

    def test_exit_scenario_basic(self):
        """Test creating a basic exit scenario."""
        scenario = ExitScenario(
            id="base_case",
            label="Base Case",
            exit_value=Decimal("50000000"),
            exit_type="M&A"
        )
        assert scenario.exit_value == Decimal("50000000")

    def test_exit_scenario_with_transaction_costs(self):
        """Test exit scenario with transaction costs."""
        scenario = ExitScenario(
            id="base_case",
            label="Base Case",
            exit_value=Decimal("50000000"),
            exit_type="M&A",
            transaction_costs_percentage=Decimal("0.03"),
            management_carveout_percentage=Decimal("0.05")
        )

        net_proceeds = scenario.calculate_net_proceeds()
        # $50M - 3% ($1.5M) = $48.5M
        # $48.5M - 5% of $48.5M ($2.425M) = ~$46.075M
        expected = Decimal("50000000") * Decimal("0.97") * Decimal("0.95")
        assert abs(net_proceeds - expected) < Decimal("0.01")

    def test_ipo_exit_requires_float(self):
        """Test that IPO exit requires float_percentage."""
        with pytest.raises(ValueError, match="requires float_percentage"):
            ExitScenario(
                id="ipo",
                label="IPO",
                exit_value=Decimal("500000000"),
                exit_type="IPO"
            )

    def test_ipo_offering_size_calculation(self):
        """Test IPO offering size calculation."""
        scenario = ExitScenario(
            id="ipo",
            label="IPO",
            exit_value=Decimal("500000000"),
            exit_type="IPO",
            float_percentage=Decimal("0.20")
        )

        offering_size = scenario.calculate_ipo_offering_size()
        assert offering_size == Decimal("100000000")  # 20% of $500M


class TestWorkbookConfig:
    """Test workbook configuration."""

    def test_workbook_cfg_basic(self):
        """Test creating a basic workbook configuration."""
        cap_table = CapTable(company_name="Acme Corp")
        cap_table.share_classes["common"] = ShareClass(
            id="common",
            name="Common Stock",
            share_type="common"
        )

        snapshot_cfg = CapTableSnapshotCFG(
            cap_table=cap_table,
            label="Current"
        )

        workbook_cfg = WorkbookCFG(
            cap_table_snapshots=[snapshot_cfg]
        )

        assert len(workbook_cfg.cap_table_snapshots) == 1
        assert workbook_cfg.cap_table_snapshots[0].label == "Current"
