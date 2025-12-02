"""Base classes for computation blocks.

This module provides the foundation for the blocks architecture:
- Block abstract base class
- BlockContext for passing data between blocks
- BlockExecutor for dependency resolution and execution
- Topological sort for DAG execution order
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
import pandas as pd


# =============================================================================
# Block Context
# =============================================================================

@dataclass
class BlockContext:
    """Context object for passing data between blocks.

    Blocks read their inputs from context and write their outputs to context.
    This enables dependency resolution and chaining.

    Example:
        context = BlockContext()
        context.set("cap_table_snapshot", snapshot)

        block1 = CapTableBlock()
        block1.execute(context)

        # block1 wrote "cap_table_ownership" to context
        ownership_df = context.get("cap_table_ownership")
    """

    _data: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        """Get value from context.

        Args:
            key: Key to retrieve

        Returns:
            Value associated with key

        Raises:
            KeyError: If key not found in context
        """
        if key not in self._data:
            raise KeyError(f"Key '{key}' not found in context. Available keys: {list(self._data.keys())}")
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        """Set value in context.

        Args:
            key: Key to set
            value: Value to associate with key
        """
        self._data[key] = value

    def has(self, key: str) -> bool:
        """Check if key exists in context.

        Args:
            key: Key to check

        Returns:
            True if key exists, False otherwise
        """
        return key in self._data

    def keys(self) -> List[str]:
        """Get all keys in context.

        Returns:
            List of all keys
        """
        return list(self._data.keys())


# =============================================================================
# Block Base Class
# =============================================================================

class Block(ABC):
    """Abstract base class for computation blocks.

    A Block is a reusable computation unit that:
    1. Declares its input dependencies (what it reads from context)
    2. Declares its output keys (what it writes to context)
    3. Implements compute logic in execute() method

    Blocks enable:
    - Explicit dependency declarations for topological execution
    - Reusable computation units (same block for different inputs)
    - Testability (mock context for unit tests)
    - Caching (cache expensive computations by output key)

    Subclass example:
        class CapTableBlock(Block):
            def __init__(self, snapshot_key: str = "cap_table_snapshot"):
                self.snapshot_key = snapshot_key

            def inputs(self) -> List[str]:
                return [self.snapshot_key]

            def outputs(self) -> List[str]:
                return ["cap_table_ownership", "cap_table_summary"]

            def execute(self, context: BlockContext) -> None:
                snapshot = context.get(self.snapshot_key)
                ownership_df = compute_ownership(snapshot)
                summary_df = compute_summary(snapshot)
                context.set("cap_table_ownership", ownership_df)
                context.set("cap_table_summary", summary_df)
    """

    @abstractmethod
    def inputs(self) -> List[str]:
        """Declare input dependencies (keys to read from context).

        Returns:
            List of context keys this block reads
        """
        pass

    @abstractmethod
    def outputs(self) -> List[str]:
        """Declare outputs (keys to write to context).

        Returns:
            List of context keys this block writes
        """
        pass

    @abstractmethod
    def execute(self, context: BlockContext) -> None:
        """Execute block computation.

        Read inputs from context, perform computation, write outputs to context.

        Args:
            context: BlockContext with inputs available

        Raises:
            KeyError: If required inputs not available in context
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(inputs={self.inputs()}, outputs={self.outputs()})"


# =============================================================================
# Dependency Resolution
# =============================================================================

class CircularDependencyError(Exception):
    """Raised when blocks have circular dependencies."""
    pass


def topological_sort(blocks: List[Block]) -> List[Block]:
    """Sort blocks in topological order for execution.

    Uses Kahn's algorithm to find valid execution order where all
    dependencies are satisfied before each block executes.

    Args:
        blocks: List of blocks to sort

    Returns:
        Blocks sorted in execution order

    Raises:
        CircularDependencyError: If blocks have circular dependencies

    Example:
        block1.outputs() = ["A"]
        block2.inputs() = ["A"], outputs() = ["B"]
        block3.inputs() = ["B"], outputs() = ["C"]

        topological_sort([block3, block1, block2])
        → [block1, block2, block3]
    """
    # Build dependency graph
    # output_to_block: which block produces each output
    output_to_block: Dict[str, Block] = {}
    for block in blocks:
        for output_key in block.outputs():
            if output_key in output_to_block:
                raise ValueError(
                    f"Multiple blocks produce '{output_key}': "
                    f"{output_to_block[output_key]} and {block}"
                )
            output_to_block[output_key] = block

    # Calculate in-degree (number of dependencies) for each block
    in_degree: Dict[Block, int] = {block: 0 for block in blocks}
    adjacency: Dict[Block, List[Block]] = {block: [] for block in blocks}

    for block in blocks:
        for input_key in block.inputs():
            # If input is produced by another block, add edge
            if input_key in output_to_block:
                producer = output_to_block[input_key]
                adjacency[producer].append(block)
                in_degree[block] += 1
            # Otherwise, input must be provided by initial context

    # Kahn's algorithm
    queue: List[Block] = [block for block in blocks if in_degree[block] == 0]
    sorted_blocks: List[Block] = []

    while queue:
        # Process block with no dependencies
        current = queue.pop(0)
        sorted_blocks.append(current)

        # Reduce in-degree for dependent blocks
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Check for circular dependencies
    if len(sorted_blocks) != len(blocks):
        remaining = [block for block in blocks if in_degree[block] > 0]
        raise CircularDependencyError(
            f"Circular dependency detected among blocks: {remaining}"
        )

    return sorted_blocks


# =============================================================================
# Block Executor
# =============================================================================

class BlockExecutor:
    """Executes blocks in dependency order.

    The executor:
    1. Resolves dependencies using topological sort
    2. Executes blocks in order
    3. Validates that all required inputs are available
    4. Returns final context with all outputs

    Example:
        # Create blocks
        cap_table_block = CapTableBlock()
        waterfall_block = WaterfallBlock()
        returns_block = ReturnsBlock()

        # Execute with initial context
        executor = BlockExecutor([cap_table_block, waterfall_block, returns_block])
        context = BlockContext()
        context.set("cap_table_snapshot", snapshot)
        context.set("exit_scenario", scenario)

        executor.execute(context)

        # Access results
        ownership_df = context.get("cap_table_ownership")
        waterfall_df = context.get("waterfall_steps")
        returns_df = context.get("returns_by_holder")
    """

    def __init__(self, blocks: List[Block]):
        """Initialize executor with blocks.

        Args:
            blocks: List of blocks to execute (order doesn't matter - will be sorted)
        """
        self.blocks = blocks
        self._sorted_blocks: Optional[List[Block]] = None

    def execute(self, context: BlockContext) -> BlockContext:
        """Execute all blocks in dependency order.

        Args:
            context: Initial context with required inputs

        Returns:
            Context with all block outputs

        Raises:
            CircularDependencyError: If blocks have circular dependencies
            KeyError: If required inputs not available in context
        """
        # Sort blocks in execution order (cache for repeated executions)
        if self._sorted_blocks is None:
            self._sorted_blocks = topological_sort(self.blocks)

        # Execute blocks in order
        for block in self._sorted_blocks:
            # Validate inputs are available
            self._validate_inputs(block, context)

            # Execute block
            block.execute(context)

            # Validate outputs were written
            self._validate_outputs(block, context)

        return context

    def _validate_inputs(self, block: Block, context: BlockContext) -> None:
        """Validate that all required inputs are available in context.

        Args:
            block: Block to validate
            context: Current context

        Raises:
            KeyError: If required input not found in context
        """
        for input_key in block.inputs():
            if not context.has(input_key):
                raise KeyError(
                    f"Block {block} requires input '{input_key}' but it's not in context. "
                    f"Available keys: {context.keys()}"
                )

    def _validate_outputs(self, block: Block, context: BlockContext) -> None:
        """Validate that block wrote all declared outputs to context.

        Args:
            block: Block to validate
            context: Current context

        Raises:
            ValueError: If declared output not written to context
        """
        for output_key in block.outputs():
            if not context.has(output_key):
                raise ValueError(
                    f"Block {block} declared output '{output_key}' but didn't write it to context"
                )
