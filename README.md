# Excel Model Generator for Cap Tables & Fund Returns

A chat-driven system for modeling cap tables, fund returns, and exit scenarios with fully functional Excel workbook generation.

## Project Goal

Build a system that can:
1. Model cap tables across prior, current, and projected rounds
2. Generate fully functional Excel workbooks (formulas, sheets, dynamic tables)
3. Model exit and fund returns scenarios
4. Import existing cap tables (Excel/CSV)
5. Require minimal manual configuration by leveraging LLMs

The system should "just work" for 80–90% of VC and startup cases.

## Current Phase: MVP (Phase 1)

Building the core domain engine and Excel renderer. Focus is on:
- Pydantic schemas for cap table configs
- Block library for modular Excel generation
- Formula helpers for IRR/MOIC/waterfall calculations
- Deterministic Excel rendering with openpyxl

## Project Structure

```
returnsproject/
├── packages/
│   ├── domain/          # Core domain logic (Pydantic schemas, blocks, validators)
│   └── excel/           # Excel rendering engine (openpyxl-based)
├── docs/                # Documentation
├── roadmap.md           # Detailed project roadmap
└── README.md            # This file
```

## Tech Stack

- **Python 3.11+**
- **Pydantic** for schemas and validation
- **openpyxl** for Excel generation
- **pytest** for testing
- Future: FastAPI (backend), Next.js (frontend), OpenAI GPT-4o (LLM)

## Getting Started

### Prerequisites
- Python 3.11 or higher
- pip

### Installation

1. Clone the repository:
```bash
git clone https://github.com/sidarthsub/returnsproject.git
cd returnsproject
```

2. Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

### Development

Each package can be worked on independently:

```bash
# Work on domain package
cd packages/domain
pytest

# Work on excel package
cd packages/excel
pytest
```

## Documentation

- [Roadmap & Architecture](roadmap.md) - Detailed project plan and technical decisions
- Package READMEs:
  - [Domain Engine](packages/domain/README.md)
  - [Excel Renderer](packages/excel/README.md)

## Contributing

This is currently a solo project by Sid. Contributions welcome once MVP is complete.

## License

TBD
