# Implementation Status & Documentation Alignment

**Last Updated:** 2025-12-02
**Purpose:** Track what's actually implemented vs what's documented

---

## ✅ Fully Implemented Features

### Core Domain Models

**ShareClass** ([share_classes.py](share_classes.py:226-320))
- ✅ LiquidationPreference (multiple, seniority_rank, pari_passu_group)
- ✅ ParticipationRights (non_participating, participating, capped_participating)
- ✅ ConversionRights (converts_to_class_id, ratios, auto-convert)
- ✅ AntiDilutionProtection (none, weighted_average_broad/narrow, full_ratchet)
- ❌ **Voting rights REMOVED** (not needed for returns modeling)
- ❌ **DividendRights REMOVED** (rare for VC-backed startups, deferred to Phase 2)

**Instruments** ([instruments.py](instruments.py))
- ✅ SAFEInstrument (post_money/pre_money, cap, discount)
- ✅ PricedRoundInstrument (investment, pre_money, price, shares)
- ✅ ConvertibleNoteInstrument (principal, interest_rate, maturity, cap, discount)
- ✅ WarrantInstrument (shares_purchasable, exercise_price, expiration)
- ❌ MFN (Most Favored Nation) flag removed from SAFE (MVP simplification)
- ❌ Pro-rata side letters removed from SAFE (MVP simplification)

**Events** ([events.py](events.py))
- ✅ ShareIssuanceEvent
- ✅ ShareTransferEvent
- ✅ ConversionEvent
- ✅ OptionExerciseEvent
- ✅ RoundClosingEvent
- ✅ SAFEConversionEvent
- ✅ OptionPoolCreation (pre_money, post_money, target_post_money)
- ✅ WarrantIssuance

**Cap Table & Snapshots** ([cap_table.py](cap_table.py))
- ✅ Event-sourced CapTable
- ✅ CapTableSnapshot with fully_diluted_shares property
- ✅ Option pool tracking (authorized, available)
- ✅ Multi-currency support (base_currency, exchange_rates)
- ❌ **total_voting_shares property REMOVED**

**Returns & Waterfall** ([returns.py](returns.py), [waterfall.py](waterfall.py))
- ✅ ExitScenario (M&A, IPO, secondary)
- ✅ Transaction costs (percentage-based)
- ✅ Management carveouts (percentage-based)
- ✅ IPO float and lockup periods
- ✅ ReturnsCFG (include_moic, include_irr)
- ✅ Waterfall computation (liquidation preferences by seniority)
- ✅ **Participation rights FULLY implemented** (participating, capped_participating, non_participating)

### Blocks Architecture

**CapTableBlock** ([cap_table.py](cap_table.py:19-237))
- ✅ Converts CapTableSnapshot → DataFrames
- ✅ Outputs:
  - `cap_table_ownership`: Per-holder breakdown with **preferred_pct** column
  - `cap_table_by_class`: Aggregated by share class
  - `cap_table_summary`: High-level metrics
- ❌ **Voting columns REMOVED** (votes, voting_pct)
- ✅ **NEW: preferred_pct column** - shows % of preferred shares owned

**WaterfallBlock** ([waterfall.py](waterfall.py))
- ✅ Liquidation preference waterfall by seniority (using cost_basis * multiple)
- ✅ Pro-rata distribution within seniority ranks (pari passu)
- ✅ Common distribution (as-converted basis)
- ✅ Transaction costs deduction
- ✅ Management carveout deduction
- ✅ **Participation rights FULLY implemented:**
  - ✅ Participating preferred (double dip: liquidation preference + pro-rata)
  - ✅ Capped participating (double dip with cap at cap_multiple * investment)
  - ✅ Non-participating (automatic choice of better: preference OR as-converted)

**ReturnsBlock** ([returns.py](returns.py))
- ✅ MOIC calculation
- ✅ IRR calculation (if dates provided)
- ✅ Per-holder returns
- ✅ Per-class returns
- ✅ Summary statistics

**Block Execution** ([base.py](base.py))
- ✅ Topological sort for dependency resolution
- ✅ BlockExecutor with validation
- ✅ BlockContext for shared state
- ✅ Input/output validation

---

## ⚠️ Partially Implemented Features

**None** - All core MVP features are fully implemented!

---

## ❌ Deferred Features (Phase 2+)

### From Schema Specification

**Anti-Dilution Calculations:**
- Schema has `anti_dilution_protection` field
- ❌ NO automatic conversion ratio adjustment
- ❌ NO AntiDilutionAdjustmentEvent
- ❌ NO weighted average calculation
- ❌ NO full ratchet implementation

**Dividend Accrual:**
- ❌ DividendRights model removed entirely
- ❌ NO accrued dividend tracking in waterfall
- ❌ NO cumulative dividend calculations

**Advanced Event Types:**
- ❌ Pay-to-play / penalty provisions
- ❌ Stock splits (can use ConversionEvent, but no dedicated type)
- ❌ Share buybacks / redemptions
- ❌ Earnout / milestone-based equity
- ❌ Multiple closings / tranched investments

**Vesting:**
- Schema tracks `vesting_schedule_id` (string reference)
- ❌ NO vesting schedule details
- ❌ NO cliff/vesting calculations
- ❌ NO time-based vesting logic

### From Default Configurations

**Removed for MVP:**
- SAFE: mfn_enabled, pro_rata_side_letter
- Convertible Note: interest_payment variations (only simple accruing supported)
- Priced Round: warrant_coverage_percentage
- Anti-dilution: carve_out_option_pool, carve_out_shares
- Exit Scenarios: transaction_costs_fixed, greenshoe, escrow, earn_out
- Workbook: formatting_theme, freeze_panes, use_named_ranges, include_charts

---

## 📊 Test Coverage

**Total Tests:** 52 passing (100%)
**Coverage:** 88%

**Breakdown:**
- Basic blocks tests: 17/17 ✅
- Complex integration tests: 11/11 ✅
- Pro-rata rights schema tests: 4/4 ✅ (from previous phase)
- Participation waterfall tests: 7/7 ✅ **NEW!**
- Schema smoke tests: 13/13 ✅

**Key Test Files:**
- [test_blocks.py](test_blocks.py) - Unit tests for blocks architecture
- [test_blocks_integration.py](test_blocks_integration.py) - Integration tests with complex scenarios
- [test_waterfall_participation.py](test_waterfall_participation.py) - **NEW:** Comprehensive waterfall participation tests
- [test_schemas_smoke.py](test_schemas_smoke.py) - Basic schema instantiation

---

## 🔧 Implementation vs Documentation Gaps

### Schema Specification (schema_specification.md)

**Status:**
- ✅ FIXED: Removed votes_per_share from ShareClass example
- ✅ FIXED: Added note about voting rights removal
- ✅ FIXED: Participation rights fully implemented in waterfall
- ⚠️ UPDATE: DividendRights removed entirely (not just optional) - should document this

### Default Configurations (default_configurations.md)

**Status:**
- ✅ FIXED: Removed votes_per_share from templates
- ✅ FIXED: Added notes about voting removal
- ✅ All templates match current implementation

### Architecture (architecture.md)

**Potential Updates:**
- ⚠️ UPDATE: Block outputs documentation (add preferred_pct column)
- ✅ Waterfall block now fully implements participation rights
- ⚠️ UPDATE: Example schemas to match current implementation if needed

---

## 🎯 Recommendations

### For Documentation

1. ✅ **DONE:** Participation waterfall fully implemented
2. ✅ **DONE:** This IMPLEMENTATION_STATUS.md serves as single source of truth
3. **TODO:** Update schema_specification.md Section 3 (Share Classes) to document DividendRights removal
4. **TODO:** Update architecture.md Block outputs to document preferred_pct column
5. **N/A:** No migration guide needed - participation is complete

### For Next Phase (Phase 2)

**Priority 1: Anti-Dilution**
- Implement weighted average broad/narrow calculations
- Add AntiDilutionAdjustmentEvent
- Update conversion ratios automatically on down rounds
- Track carve-outs for option pools

**Priority 2: Dividend Accrual**
- Re-add DividendRights model (if needed for customers)
- Implement accrued dividend tracking
- Add to waterfall distribution (before liquidation preferences)

**Priority 3: Advanced Event Types**
- Pay-to-play / penalty provisions
- Stock splits
- Share buybacks / redemptions
- Multiple closings / tranched investments

---

## 📝 Quick Reference: What Changed from Docs

| Feature | Doc Says | Actually Implemented | Status |
|---------|----------|---------------------|---------|
| votes_per_share | Required field | **Removed** | ✅ Docs updated |
| total_voting_shares | Property exists | **Removed** | ✅ Docs updated |
| preferred_pct | Not mentioned | **Added** to cap_table output | ⚠️ Need to document |
| Participation waterfall | "Implemented" | **✅ FULLY IMPLEMENTED** | ✅ Complete! |
| DividendRights | "Optional field" | **Completely removed** | ⚠️ Need to update |
| Anti-dilution calc | "Implemented" | **Schema only**, no calculation | ⚠️ Need to clarify |
| SAFE MFN | In schema spec | **Removed** | ⚠️ Need to update |
| Pro-rata side letter | In schema spec | **Removed** | ⚠️ Need to update |

---

**Next Steps:**
1. Review this document with team
2. Update schema_specification.md based on gaps identified
3. Update architecture.md with correct block outputs
4. Plan Phase 2 priorities
