"""Cap Table Domain Engine - Core domain models and business logic.

This package provides the foundational layer for cap table modeling:
- Event-sourced cap table architecture
- Share classes with economic and voting rights
- Instruments (SAFEs, priced rounds, convertible notes, warrants)
- Waterfall analysis and returns calculations

The domain layer is designed to be:
- Framework-agnostic (no FastAPI, no web dependencies)
- Testable (pure Python with Pydantic validation)
- Extensible (easy to add new event types, share classes, etc.)
"""

from .schemas import *  # noqa: F403, F401

__version__ = "0.1.0"
