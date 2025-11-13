# Excel Model Generator – Development Roadmap & Architecture
Version: 0.1  
Author: Sid  
Last Updated: {{today}}

---

## 1. Product Goal

Build a chat-driven system that can:

1. Model cap tables across prior, current, and projected rounds  
2. Generate fully functional Excel workbooks (formulas, sheets, dynamic tables)  
3. Model exit and fund returns scenarios  
4. Import existing cap tables (Excel/CSV)  
5. Require minimal manual configuration by leveraging LLMs for structure extraction and model configuration  

The system should “just work” for 80–90% of VC and startup cases.

---

## 2. High-Level System Architecture

Five subsystems:

### 2.1 Front-End / Chat UI
- Built in React / Next.js  
- Chatbot interface for describing terms, rounds, scenarios  
- Upload Excel/CSV for cap table import  
- Download generated Excel models  
- Optional data visualizations  

### 2.2 Backend API
- Stateless FastAPI or Node backend  
- Responsibilities:
  - Manage sessions
  - Handle file uploads
  - Invoke LLM Orchestrator for cfg generation
  - Invoke Domain Engine to validate/patch cfg
  - Invoke Excel Renderer  
- Persist data in DB (Postgres / Supabase)

### 2.3 Domain Engine
- Pure deterministic logic layer
- Contains:
  - Config schemas (`CapTableCFG`, `ReturnsCFG`, `WorkbookCFG`)
  - Block library (`RoundTableBlock`, `OwnershipBlock`, `WaterfallBlock`, etc.)
  - Formula helpers for IRR/MOIC/distribution logic
  - Sanity checks (sum of shares, distributions = EV, etc.)

### 2.4 Excel Renderer
- Python (XlsxWriter or openpyxl) or Node (ExcelJS)
- Renders:
  - Sheets for each round  
  - Sheets for each returns scenario  
  - Summary + audit sheets  
- Applies formatting, named ranges, table styles  
- Purely deterministic, no LLM involvement

### 2.5 LLM Orchestrator
- Converts:
  - Natural language → config patches
  - Imported cap tables → structured schema  
  - Term sheet text → Rounds CFG  
  - Questions → explanations  
- Performs intent classification + structured output (function calling)

### 2.6 Storage Layer
- Postgres/Supabase: cfgs, user sessions, logs  
- S3/GCS: uploaded spreadsheets + generated Excel workbooks  

---

## 3. Core Architecture

**📖 See [docs/architecture.md](docs/architecture.md) for complete architectural documentation.**

### 3.1 Key Architectural Decisions

Based on comprehensive analysis of cap table complexity and extensibility requirements:

1. **Event-Sourced Data Model**
   - Cap table state is computed from events, not stored directly
   - Enables historical queries: "What was ownership on June 1, 2023?"
   - Full audit trail and time-travel capabilities
   - Events: ShareIssuance, RoundClosing, Conversion, OptionExercise, Transfer

2. **Discriminated Unions for Instrument Types**
   - SAFE, Priced Round, Convertible Note, Warrant as separate types
   - Type safety prevents invalid states (no "SAFE with price_per_share")
   - Each instrument has exactly the fields it needs
   - Easily extensible to new instrument types

3. **Rounds ≠ Share Classes**
   - Round = financing transaction/event (e.g., "Series A closing")
   - ShareClass = security with economic rights (e.g., "Series A Preferred Stock")
   - A round creates one or more share classes

4. **Computation/Rendering Separation**
   - Blocks compute data in Python (testable, reusable)
   - Blocks render to Excel (formatting only, no business logic)
   - Enables testing without Excel dependencies

5. **Excel Tables + Named Ranges**
   - Never use hardcoded cell ranges (e.g., `B2:B50`)
   - Always use Excel Tables with structured references: `CapTable[Shares]`
   - Named ranges for cross-sheet references
   - Formulas automatically adapt to data changes

### 3.2 Schema Overview (Event-Sourced)

**Core Concept:** Cap table = sequence of events → snapshot at any point in time

```python
# Event Store
class CapTable:
    company_name: str
    events: List[CapTableEvent]  # Chronological history
    share_classes: Dict[str, ShareClass]  # Share class definitions

    def snapshot(self, as_of_date: date) -> CapTableSnapshot:
        """Replay events up to date to compute state"""

# Events (what happened)
CapTableEvent (base)
├── ShareIssuanceEvent (shares issued to holder)
├── RoundClosingEvent (financing round closes)
├── ConversionEvent (preferred → common)
├── OptionExerciseEvent (employee exercises options)
└── ShareTransferEvent (secondary sale)

# Instruments (discriminated unions)
Instrument (union)
├── SAFEInstrument
├── PricedRoundInstrument
├── ConvertibleNoteInstrument
└── WarrantInstrument

# Share Classes (economic rights)
class ShareClass:
    id: str
    name: str
    share_type: Literal["common", "preferred", "option", "warrant"]
    liquidation_preference: Optional[LiquidationPreference]
    participation_rights: Optional[ParticipationRights]
    conversion_rights: Optional[ConversionRights]
    anti_dilution_protection: Optional[AntiDilutionProtection]

# State (computed from events)
class CapTableSnapshot:
    as_of_date: date
    positions: List[Position]  # Who owns what
    total_shares_outstanding: Decimal

class Position:
    holder_id: str
    share_class_id: str
    shares: Decimal
    acquisition_date: date
    cost_basis: Optional[Decimal]
    vesting_schedule_id: Optional[str]
```

### 3.3 Example: Event-Sourced Cap Table

```python
# Define events chronologically
events = [
    # Founders issue shares
    ShareIssuanceEvent(
        event_date="2023-01-01",
        holder_id="founder_a",
        share_class_id="common",
        shares=7_000_000,
    ),
    ShareIssuanceEvent(
        event_date="2023-01-01",
        holder_id="founder_b",
        share_class_id="common",
        shares=3_000_000,
    ),

    # Seed round closes
    RoundClosingEvent(
        event_date="2023-06-01",
        round_id="seed",
        round_name="Seed Round",
        instruments=[
            PricedRoundInstrument(
                type="priced",
                investment_amount=2_000_000,
                pre_money_valuation=8_000_000,
                price_per_share=1.0,
                shares_issued=2_500_000,
            )
        ],
        share_issuances=[
            ShareIssuanceEvent(
                holder_id="seed_vc",
                share_class_id="seed_preferred",
                shares=2_500_000,
                price_per_share=0.80,
            )
        ],
    ),
]

# Compute snapshot at any point in time
cap_table = CapTable(company_name="Acme Inc", events=events, ...)

# Current state
current = cap_table.snapshot(date.today())
print(current.ownership_percentage("founder_a"))  # 0.56 (7M / 12.5M)

# Historical state
pre_seed = cap_table.snapshot(date(2023, 5, 1))
print(pre_seed.ownership_percentage("founder_a"))  # 0.70 (7M / 10M)

# Dilution analysis
dilution = DilutionReport.compare(pre_seed, current)
print(dilution.dilution_percentage("founder_a"))  # 14% dilution
```

### 3.4 Detailed Schema Specifications

**Full Pydantic model definitions will be in:**
- `packages/domain/src/schemas/events.py` - All event types
- `packages/domain/src/schemas/instruments.py` - Instrument discriminated unions
- `packages/domain/src/schemas/share_classes.py` - ShareClass and economic rights
- `packages/domain/src/schemas/cap_table.py` - CapTable and CapTableSnapshot
- `packages/domain/src/schemas/positions.py` - Position and related models

**See [docs/architecture.md](docs/architecture.md) for detailed specifications.**

### 3.5 Returns & Waterfall Configuration

```python
class ExitScenario:
    id: str
    label: str  # "Acquisition", "IPO", etc.
    exit_value: Decimal
    exit_type: Literal["M&A", "IPO", "secondary"]
    exit_date: Optional[date]

class ReturnsCFG:
    scenarios: List[ExitScenario]
    include_irr: bool
    include_moic: bool

class WorkbookCFG:
    """Top-level configuration for Excel workbook generation."""
    cap_table: CapTable  # Event-sourced cap table
    returns: Optional[ReturnsCFG]
    include_audit_sheet: bool
    include_summary_sheet: bool
    formatting_theme: Literal["professional", "minimal", "detailed"]
```

---

## 4. Tech Stack (Finalized)

### 4.1 Core Technologies
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind CSS
- **Backend**: FastAPI (Python 3.11+)
- **Domain Engine**: Python package with Pydantic models
- **Excel Renderer**: openpyxl (Python)
- **LLM**: OpenAI GPT-4o (structured outputs) - *Phase 2*
- **Database**: Supabase (Postgres + auth + storage)
- **Deployment**: Vercel (frontend) + Railway/Render (backend)

### 4.2 Project Structure

```
returnsproject/
├── apps/
│   ├── web/                    # Next.js frontend (Phase 2)
│   │   ├── src/
│   │   │   ├── app/
│   │   │   ├── components/
│   │   │   └── lib/
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── api/                    # FastAPI backend (Phase 2)
│       ├── src/
│       │   ├── routers/
│       │   ├── services/
│       │   └── main.py
│       ├── requirements.txt
│       └── pyproject.toml
│
├── packages/
│   ├── domain/                 # Core domain logic (Phase 1 - MVP)
│   │   ├── src/
│   │   │   ├── schemas/       # Pydantic models (CapTableCFG, etc.)
│   │   │   ├── blocks/        # Block library
│   │   │   ├── formulas/      # Formula generation helpers
│   │   │   ├── validators/    # Sanity checks
│   │   │   └── __init__.py
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   │
│   ├── excel/                  # Excel rendering engine (Phase 1 - MVP)
│   │   ├── src/
│   │   │   ├── renderer/      # Core rendering logic
│   │   │   ├── formatters/    # Cell/sheet formatting
│   │   │   ├── builders/      # Sheet builders
│   │   │   └── __init__.py
│   │   ├── tests/
│   │   ├── examples/          # Sample generated workbooks
│   │   ├── pyproject.toml
│   │   └── README.md
│   │
│   └── llm/                    # LLM orchestration (Phase 2)
│       ├── src/
│       │   ├── parsers/       # Excel → JSON parsing
│       │   ├── generators/    # Natural language → config
│       │   └── __init__.py
│       ├── tests/
│       └── pyproject.toml
│
├── shared/
│   └── types/                  # Shared TypeScript types (Phase 2)
│       └── index.ts
│
├── docs/                       # Documentation
│   ├── architecture.md
│   ├── api-spec.md
│   └── examples/
│
├── .github/
│   └── workflows/             # CI/CD pipelines
│
├── docker-compose.yml          # Local development environment
├── README.md
├── roadmap.md                  # This file
└── .gitignore
```

---

## 5. Development Phases

### Phase 1: MVP - Core Domain & Excel Engine (Current Focus)

**Goal**: Build the deterministic core that can generate Excel workbooks from JSON configs.

**Scope**:
1. Define and implement all Pydantic schemas (CapTableCFG, ReturnsCFG, WorkbookCFG)
2. Build block library:
   - `RoundTableBlock`: Renders a single financing round
   - `OwnershipBlock`: Calculates ownership percentages
   - `WaterfallBlock`: Distributes exit proceeds
   - `SummaryBlock`: High-level metrics (ownership %, dilution, etc.)
   - `AuditBlock`: Sanity checks and validation
3. Implement formula helpers:
   - IRR calculations
   - MOIC calculations
   - Waterfall distribution logic
   - Pro-rata calculations
4. Build Excel renderer:
   - Sheet generation (one per round + summary + returns scenarios)
   - Formula injection (dynamic, not pre-calculated)
   - Table formatting and named ranges
   - Professional styling
5. Validators and sanity checks:
   - Sum of shares = total shares outstanding
   - Sum of distributions = exit value
   - Ownership percentages = 100%
   - Liquidation preferences are valid

**Input**: JSON file (CapTableCFG + ReturnsCFG)
**Output**: Excel workbook with formulas and formatting
**Testing**: Unit tests + sample cap tables (simple, SAFE, multi-round, waterfall scenarios)

**Deliverables**:
- ✅ Fully functional `packages/domain/` module
- ✅ Fully functional `packages/excel/` module
- ✅ CLI tool for testing: `python -m excel.cli generate config.json output.xlsx`
- ✅ Test suite with 80%+ coverage
- ✅ 3-5 example workbooks demonstrating different scenarios

**Success Criteria**:
- Can generate a valid Excel workbook from a JSON config
- Formulas recalculate correctly when users edit cells
- All sanity checks pass
- Workbook opens in Excel/Google Sheets without errors

---

### Phase 2: Backend API & File Upload

**Goal**: Wrap the domain engine in a REST API and enable file uploads.

**Scope**:
1. FastAPI backend with endpoints:
   - `POST /api/generate` - Generate workbook from JSON
   - `POST /api/upload` - Upload Excel/CSV (returns validation report)
   - `GET /api/sessions/{id}` - Retrieve session config
   - `PUT /api/sessions/{id}` - Update session config
2. Session management (versioned configs):
   - Store each version of CapTableCFG
   - Allow rollback to previous versions
3. File upload handling:
   - Accept Excel/CSV files
   - Basic validation (columns exist, data types correct)
4. Integration with domain + excel packages
5. Database schema (Supabase):
   - `sessions` table (id, user_id, created_at, updated_at)
   - `config_versions` table (session_id, version, config_json, created_at)
   - `generated_files` table (session_id, file_url, created_at)

**Deliverables**:
- ✅ Functional FastAPI backend
- ✅ Supabase database setup
- ✅ API documentation (OpenAPI/Swagger)
- ✅ Docker Compose for local development

---

### Phase 3: LLM Orchestration

**Goal**: Add intelligence to parse uploaded files and generate configs from natural language.

**Scope**:
1. Excel/CSV parser using GPT-4o:
   - Extract holder names, share classes, amounts
   - Infer round types (seed, Series A, etc.)
   - Detect liquidation preferences, participation rights
2. Natural language to config:
   - "Add a Series A round with $5M investment at $20M pre-money"
   - "Model a 2x participating preferred with 3x cap"
3. Intent classification:
   - Generate vs. Modify vs. Explain
4. Structured output validation:
   - Ensure LLM output conforms to Pydantic schemas
   - Patch configs incrementally

**Deliverables**:
- ✅ `packages/llm/` module
- ✅ Parser for Excel → CapTableCFG
- ✅ Config generator from natural language
- ✅ API endpoints integrated with backend

---

### Phase 4: Frontend & Chat Interface

**Goal**: Build the user-facing application.

**Scope**:
1. Next.js app with:
   - File upload interface
   - Chat interface for describing rounds/scenarios
   - Config editor (JSON or form-based)
   - Download generated Excel files
   - Optional: data visualizations (ownership charts, waterfall charts)
2. Authentication (Supabase Auth)
3. Session history and version control UI

**Deliverables**:
- ✅ Production-ready Next.js app
- ✅ Deployed to Vercel
- ✅ Full user flow: upload → chat → generate → download

---

### Phase 5: Refinement & Advanced Features

**Scope**:
1. Multi-user collaboration
2. Template library (common cap table structures)
3. Advanced waterfall scenarios (carve-outs, management pools, etc.)
4. Export to other formats (PDF reports, CSV exports)
5. Performance optimization for large cap tables

---

## 6. Key Architectural Decisions

### Session Management
- **Versioned**: Each config change creates a new version
- **Single-user**: No real-time collaboration (Phase 1-4)
- **Synchronous**: Excel generation happens inline (no job queue initially)

### Excel Generation Strategy
- **Formulas**: Use Excel formulas (not pre-calculated values)
- **Dynamic**: Users can edit assumptions and formulas recalculate
- **Formatted**: Professional styling with named ranges and table styles

### Data Flow (Phase 1)
```
JSON Config File
      ↓
Domain Engine (validate + build blocks)
      ↓
Excel Renderer (generate sheets + formulas)
      ↓
Excel Workbook (.xlsx)
```

### Data Flow (Phase 2+)
```
User Upload (Excel/CSV) OR JSON Config
      ↓
Backend API (session management)
      ↓
LLM Orchestrator (optional: parse uploaded file)
      ↓
Domain Engine (validate + build blocks)
      ↓
Excel Renderer (generate sheets + formulas)
      ↓
Storage (S3/Supabase) + Return download URL
```

---

## 7. Testing Strategy

### Phase 1 (Domain + Excel)
- **Unit tests**: Each block, formula helper, validator
- **Integration tests**: Full config → workbook generation
- **Example scenarios**:
  - Simple cap table (founders + seed round)
  - SAFE conversion scenarios
  - Multi-round with preferred stock
  - Complex waterfall (participating preferred, carve-outs)

### Phase 2+ (API + LLM)
- **API tests**: Endpoint contracts, error handling
- **LLM tests**: Prompt testing, schema validation
- **End-to-end tests**: Upload → parse → generate → download

---

## 8. Open Questions & Future Considerations

1. **Performance**: How large can cap tables get? (# of holders, # of rounds)
2. **Edge cases**: Exotic instruments (PIK notes, ratchets, etc.)
3. **Internationalization**: Multi-currency support?
4. **Audit trail**: Should we log all LLM interactions for debugging?
5. **Pricing model**: Usage-based (per workbook) or subscription?

---

## 9. Current Status

**Phase**: Phase 1 (MVP - Core Domain & Excel Engine)
**Next Steps**:
1. Set up project structure (monorepo with packages/)
2. Implement Pydantic schemas in `packages/domain/`
3. Build first block: `RoundTableBlock`
4. Implement basic Excel renderer
5. Create first test case: simple cap table → Excel

**Updated**: 2025-11-13
