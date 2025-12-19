# Cap Table Model Generator - Architecture Documentation

**Version:** 1.0
**Last Updated:** 2025-11-13
**Status:** Design Phase

---

## Table of Contents

1. [Overview](#overview)
2. [Core Architectural Principles](#core-architectural-principles)
3. [Event-Sourced Data Model](#event-sourced-data-model)
4. [Schema Design](#schema-design)
5. [Block Architecture](#block-architecture)
6. [Excel Rendering Strategy](#excel-rendering-strategy)
7. [Computation vs Rendering Separation](#computation-vs-rendering-separation)
8. [Dependency Management](#dependency-management)
9. [Formula Generation](#formula-generation)
10. [Validation Strategy](#validation-strategy)
11. [Extensibility Patterns](#extensibility-patterns)
12. [Design Decisions & Trade-offs](#design-decisions--trade-offs)

---

## Overview

This system generates Excel workbooks that model venture capital cap tables, including:
- Ownership tracking across multiple financing rounds
- Complex securities (SAFEs, convertible notes, preferred stock, warrants)
- Liquidation waterfall scenarios
- Returns analysis (IRR, MOIC)

**Key Challenge:** Cap tables have extreme complexity:
- Multiple share classes with different economic rights
- Time-based state changes (vesting, conversions)
- Complex waterfall logic (liquidation preferences, participation rights, seniority)
- Need for both current state AND historical analysis

**Solution:** Event-sourced architecture with computation/rendering separation.

---

## Core Architectural Principles

### 1. Event Sourcing Over Point-in-Time State

**Problem:** Traditional approach stores current state only:
```python
# ❌ BAD: Can't answer "what was ownership on June 1, 2023?"
class CapTable:
    holders: List[HolderPosition]  # Current state only
```

**Solution:** Store events, compute state on demand:
```python
# ✅ GOOD: Full history, compute any point in time
class CapTable:
    events: List[CapTableEvent]  # All events chronologically

    def snapshot(self, as_of_date: date) -> CapTableSnapshot:
        """Replay events up to date to compute state"""
        pass
```

**Benefits:**
- Historical queries: "Show dilution over time"
- Audit trail: "When did this shareholder acquire shares?"
- Time travel: "What if we modeled the Series B differently?"
- Debugging: Replay events to understand current state

### 2. Discriminated Unions Over Optional Fields

**Problem:** Optional fields create invalid states:
```python
# ❌ BAD: Can create invalid SAFEs
class Round:
    instrument_type: str
    safe_cap: Optional[Decimal]  # Only for SAFEs
    price_per_share: Optional[Decimal]  # Only for priced
    # Can create SAFE with price_per_share!
```

**Solution:** Discriminated unions enforce validity:
```python
# ✅ GOOD: Type system prevents invalid states
class SAFEInstrument(BaseModel):
    type: Literal["SAFE"] = "SAFE"
    investment_amount: Decimal
    valuation_cap: Optional[Decimal]
    discount_rate: Optional[Decimal]

    @model_validator(mode="after")
    def validate_cap_or_discount(self):
        if not self.valuation_cap and not self.discount_rate:
            raise ValueError("SAFE must have cap or discount")
        return self

class PricedRoundInstrument(BaseModel):
    type: Literal["priced"] = "priced"
    investment_amount: Decimal
    pre_money_valuation: Decimal
    price_per_share: Decimal
    shares_issued: Decimal

Instrument = Annotated[
    SAFEInstrument | PricedRoundInstrument | ConvertibleNoteInstrument,
    Field(discriminator="type")
]
```

**Benefits:**
- Type safety: mypy catches errors at compile time
- Self-documenting: Each instrument type has exactly its required fields
- Extensibility: Adding new instrument types doesn't pollute existing classes
- Validation: Business rules encoded in type system

### 3. Separation of Concerns: Computation vs Rendering

**Problem:** Mixing business logic with Excel rendering:
```python
# ❌ BAD: Business logic tied to Excel
class WaterfallBlock:
    def render(self, sheet: Worksheet):
        # Calculate waterfall
        for holder in holders:
            proceeds = calculate_proceeds(holder)  # Business logic
            sheet.cell(row, col).value = proceeds  # Rendering
            # Can't test calculation without Excel!
```

**Solution:** Separate computation from rendering:
```python
# ✅ GOOD: Computation is Excel-agnostic
class WaterfallBlock:
    def compute(self, context: CapTableContext) -> BlockOutput:
        """Pure Python calculation - easily testable"""
        waterfall_df = self._calculate_waterfall(context)
        return BlockOutput(data=waterfall_df, ...)

    def render(self, output: BlockOutput, sheet: Worksheet):
        """Only handles Excel formatting - no business logic"""
        self._write_to_sheet(output.data, sheet)
```

**Benefits:**
- **Testability:** Compute without Excel dependencies
- **Reusability:** Use computations in API, CLI, web UI
- **Performance:** Compute once, render to multiple formats
- **Debugging:** Inspect intermediate data structures

### 4. Excel Tables + Named Ranges (Never Hardcoded Ranges)

**Problem:** Hardcoded cell ranges break with dynamic data:
```python
# ❌ BAD: Breaks when rows are added
sheet["D2"].value = "=SUM(B2:B6)"
# User adds 3 holders → formula is now wrong
```

**Solution:** Use Excel Tables and named ranges:
```python
# ✅ GOOD: Formulas adapt to data changes
sheet.add_table(
    ref="A1:C10",
    name="HoldersTable",
    displayName="Cap Table"
)
sheet["D2"].value = "=[@Shares]/SUM(HoldersTable[Shares])"
# Adding rows automatically updates formula range
```

**Benefits:**
- **Dynamic:** Formulas automatically adjust to data changes
- **Readable:** `HoldersTable[Shares]` is clearer than `B2:B6`
- **Cross-sheet references:** Named ranges work across sheets
- **User-friendly:** Users can reference tables in their own formulas

---

## Event-Sourced Data Model

### Philosophy

**Cap table state is derived from events, not stored directly.**

Think of a cap table like a bank account:
- You don't store "current balance" (state)
- You store transactions (events)
- Balance is computed by summing transactions

Similarly:
- Don't store "current ownership %" (state)
- Store share issuances, transfers, conversions (events)
- Ownership is computed by processing events

### Event Types

```python
from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from pydantic import BaseModel

class CapTableEvent(BaseModel, ABC):
    """Base class for all cap table events."""
    event_id: str
    event_date: date
    description: Optional[str] = None

    @abstractmethod
    def apply(self, snapshot: CapTableSnapshot) -> None:
        """Apply this event to a snapshot to update its state."""
        pass

class ShareIssuanceEvent(CapTableEvent):
    """Shares are issued to a holder."""
    event_type: Literal["share_issuance"] = "share_issuance"
    holder_id: str
    share_class_id: str
    shares: Decimal
    price_per_share: Optional[Decimal] = None
    vesting_schedule_id: Optional[str] = None

    def apply(self, snapshot: CapTableSnapshot) -> None:
        snapshot.add_or_update_position(
            Position(
                holder_id=self.holder_id,
                share_class_id=self.share_class_id,
                shares=self.shares,
                acquisition_date=self.event_date,
                cost_basis=self.price_per_share * self.shares if self.price_per_share else None,
                vesting_schedule_id=self.vesting_schedule_id,
            )
        )

class ShareTransferEvent(CapTableEvent):
    """Shares are transferred from one holder to another."""
    event_type: Literal["share_transfer"] = "share_transfer"
    from_holder_id: str
    to_holder_id: str
    share_class_id: str
    shares: Decimal
    price_per_share: Optional[Decimal] = None

    def apply(self, snapshot: CapTableSnapshot) -> None:
        snapshot.transfer_shares(
            from_holder=self.from_holder_id,
            to_holder=self.to_holder_id,
            share_class_id=self.share_class_id,
            shares=self.shares,
            transfer_date=self.event_date,
            transfer_price=self.price_per_share,
        )

class ConversionEvent(CapTableEvent):
    """Shares convert from one class to another (e.g., preferred → common)."""
    event_type: Literal["conversion"] = "conversion"
    holder_id: str
    from_share_class_id: str
    to_share_class_id: str
    shares_converted: Decimal
    conversion_ratio: Decimal

    def apply(self, snapshot: CapTableSnapshot) -> None:
        new_shares = self.shares_converted * self.conversion_ratio
        snapshot.reduce_position(self.holder_id, self.from_share_class_id, self.shares_converted)
        snapshot.add_or_update_position(
            Position(
                holder_id=self.holder_id,
                share_class_id=self.to_share_class_id,
                shares=new_shares,
                acquisition_date=self.event_date,
            )
        )

class OptionExerciseEvent(CapTableEvent):
    """Employee exercises stock options."""
    event_type: Literal["option_exercise"] = "option_exercise"
    holder_id: str
    option_grant_id: str
    shares_exercised: Decimal
    exercise_price: Decimal
    resulting_share_class_id: str  # Usually "common"

    def apply(self, snapshot: CapTableSnapshot) -> None:
        # Reduce option pool
        snapshot.reduce_option_pool(self.shares_exercised)
        # Issue common shares
        snapshot.add_or_update_position(
            Position(
                holder_id=self.holder_id,
                share_class_id=self.resulting_share_class_id,
                shares=self.shares_exercised,
                acquisition_date=self.event_date,
                cost_basis=self.exercise_price * self.shares_exercised,
            )
        )

class RoundClosingEvent(CapTableEvent):
    """
    A financing round closes.

    This is a composite event that may trigger:
    - SAFE/convertible conversions
    - New share issuances
    - Option pool creation
    - Warrant issuances
    """
    event_type: Literal["round_closing"] = "round_closing"
    round_id: str
    round_name: str  # "Seed", "Series A", etc.
    instruments: List[Instrument]  # SAFEs, priced equity, etc.
    safe_conversions: List[SAFEConversionEvent] = []
    share_issuances: List[ShareIssuanceEvent] = []
    option_pool_created: Optional[OptionPoolCreation] = None
    warrants_issued: List[WarrantIssuance] = []

    def apply(self, snapshot: CapTableSnapshot) -> None:
        # Step 1: Convert SAFEs/convertibles
        for conversion in self.safe_conversions:
            conversion.apply(snapshot)

        # Step 2: Issue new shares
        for issuance in self.share_issuances:
            issuance.apply(snapshot)

        # Step 3: Create option pool
        if self.option_pool_created:
            self.option_pool_created.apply(snapshot)

        # Step 4: Issue warrants
        for warrant in self.warrants_issued:
            warrant.apply(snapshot)
```

### Cap Table Snapshot

**Snapshot = point-in-time state computed from events**

```python
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class Position:
    """A holder's position in a specific share class."""
    holder_id: str
    share_class_id: str
    shares: Decimal
    acquisition_date: date
    cost_basis: Optional[Decimal] = None
    vesting_schedule_id: Optional[str] = None

    # For options/warrants
    is_option: bool = False
    exercise_price: Optional[Decimal] = None
    expiration_date: Optional[date] = None

@dataclass
class CapTableSnapshot:
    """Point-in-time cap table state."""
    as_of_date: date
    positions: List[Position] = field(default_factory=list)
    share_classes: Dict[str, ShareClass] = field(default_factory=dict)
    total_shares_outstanding: Decimal = Decimal("0")
    option_pool_available: Decimal = Decimal("0")

    def add_or_update_position(self, position: Position) -> None:
        """Add a new position or update existing."""
        # Find existing position for this holder + share class
        existing = next(
            (p for p in self.positions
             if p.holder_id == position.holder_id
             and p.share_class_id == position.share_class_id),
            None
        )

        if existing:
            existing.shares += position.shares
        else:
            self.positions.append(position)

        self.total_shares_outstanding += position.shares

    def ownership_percentage(self, holder_id: str, fully_diluted: bool = False) -> Decimal:
        """Calculate ownership % for a holder."""
        holder_shares = sum(
            p.shares for p in self.positions
            if p.holder_id == holder_id and not p.is_option
        )

        if fully_diluted:
            total = self.total_shares_outstanding + self.option_pool_available
        else:
            total = self.total_shares_outstanding

        return holder_shares / total if total > 0 else Decimal("0")

    def get_positions_by_class(self, share_class_id: str) -> List[Position]:
        """Get all positions for a specific share class."""
        return [p for p in self.positions if p.share_class_id == share_class_id]
```

### Computing Snapshots

```python
class CapTable:
    """Event-sourced cap table."""

    def __init__(
        self,
        company_name: str,
        events: List[CapTableEvent],
        share_classes: Dict[str, ShareClass],
    ):
        self.company_name = company_name
        self.events = sorted(events, key=lambda e: e.event_date)
        self.share_classes = share_classes

    def snapshot(self, as_of_date: date) -> CapTableSnapshot:
        """
        Compute cap table state at a specific date.

        This is the CORE OPERATION of the event-sourced model.
        """
        snapshot = CapTableSnapshot(
            as_of_date=as_of_date,
            share_classes=self.share_classes,
        )

        # Replay events chronologically up to as_of_date
        for event in self.events:
            if event.event_date <= as_of_date:
                event.apply(snapshot)

        return snapshot

    def current_snapshot(self) -> CapTableSnapshot:
        """Get current cap table state (all events applied)."""
        return self.snapshot(date.today())

    def dilution_analysis(self, from_date: date, to_date: date) -> DilutionReport:
        """Analyze dilution between two dates."""
        before = self.snapshot(from_date)
        after = self.snapshot(to_date)

        return DilutionReport.compare(before, after)
```

---

## Schema Design

### Core Principles

1. **Rounds ≠ Share Classes**
   - A round is a financing transaction/event
   - A round creates one or more share classes
   - Example: Series A round creates "Series A Preferred" share class + warrants

2. **Instrument Types Use Discriminated Unions**
   - SAFEInstrument, PricedRoundInstrument, ConvertibleNoteInstrument
   - Each has exactly the fields it needs
   - Type system prevents invalid states

3. **Share Classes Model Economic Rights**
   - Liquidation preferences
   - Participation rights
   - Conversion rights
   - Anti-dilution protection
   - Voting rights

4. **Positions Track Holder Ownership**
   - Who owns how many shares of what class
   - When acquired, at what price
   - Vesting schedule (if applicable)

### Schema Hierarchy

```
CapTable (root)
├── Company Info (name, currency)
├── Events[] (chronological history)
│   ├── ShareIssuanceEvent
│   ├── RoundClosingEvent
│   ├── ConversionEvent
│   └── ...
├── ShareClasses{} (share class definitions)
│   └── ShareClass
│       ├── LiquidationPreference
│       ├── ParticipationRights
│       ├── ConversionRights
│       └── AntiDilutionProtection
└── (State is computed via snapshot())

Snapshot (computed)
├── as_of_date
├── Positions[]
│   └── Position (holder + share_class + shares + metadata)
├── total_shares_outstanding
└── option_pool_available
```

### Detailed Schema Definitions

See [schema_design.md](schema_design.md) for complete Pydantic model definitions.

**Key Models:**

- **CapTable**: Event store + share class definitions
- **CapTableEvent**: Base class for all events
- **Instrument** (union): SAFE | PricedRound | ConvertibleNote | Warrant
- **ShareClass**: Economic and voting rights
- **CapTableSnapshot**: Point-in-time state
- **Position**: Holder ownership of a share class

---

## Block Architecture

### Block Responsibilities

**Blocks are modular components that:**
1. **Compute** data in Python (business logic)
2. **Render** data to Excel (formatting, formulas)
3. **Register** named ranges for cross-references
4. **Declare** dependencies on other blocks

### Current Implemented Blocks (MVP)

- **CapTableBlock** computes three DataFrames: `cap_table_ownership` (per-holder detail with `preferred_pct` and `liquidation_preference_multiple` columns), `cap_table_by_class` (class-level aggregation), and `cap_table_summary` (totals for fully diluted shares, holders, share classes, common/preferred/option pool counts).
- **WaterfallBlock** computes `waterfall_steps`, `waterfall_by_holder`, and `waterfall_by_class`. Participation handling matches the code: participating and capped participating get double-dip distributions (capped at `cap_multiple`), non-participating automatically pick the better of liquidation preference or as-converted common, and liquidation preference amounts use cost basis when available (fallback to shares * multiple).

### Block Base Classes

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Any
import pandas as pd
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

@dataclass
class BlockOutput:
    """Output of block computation (Excel-agnostic)."""
    data: pd.DataFrame
    metadata: Dict[str, Any]
    dependencies: List[str]  # Block names this depends on

@dataclass
class RenderResult:
    """Output of block rendering (Excel-specific)."""
    sheet_name: str
    used_range: str  # e.g., "A1:F20"
    named_ranges: Dict[str, str]  # name -> cell reference
    tables: Dict[str, str]  # table name -> range

class Block(ABC):
    """Base class for all blocks."""

    @property
    @abstractmethod
    def block_name(self) -> str:
        """Unique identifier for this block."""
        pass

    @abstractmethod
    def compute(self, context: 'BlockContext') -> BlockOutput:
        """
        Compute block data in Python.

        Rules:
        - Must NOT touch Excel
        - Must be deterministic
        - Must be easily testable
        - Should use Pandas for data manipulation
        """
        pass

    @abstractmethod
    def render(
        self,
        computation: BlockOutput,
        workbook: Workbook,
        registry: 'NamedRangeRegistry',
    ) -> RenderResult:
        """
        Render computation result to Excel.

        Rules:
        - Must NOT contain business logic
        - Should use Excel Tables for dynamic ranges
        - Should register named ranges for cross-references
        - Should apply formatting (styles, colors, borders)
        """
        pass
```

### Block Context

**Context = shared state passed to all blocks during computation**

```python
@dataclass
class BlockContext:
    """Shared context for block computations."""
    cap_table: CapTable
    snapshot: CapTableSnapshot
    exit_scenarios: List[ExitScenario]
    computed_outputs: Dict[str, BlockOutput]  # Cache

    def get_output(self, block_name: str) -> BlockOutput:
        """Get computation output from another block."""
        if block_name not in self.computed_outputs:
            raise ValueError(f"Block '{block_name}' not computed yet")
        return self.computed_outputs[block_name]

    def register_output(self, block_name: str, output: BlockOutput) -> None:
        """Register this block's output for other blocks to use."""
        self.computed_outputs[block_name] = output
```

### Example Block: Current Cap Table

```python
class CurrentCapTableBlock(Block):
    """Renders current cap table ownership."""

    @property
    def block_name(self) -> str:
        return "current_cap_table"

    def compute(self, context: BlockContext) -> BlockOutput:
        """Compute ownership data."""
        snapshot = context.snapshot

        # Build DataFrame
        data = []
        for position in snapshot.positions:
            if not position.is_option:
                data.append({
                    "Holder": position.holder_id,
                    "Share Class": position.share_class_id,
                    "Shares": float(position.shares),
                    "Ownership %": float(snapshot.ownership_percentage(position.holder_id)),
                    "Cost Basis": float(position.cost_basis) if position.cost_basis else None,
                })

        df = pd.DataFrame(data)

        return BlockOutput(
            data=df,
            metadata={"as_of_date": snapshot.as_of_date},
            dependencies=[],
        )

    def render(
        self,
        computation: BlockOutput,
        workbook: Workbook,
        registry: NamedRangeRegistry,
    ) -> RenderResult:
        """Render to Excel sheet."""
        # Create sheet
        sheet = workbook.create_sheet(title="Cap Table")

        # Write headers
        headers = ["Holder", "Share Class", "Shares", "Ownership %", "Cost Basis"]
        for col_idx, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=col_idx)
            cell.value = header
            cell.font = Font(bold=True)

        # Write data
        df = computation.data
        for row_idx, row_data in enumerate(df.itertuples(index=False), start=2):
            for col_idx, value in enumerate(row_data, start=1):
                sheet.cell(row=row_idx, column=col_idx).value = value

        # Create Excel Table
        table_ref = f"A1:E{len(df) + 1}"
        table = Table(displayName="CapTable", ref=table_ref)
        sheet.add_table(table)

        # Register named range for total shares
        total_shares_cell = f"C{len(df) + 2}"
        sheet[total_shares_cell].value = f"=SUM(CapTable[Shares])"
        registry.register("TotalShares", "Cap Table", total_shares_cell)

        return RenderResult(
            sheet_name="Cap Table",
            used_range=table_ref,
            named_ranges={"TotalShares": total_shares_cell},
            tables={"CapTable": table_ref},
        )
```

### Block Dependency Graph

**Blocks may depend on other blocks' computations.**

```python
class WaterfallBlock(Block):
    """Distributes exit proceeds using waterfall logic."""

    @property
    def block_name(self) -> str:
        return "waterfall"

    def compute(self, context: BlockContext) -> BlockOutput:
        # Depends on cap table data
        cap_table_output = context.get_output("current_cap_table")

        # Compute waterfall
        waterfall_df = self._calculate_waterfall(
            positions=context.snapshot.positions,
            share_classes=context.snapshot.share_classes,
            exit_value=context.exit_scenarios[0].exit_value,
        )

        return BlockOutput(
            data=waterfall_df,
            metadata={"exit_scenario_id": context.exit_scenarios[0].id},
            dependencies=["current_cap_table"],  # ← Declares dependency
        )

    def _calculate_waterfall(self, positions, share_classes, exit_value):
        """Waterfall calculation logic (see Waterfall section)."""
        # ... implementation
        pass
```

**Dependency Resolution:**

```python
class BlockOrchestrator:
    """Manages block execution order based on dependencies."""

    def __init__(self, blocks: List[Block]):
        self.blocks = {b.block_name: b for b in blocks}
        self.dependency_graph = self._build_graph()

    def _build_graph(self) -> Dict[str, List[str]]:
        """Build dependency graph."""
        graph = {}
        for block in self.blocks.values():
            # Compute to discover dependencies
            # (In practice, blocks should declare dependencies statically)
            graph[block.block_name] = block.dependencies
        return graph

    def execution_order(self) -> List[str]:
        """
        Topological sort to determine execution order.

        Ensures blocks are computed before their dependents.
        """
        visited = set()
        order = []

        def visit(block_name: str):
            if block_name in visited:
                return
            visited.add(block_name)

            for dependency in self.dependency_graph.get(block_name, []):
                visit(dependency)

            order.append(block_name)

        for block_name in self.blocks:
            visit(block_name)

        return order
```

---

## Excel Rendering Strategy

### Named Ranges

**Purpose:** Enable cross-sheet references that are maintainable.

```python
class NamedRangeRegistry:
    """Central registry for named ranges in the workbook."""

    def __init__(self, workbook: Workbook):
        self.workbook = workbook
        self.ranges: Dict[str, str] = {}

    def register(self, name: str, sheet_name: str, cell_ref: str, scope: str = "workbook") -> None:
        """
        Register a named range.

        Args:
            name: Name for the range (e.g., "TotalShares")
            sheet_name: Sheet containing the range
            cell_ref: Cell reference (e.g., "C10" or "A1:C10")
            scope: "workbook" or sheet name for sheet-scoped names
        """
        full_ref = f"'{sheet_name}'!{cell_ref}"

        if scope == "workbook":
            self.workbook.defined_names.append(
                DefinedName(name=name, attr_text=full_ref)
            )
        else:
            # Sheet-scoped name
            sheet = self.workbook[sheet_name]
            sheet.defined_names.append(
                DefinedName(name=name, attr_text=full_ref, localSheetId=sheet._id)
            )

        self.ranges[name] = full_ref

    def get_formula_ref(self, name: str) -> str:
        """Get formula reference for a named range."""
        return name  # Excel resolves named ranges automatically
```

**Usage:**

```python
# In CapTableBlock.render():
registry.register("TotalShares", "Cap Table", "C50")

# In WaterfallBlock.render():
formula = f"=A2 / TotalShares"  # References cap table total
sheet["D2"].value = formula
```

### Excel Tables

**Purpose:** Dynamic ranges that expand automatically.

```python
from openpyxl.worksheet.table import Table, TableStyleInfo

def create_table(sheet: Worksheet, data_range: str, table_name: str) -> None:
    """Create an Excel Table with structured references."""

    table = Table(displayName=table_name, ref=data_range)

    # Add a table style
    style = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    table.tableStyleInfo = style

    sheet.add_table(table)

# Usage:
create_table(sheet, "A1:E20", "CapTable")

# Now formulas can use structured references:
sheet["F2"].value = "=[@Shares] / SUM(CapTable[Shares])"
```

**Benefits:**
- Formulas auto-update when rows added/removed
- More readable than cell references
- Works with filters and sorts

---

## Computation vs Rendering Separation

### Why This Matters

**Problem:** Mixing computation and rendering makes testing impossible.

```python
# ❌ BAD: Can't test without Excel
def generate_waterfall(sheet: Worksheet, exit_value: Decimal):
    # Business logic mixed with Excel code
    for holder in holders:
        proceeds = calculate_proceeds(holder, exit_value)
        sheet.cell(row, col).value = proceeds
```

**Solution:** Separate concerns.

```python
# ✅ GOOD: Computation is testable
def compute_waterfall(positions, exit_value) -> pd.DataFrame:
    """Pure Python - no Excel dependency."""
    data = []
    for position in positions:
        proceeds = calculate_proceeds(position, exit_value)
        data.append({"Holder": position.holder_id, "Proceeds": proceeds})
    return pd.DataFrame(data)

# ✅ GOOD: Rendering is simple
def render_waterfall(df: pd.DataFrame, sheet: Worksheet):
    """Only handles Excel formatting."""
    for idx, row in df.iterrows():
        sheet.cell(idx + 2, 1).value = row["Holder"]
        sheet.cell(idx + 2, 2).value = row["Proceeds"]
```

### Testing Strategy

**Computation tests:**
```python
def test_waterfall_computation():
    """Test business logic without Excel."""
    positions = [
        Position(holder_id="A", share_class_id="common", shares=Decimal("100")),
        Position(holder_id="B", share_class_id="preferred", shares=Decimal("50")),
    ]

    df = compute_waterfall(positions, exit_value=Decimal("1000000"))

    assert df.loc[df["Holder"] == "A", "Proceeds"].iloc[0] == Decimal("666666.67")
    assert df.loc[df["Holder"] == "B", "Proceeds"].iloc[0] == Decimal("333333.33")
```

**Rendering tests:**
```python
def test_waterfall_rendering():
    """Test Excel output."""
    df = pd.DataFrame({"Holder": ["A", "B"], "Proceeds": [100, 200]})
    workbook = Workbook()
    sheet = workbook.create_sheet("Test")

    render_waterfall(df, sheet)

    assert sheet["A2"].value == "A"
    assert sheet["B2"].value == 100
    # Verify formulas, formatting, etc.
```

---

## Dependency Management

See [Block Dependency Graph](#block-dependency-graph) section above.

**Key Points:**
- Blocks declare dependencies explicitly
- Orchestrator computes execution order (topological sort)
- Blocks access dependency outputs via context
- Circular dependencies are detected and rejected

---

## Formula Generation

### Strategy

**Goal:** Generate formulas that are:
1. **Correct:** Calculate the right values
2. **Maintainable:** Use named ranges and table references
3. **Transparent:** Users can see and understand formulas
4. **Dynamic:** Automatically adjust to data changes

### Formula Helpers

```python
class FormulaBuilder:
    """Helper for building Excel formulas."""

    @staticmethod
    def sum_column(table_name: str, column_name: str) -> str:
        """SUM of a table column."""
        return f"=SUM({table_name}[{column_name}])"

    @staticmethod
    def ownership_percentage(shares_cell: str, total_named_range: str) -> str:
        """Calculate ownership percentage."""
        return f"={shares_cell}/{total_named_range}"

    @staticmethod
    def liquidation_preference(investment: Decimal, multiple: Decimal) -> str:
        """Liquidation preference formula."""
        return f"={float(investment)}*{float(multiple)}"

    @staticmethod
    def moic(proceeds_cell: str, investment_cell: str) -> str:
        """Multiple on Invested Capital."""
        return f"={proceeds_cell}/{investment_cell}"

    @staticmethod
    def irr(cash_flows_range: str) -> str:
        """Internal Rate of Return."""
        return f"=IRR({cash_flows_range})"
```

### Waterfall Formulas

Waterfall logic is too complex for a single formula. Use helper columns:

```
| Holder | Class | Liquidation Pref | Participation | Proceeds |
|--------|-------|------------------|---------------|----------|
| A      | Pref  | =investment*1x   | =IF(...)      | =SUM(...)|
| B      | Common| 0                | =pro_rata     | =...     |
```

See detailed waterfall implementation in [waterfall.md](waterfall.md).

---

## Validation Strategy

### Two-Level Validation

**Level 1: Pydantic Field Validators**
- Enforce field-level constraints
- Data type validation
- Required fields
- Simple business rules

**Level 2: Domain Validators**
- Cross-entity validation
- Referential integrity
- Sum checks
- Complex business rules

### Example: Pydantic Validators

```python
from pydantic import BaseModel, field_validator, model_validator

class ShareClass(BaseModel):
    id: str
    participation: Literal["non_participating", "participating", "capped_participating"]
    participation_cap_multiple: Optional[Decimal] = None

    @model_validator(mode="after")
    def validate_participation_cap(self):
        """If capped participating, must have cap multiple."""
        if self.participation == "capped_participating":
            if self.participation_cap_multiple is None:
                raise ValueError("Capped participating requires participation_cap_multiple")
        return self
```

### Example: Domain Validators

```python
class CapTableValidator:
    """Validates cap table consistency."""

    @staticmethod
    def validate_snapshot(snapshot: CapTableSnapshot) -> ValidationResult:
        """Validate a cap table snapshot."""
        errors = []

        # Check 1: Total shares matches sum of positions
        position_total = sum(p.shares for p in snapshot.positions if not p.is_option)
        if position_total != snapshot.total_shares_outstanding:
            errors.append(
                f"Position total ({position_total}) != "
                f"total shares outstanding ({snapshot.total_shares_outstanding})"
            )

        # Check 2: All positions reference valid share classes
        valid_classes = set(snapshot.share_classes.keys())
        for position in snapshot.positions:
            if position.share_class_id not in valid_classes:
                errors.append(
                    f"Position references invalid share class: {position.share_class_id}"
                )

        # Check 3: Ownership percentages sum to ~100%
        total_ownership = sum(
            snapshot.ownership_percentage(p.holder_id)
            for p in snapshot.positions
        )
        if not (Decimal("0.99") <= total_ownership <= Decimal("1.01")):
            errors.append(
                f"Ownership percentages sum to {total_ownership*100}%, expected ~100%"
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors)
```

---

## Extensibility Patterns

### Adding New Instrument Types

**Current instruments:** SAFE, Priced Round, Convertible Note, Warrant

**To add a new instrument (e.g., "KISS" - Keep It Simple Security):**

1. **Define the instrument:**
```python
class KISSInstrument(BaseModel):
    type: Literal["KISS"] = "KISS"
    investment_amount: Decimal
    valuation_cap: Optional[Decimal]
    discount_rate: Optional[Decimal]
    interest_rate: Decimal  # KISS accrues interest

    @model_validator(mode="after")
    def validate(self):
        # KISS validation rules
        pass
```

2. **Add to discriminated union:**
```python
Instrument = Annotated[
    SAFEInstrument | PricedRoundInstrument | ConvertibleNoteInstrument | KISSInstrument,
    Field(discriminator="type")
]
```

3. **Implement conversion logic:**
```python
class KISSConversionHandler:
    def convert(self, kiss: KISSInstrument, round: PricedRoundInstrument) -> ShareIssuanceEvent:
        # Calculate shares issued based on KISS terms
        pass
```

**That's it.** Type system ensures no existing code breaks.

### Adding New Block Types

**To add a new block (e.g., "Vesting Schedule Block"):**

1. **Subclass Block:**
```python
class VestingScheduleBlock(Block):
    @property
    def block_name(self) -> str:
        return "vesting_schedule"

    def compute(self, context: BlockContext) -> BlockOutput:
        # Compute vesting data
        pass

    def render(self, computation: BlockOutput, workbook: Workbook, registry: NamedRangeRegistry) -> RenderResult:
        # Render to Excel
        pass
```

2. **Register with orchestrator:**
```python
orchestrator = BlockOrchestrator([
    CurrentCapTableBlock(),
    WaterfallBlock(),
    VestingScheduleBlock(),  # ← New block
])
```

3. **Other blocks can now depend on it:**
```python
class SomeOtherBlock(Block):
    def compute(self, context: BlockContext) -> BlockOutput:
        vesting_data = context.get_output("vesting_schedule")
        # Use vesting data
        pass
```

### Adding New Event Types

**To add a new event (e.g., "Stock Split Event"):**

1. **Define the event:**
```python
class StockSplitEvent(CapTableEvent):
    event_type: Literal["stock_split"] = "stock_split"
    split_ratio: Decimal  # 2.0 for 2-for-1 split
    affected_share_class_id: str

    def apply(self, snapshot: CapTableSnapshot) -> None:
        for position in snapshot.positions:
            if position.share_class_id == self.affected_share_class_id:
                position.shares *= self.split_ratio
                if position.cost_basis:
                    position.cost_basis /= self.split_ratio
```

2. **Use it:**
```python
events = [
    ShareIssuanceEvent(...),
    StockSplitEvent(event_date=date(2024, 6, 1), split_ratio=Decimal("2.0"), ...),
    RoundClosingEvent(...),
]
```

Event sourcing handles the rest automatically.

---

## Design Decisions & Trade-offs

### Event Sourcing

**Decision:** Use event sourcing for cap table state.

**Pros:**
- Full audit trail
- Time travel (historical queries)
- Debugging (replay events to understand state)
- Flexibility (add new event types without migration)

**Cons:**
- More complex than storing state directly
- Slightly slower (need to replay events)
- Requires careful event design

**Trade-off:** Complexity is worth it for cap table domain. Historical analysis is critical.

### Discriminated Unions vs Optional Fields

**Decision:** Use discriminated unions for instrument types.

**Pros:**
- Type safety (mypy catches errors)
- Self-documenting (each type has exact fields)
- No invalid states

**Cons:**
- More verbose (separate class per type)
- Slightly more code

**Trade-off:** Type safety is worth the verbosity. Financial calculations require correctness.

### Computation/Rendering Separation

**Decision:** Separate business logic from Excel rendering.

**Pros:**
- Testability (test without Excel)
- Reusability (use in API, CLI, web)
- Performance (compute once, render to multiple formats)

**Cons:**
- More abstraction layers
- Need to pass data between layers

**Trade-off:** Testability and reusability are critical. Abstraction is manageable.

### Excel Tables vs Hardcoded Ranges

**Decision:** Always use Excel Tables and named ranges.

**Pros:**
- Dynamic (formulas auto-update)
- Readable (`CapTable[Shares]` > `B2:B50`)
- Maintainable (cross-sheet references by name)

**Cons:**
- Slightly more code to set up
- Need to manage table/name registry

**Trade-off:** Maintainability is critical. Extra setup is worth it.

### Walking Skeleton Approach

**Decision:** Build minimal end-to-end first, then iterate.

**Pros:**
- Validates architecture early
- Proves integration works
- Enables early feedback

**Cons:**
- Tempting to cut corners
- May need refactoring if design is wrong

**Trade-off:** Must design schema correctly first. Then walking skeleton de-risks the rest.

---

## Next Steps

1. **Implement Pydantic schemas** based on this architecture
2. **Build block base classes** and infrastructure
3. **Create walking skeleton** (2 founders + 1 round + simple waterfall)
4. **Iterate** to add complexity

See [implementation_plan.md](implementation_plan.md) for detailed roadmap.

---

**Document Version:** 1.0
**Last Updated:** 2025-11-13
**Status:** Approved - Ready for Implementation
