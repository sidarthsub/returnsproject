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

## 3. Core Specifications

### 3.1 CapTableCFG

```ts
interface ShareClass {
  id: string;
  name: string;
  type: "common" | "preferred" | "option_pool" | "SAFE" | "warrant" | "convertible";
  seniority_rank: number;
  liquidation_pref_multiple?: number;
  participation?: "non_participating" | "participating" | "capped_participating";
  participation_cap_multiple?: number | null;
  conversion_ratio?: number;
}

interface Round {
  id: string;
  label: string;
  instrument_type: "SAFE" | "priced" | "convertible" | "warrant";
  date?: string;
  pre_money_valuation?: number;
  investment_amount?: number;
  price_per_share?: number;
  safe_cap?: number;
  safe_discount?: number;
  safe_type?: "pre_money" | "post_money";
  has_warrants?: boolean;
  warrant_coverage_pct?: number | null;
}

interface HolderPosition {
  holder_id: string;
  holder_name: string;
  share_class_id: string;
  shares: number;
  fully_diluted: boolean;
}

interface CapTableCFG {
  company_name: string;
  currency: string;
  share_classes: ShareClass[];
  rounds: Round[];
  holders: HolderPosition[];
  option_pool_shares?: number;
  as_of_date: string;
}
```

### 3.2 ReturnsCFG

```ts
interface ExitScenario {
  id: string;
  label: string;
  exit_value: number;
  exit_type: "M&A" | "IPO" | "secondary";
  date?: string;
}

interface ReturnsCFG {
  scenarios: ExitScenario[];
  include_irr: boolean;
  include_moic: boolean;
  waterfall_order: "seniority" | "pro_rata" | "custom";
}
```

### 3.3 WorkbookCFG

```ts
interface WorkbookCFG {
  cap_table: CapTableCFG;
  returns?: ReturnsCFG;
  include_audit_sheet: boolean;
  include_summary_sheet: boolean;
  formatting_theme: "professional" | "minimal" | "detailed";
}
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
