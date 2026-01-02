"""Goal registry for managing agent goals and configurations."""

from typing import Dict, Callable, Any
from models.core import AgentGoal


def create_submission_pack_parser_agent_goal(program_id: str, submission_packs_directory: str) -> AgentGoal:
    """
    Create a Submission Pack Parser agent goal with specific parameters.
    
    Args:
        program_id: The program ID to extract catastrophe events for
        submission_packs_directory: The directory containing submission packs
        
    Returns:
        An AgentGoal configured for submission pack parsing
    """
    from agents.supervisor.tools.submission_pack_parser.goal import SUBMISSION_PACK_PARSER_AGENT_GOAL
    
    # Create a copy of the goal with a customized starter prompt
    goal = AgentGoal(
        agent_name=SUBMISSION_PACK_PARSER_AGENT_GOAL.agent_name,
        tools=SUBMISSION_PACK_PARSER_AGENT_GOAL.tools,
        description=SUBMISSION_PACK_PARSER_AGENT_GOAL.description,
        starter_prompt=f"Extract catastrophe events for Program ID {program_id} from the submission packs in {submission_packs_directory}. Start by locating the submission pack file.",
        example_conversation_history=SUBMISSION_PACK_PARSER_AGENT_GOAL.example_conversation_history
    )
    
    return goal


def create_sheet_identification_agent_goal(file_path: str) -> AgentGoal:
    """
    Create a Sheet Identification agent goal with specific parameters.
    
    Args:
        file_path: The path to the Excel file to analyze
        
    Returns:
        An AgentGoal configured for sheet identification
    """
    from agents.supervisor.tools.submission_pack_parser.tools.sheet_identification.goal import SHEET_IDENTIFICATION_AGENT_GOAL
    
    # Create a copy of the goal with a customized starter prompt
    goal = AgentGoal(
        agent_name=SHEET_IDENTIFICATION_AGENT_GOAL.agent_name,
        tools=SHEET_IDENTIFICATION_AGENT_GOAL.tools,
        description=SHEET_IDENTIFICATION_AGENT_GOAL.description,
        starter_prompt=f"Analyze the Excel workbook at '{file_path}' to identify catastrophe loss data sheets. Start by using GetSheetNames with file_path='{file_path}' to get the complete list of sheets, then examine the structure to identify catastrophe data.",
        example_conversation_history=SHEET_IDENTIFICATION_AGENT_GOAL.example_conversation_history
    )
    
    return goal


# Tool-to-Goal Factory Mapping
TOOL_TO_GOAL_FACTORY: Dict[str, Callable] = {
    "SubmissionPackParserAgent": create_submission_pack_parser_agent_goal,
    "SheetIdentificationAgent": create_sheet_identification_agent_goal,
    "SheetIdentifier": create_sheet_identification_agent_goal,  # Map tool name to goal factory
}


def create_goal_for_tool(tool_name: str, tool_args: Dict[str, Any]) -> AgentGoal:
    """
    Create an agent goal for a child workflow tool.
    
    Args:
        tool_name: Name of the tool that should be executed as a child workflow
        tool_args: Arguments passed to the tool
        
    Returns:
        An AgentGoal configured for the specific tool
        
    Raises:
        ValueError: If tool_name is not a known child workflow tool
    """
    factory = TOOL_TO_GOAL_FACTORY.get(tool_name)
    if not factory:
        raise ValueError(f"No goal factory found for child workflow tool: {tool_name}")
    
    # Call the factory function with the tool arguments
    # Each factory function has its own signature, so we need to map appropriately
    if tool_name == "SubmissionPackParserAgent":
        program_id = tool_args.get("program_id", "unknown")
        submission_packs_directory = tool_args.get("submission_packs_directory", "data/Submission Packs")
        return factory(program_id, submission_packs_directory)
    elif tool_name in ["SheetIdentificationAgent", "SheetIdentifier"]:
        file_path = tool_args.get("file_path", "")
        return factory(file_path)
    else:
        raise ValueError(f"Unknown argument mapping for tool: {tool_name}")


def get_agent_goal_by_name(agent_name: str) -> AgentGoal | None:
    """
    Get an agent goal by its name.
    
    Args:
        agent_name: The name of the agent to get the goal for
        
    Returns:
        The AgentGoal if found, None otherwise
    """
    # Import goals lazily to avoid circular imports
    if agent_name == "Supervisor Agent":
        try:
            from agents.supervisor.goal import SUPERVISOR_AGENT_GOAL
            return SUPERVISOR_AGENT_GOAL
        except ImportError:
            return None
    
    elif agent_name == "Submission Pack Parser":
        try:
            from agents.supervisor.tools.submission_pack_parser.goal import SUBMISSION_PACK_PARSER_AGENT_GOAL
            return SUBMISSION_PACK_PARSER_AGENT_GOAL
        except ImportError:
            return None
    
    elif agent_name == "Sheet Identification Specialist":
        try:
            from agents.supervisor.tools.submission_pack_parser.tools.sheet_identification.goal import SHEET_IDENTIFICATION_AGENT_GOAL
            return SHEET_IDENTIFICATION_AGENT_GOAL
        except ImportError:
            return None
    
    return None