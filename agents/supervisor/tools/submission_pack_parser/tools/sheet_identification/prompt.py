"""Prompt generator for Sheet Identification Specialist agent."""

import json
from typing import Optional

from models.core import AgentGoal
from models.requests import ConversationHistory, ToolData


def generate_sheet_identification_prompt(
    agent_goal: AgentGoal,
    conversation_history: ConversationHistory,
    raw_json: Optional[ToolData] = None,
) -> str:
    """
    Generate specialized prompts for sheet identification agent.
    
    This function creates prompts specifically designed for sheet identification,
    with emphasis on cross-referencing TOC data with sheet names and making
    intelligent synthesis decisions.
    
    Args:
        agent_goal: The sheet identification agent's goal configuration
        conversation_history: The ongoing conversation context
        raw_json: Optional existing tool data for validation
        
    Returns:
        str: Specialized prompt for sheet identification agent
    """
    # Import here to avoid circular imports
    from agents.core.agent_prompt_generators import compress_conversation_history
    
    # Compress conversation history
    compressed_history = compress_conversation_history(conversation_history, max_recent_messages=8)
    
    # Format available tools for the prompt
    tools_description = []
    for tool in agent_goal.tools:
        tool_str = f"- {tool.name}: {tool.description}"
        if tool.arguments:
            required_args = [f"{arg.name} ({arg.type})" for arg in tool.arguments if getattr(arg, 'required', True)]
            optional_args = [f"{arg.name} ({arg.type}, optional)" for arg in tool.arguments if not getattr(arg, 'required', True)]
            
            args_parts = []
            if required_args:
                args_parts.append(f"Required: {', '.join(required_args)}")
            if optional_args:
                args_parts.append(f"Optional: {', '.join(optional_args)}")
            
            if args_parts:
                tool_str += f" | Arguments - {' | '.join(args_parts)}"
        tools_description.append(tool_str)
    tools_str = "\n".join(tools_description)
    
    # Build the specialized prompt
    base_prompt = f"""You are a Sheet Identification Specialist for Excel workbooks containing insurance catastrophe loss data.

GOAL: {agent_goal.description}

AVAILABLE TOOLS:
{tools_str}

ARGUMENT EXTRACTION:
- Look in the conversation history for file paths mentioned by the user or parent agent
- Common patterns: "data/Submission Packs/[filename].xlsx" or user-provided paths
- If no file path is found, ask the user to provide it

RESPONSE FORMAT:
You MUST respond with valid JSON ONLY. No other text before or after the JSON.
{{
    "next": "confirm|question|done",
    "tool": "tool_name_or_null", 
    "args": {{"arg1": "value1"}},
    "response": "Your reasoning here"
}}

DECISION RULES:
- "next": "confirm" → Execute a tool
- "next": "question" → Need user input
- "next": "done" → Analysis complete, provide final recommendation

CURRENT CONVERSATION:
{json.dumps(compressed_history, indent=2)}"""

    # Add raw_json context if provided
    if raw_json:
        base_prompt += f"\n\nCURRENT TOOL DATA FOR VALIDATION:\n{json.dumps(raw_json, indent=2)}"

    return base_prompt
