"""Request and response models for the temporal supervisor agent."""

from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Literal, Optional, TypedDict, Union
from models.core import AgentGoal


# Common type aliases
Message = Dict[str, Union[str, Dict[str, Any]]]
ConversationHistory = Dict[str, List[Message]]
NextStep = Literal["confirm", "question", "done"]
CurrentTool = str


@dataclass
class AgentGoalWorkflowParams:
    """Parameters for workflow continuation."""
    conversation_summary: Optional[str] = None
    prompt_queue: Optional[Deque[str]] = None
    parent_workflow_id: Optional[str] = None  # ID of parent workflow if this is a child
    bridge_workflow_id: Optional[str] = None  # ID of root BridgeWorkflow for inter-agent data store


@dataclass
class CombinedInput:
    """Combined input for workflow activities."""
    agent_goal: AgentGoal
    tool_params: Optional[AgentGoalWorkflowParams] = None


@dataclass
class ToolPromptInput:
    """Input for tool prompt generation."""
    prompt: str
    context_instructions: str


class ToolData(TypedDict, total=False):
    """Tool execution data structure."""
    next: NextStep
    tool: str
    response: str
    args: Dict[str, Any]
    force_confirm: bool
    status: str
    error: str
    required_args: List[str]
