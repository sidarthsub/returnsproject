# Cap Table Excel Renderer

Professional Excel cap table generation for venture-backed companies.

> **📘 New: Interactive Features!** See [INTERACTIVE_CAP_TABLE.md](INTERACTIVE_CAP_TABLE.md) for the latest interactive Excel features including:
> - 🔵 Visual input cell formatting (blue = editable)
> - 🔒 Protected formulas (prevents accidental changes)
> - 📝 Helpful hover comments (built-in guidance)
> - ✅ Production ready with 87% test coverage

## Overview

The `RoundSheetRenderer` generates clean, formulaic Excel cap tables with:
- **One sheet per snapshot** (e.g., Post-Seed, Post-Series-A)
- **Columns organized by round** (Common, Seed $, Seed #, Series A $, Series A #, etc.)
- **Interactive inputs** - Blue cells = editable, white = calculated
- **Protected formulas** - Can't accidentally break calculations
- **Built-in guidance** - Hover over blue cells for help
- **Fully formulaic** - Edit pre-money valuations and see shares/ownership recalculate
- **Block-verified** - Excel calculations match domain model computations

## Quick Start

```python
from captable_excel import RoundSheetRenderer
from captable_domain.schemas import CapTable, CapTableSnapshotCFG, WorkbookCFG
from datetime import date

# Build your cap table
cap_table = CapTable(company_name="MyStartup")
# ... add events ...

# Configure snapshots
post_seed = CapTableSnapshotCFG(
    cap_table=cap_table,
    label="Post-Seed",
    as_of_date=date(2024, 3, 31)
)

post_series_a = CapTableSnapshotCFG(
    cap_table=cap_table,
    label="Post-Series-A",
    as_of_date=None  # Current
)

# Render Excel
cfg = WorkbookCFG(cap_table_snapshots=[post_seed, post_series_a])
renderer = RoundSheetRenderer(cfg)
renderer.render("output/cap_table.xlsx")
```

## Excel Structure

### Sheet Layout

```
Row 1:   Cap Table - [Snapshot Label]
Row 3:   Headers
Row 4+:  Common shareholders
Row N:   [EMPTY ROW]
Row N+1: Allocated Options
Row N+2: ESOP Available
Row N+3: [EMPTY ROW]
Row N+4: "Preferred Rounds" header
Row N+5+: Preferred investors (by round)
Row M:   Totals
Row M+1: Starting Shares (pre-round)
Row M+2: Pre-Money Valuation
Row M+3: Price per Share
Row M+4: Post-Money Valuation
```

### Columns

```
A:   Holder Name
B:   Common # Shares
C:   [EMPTY GAP]
D:   [Round1] $ Invested
E:   [Round1] Preferred Shares
F:   [Round1] Option Pool
G:   [EMPTY GAP]
H:   [Round2] $ Invested
I:   [Round2] Preferred Shares
J:   [Round2] Option Pool
K:   [EMPTY GAP]
...
N:   Total Shares (FD) - consolidated fully diluted shares
N+1: % FD (fully diluted %)
```

**Note:**
- Each preferred round has its own option pool column, as each round may include option pool expansion
- Option pool is shown in two rows under the common shareholders section:
  - **Allocated Options**: Options that have been granted to employees
  - **ESOP Available**: Options still available for future grants
  - Total option pool per round = Allocated + Available
- "Total Shares (FD)" consolidates what were previously two columns ("Total Shares" and "Total FD Shares") since they represent the same value

### Formula Architecture

**Per preferred round:**
1. **Starting Shares** = Common + Option Pool + Prior Preferred Rounds
2. **Pre-Money Valuation** = Calculated from actual investment data (user can edit)
3. **Price Per Share** = Pre-Money / Starting Shares
4. **Per-Investor Shares** = Investment Amount / PPS
5. **Post-Money Valuation** = Pre-Money + Total Invested

**Per holder:**
- **Total Shares** = Sum of all share columns
- **% FD** = Total Shares / Total FD Shares
- **Totals row shows 100%** to verify ownership adds up correctly

## Features

### ✅ Professional Formatting
- **Color-coded values**:
  - Blue for user inputs (pre-money, investments)
  - Black for calculated values
  - Dark green for values carried forward from previous rounds (with comments)
- **Strategic borders**: Minimal use - header underlines, totals separators, section dividers, and valuation boxes
- **Visual spacing**:
  - Empty columns between sections (Common | GAP | Seed ($, #, Option Pool) | GAP | Series A ($, #, Option Pool) | GAP | Summary)
  - Empty rows between holder groups (common holders, option pool section, preferred rounds, totals)
  - Option pool section shows "Allocated Options" and "ESOP Available" as separate rows
- **Box around cap table**: Medium borders around entire data area with gridlines hidden
- **Header styling**: Gray backgrounds with bottom borders for clear column identification
- **Column widths**: Auto-adjusted (25 chars for names, 15 for numbers, 12 for percentages)
- **Number formatting**: Currency ($), share counts (#,##0), and percentages (0.0%)

### ✅ Clean Data Structure
- Pre-Money row only shows dollar values (not confusing share counts)
- Separate "Starting Shares" row for clarity
- No formulas in section header rows

### ✅ Intelligent Formula Scoping
- Investors only have share formulas for rounds they participated in
- Blank cells (not zeros) for non-participated rounds

### ✅ Transparency
- Total Shares column shows each holder's aggregate ownership
- % FD totals to 100% for validation
- All formulas visible for user inspection/modification

### ✅ Block-Verified Accuracy
- Excel output matches domain model calculations
- Comprehensive test suite ensures correctness

### ✅ Round Design Calculator with Allocation Modes
The Round Design Calculator drives how cap table cells are populated, allowing flexible round modeling with different allocation strategies.

**Core concept:** Cap table cells can be either:
- **Hardcoded (blue font)** - Manual entry by user
- **Formula-driven (black font)** - Calculated automatically based on allocation rules

#### Investment Allocation Modes

- **manual** (default): All investments hardcoded (blue font, user editable)
- **target_ownership**: Calculate investment needed to achieve target ownership % (formula, black font)
- **pro_rata**: Calculate investment to maintain previous round ownership % (formula, black font)
- **mixed**: Different investors use different allocation methods (per-investor configuration)

#### Option Pool Modes

- **manual** (default): Hardcoded shares (blue font, user editable)
- **expansion_pct**: Add X% more shares (formula, black font)
- **target_pct_inclusive**: X% total post-money including existing pool (formula, black font)
- **target_pct_exclusive**: X% post-money net new excluding existing pool (formula, black font)

#### Example Usage

```python
from captable_domain.schemas import CapTableSnapshotCFG, RoundCalculatorCFG

# All manual (default - backward compatible)
snap_cfg = CapTableSnapshotCFG(
    cap_table=cap_table,
    label="Post-Seed",
    round_calculator=RoundCalculatorCFG(enabled=False)
)

# Target ownership for all investors
snap_cfg = CapTableSnapshotCFG(
    cap_table=cap_table,
    label="Post-Series-A",
    round_calculator=RoundCalculatorCFG(
        enabled=True,
        investment_allocation_mode="target_ownership",
        target_ownership_pct=0.20,  # 20% target for all
        show_calculator_section=False  # Hide calculator, keep formulas
    )
)

# Pro-rata for all investors
snap_cfg = CapTableSnapshotCFG(
    cap_table=cap_table,
    label="Post-Series-A",
    round_calculator=RoundCalculatorCFG(
        enabled=True,
        investment_allocation_mode="pro_rata"
    )
)

# Mixed: some manual, some target, some pro-rata
snap_cfg = CapTableSnapshotCFG(
    cap_table=cap_table,
    label="Post-Series-A",
    round_calculator=RoundCalculatorCFG(
        enabled=True,
        investment_allocation_mode="manual",  # Default for others
        per_investor_allocation={
            "Lead Investor": "target_ownership",
            "Follow-on Fund": "pro_rata"
        },
        per_investor_target_pct={
            "Lead Investor": 0.25  # 25% target for lead
        }
    )
)

# Option pool expansion by %
snap_cfg = CapTableSnapshotCFG(
    cap_table=cap_table,
    label="Post-Series-A",
    round_calculator=RoundCalculatorCFG(
        enabled=True,
        option_pool_mode="expansion_pct",
        option_pool_expansion_pct=0.10  # Add 10% more shares
    )
)

# Option pool target % (post-money)
snap_cfg = CapTableSnapshotCFG(
    cap_table=cap_table,
    label="Post-Series-A",
    round_calculator=RoundCalculatorCFG(
        enabled=True,
        option_pool_mode="target_pct_inclusive",
        option_pool_target_pct=0.15  # 15% total post-money
    )
)
```

#### Features

- **Conditional cell population** - Cells are either hardcoded (blue) or formula-driven (black) based on allocation mode
- **Calculator section optional** - Can be shown for reference or hidden while keeping formula-driven cells
- **Per-investor configuration** - Mix and match allocation strategies for different investors
- **Iterative calculation enabled** - Handles circular dependencies (e.g., option pool % affects total shares)
- **Reverse-populated** - Formulas link to actual cap table data
- **Configurable per snapshot** - Different snapshots can use different allocation modes

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest packages/excel/tests/test_round_sheet_renderer.py -v

# Or run directly
python3 packages/excel/tests/test_round_sheet_renderer.py
```

Tests include:
1. **Block Verification** - Excel matches domain calculations
2. **Formula Structure** - Formulas are correctly formed
3. **Pre-Money Row** - Only $ values, no share counts
4. **% FD Totals** - Ownership adds to 100%
5. **Total Shares Column** - Present and correct
6. **Header Rows** - Clean, no data formulas
7. **Round Calculator** - Calculator section renders with all required fields
8. **Investor Scoping** - Formulas only for participated rounds
9. **Target Ownership Allocation** - Formula-driven investments work correctly

## Development

### File Structure

```
packages/excel/
├── src/captable_excel/
│   ├── __init__.py
│   └── round_sheet_renderer.py     # Main renderer
├── tests/
│   ├── test_round_sheet_renderer.py # Comprehensive tests
│   └── output/                      # Generated test files
└── README.md
```

### Running Tests

```bash
# Run with pytest
cd packages/excel
pytest tests/test_round_sheet_renderer.py -v

# Run standalone
python3 tests/test_round_sheet_renderer.py
```

## Implementation Details

### Key Design Decisions

1. **Formulaic by Default** - All calculations use Excel formulas (not static values) so users can modify inputs and see results update

2. **Pre-Money as Input** - Pre-money valuations are reverse-calculated from actual data and presented as editable inputs

3. **Investor-Specific Columns** - Each preferred round gets dedicated $ Invested and Preferred Shares columns

4. **Block Integration** - Leverages `CapTableBlock` for authoritative calculations, ensuring Excel matches domain logic

5. **Visual Clarity Through Formatting**:
   - **Blue font (0000FF)** - Hardcoded inputs users can edit (pre-money valuations, investment amounts, common shares, option pool)
   - **Black font (000000)** - Calculated values (PPS, post-money, total shares, % FD, derived share counts)
   - **Dark green font (006400)** - Values carried forward from previous rounds (e.g., Series A sheet shows common shares from Seed in green with comments)
   - **Strategic borders** - Not every cell has borders. Used only for:
     - Header row: bottom border for underline effect
     - Section dividers: left borders on first column of each section (Common, each Preferred, Option Pool, Summary)
     - Totals row: top and bottom borders for emphasis
     - Valuation box: thin borders around the 4-row valuation section (Starting Shares through Post-Money)
     - Outer box: medium borders around entire cap table area
   - **Gray fills** - Light gray (E0E0E0) on column headers, slightly darker (F0F0F0) on valuation rows
   - **Column and row spacing** - Empty columns and rows create visual separation between sections
   - **Hidden gridlines** - Sheet gridlines disabled for cleaner appearance

6. **Cross-Sheet Awareness**:
   - When multiple snapshots exist (e.g., Post-Seed, Post-Series-A), later sheets show ALL data from earlier rounds in dark green:
     - Common shares (from previous snapshot)
     - Previous round preferred investments
     - Previous round preferred shares
     - Previous round option pool expansions
     - Previous round pre-money valuations
   - Excel comments indicate the source sheet (e.g., "Value from Post-Seed")
   - Calculated values (PPS, post-money) remain black even for previous rounds as they're derived from formulas
   - Helps users understand which values are carried forward vs. new in each round

### Formula Examples

**Total Shares (per holder):**
```excel
=IFERROR(B4+D4+E4+G4+H4+...,0)  // Sum of Common + all Preferred Shares + all Option Pools
```

Note: Each round contributes shares and option pool separately (e.g., Seed Shares + Seed Option Pool + Series-A Shares + Series-A Option Pool)

**% FD:**
```excel
=IFERROR(G4/G12,0)  // Total Shares / Total FD Shares
```

**Per-Investor Shares:**
```excel
=IFERROR(C10/C14,0)  // Investment / PPS
```

Only added for rounds where investor has an investment amount (otherwise blank).

## Version History

**v0.1.0** - Initial release
- Round-style renderer with formulaic approach
- Block-verified accuracy
- Comprehensive test coverage
- Clean data structure with separated pre-money/starting shares rows
