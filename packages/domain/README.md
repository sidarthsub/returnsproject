# Cap Table Domain Engine

Core domain logic for cap table modeling and validation.

## Overview

This package contains:
- **Schemas**: Pydantic models for CapTableCFG, ReturnsCFG, WorkbookCFG
- **Blocks**: Modular components for rendering different parts of the model
- **Formulas**: Helper functions for financial calculations (IRR, MOIC, waterfall)
- **Validators**: Sanity checks and business logic validation

## Installation

```bash
pip install -e .
```

For development:
```bash
pip install -e ".[dev]"
```

## Usage

```python
from captable_domain.schemas import CapTableCFG, ShareClass, Round

# Define a simple cap table
cap_table = CapTableCFG(
    company_name="Acme Inc",
    currency="USD",
    share_classes=[...],
    rounds=[...],
    holders=[...],
    as_of_date="2024-01-01"
)
```

## Testing

```bash
pytest
```
