"""Prompt generators for agent workflows."""

import json
from typing import Optional

from models.core import AgentGoal
from models.requests import ConversationHistory, ToolData
from agents.core.prompts import (
    GENAI_PROMPT,
    TOOLCHAIN_COMPLETE_GUIDANCE_PROMPT,
)


def _truncate_large_data(data: any, max_length: int = 500) -> any:
    """
    Truncate large data structures to reduce token usage while preserving usefulness.
    
    Args:
        data: Data to potentially truncate (dict, list, str, or other)
        max_length: Maximum characters for strings (default: 500)
        
    Returns:
        Truncated version of the data that's still useful
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # For historical_matches, just show count and availability note (they're too large for history)
            if key == "historical_matches" and isinstance(value, list):
                result[key] = {
                    "_summary": f"{len(value)} historical matches available",
                    "_count": len(value),
                    "_note": "Full data stored in workflow state, accessible to tools"
                }
            # For event/item lists, show first 3 items instead of all
            elif key in ["events", "processed_events", "extracted_events"] and isinstance(value, list):
                if len(value) > 3:
                    result[key] = value[:3] + [f"... and {len(value) - 3} more items"]
                else:
                    result[key] = value
            # Truncate large strings
            elif isinstance(value, str) and len(value) > max_length:
                result[key] = value[:max_length] + "..."
            # Recursively truncate nested dicts
            elif isinstance(value, dict):
                result[key] = _truncate_large_data(value, max_length)
            # Keep lists as-is if small
            elif isinstance(value, list):
                if len(value) > 10:
                    result[key] = value[:10] + [f"... and {len(value) - 10} more items"]
                else:
                    result[key] = value
            else:
                result[key] = value
        return result
    elif isinstance(data, str) and len(data) > max_length:
        return data[:max_length] + "..."
    elif isinstance(data, list) and len(data) > 10:
        return data[:10] + [f"... and {len(data) - 10} more items"]
    else:
        return data


def compress_conversation_history(
    conversation_history: ConversationHistory,
    max_recent_messages: int = 10
) -> ConversationHistory:
    """
    Compress conversation history to reduce token usage while preserving context.
    
    Strategy:
    - Keep the most recent N messages (default: 10)
    - Summarize older messages into a condensed format
    - Preserve key information like tool results and decisions
    - Truncate large data structures (show first 3 items of large lists)
    
    Args:
        conversation_history: The full conversation history
        max_recent_messages: Number of recent messages to keep in full (default: 10)
        
    Returns:
        ConversationHistory: Compressed version of the history
    """
    messages = conversation_history.get("messages", [])
    
    # If history is small enough, still truncate large data
    if len(messages) <= max_recent_messages:
        compressed_messages = []
        for msg in messages:
            compressed_msg = msg.copy()
            # Handle both "data" and "response" fields (response is used for tool_result messages)
            if "data" in compressed_msg:
                compressed_msg["data"] = _truncate_large_data(compressed_msg["data"])
            if "response" in compressed_msg and isinstance(compressed_msg["response"], dict):
                compressed_msg["response"] = _truncate_large_data(compressed_msg["response"])
            compressed_messages.append(compressed_msg)
        return {"messages": compressed_messages}
    
    # Split into old and recent messages
    old_messages = messages[:-max_recent_messages]
    recent_messages = messages[-max_recent_messages:]
    
    # Create summary of old messages
    tool_executions = []
    user_queries = []
    
    for msg in old_messages:
        msg_type = msg.get("type", "")
        
        # Track tool executions
        if msg_type == "user_confirmed_tool_run":
            tool_name = msg.get("data", {}).get("tool")
            if tool_name:
                tool_executions.append(tool_name)
        
        # Track user queries
        elif msg_type == "user":
            user_msg = msg.get("data", {}).get("message", "")
            if user_msg and len(user_msg) < 100:  # Only short queries
                user_queries.append(user_msg)
    
    # Create condensed summary message
    summary_parts = []
    if tool_executions:
        tool_counts = {}
        for tool in tool_executions:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
        tool_summary = ", ".join([f"{tool}({count})" for tool, count in tool_counts.items()])
        summary_parts.append(f"Tools executed: {tool_summary}")
    
    if user_queries:
        summary_parts.append(f"Earlier queries: {'; '.join(user_queries[:3])}")
    
    summary_message = {
        "type": "system_summary",
        "data": {
            "message": f"[Earlier conversation summary] {' | '.join(summary_parts)}",
            "compressed_messages": len(old_messages)
        }
    }
    
    # Truncate large data in recent messages
    compressed_recent = []
    for msg in recent_messages:
        compressed_msg = msg.copy()
        # Handle both "data" and "response" fields (response is used for tool_result messages)
        if "data" in compressed_msg:
            compressed_msg["data"] = _truncate_large_data(compressed_msg["data"])
        if "response" in compressed_msg and isinstance(compressed_msg["response"], dict):
            compressed_msg["response"] = _truncate_large_data(compressed_msg["response"])
        compressed_recent.append(compressed_msg)
    
    # Return compressed history
    return {
        "messages": [summary_message] + compressed_recent
    }


def generate_genai_prompt(
    agent_goal: AgentGoal,
    conversation_history: ConversationHistory,
    raw_json: Optional[ToolData] = None,
) -> str:
    """
    Generates a concise prompt for producing or validating JSON instructions
    with the provided tools and conversation history.
    
    Enhanced to detect different agent types and use specialized prompts.
    
    Args:
        agent_goal: The agent's goal configuration with tools and description
        conversation_history: The ongoing conversation context
        raw_json: Optional existing tool data for validation
        
    Returns:
        str: Formatted prompt string for LLM processing
    """
    # Check if this is a sheet identification agent
    if agent_goal.agent_name == "Sheet Identification Specialist":
        from agents.supervisor.tools.submission_pack_parser.tools.sheet_identification.prompt import generate_sheet_identification_prompt
        return generate_sheet_identification_prompt(agent_goal, conversation_history, raw_json)
    
    # Use standard prompt generation for all agents (including catastrophe extraction)
    # The catastrophe-specific prompt was removed as SubmissionPackParserAgent handles extraction directly
    return generate_standard_agent_prompt(agent_goal, conversation_history, raw_json)


def generate_standard_agent_prompt(
    agent_goal: AgentGoal,
    conversation_history: ConversationHistory,
    raw_json: Optional[ToolData] = None,
) -> str:
    """
    Generates the standard agent prompt for non-catastrophe agents.
    
    This is the original prompt generation logic, extracted for clarity.
    """
    # Compress conversation history to reduce token usage
    original_msg_count = len(conversation_history.get("messages", []))
    compressed_history = compress_conversation_history(conversation_history, max_recent_messages=10)
    compressed_msg_count = len(compressed_history.get("messages", []))
    
    # Log compression stats
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Conversation compression: {original_msg_count} msgs → {compressed_msg_count} msgs")
    
    # Prepare template variables
    template_vars = {
        "agent_goal": agent_goal,
        "conversation_history_json": json.dumps(compressed_history, indent=2),
        "toolchain_complete_guidance": TOOLCHAIN_COMPLETE_GUIDANCE_PROMPT,
        "raw_json": raw_json,
        "raw_json_str": (
            json.dumps(raw_json, indent=2) if raw_json is not None else None
        ),
    }

    return GENAI_PROMPT.render(**template_vars)


def generate_tool_completion_prompt(current_tool: str, dynamic_result: dict, agent_goal=None) -> str:
    """
    Generates a prompt for handling tool completion and determining next steps.
    Uses agent-specific prompts based on the agent type.

    Args:
        current_tool: The name of the tool that just completed
        dynamic_result: The result data from the tool execution
        agent_goal: The agent goal to determine which prompt to use

    Returns:
        str: A formatted prompt string for the agent to process the tool completion
    """
    if agent_goal and hasattr(agent_goal, 'agent_name'):
        agent_name = agent_goal.agent_name
        
        # Use agent-specific tool completion prompts
        if agent_name == "Supervisor Agent":
            try:
                from agents.supervisor.tool_completion import generate_supervisor_tool_completion_prompt
                return generate_supervisor_tool_completion_prompt(current_tool, dynamic_result)
            except ImportError:
                pass
        
        elif agent_name == "Submission Pack Parser":
            try:
                from agents.supervisor.tools.submission_pack_parser.tool_completion import generate_submission_pack_parser_tool_completion_prompt
                return generate_submission_pack_parser_tool_completion_prompt(current_tool, dynamic_result)
            except ImportError:
                pass
        
        elif agent_name == "Sheet Identification Specialist":
            try:
                from agents.supervisor.tools.submission_pack_parser.tools.sheet_identification.tool_completion import generate_sheet_identification_tool_completion_prompt
                return generate_sheet_identification_tool_completion_prompt(current_tool, dynamic_result)
            except ImportError:
                pass
    
    # Fallback to Supervisor prompt as default (most generic)
    from agents.supervisor.tool_completion import generate_supervisor_tool_completion_prompt
    return generate_supervisor_tool_completion_prompt(current_tool, dynamic_result)
