"""Supervisor Agent goal definition."""

import logging
from models.core import AgentGoal
from agents.supervisor.tools.tool_registry import SUPERVISOR_TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

# Log when this module is imported
logger.info("SUPERVISOR_GOAL: Supervisor goal module imported")
logger.info(f"SUPERVISOR_GOAL: SUPERVISOR_TOOL_DEFINITIONS has {len(SUPERVISOR_TOOL_DEFINITIONS)} tools")
logger.info(f"SUPERVISOR_GOAL: Tool names: {[tool.name for tool in SUPERVISOR_TOOL_DEFINITIONS]}")

SUPERVISOR_AGENT_GOAL = AgentGoal(
    agent_name="Supervisor Agent",
    tools=SUPERVISOR_TOOL_DEFINITIONS,
    description="""A specialized AI agent for processing insurance submission pack documents through multi-step workflows with parallel processing capabilities.

RECOMMENDED WORKFLOW SEQUENCE (flexible based on user needs):
1. SubmissionPackParserAgent (locate file and extract catastrophe events AND as_of_year from the submission pack using LLM)
3. HistoricalMatcher (match extracted events with historical database - generates historical_matches)
4. PopulateCedantData (populate cedant data using events_data + historical_matches from step 3)
5. CompareToExistingCedantData (compare new records against existing data in Cedant Loss Data table)

IMPORTANT GUIDELINES:
- The above sequence is the TYPICAL workflow, but I can adapt based on user requests
- HistoricalMatcher should generally be called after SubmissionPackParserAgent (it generates historical_matches)
- PopulateCedantData requires both events_data and historical_matches to work properly
- CompareToExistingCedantData is useful to show what would change, but can be skipped if user doesn't need it
- I should follow the user's lead - if they want to skip steps, test specific tools, or go in a different order, I can accommodate
- I should ask for confirmation before completing the workflow

FLEXIBILITY:
- User may want to test individual tools (e.g., just run HistoricalMatcher with specific event data)
- User may want to skip certain steps (e.g., skip CompareToExistingCedantData if they trust the results)
- User may want to review results between steps before proceeding
- User may want to run tools multiple times with different parameters

The events_data comes from SubmissionPackParserAgent. The historical_matches comes from HistoricalMatcher. Both are needed for PopulateCedantData. The new_records and loss_data_id come from PopulateCedantData and are needed for CompareToExistingCedantData.""",
    starter_prompt="Hello! I'm your submission pack processing assistant. I can help you process insurance submission pack documents. I can locate files by Program ID, extract As Of Years, analyze document structure, and extract catastrophe loss data. What would you like me to help you with?",
    example_conversation_history="""User: I need to process submission pack for Program ID 200000
Agent: Let's start by extracting catastrophe events from the submission pack for program 200000.
[Tool: SubmissionPackParserAgent(program_id="200000")]
Successfully extracted 63 catastrophe events including Hurricane Irma ($400M), Hurricane Ian ($1.5B), and others. Now I'll match these events with the historical database.
[Tool: HistoricalMatcher(program_id="200000")]
Successfully matched all 63 events with the historical database. Found 59 exact matches. Now let me populate the cedant data with the matched events.
[Tool: PopulateCedantData(program_id="200000", as_of_year="2023")]
Successfully populated cedant data with 63 records for LossDataID 534129. Now let me check the differences with existing data.
[Tool: CompareToExistingCedantData(loss_data_id="534129", new_records="USE_PREVIOUS_RESULT")]
Comparison complete! Found 45 additions (new events), 10 modifications (updated values), and 4 unchanged records. The complete submission pack processing workflow is now finished.

User: Great! Can you show me the Hurricane Irma details?
Agent: Based on the processing results, Hurricane Irma (2017) had an original loss of $400,367,086 and was successfully matched to historical event ID 18659 in our database.

User: Perfect, thank you!
Agent: You're welcome! The complete workflow processed all catastrophe events and generated the cedant data records for Program ID 200000."""
)

# Log the goal state when it's created
logger.info(f"SUPERVISOR_GOAL: SUPERVISOR_AGENT_GOAL created with {len(SUPERVISOR_AGENT_GOAL.tools)} tools")
logger.info(f"SUPERVISOR_GOAL: Goal object ID: {id(SUPERVISOR_AGENT_GOAL)}")
logger.info(f"SUPERVISOR_GOAL: Tools list ID: {id(SUPERVISOR_AGENT_GOAL.tools)}")
logger.info(f"SUPERVISOR_GOAL: Tools are same object as SUPERVISOR_TOOL_DEFINITIONS: {SUPERVISOR_AGENT_GOAL.tools is SUPERVISOR_TOOL_DEFINITIONS}")

# DEBUG: Log each tool's execution_type at module load time
for tool in SUPERVISOR_AGENT_GOAL.tools:
    logger.info(f"SUPERVISOR_GOAL: Tool '{tool.name}' execution_type={tool.execution_type}, activity_name={tool.activity_name}, obj_id={id(tool)}")

# CRITICAL: Add a property to detect if tools are modified
def _check_tools_integrity():
    """Check if the supervisor goal tools have been corrupted."""
    if len(SUPERVISOR_AGENT_GOAL.tools) != 6:
        logger.error(f"CORRUPTION DETECTED: SUPERVISOR_AGENT_GOAL now has {len(SUPERVISOR_AGENT_GOAL.tools)} tools instead of 6!")
        logger.error(f"Current tools: {[tool.name for tool in SUPERVISOR_AGENT_GOAL.tools]}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_stack()}")
    return SUPERVISOR_AGENT_GOAL

# Replace the goal with a function that checks integrity on access
def get_supervisor_agent_goal():
    """Get the supervisor agent goal with integrity checking."""
    return _check_tools_integrity()

# Export the function instead of the object to catch access
# SUPERVISOR_AGENT_GOAL = get_supervisor_agent_goal
