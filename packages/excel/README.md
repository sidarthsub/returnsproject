# Cap Table Excel Renderer

Excel workbook generation engine for cap table models.

## Overview

This package transforms domain configs into fully-functional Excel workbooks with:
- Formula-driven calculations (not hardcoded values)
- Professional formatting and styling
- Multiple sheets (rounds, scenarios, summary, audit)
- Named ranges and table structures

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
from captable_domain.schemas import WorkbookCFG
from captable_excel.renderer import ExcelRenderer

# Load your config
config = WorkbookCFG(...)

# Generate workbook
renderer = ExcelRenderer(config)
renderer.render("output.xlsx")
```

## CLI

```bash
python -m captable_excel.cli generate config.json output.xlsx
```

## Testing

```bash
pytest
```
