"""Cap table domain schemas.

This package contains all Pydantic models for the cap table domain layer:
- Base types and conventions
- Share classes and economic rights
- Instruments (SAFE, priced rounds, convertible notes, warrants)
- Positions and ownership
- Events (event-sourced architecture)
- Cap tables and snapshots
- Returns and waterfall analysis
- Workbook configuration

Usage:
    from captable_domain.schemas import (
        CapTable, CapTableSnapshot, ShareClass, Position,
        ShareIssuanceEvent, RoundClosingEvent,
        ExitScenario, ReturnsCFG, WorkbookCFG
    )
"""

# Base types
from .base import (
    DomainModel,
    ShareCount,
    MoneyAmount,
    Percentage,
    Multiple,
    ShareClassId,
    HolderId,
    EventId,
    RoundId,
)

# Share classes and economic rights
from .share_classes import (
    ShareClass,
    LiquidationPreference,
    ParticipationRights,
    ConversionRights,
    AntiDilutionProtection,
)

# Instruments
from .instruments import (
    Instrument,
    SAFEInstrument,
    PricedRoundInstrument,
    ConvertibleNoteInstrument,
    WarrantInstrument,
)

# Positions
from .positions import Position

# Events
from .events import (
    CapTableEvent,
    ShareIssuanceEvent,
    ShareTransferEvent,
    ConversionEvent,
    OptionExerciseEvent,
    RoundClosingEvent,
    SAFEConversionEvent,
    OptionPoolCreation,
    WarrantIssuance,
)

# Cap table
from .cap_table import (
    CapTable,
    CapTableSnapshot,
    CurrencyAmount,
)

# Returns
from .returns import (
    ExitScenario,
    ReturnsCFG,
)

# Workbook
from .workbook import (
    WorkbookCFG,
    CapTableSnapshotCFG,
    WaterfallAnalysisCFG,
)

__all__ = [
    # Base types
    "DomainModel",
    "ShareCount",
    "MoneyAmount",
    "Percentage",
    "Multiple",
    "ShareClassId",
    "HolderId",
    "EventId",
    "RoundId",
    # Share classes
    "ShareClass",
    "LiquidationPreference",
    "ParticipationRights",
    "ConversionRights",
    "AntiDilutionProtection",
    # Instruments
    "Instrument",
    "SAFEInstrument",
    "PricedRoundInstrument",
    "ConvertibleNoteInstrument",
    "WarrantInstrument",
    # Positions
    "Position",
    # Events
    "CapTableEvent",
    "ShareIssuanceEvent",
    "ShareTransferEvent",
    "ConversionEvent",
    "OptionExerciseEvent",
    "RoundClosingEvent",
    "SAFEConversionEvent",
    "OptionPoolCreation",
    "WarrantIssuance",
    # Cap table
    "CapTable",
    "CapTableSnapshot",
    "CurrencyAmount",
    # Returns
    "ExitScenario",
    "ReturnsCFG",
    # Workbook
    "WorkbookCFG",
    "CapTableSnapshotCFG",
    "WaterfallAnalysisCFG",
]
