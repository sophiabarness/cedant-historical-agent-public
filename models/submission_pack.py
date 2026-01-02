"""Data models for submission pack parser functionality."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CatastropheEvent:
    """Represents a catastrophe event extracted from submission pack."""
    loss_year: Optional[str] = None
    loss_description: Optional[str] = None
    original_loss_gross: Optional[float] = None
    source_worksheet: str = ""
    source_row: int = 0


# Tool Input/Output Models

@dataclass
class FileLocatorInput:
    """Input for file location tool."""
    program_id: str
    submission_packs_directory: str = None  # Default set at runtime from config


@dataclass
class FileLocatorOutput:
    """Output from file location tool."""
    success: bool
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None  # "excel", "pdf"
    error_message: str = ""


@dataclass
class AsOfYearInput:
    """Input for As Of Year extraction tool."""
    file_path: str
    bridge_workflow_id: Optional[str] = None  # For signaling to BridgeWorkflow


@dataclass
class AsOfYearOutput:
    """Output from As Of Year extraction tool."""
    success: bool
    as_of_year: Optional[str] = None
    source_location: str = ""  # worksheet name and cell reference
    confidence_level: str = "low"  # "high", "medium", "low"
    extracted_text: str = ""  # raw text found
    error_message: str = ""


@dataclass
class HistoricalMatchInput:
    """Input for historical event matching tool."""
    event: CatastropheEvent
    historical_db_path: str = None  # Default set at runtime from config


@dataclass
class HistoricalMatchOutput:
    """Output from historical event matching tool."""
    success: bool
    hist_event_id: Optional[str] = None
    match_confidence: str = "none"  # "exact", "partial", "none"
    potential_matches: List[Dict[str, Any]] = field(default_factory=list)
    error_message: str = ""


@dataclass
class HistoricalEvent:
    """Represents a historical catastrophe event from the database."""
    hist_event_id: str
    event_name: str
    year: str
    pcs_code: Optional[str] = None
    event_date: Optional[str] = None  # Full date from EventDate column
    source_row: int = 0


@dataclass
class CedantRecord:
    """Represents a record in the Cedant Loss Data table."""
    loss_data_id: str
    index_num: int
    as_of_year: str
    hist_event_id: Optional[str]
    loss_year: str
    loss_description: str
    original_loss_gross: float
    source_info: str = ""  # For audit trail


# Sheet Identification Tool Models

@dataclass
class GetSheetNamesInput:
    """Input for getting sheet names from an Excel file."""
    file_path: str


@dataclass
class GetSheetNamesOutput:
    """Output from getting sheet names from an Excel file."""
    success: bool
    sheet_names: List[str] = field(default_factory=list)
    total_sheets: int = 0
    file_path: str = ""
    file_size_mb: Optional[float] = None
    error_message: str = ""


@dataclass
class ReadSheetInput:
    """Input for reading sheet content from an Excel file."""
    file_path: str
    sheet_name: str
    mode: str = "preview"  # "preview" or "full"


@dataclass
class ReadSheetOutput:
    """Output from reading sheet content from an Excel file."""
    success: bool
    sheet_name: str = ""
    headers: List[str] = field(default_factory=list)
    data_rows: List[List[str]] = field(default_factory=list)
    total_rows: int = 0
    total_columns: int = 0
    filtered_columns: int = 0
    filtered_rows: int = 0
    mode: str = "preview"
    rows_returned: int = 0
    error_message: str = ""
