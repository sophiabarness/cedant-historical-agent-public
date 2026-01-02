"""Tool registry for Supervisor Agent tools."""

import logging
from typing import Dict, Callable, Optional, List
from models.core import ToolDefinition, ToolArgument

logger = logging.getLogger(__name__)

# Log when this module is imported
logger.info("TOOL_REGISTRY: Supervisor tool registry module imported")


# Supervisor Agent Tool Definitions
POPULATE_CEDANT_DATA_TOOL = ToolDefinition(
    name="PopulateCedantData",
    description="Populate cedant loss data with historical matches from HistoricalMatcher. This is read-only and generates a diff report. Historical matches and as_of_year are automatically retrieved from the workflow's data store - do NOT provide as_of_year unless you need to override the extracted value.",
    arguments=[
        ToolArgument(
            name="program_id",
            type="string",
            description="Program ID for the submission pack",
            required=True
        ),
        ToolArgument(
            name="as_of_year",
            type="string",
            description="(Optional) As Of Year - automatically retrieved from workflow data store. Only provide if you need to override the extracted value.",
            required=False
        )
    ],
    execution_type="activity",
    activity_name="populate_cedant_data"
)

COMPARE_TO_EXISTING_CEDANT_DATA_TOOL = ToolDefinition(
    name="CompareToExistingCedantData",
    description="Compare newly generated cedant records against existing data in the Cedant Loss Data table for a given LossDataID. Shows what would be added, modified, or unchanged.",
    arguments=[
        ToolArgument(
            name="loss_data_id",
            type="string",
            description="LossDataID to check records for (obtained from PopulateCedantData result)"
        ),
        ToolArgument(
            name="new_records",
            type="array",
            description="Array of newly generated records from PopulateCedantData (use 'all_records' field from result)"
        ),
        ToolArgument(
            name="cedant_data_path",
            type="string",
            description="(Optional) Path to cedant data file. Defaults to DATA_DIR/Cedant Loss Data.xlsx"
        )
    ],
    execution_type="activity",
    activity_name="compare_to_existing_cedant_data"
)

GENERATE_DIFF_REPORT_TOOL = ToolDefinition(
    name="GenerateDiffReport",
    description="Generate a comprehensive diff report comparing existing and new cedant records with impact assessment and recommendations.",
    arguments=[
        ToolArgument(
            name="loss_data_id",
            type="string",
            description="The LossDataID being processed"
        ),
        ToolArgument(
            name="existing_records",
            type="array",
            description="List of existing records from cedant data"
        ),
        ToolArgument(
            name="new_records",
            type="array",
            description="List of newly generated records"
        ),
        ToolArgument(
            name="program_id",
            type="string",
            description="Program ID for context"
        ),
        ToolArgument(
            name="as_of_year",
            type="string",
            description="As Of Year for context"
        )
    ],
    execution_type="activity",
    activity_name=None  # TODO: Create direct activity when ready for testing
)

EXPORT_DIFF_REPORT_TOOL = ToolDefinition(
    name="ExportDiffReport",
    description="Export diff report to file in JSON or text format.",
    arguments=[
        ToolArgument(
            name="diff_report",
            type="object",
            description="The diff report to export (from GenerateDiffReport)"
        ),
        ToolArgument(
            name="output_path",
            type="string",
            description="(Optional) Output file path. If None, generates default path"
        ),
        ToolArgument(
            name="format",
            type="string",
            description="Export format: 'json' or 'txt' (default: 'json')"
        )
    ],
    execution_type="activity",
    activity_name=None  # TODO: Create direct activity when ready for testing
)

# Sub-agent tools (these are agents that act as tools for the supervisor)
SUBMISSION_PACK_PARSER_AGENT_TOOL = ToolDefinition(
    name="SubmissionPackParserAgent",
    description="Extract catastrophe loss events from a submission pack using a specialized agent. The agent will first locate the submission pack file using LocateSubmissionPack tool, then extract structured event data including loss amounts, dates, descriptions, and peril types.",
    arguments=[
        ToolArgument(
            name="program_id",
            type="string",
            description="Program ID for tracking and identification (e.g., '153300')",
            required=True
        )
    ],
    execution_type="agent",
    activity_name=None
)

HISTORICAL_MATCHER_AGENT_TOOL = ToolDefinition(
    name="HistoricalMatcher",
    description="Process multiple catastrophe events in parallel using Temporal child workflows. Each event gets its own workflow instance for better fault isolation and performance. Events are automatically retrieved from the workflow's data store - no need to pass them explicitly.",
    arguments=[
        ToolArgument(
            name="program_id",
            type="string",
            description="Program ID for tracking and identification"
        )
    ],
    execution_type="activity",  # This is an activity, not an agent workflow
    activity_name="process_events_parallel"
)

# DEBUG: Verify tool definition at module load time
logger.info(f"TOOL_REGISTRY: HISTORICAL_MATCHER_AGENT_TOOL created:")
logger.info(f"  name: {HISTORICAL_MATCHER_AGENT_TOOL.name}")
logger.info(f"  execution_type: {HISTORICAL_MATCHER_AGENT_TOOL.execution_type}")
logger.info(f"  activity_name: {HISTORICAL_MATCHER_AGENT_TOOL.activity_name}")
logger.info(f"  object id: {id(HISTORICAL_MATCHER_AGENT_TOOL)}")

# Supervisor Agent Tool Definitions Registry
_SUPERVISOR_TOOL_DEFINITIONS_LIST = [
    # Sub-agent tools (agents acting as tools)
    SUBMISSION_PACK_PARSER_AGENT_TOOL,
    HISTORICAL_MATCHER_AGENT_TOOL,
    # Direct supervisor tools
    POPULATE_CEDANT_DATA_TOOL,
    COMPARE_TO_EXISTING_CEDANT_DATA_TOOL,
    GENERATE_DIFF_REPORT_TOOL,
    EXPORT_DIFF_REPORT_TOOL,
]

# Make the tool definitions immutable by creating a tuple
SUPERVISOR_TOOL_DEFINITIONS = tuple(_SUPERVISOR_TOOL_DEFINITIONS_LIST)

# Log the tool registry state when it's created
logger.info(f"TOOL_REGISTRY: SUPERVISOR_TOOL_DEFINITIONS created with {len(SUPERVISOR_TOOL_DEFINITIONS)} tools")
logger.info(f"TOOL_REGISTRY: Tool names: {[tool.name for tool in SUPERVISOR_TOOL_DEFINITIONS]}")
logger.info(f"TOOL_REGISTRY: List object ID: {id(SUPERVISOR_TOOL_DEFINITIONS)}")
logger.info(f"TOOL_REGISTRY: List is immutable tuple: {type(SUPERVISOR_TOOL_DEFINITIONS)}")
