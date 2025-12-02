"""Computation blocks for cap table analysis.

This package contains the computation layer that transforms domain schemas into
DataFrames suitable for Excel rendering or other consumption.

Architecture:
    Schemas (data models) → Blocks (computation) → DataFrames (output)

Key concepts:
- Blocks are reusable computation units with explicit dependencies
- Each block declares its inputs and outputs
- Dependency graph enables topological execution
- All outputs are pandas DataFrames for downstream consumption

Available blocks:
- CapTableBlock: Converts CapTableSnapshot to ownership DataFrame
- WaterfallBlock: Computes liquidation preference waterfall
- ReturnsBlock: Calculates MOIC, IRR, and other return metrics

Usage:
    from captable_domain.blocks import BlockExecutor, CapTableBlock

    # Create blocks
    cap_table_block = CapTableBlock(snapshot)

    # Execute with dependency resolution
    executor = BlockExecutor([cap_table_block])
    results = executor.execute()

    # Access output DataFrames
    ownership_df = results["cap_table_ownership"]
"""

from .base import Block, BlockExecutor, BlockContext
from .cap_table import CapTableBlock
from .waterfall import WaterfallBlock
from .returns import ReturnsBlock

__all__ = [
    "Block",
    "BlockExecutor",
    "BlockContext",
    "CapTableBlock",
    "WaterfallBlock",
    "ReturnsBlock",
]
