# Default Configurations Guide

**Purpose:** This document specifies sensible defaults for all schemas to minimize configuration burden and enable LLM-based imports with minimal user input.

**Philosophy:**
- Defaults should represent the most common VC/startup scenario
- Optional fields should have `None` as default (explicitly opt-in to complexity)
- Boolean flags should default to the safer/simpler option
- All required fields are truly essential - everything else gets a default

---

## Base Types - No Defaults Needed

Type aliases are primitives - no configuration needed.

---

## Share Classes

### Common Stock (Default Template)
```python
ShareClass(
    id="common",  # REQUIRED
    name="Common Stock",  # REQUIRED
    share_type="common",  # REQUIRED

    # Defaults for common:
    liquidation_preference=None,  # Common has no preference
    participation_rights=None,
    conversion_rights=None,
    anti_dilution_protection=None,
    votes_per_share=Decimal("1.0"),  # DEFAULT: 1 vote per share
    created_in_round_id=None,
)
```

### Preferred Stock (Default Template)
```python
ShareClass(
    id="series_a_preferred",  # REQUIRED
    name="Series A Preferred Stock",  # REQUIRED
    share_type="preferred",  # REQUIRED

    # REQUIRED for preferred:
    liquidation_preference=LiquidationPreference(
        multiple=Decimal("1.0"),  # DEFAULT: 1x
        seniority_rank=0,  # REQUIRED (0 = highest priority)
        pari_passu_group=None,  # DEFAULT: no pari passu
    ),

    # Common defaults for preferred:
    participation_rights=ParticipationRights(
        participation_type="non_participating",  # DEFAULT: most common
        cap_multiple=None,
    ),

    conversion_rights=ConversionRights(
        converts_to_class_id="common",  # DEFAULT: convert to common
        initial_conversion_ratio=Decimal("1.0"),  # DEFAULT: 1:1
        current_conversion_ratio=Decimal("1.0"),  # DEFAULT: 1:1
        auto_convert_on_ipo=True,  # DEFAULT: auto-convert
        qualified_ipo_threshold=None,  # Optional threshold
    ),

    anti_dilution_protection=AntiDilutionProtection(
        protection_type="weighted_average_broad",  # DEFAULT: most common
    ),

    votes_per_share=Decimal("1.0"),  # DEFAULT: 1 vote per share
    created_in_round_id=None,  # Optional
)
```

**LLM Import Guidance:**
- If user says "Series A Preferred with 1x liquidation preference" → Use above defaults
- If user specifies "2x liquidation preference" → Only change `multiple` field
- If user says "participating" → Change `participation_type` only
- Seniority: Series A = rank 0, Series B = rank 1, etc.

---

## Instruments

### SAFE (Default Template)
```python
SAFEInstrument(
    type="SAFE",  # REQUIRED (discriminator)
    investment_amount=Decimal("100000"),  # REQUIRED

    # User must specify at least one:
    valuation_cap=Decimal("5000000"),  # REQUIRED or discount_rate
    discount_rate=None,  # OR this (or both)

    safe_type="post_money",  # DEFAULT: post-money (most common post-2018)
)
```

### Priced Round (Default Template)
```python
PricedRoundInstrument(
    type="priced",  # REQUIRED (discriminator)
    investment_amount=Decimal("5000000"),  # REQUIRED
    pre_money_valuation=Decimal("20000000"),  # REQUIRED
    price_per_share=Decimal("2.0"),  # REQUIRED
    shares_issued=Decimal("2500000"),  # REQUIRED
)
```

### Convertible Note (Default Template)
```python
ConvertibleNoteInstrument(
    type="convertible_note",  # REQUIRED (discriminator)
    principal_amount=Decimal("500000"),  # REQUIRED
    interest_rate=Decimal("0.05"),  # REQUIRED (5% common)
    interest_type="simple",  # DEFAULT: simple interest
    issue_date=date(2024, 1, 1),  # REQUIRED
    maturity_date=date(2026, 1, 1),  # REQUIRED (typically 2 years)

    # User must specify at least one:
    valuation_cap=Decimal("10000000"),  # REQUIRED or discount_rate
    discount_rate=None,  # OR this (or both)
)
```

### Warrant (Default Template)
```python
WarrantInstrument(
    type="warrant",  # REQUIRED (discriminator)
    shares_purchasable=Decimal("100000"),  # REQUIRED
    exercise_price=Decimal("2.0"),  # REQUIRED
    share_class_id="common",  # REQUIRED
    issue_date=date(2024, 1, 1),  # REQUIRED
    expiration_date=None,  # DEFAULT: no expiration
)
```

**LLM Import Guidance:**
- SAFE: Default to post-money with cap only (no discount) unless specified
- Priced Round: All 4 fields required, validate math
- Convertible Note: Default 5% simple interest, 2-year maturity
- Warrant: Default no expiration unless specified

---

## Events

### Share Issuance (Default Template)
```python
ShareIssuanceEvent(
    event_id="founder_grant_001",  # REQUIRED (generate UUID or descriptive)
    event_date=date(2024, 1, 1),  # REQUIRED
    holder_id="founder_alice",  # REQUIRED
    share_class_id="common",  # REQUIRED
    shares=Decimal("5000000"),  # REQUIRED

    # Defaults:
    price_per_share=None,  # DEFAULT: None (no cost basis for founder shares)
    vesting_schedule_id=None,  # DEFAULT: fully vested
    description=None,  # Optional human description
)
```

### Option Pool Creation (Default Template)
```python
OptionPoolCreation(
    event_id="pool_001",  # REQUIRED
    event_date=date(2024, 1, 1),  # REQUIRED
    shares_authorized=Decimal("2000000"),  # REQUIRED
    pool_timing="pre_money",  # DEFAULT: pre-money (most common)

    # Conditionally required:
    target_percentage=None,  # Only if pool_timing="target_post_money"

    share_class_id="common",  # DEFAULT: options are for common stock
)
```

### Round Closing (Default Template)
```python
RoundClosingEvent(
    event_id="series_a_closing",  # REQUIRED
    event_date=date(2024, 6, 15),  # REQUIRED
    round_id="series_a",  # REQUIRED
    round_name="Series A",  # REQUIRED
    instruments=[...],  # REQUIRED: List of instruments in round

    # Defaults (all optional):
    safe_conversions=[],  # DEFAULT: empty (no SAFEs converting)
    share_issuances=[],  # DEFAULT: empty (built from instruments)
    option_pool_created=None,  # DEFAULT: no pool creation
    warrants_issued=[],  # DEFAULT: empty (no warrants)
)
```

**LLM Import Guidance:**
- Share Issuance: Founder grants have no price_per_share
- Option Pool: Default pre-money unless specified otherwise
- Round Closing: Can be auto-constructed from instruments list
- Event IDs: Generate descriptive IDs like "founder_alice_initial" or UUIDs

---

## Cap Table

### Cap Table (Default Template)
```python
CapTable(
    company_name="Acme Corp",  # REQUIRED

    # Defaults:
    base_currency="USD",  # DEFAULT: USD
    events=[],  # DEFAULT: empty (add events with add_event())
    share_classes={},  # DEFAULT: empty (add classes manually)
    exchange_rates={},  # DEFAULT: empty (single currency)
)
```

**LLM Import Guidance:**
- Always create common stock share class first
- Add events in chronological order
- Exchange rates only needed for multi-currency (rare)

---

## Returns & Exit Scenarios

### Exit Scenario (Simplified - Default Template)
```python
ExitScenario(
    id="base_case",  # REQUIRED
    label="Base Case",  # REQUIRED
    exit_value=Decimal("50000000"),  # REQUIRED
    exit_type="M&A",  # REQUIRED: "M&A" | "IPO" | "secondary"

    # Defaults:
    exit_date=None,  # Optional (for IRR)
    transaction_costs_percentage=Decimal("0.03"),  # DEFAULT: 3% (common for M&A)
    management_carveout_percentage=None,  # DEFAULT: None (no carveout)

    # IPO-specific (required if exit_type="IPO"):
    float_percentage=None,  # REQUIRED for IPO
    lockup_period_days=180,  # DEFAULT: 180 days (common)
)
```

### Returns Config (Simplified - Default Template)
```python
ReturnsCFG(
    scenarios=[...],  # REQUIRED: List of ExitScenario

    # Defaults:
    include_irr=False,  # DEFAULT: False (requires dates)
    include_moic=True,  # DEFAULT: True (always useful)
    show_by_holder=True,  # DEFAULT: True
    show_by_share_class=True,  # DEFAULT: True
    show_waterfall_steps=True,  # DEFAULT: True (educational)
)
```

**LLM Import Guidance:**
- Default 3 scenarios: "Conservative" ($25M), "Base Case" ($50M), "Upside" ($100M)
- M&A: 3% transaction costs
- IPO: 20% float, 180-day lockup, 7% transaction costs
- Management carveout: Only add if explicitly mentioned (5-10% typical)

---

## Workbook Config

### Workbook (Simplified - Default Template)
```python
WorkbookCFG(
    cap_table_snapshots=[
        CapTableSnapshotCFG(
            cap_table=cap_table,  # REQUIRED
            label="Current",  # REQUIRED
            as_of_date=None,  # DEFAULT: None = current (all events)
        )
    ],  # REQUIRED

    # Optional waterfall analyses:
    waterfall_analyses=None,  # DEFAULT: None (just show cap table)

    # Sheet inclusion (all default True):
    include_audit_sheet=True,
    include_summary_sheet=True,
    include_events_sheet=True,
    include_share_classes_sheet=True,
)
```

**LLM Import Guidance:**
- Single snapshot by default (current state)
- Only add waterfall if user mentions "returns" or "exit scenarios"
- All sheets included by default (users can filter in Excel)

---

## Summary: Minimal Required Fields for LLM Import

### Absolute Minimum Cap Table
```python
# 1. Create cap table
cap_table = CapTable(company_name="Acme Corp")

# 2. Add common stock
cap_table.share_classes["common"] = ShareClass(
    id="common",
    name="Common Stock",
    share_type="common"
)

# 3. Add founder shares
cap_table.add_event(ShareIssuanceEvent(
    event_id="founder_001",
    event_date=date(2024, 1, 1),
    holder_id="founder_alice",
    share_class_id="common",
    shares=Decimal("10000000")
))

# 4. Create workbook
workbook = WorkbookCFG(
    cap_table_snapshots=[
        CapTableSnapshotCFG(
            cap_table=cap_table,
            label="Current"
        )
    ]
)
```

### Typical Startup (Post-Seed)
```python
# 1. Cap table with 2 share classes
cap_table = CapTable(company_name="Acme Corp")

# Common stock
cap_table.share_classes["common"] = ShareClass(
    id="common", name="Common Stock", share_type="common"
)

# Seed preferred
cap_table.share_classes["seed_preferred"] = ShareClass(
    id="seed_preferred",
    name="Seed Preferred",
    share_type="preferred",
    liquidation_preference=LiquidationPreference(
        multiple=Decimal("1.0"),
        seniority_rank=0
    )
)

# 2. Events: Founders + Seed Round
cap_table.add_event(ShareIssuanceEvent(...))  # Founders
cap_table.add_event(OptionPoolCreation(...))  # 20% option pool
cap_table.add_event(RoundClosingEvent(...))   # Seed round

# 3. Workbook with returns
workbook = WorkbookCFG(
    cap_table_snapshots=[
        CapTableSnapshotCFG(cap_table=cap_table, label="Post-Seed")
    ],
    waterfall_analyses=[
        WaterfallAnalysisCFG(
            cap_table_snapshot=...,
            returns_cfg=ReturnsCFG(
                scenarios=[
                    ExitScenario(id="base", label="Base", exit_value=Decimal("50000000"), exit_type="M&A")
                ]
            ),
            label="Returns Analysis"
        )
    ]
)
```

---

## Key Principles for LLM Imports

1. **Generate Event IDs:** Use descriptive IDs like `"founder_alice_initial"` or UUIDs
2. **Chronological Order:** Add events in date order (cap_table.add_event() auto-sorts)
3. **Share Classes First:** Define all share classes before adding events
4. **Defaults Are Safe:** Every default is the most common/safe choice
5. **Validation Helps:** Pydantic will catch missing required fields with clear errors
6. **Optional = Rare:** If a field is optional, it's probably not needed for MVP

---

## What We Removed (Post-Simplification)

These fields were deemed too niche for MVP:

### From Instruments:
- SAFE: `mfn_enabled`, `pro_rata_side_letter`
- Convertible Note: `interest_payment` variations
- Priced Round: `warrant_coverage_percentage`

### From Share Classes:
- `DividendRights` class (entire class removed)
- Anti-dilution: `carve_out_option_pool`, `carve_out_shares`

### From Exit Scenarios:
- `transaction_costs_fixed`, `management_carveout_fixed`
- `management_carveout_recipients`
- `greenshoe_percentage`, `escrow_percentage`, `earn_out_percentage`

### From Workbook Config:
- `formatting_theme`, `freeze_panes`, `add_filters`
- `use_named_ranges`, `use_tables`, `include_formulas`
- `fully_diluted_ownership`, `compare_snapshots_side_by_side`, `include_charts`

### From Returns Config:
- `include_sensitivity`, `sensitivity_range`
- `include_unrealized_gains`

These can be added back in Phase 2 if needed.
