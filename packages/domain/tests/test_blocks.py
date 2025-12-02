"""Tests for blocks architecture.

Tests cover:
- BlockContext get/set/has operations
- Block abstract base class
- Topological sort and dependency resolution
- BlockExecutor validation and execution
- CapTableBlock, WaterfallBlock, ReturnsBlock integration
"""

import pytest
from decimal import Decimal
from datetime import date

from captable_domain.blocks import (
    Block,
    BlockContext,
    BlockExecutor,
    CapTableBlock,
    WaterfallBlock,
    ReturnsBlock,
)
from captable_domain.blocks.base import topological_sort, CircularDependencyError
from captable_domain.schemas import (
    CapTable,
    ShareClass,
    ShareIssuanceEvent,
    ExitScenario,
    ReturnsCFG,
    LiquidationPreference,
)


# =============================================================================
# BlockContext Tests
# =============================================================================

def test_block_context_get_set():
    """Test basic get/set operations."""
    context = BlockContext()
    context.set("key1", "value1")
    assert context.get("key1") == "value1"


def test_block_context_has():
    """Test has() method."""
    context = BlockContext()
    assert not context.has("key1")
    context.set("key1", "value1")
    assert context.has("key1")


def test_block_context_keys():
    """Test keys() method."""
    context = BlockContext()
    context.set("key1", "value1")
    context.set("key2", "value2")
    assert set(context.keys()) == {"key1", "key2"}


def test_block_context_get_missing_key():
    """Test that getting missing key raises KeyError."""
    context = BlockContext()
    with pytest.raises(KeyError, match="Key 'missing' not found"):
        context.get("missing")


# =============================================================================
# Topological Sort Tests
# =============================================================================

class SimpleBlock(Block):
    """Simple block for testing."""

    def __init__(self, name, inputs, outputs):
        self.name = name
        self._inputs = inputs
        self._outputs = outputs

    def inputs(self):
        return self._inputs

    def outputs(self):
        return self._outputs

    def execute(self, context):
        # Write outputs based on inputs
        for output in self._outputs:
            context.set(output, f"{self.name}_output")

    def __repr__(self):
        return f"SimpleBlock({self.name})"


def test_topological_sort_linear_chain():
    """Test sorting linear dependency chain: A -> B -> C."""
    block_a = SimpleBlock("A", [], ["data_a"])
    block_b = SimpleBlock("B", ["data_a"], ["data_b"])
    block_c = SimpleBlock("C", ["data_b"], ["data_c"])

    # Sort in random order
    sorted_blocks = topological_sort([block_c, block_a, block_b])

    # Should be sorted A, B, C
    assert sorted_blocks == [block_a, block_b, block_c]


def test_topological_sort_parallel_blocks():
    """Test sorting parallel blocks with shared dependency."""
    block_a = SimpleBlock("A", [], ["data_a"])
    block_b = SimpleBlock("B", ["data_a"], ["data_b"])
    block_c = SimpleBlock("C", ["data_a"], ["data_c"])

    sorted_blocks = topological_sort([block_c, block_b, block_a])

    # A must be first, B and C can be in any order
    assert sorted_blocks[0] == block_a
    assert set(sorted_blocks[1:]) == {block_b, block_c}


def test_topological_sort_circular_dependency():
    """Test that circular dependencies are detected."""
    block_a = SimpleBlock("A", ["data_c"], ["data_a"])
    block_b = SimpleBlock("B", ["data_a"], ["data_b"])
    block_c = SimpleBlock("C", ["data_b"], ["data_c"])

    with pytest.raises(CircularDependencyError, match="Circular dependency detected"):
        topological_sort([block_a, block_b, block_c])


def test_topological_sort_duplicate_output():
    """Test that duplicate outputs are detected."""
    block_a = SimpleBlock("A", [], ["data_a"])
    block_b = SimpleBlock("B", [], ["data_a"])  # Same output as A

    with pytest.raises(ValueError, match="Multiple blocks produce"):
        topological_sort([block_a, block_b])


def test_topological_sort_external_inputs():
    """Test blocks with external inputs (not produced by other blocks)."""
    # Block A requires external input "external_data"
    block_a = SimpleBlock("A", ["external_data"], ["data_a"])
    block_b = SimpleBlock("B", ["data_a"], ["data_b"])

    # Should sort successfully - external inputs don't need producers
    sorted_blocks = topological_sort([block_b, block_a])
    assert sorted_blocks == [block_a, block_b]


# =============================================================================
# BlockExecutor Tests
# =============================================================================

def test_block_executor_simple_chain():
    """Test executor with simple linear chain."""
    block_a = SimpleBlock("A", [], ["data_a"])
    block_b = SimpleBlock("B", ["data_a"], ["data_b"])

    context = BlockContext()
    executor = BlockExecutor([block_a, block_b])
    executor.execute(context)

    assert context.get("data_a") == "A_output"
    assert context.get("data_b") == "B_output"


def test_block_executor_missing_input():
    """Test that executor validates required inputs."""
    block = SimpleBlock("A", ["missing_input"], ["output"])

    context = BlockContext()
    executor = BlockExecutor([block])

    with pytest.raises(KeyError, match="requires input 'missing_input'"):
        executor.execute(context)


def test_block_executor_missing_output():
    """Test that executor validates block outputs."""

    class BadBlock(Block):
        def inputs(self):
            return []

        def outputs(self):
            return ["output"]

        def execute(self, context):
            # Doesn't write output!
            pass

    context = BlockContext()
    executor = BlockExecutor([BadBlock()])

    with pytest.raises(ValueError, match="declared output 'output' but didn't write"):
        executor.execute(context)


# =============================================================================
# CapTableBlock Integration Tests
# =============================================================================

def test_cap_table_block_basic():
    """Test CapTableBlock with simple cap table."""
    # Create simple cap table
    cap_table = CapTable(company_name="Test Corp")
    cap_table.share_classes["common"] = ShareClass(
        id="common", name="Common Stock", share_type="common"
    )

    # Add founder shares
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="founder_001",
            event_date=date(2024, 1, 1),
            holder_id="founder_alice",
            share_class_id="common",
            shares=Decimal("8000000"),
        )
    )

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="founder_002",
            event_date=date(2024, 1, 1),
            holder_id="founder_bob",
            share_class_id="common",
            shares=Decimal("2000000"),
        )
    )

    # Get snapshot
    snapshot = cap_table.current_snapshot()

    # Execute block
    context = BlockContext()
    context.set("cap_table_snapshot", snapshot)

    block = CapTableBlock()
    block.execute(context)

    # Verify outputs
    ownership_df = context.get("cap_table_ownership")
    assert len(ownership_df) == 2
    assert ownership_df.iloc[0]["holder_id"] == "founder_alice"
    assert ownership_df.iloc[0]["ownership_pct"] == 80.0
    assert ownership_df.iloc[1]["holder_id"] == "founder_bob"
    assert ownership_df.iloc[1]["ownership_pct"] == 20.0

    by_class_df = context.get("cap_table_by_class")
    assert len(by_class_df) == 1
    assert by_class_df.iloc[0]["share_class_id"] == "common"
    assert by_class_df.iloc[0]["shares"] == 10_000_000

    summary_df = context.get("cap_table_summary")
    assert summary_df.iloc[0]["total_shares"] == 10_000_000
    assert summary_df.iloc[0]["total_holders"] == 2
    assert summary_df.iloc[0]["common_shares"] == 10_000_000


def test_cap_table_block_with_preferred():
    """Test CapTableBlock with preferred shares."""
    cap_table = CapTable(company_name="Test Corp")

    # Add share classes
    cap_table.share_classes["common"] = ShareClass(
        id="common", name="Common Stock", share_type="common"
    )
    cap_table.share_classes["series_a"] = ShareClass(
        id="series_a",
        name="Series A Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"), seniority_rank=0
        ),
    )

    # Add events
    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="founder_001",
            event_date=date(2024, 1, 1),
            holder_id="founder_alice",
            share_class_id="common",
            shares=Decimal("7000000"),
        )
    )

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="series_a_001",
            event_date=date(2024, 6, 1),
            holder_id="investor_vc",
            share_class_id="series_a",
            shares=Decimal("3000000"),
        )
    )

    snapshot = cap_table.current_snapshot()

    # Execute block
    context = BlockContext()
    context.set("cap_table_snapshot", snapshot)

    block = CapTableBlock()
    block.execute(context)

    # Verify
    ownership_df = context.get("cap_table_ownership")
    assert len(ownership_df) == 2

    by_class_df = context.get("cap_table_by_class")
    assert len(by_class_df) == 2
    assert by_class_df.iloc[0]["share_class_id"] == "common"  # common has 70% ownership


# =============================================================================
# WaterfallBlock Integration Tests
# =============================================================================

def test_waterfall_block_basic():
    """Test WaterfallBlock with simple M&A exit."""
    # Create cap table with preferred
    cap_table = CapTable(company_name="Test Corp")
    cap_table.share_classes["common"] = ShareClass(
        id="common", name="Common Stock", share_type="common"
    )
    cap_table.share_classes["series_a"] = ShareClass(
        id="series_a",
        name="Series A Preferred",
        share_type="preferred",
        liquidation_preference=LiquidationPreference(
            multiple=Decimal("1.0"), seniority_rank=0
        ),
    )

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="founder_001",
            event_date=date(2024, 1, 1),
            holder_id="founder_alice",
            share_class_id="common",
            shares=Decimal("7000000"),
        )
    )

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="series_a_001",
            event_date=date(2024, 6, 1),
            holder_id="investor_vc",
            share_class_id="series_a",
            shares=Decimal("3000000"),
        )
    )

    snapshot = cap_table.current_snapshot()

    # Create exit scenario
    scenario = ExitScenario(
        id="base_case",
        label="Base Case M&A",
        exit_value=Decimal("50_000_000"),
        exit_type="M&A",
        transaction_costs_percentage=Decimal("0.03"),
    )

    # Execute block
    context = BlockContext()
    context.set("cap_table_snapshot", snapshot)
    context.set("exit_scenario", scenario)

    block = WaterfallBlock()
    block.execute(context)

    # Verify outputs exist
    waterfall_steps = context.get("waterfall_steps")
    assert len(waterfall_steps) > 0

    by_holder_df = context.get("waterfall_by_holder")
    assert len(by_holder_df) == 2

    by_class_df = context.get("waterfall_by_class")
    assert len(by_class_df) == 2


# =============================================================================
# ReturnsBlock Integration Tests
# =============================================================================

def test_returns_block_basic():
    """Test ReturnsBlock with waterfall output."""
    # Create simple waterfall output (mock)
    import pandas as pd

    waterfall_df = pd.DataFrame(
        [
            {
                "holder_id": "founder_alice",
                "share_class_id": "common",
                "shares": 7_000_000,
                "ownership_pct": 70.0,
                "liquidation_preference_amount": 0,
                "participation_amount": 0,
                "common_distribution_amount": 34_000_000,
                "total_distribution": 34_000_000,
                "distribution_pct": 70.0,
            },
            {
                "holder_id": "investor_vc",
                "share_class_id": "series_a",
                "shares": 3_000_000,
                "ownership_pct": 30.0,
                "liquidation_preference_amount": 3_000_000,
                "participation_amount": 0,
                "common_distribution_amount": 12_000_000,
                "total_distribution": 15_000_000,
                "distribution_pct": 30.0,
            },
        ]
    )

    scenario = ExitScenario(
        id="base_case",
        label="Base Case",
        exit_value=Decimal("50_000_000"),
        exit_type="M&A",
    )

    config = ReturnsCFG(
        scenarios=[scenario], include_moic=True, include_irr=False
    )

    # Execute block
    context = BlockContext()
    context.set("waterfall_by_holder", waterfall_df)
    context.set("exit_scenario", scenario)
    context.set("returns_cfg", config)

    block = ReturnsBlock()
    block.execute(context)

    # Verify outputs exist
    returns_by_holder = context.get("returns_by_holder")
    assert len(returns_by_holder) == 2

    returns_by_class = context.get("returns_by_class")
    assert len(returns_by_class) == 2

    returns_summary = context.get("returns_summary")
    assert len(returns_summary) == 1


# =============================================================================
# Full Pipeline Integration Test
# =============================================================================

def test_full_blocks_pipeline():
    """Test full pipeline: CapTable -> Waterfall -> Returns."""
    # Create cap table
    cap_table = CapTable(company_name="Test Corp")
    cap_table.share_classes["common"] = ShareClass(
        id="common", name="Common Stock", share_type="common"
    )

    cap_table.add_event(
        ShareIssuanceEvent(
            event_id="founder_001",
            event_date=date(2024, 1, 1),
            holder_id="founder_alice",
            share_class_id="common",
            shares=Decimal("10000000"),
        )
    )

    snapshot = cap_table.current_snapshot()

    # Create exit scenario and config
    scenario = ExitScenario(
        id="base_case",
        label="Base Case",
        exit_value=Decimal("50_000_000"),
        exit_type="M&A",
    )

    returns_cfg = ReturnsCFG(
        scenarios=[scenario], include_moic=True, include_irr=False
    )

    # Create blocks
    cap_table_block = CapTableBlock()
    waterfall_block = WaterfallBlock()
    returns_block = ReturnsBlock()

    # Execute pipeline
    context = BlockContext()
    context.set("cap_table_snapshot", snapshot)
    context.set("exit_scenario", scenario)
    context.set("returns_cfg", returns_cfg)

    executor = BlockExecutor([cap_table_block, waterfall_block, returns_block])
    executor.execute(context)

    # Verify all outputs exist
    assert context.has("cap_table_ownership")
    assert context.has("cap_table_by_class")
    assert context.has("cap_table_summary")
    assert context.has("waterfall_steps")
    assert context.has("waterfall_by_holder")
    assert context.has("waterfall_by_class")
    assert context.has("returns_by_holder")
    assert context.has("returns_by_class")
    assert context.has("returns_summary")

    # Verify basic sanity checks
    ownership_df = context.get("cap_table_ownership")
    assert len(ownership_df) == 1
    assert ownership_df.iloc[0]["ownership_pct"] == 100.0

    waterfall_by_holder = context.get("waterfall_by_holder")
    assert len(waterfall_by_holder) == 1

    returns_summary = context.get("returns_summary")
    assert returns_summary.iloc[0]["total_distribution"] > 0
