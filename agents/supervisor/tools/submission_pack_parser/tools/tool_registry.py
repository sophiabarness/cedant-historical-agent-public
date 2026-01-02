"""Tool registry for Submission Pack Parser Agent tools."""

from models.core import ToolDefinition, ToolArgument


# Submission Pack Parser Agent Tool Definitions
LOCATE_SUBMISSION_PACK_TOOL = ToolDefinition(
    name="LocateSubmissionPack",
    description="Locate submission pack file based on Program ID within the configured data directory (searches recursively).",
    arguments=[
        ToolArgument(
            name="program_id",
            type="string",
            description="The Program ID to search for (e.g., '153300', '154516')",
            required=True
        )
    ],
    execution_type="activity",
    activity_name="locate_submission_pack_activity"
)

EXTRACT_AS_OF_YEAR_TOOL = ToolDefinition(
    name="ExtractAsOfYear",
    description="Extract the As Of Year from submission pack files to establish the data timeframe.",
    arguments=[
        ToolArgument(
            name="file_path",
            type="string",
            description="Path to the submission pack file to extract As Of Year from",
            required=True
        )
    ],
    execution_type="activity",
    activity_name="extract_as_of_year"
)

LLM_EXTRACT_CATASTROPHE_DATA_TOOL = ToolDefinition(
    name="LLMExtractCatastropheData",
    description="Use LLM to extract catastrophe data with actual calculated values from Excel formulas. Supports multiple sheets in a single call.",
    arguments=[
        ToolArgument(
            name="file_path",
            type="string",
            description="Path to submission pack Excel file"
        ),
        ToolArgument(
            name="sheet_names",
            type="array",
            description="List of sheet names to extract catastrophe data from"
        ),
        ToolArgument(
            name="extraction_approach",
            type="string",
            description="Optional extraction approach description (default: 'LLM-guided extraction with calculated values')",
            required=False
        ),
        ToolArgument(
            name="user_instructions",
            type="string",
            description="Optional user-provided instructions to customize extraction behavior (e.g., 'Only extract Total entries when HPCIC, NBIC, and Total variants exist for the same event')",
            required=False
        )
    ],
    execution_type="activity",
    activity_name="llm_extract_catastrophe_data_activity"
)

# Sub-agent tool (Sheet Identification Agent as tool)
IDENTIFY_SHEETS_TOOL = ToolDefinition(
    name="SheetIdentifier",
    description="Identify catastrophe loss data sheets within an Excel submission pack using specialized sheet identification agent. This tool spawns a child workflow that intelligently analyzes the workbook structure, examines table of contents, and identifies sheets containing catastrophe data.",
    arguments=[
        ToolArgument(
            name="file_path",
            type="string",
            description="Path to the Excel submission pack file to analyze"
        )
    ],
    execution_type="agent",
    activity_name=None  # Agent workflows don't use activity names
)

SUBMISSION_PACK_PARSER_TOOL_DEFINITIONS = [
    LOCATE_SUBMISSION_PACK_TOOL,
    EXTRACT_AS_OF_YEAR_TOOL,
    LLM_EXTRACT_CATASTROPHE_DATA_TOOL,
    IDENTIFY_SHEETS_TOOL,
]