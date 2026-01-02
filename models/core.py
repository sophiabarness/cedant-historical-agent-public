"""Core data models for the temporal supervisor agent."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ToolArgument:
    """Represents an argument for a tool definition."""
    name: str
    type: str  # "string", "float", "ISO8601", etc.
    description: str
    required: bool = True  # Default to required unless explicitly set to False


@dataclass
class ToolDefinition:
    """Represents a tool that can be used by the agent.
    
    IMPORTANT: When Temporal serializes/deserializes this dataclass, it uses JSON.
    The default JSON converter may not preserve field values correctly if they
    rely on Python defaults. Always explicitly set execution_type and activity_name.
    """
    name: str
    description: str
    arguments: List[ToolArgument]
    # CRITICAL: These fields MUST be explicitly set when creating ToolDefinition
    # Do NOT rely on defaults - Temporal serialization may not preserve them correctly
    execution_type: str = field(default="activity")  # "activity" or "agent"
    activity_name: Optional[str] = field(default=None)  # Optional: specify exact activity name
    
    def __post_init__(self):
        """Validate and log tool definition creation."""
        # Ensure execution_type is valid
        if self.execution_type not in ("activity", "agent"):
            raise ValueError(f"Invalid execution_type: {self.execution_type}. Must be 'activity' or 'agent'")


@dataclass
class AgentGoal:
    """Represents an agent goal configuration."""
    agent_name: str
    tools: List[ToolDefinition]
    description: str
    starter_prompt: str
    example_conversation_history: str