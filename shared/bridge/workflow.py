"""Shared workflow that uses the simplified bridge communication.

This workflow can be used by any agent type and provides a clean interface
for frontend communication without the complexity of the agent stream system.
"""

import asyncio
from collections import deque
from datetime import timedelta
from typing import Any, Deque, Dict, Optional, List

from temporalio import workflow
from temporalio.common import RetryPolicy

from models.core import AgentGoal
from models.requests import CombinedInput, CurrentTool
from shared.config import (
    LLM_ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
    LLM_ACTIVITY_START_TO_CLOSE_TIMEOUT,
)

with workflow.unsafe.imports_passed_through():
    from agents.core.agent_activities import AgentActivities


@workflow.defn
class BridgeWorkflow:
    """Shared workflow that uses the simplified bridge for communication.
    
    This workflow can be used by any agent type and provides:
    - Direct frontend communication via the bridge
    - Simple tool confirmation workflow
    - Clean message handling without complex routing
    - Compatible with existing agent activities
    """

    def __init__(self) -> None:
        """Initialize workflow state."""
        # Frontend messages for API polling
        self.frontend_messages: List[Dict[str, Any]] = []
        self.prompt_queue: Deque[str] = deque()
        
        # Tool execution state (confirmation routing only - actual execution in AgentGoalWorkflow)
        self.waiting_for_confirm: bool = False
        self.confirmed: bool = False
        
        # Agent configuration
        self.goal: Optional[AgentGoal] = None
        self.show_tool_args_confirmation: bool = True
        
        # Frontend communication state
        self.workflow_id: Optional[str] = None
        self.agent_name: Optional[str] = None
        self._frontend_initialized = False
        
        # Agent workflow management
        self.agent_workflow_handle = None
        self.agent_workflow_id: Optional[str] = None
        
        # Active child workflow tracking for user prompt routing and tool confirmations
        self.active_child_workflow_id: Optional[str] = None
        
        # Track pending completion requests for routing confirm_completion signals
        self.pending_completion_workflow_id: Optional[str] = None
        
        # Inter-agent data store - simple storage for current workflow run
        self.as_of_year: Optional[str] = None
        self.events: List[dict] = []
        self.historical_matches: List[dict] = []
        self.cedant_records: List[dict] = []

    @workflow.run
    async def run(self, combined_input: CombinedInput) -> Dict[str, Any]:
        """Main workflow execution method using bridge."""
        # Setup phase
        params = combined_input.tool_params
        self.goal = combined_input.agent_goal

        # Log goal state for debugging
        workflow.logger.info(f"BRIDGE: Received goal '{self.goal.agent_name}' with {len(self.goal.tools)} tools")
        workflow.logger.info(f"BRIDGE: Tool names: {[tool.name for tool in self.goal.tools]}")

        # Initialize frontend communication
        if not self._frontend_initialized:
            workflow_id = workflow.info().workflow_id
            
            # Ensure goal is properly initialized before setting agent name
            if self.goal is None:
                workflow.logger.error("Goal is None during frontend initialization - this indicates an initialization timing issue")
                raise RuntimeError("Agent goal must be initialized before frontend initialization")
            
            agent_name = self.goal.agent_name
            
            workflow.logger.info(f"Initializing bridge for {agent_name} (workflow: {workflow_id})")
            
            # Store workflow info
            self.workflow_id = workflow_id
            self.agent_name = agent_name
            self._frontend_initialized = True
            
            # Send initial message directly to workflow state
            try:
                self.add_frontend_message("agent", f"Hello! I'm {agent_name}. How can I help you today?")
                workflow.logger.info(f"Initial message added successfully. Total messages: {len(self.frontend_messages)}")
            except Exception as e:
                workflow.logger.error(f"Error adding initial message: {e}")
                raise
            
            workflow.logger.info("Bridge initialization complete")

        # Look up environment settings
        await self.lookup_wf_env_settings()

        # Initialize prompt queue if provided
        if params and params.prompt_queue:
            self.prompt_queue.extend(params.prompt_queue)

        current_tool: Optional[CurrentTool] = None

        # Main interactive loop - wait for user to send first prompt
        while True:
            # Wait for input with timeout
            try:
                await workflow.wait_condition(
                    lambda: bool(self.prompt_queue) or self.confirmed,
                    timeout=timedelta(seconds=30)  # Longer timeout for user input
                )
            except asyncio.TimeoutError:
                # Continue waiting - this is normal when waiting for user input
                await workflow.sleep(1)
                continue

            # Tool confirmation handling is delegated to agent workflows
            if self.confirmed:
                # Reset confirmation state - actual tool execution handled by agent workflow
                self.confirmed = False
                self.waiting_for_confirm = False

            # Process user prompts
            if self.prompt_queue:
                user_prompt = self.prompt_queue.popleft()
                workflow.logger.info(f"Processing user prompt: {user_prompt[:50]}...")
                
                # Add user message to frontend messages
                if user_prompt != "system_ready":
                    self.add_frontend_message("user", user_prompt)
                
                # Forward to agent workflow
                await self.process_user_prompt(user_prompt)

    async def lookup_wf_env_settings(self):
        """Look up workflow environment settings."""
        # For now, use default settings
        self.show_tool_args_confirmation = True

    async def process_user_prompt(self, user_prompt: str):
        """Forward user prompt to the appropriate workflow (active child or main agent)."""
        try:
            workflow.logger.info(f"ROUTING DEBUG: active_child_workflow_id = {self.active_child_workflow_id}")
            
            # PRIORITY 1: Forward to active child workflow if one exists
            if self.active_child_workflow_id:
                workflow.logger.info(f"Forwarding prompt to active child workflow: {self.active_child_workflow_id}")
                try:
                    child_handle = workflow.get_external_workflow_handle(self.active_child_workflow_id)
                    await child_handle.signal("user_prompt", user_prompt)
                    workflow.logger.info(f"Successfully forwarded prompt to child workflow: {user_prompt[:50]}...")
                    return
                except Exception as e:
                    workflow.logger.error(f"Failed to forward prompt to child workflow {self.active_child_workflow_id}: {e}")
                    # Clear the invalid child workflow ID and fall back to main agent
                    self.active_child_workflow_id = None
            
            # PRIORITY 2: Forward to main agent workflow if no active child or child failed
            if hasattr(self, 'agent_workflow_handle') and self.agent_workflow_handle:
                await self.agent_workflow_handle.signal("user_prompt", user_prompt)
                workflow.logger.info(f"Forwarded prompt to main agent workflow: {user_prompt[:50]}...")
            else:
                # Start agent workflow if not already started
                await self.start_agent_workflow()
                if self.agent_workflow_handle:
                    await self.agent_workflow_handle.signal("user_prompt", user_prompt)
                else:
                    error_msg = "Failed to start agent workflow"
                    workflow.logger.error(error_msg)
                    self.add_frontend_message("agent", {"error": error_msg}, message_type="error")
                
        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            workflow.logger.error(error_msg)
            self.add_frontend_message("agent", {"error": error_msg}, message_type="error")

    # Signal handlers for compatibility with existing API
    @workflow.signal
    def user_prompt(self, prompt: str) -> None:
        """Signal handler for user prompts."""
        workflow.logger.info(f"Signal received: user_prompt - '{prompt[:50]}...'")
        self.prompt_queue.append(prompt)

    @workflow.signal
    def confirm_tool(self) -> None:
        """Signal handler for tool confirmation - forward to correct child workflow."""
        workflow.logger.info("Signal received: confirm_tool")
        
        # If we have a pending tool confirmation from a specific child workflow, forward to that workflow
        if self.active_child_workflow_id:
            workflow.logger.info(f"Forwarding confirmation to child workflow: {self.active_child_workflow_id}")
            try:
                # Get handle to the specific child workflow that requested confirmation
                child_handle = workflow.get_external_workflow_handle(self.active_child_workflow_id)
                asyncio.create_task(child_handle.signal("confirm_tool"))
                # Clear the pending child workflow ID
                self.active_child_workflow_id = None
            except Exception as e:
                workflow.logger.error(f"Failed to forward confirmation to child workflow {self.active_child_workflow_id}: {e}")
                # Fallback to forwarding to our own child workflow
                if hasattr(self, 'agent_workflow_handle') and self.agent_workflow_handle:
                    asyncio.create_task(self.agent_workflow_handle.signal("confirm_tool"))
        elif hasattr(self, 'agent_workflow_handle') and self.agent_workflow_handle:
            # Fallback: Forward confirmation to our own child workflow
            workflow.logger.info("No pending child workflow, forwarding to own child workflow")
            asyncio.create_task(self.agent_workflow_handle.signal("confirm_tool"))
        
        self.confirmed = True
        self.waiting_for_confirm = False

    @workflow.signal
    def cancel_tool(self) -> None:
        """Signal handler for tool cancellation - forward to correct child workflow."""
        workflow.logger.info("Signal received: cancel_tool")
        
        # If we have a pending tool confirmation from a specific child workflow, forward to that workflow
        if self.active_child_workflow_id:
            workflow.logger.info(f"Forwarding cancellation to child workflow: {self.active_child_workflow_id}")
            try:
                # Get handle to the specific child workflow that requested confirmation
                child_handle = workflow.get_external_workflow_handle(self.active_child_workflow_id)
                asyncio.create_task(child_handle.signal("cancel_tool"))
                # DON'T clear the active child workflow ID - the cancelled workflow should remain active
                # so that subsequent "let's try again" prompts get routed to it
                workflow.logger.info(f"Keeping {self.active_child_workflow_id} as active child for potential retry")
            except Exception as e:
                workflow.logger.error(f"Failed to forward cancellation to child workflow {self.active_child_workflow_id}: {e}")
                # Fallback to forwarding to our own child workflow
                if hasattr(self, 'agent_workflow_handle') and self.agent_workflow_handle:
                    asyncio.create_task(self.agent_workflow_handle.signal("cancel_tool"))
        elif hasattr(self, 'agent_workflow_handle') and self.agent_workflow_handle:
            # Fallback: Forward cancellation to our own child workflow
            workflow.logger.info("No pending child workflow, forwarding to own child workflow")
            asyncio.create_task(self.agent_workflow_handle.signal("cancel_tool"))
        
        self.confirmed = False
        self.waiting_for_confirm = False


    @workflow.signal
    def confirm_completion(self) -> None:
        """Signal handler for workflow completion confirmation - forward to correct child workflow."""
        workflow.logger.info("Signal received: confirm_completion")
        workflow.logger.info(f"pending_completion_workflow_id: {self.pending_completion_workflow_id}, active_child_workflow_id: {self.active_child_workflow_id}")
        
        # PRIORITY 1: Use pending_completion_workflow_id if set (most accurate for nested workflows)
        if self.pending_completion_workflow_id:
            workflow.logger.info(f"Forwarding completion confirmation to pending completion workflow: {self.pending_completion_workflow_id}")
            try:
                child_handle = workflow.get_external_workflow_handle(self.pending_completion_workflow_id)
                asyncio.create_task(child_handle.signal("confirm_completion"))
                # Clear the pending completion workflow ID after forwarding
                self.pending_completion_workflow_id = None
                return
            except Exception as e:
                workflow.logger.error(f"Failed to forward completion confirmation to pending workflow {self.pending_completion_workflow_id}: {e}")
                self.pending_completion_workflow_id = None
                # Fall through to try other options
        
        # PRIORITY 2: If we have an active child workflow, forward to that workflow
        if self.active_child_workflow_id:
            workflow.logger.info(f"Forwarding completion confirmation to active child workflow: {self.active_child_workflow_id}")
            try:
                child_handle = workflow.get_external_workflow_handle(self.active_child_workflow_id)
                asyncio.create_task(child_handle.signal("confirm_completion"))
                return
            except Exception as e:
                workflow.logger.error(f"Failed to forward completion confirmation to child workflow {self.active_child_workflow_id}: {e}")
                # Fall through to fallback
        
        # PRIORITY 3: Fallback to our own child workflow
        if hasattr(self, 'agent_workflow_handle') and self.agent_workflow_handle:
            workflow.logger.info("No active child workflow, forwarding completion confirmation to own child workflow")
            asyncio.create_task(self.agent_workflow_handle.signal("confirm_completion"))

    @workflow.signal
    def cancel_completion(self) -> None:
        """Signal handler for workflow completion cancellation - forward to correct child workflow."""
        workflow.logger.info("Signal received: cancel_completion")
        workflow.logger.info(f"pending_completion_workflow_id: {self.pending_completion_workflow_id}, active_child_workflow_id: {self.active_child_workflow_id}")
        
        # PRIORITY 1: Use pending_completion_workflow_id if set (most accurate for nested workflows)
        if self.pending_completion_workflow_id:
            workflow.logger.info(f"Forwarding completion cancellation to pending completion workflow: {self.pending_completion_workflow_id}")
            try:
                child_handle = workflow.get_external_workflow_handle(self.pending_completion_workflow_id)
                asyncio.create_task(child_handle.signal("cancel_completion"))
                # Clear the pending completion workflow ID after forwarding
                self.pending_completion_workflow_id = None
                return
            except Exception as e:
                workflow.logger.error(f"Failed to forward completion cancellation to pending workflow {self.pending_completion_workflow_id}: {e}")
                self.pending_completion_workflow_id = None
                # Fall through to try other options
        
        # PRIORITY 2: If we have an active child workflow, forward to that workflow
        if self.active_child_workflow_id:
            workflow.logger.info(f"Forwarding completion cancellation to active child workflow: {self.active_child_workflow_id}")
            try:
                child_handle = workflow.get_external_workflow_handle(self.active_child_workflow_id)
                asyncio.create_task(child_handle.signal("cancel_completion"))
                return
            except Exception as e:
                workflow.logger.error(f"Failed to forward completion cancellation to child workflow {self.active_child_workflow_id}: {e}")
                # Fall through to fallback
        
        # PRIORITY 3: Fallback to our own child workflow
        if hasattr(self, 'agent_workflow_handle') and self.agent_workflow_handle:
            workflow.logger.info("No active child workflow, forwarding completion cancellation to own child workflow")
            asyncio.create_task(self.agent_workflow_handle.signal("cancel_completion"))

    @workflow.signal
    async def store_extraction_data(self, data: dict) -> None:
        """Signal handler for storing extraction data from activities.
        
        Args:
            data: Dictionary containing:
                - type: Data type ("as_of_year" or "events")
                - value: The actual data to store
        """
        try:
            data_type = data.get("type")
            value = data.get("value")
            
            if not data_type:
                workflow.logger.error("Missing data type in store_extraction_data signal")
                return
            
            if value is None:
                workflow.logger.error("Missing value in store_extraction_data signal")
                return
            
            if data_type == "as_of_year":
                self.as_of_year = str(value)
                workflow.logger.info(f"Stored AsOfYear: '{value}'")
            elif data_type == "events":
                if isinstance(value, list):
                    self.events = value
                    workflow.logger.info(f"Stored {len(value)} events")
                else:
                    workflow.logger.error(f"Events data must be a list, got {type(value)}")
                    return
            elif data_type == "historical_matches":
                if isinstance(value, list):
                    self.historical_matches = value
                    workflow.logger.info(f"Stored {len(value)} historical_matches")
                else:
                    workflow.logger.error(f"historical_matches data must be a list, got {type(value)}")
                    return
            elif data_type == "cedant_records":
                if isinstance(value, list):
                    self.cedant_records = value
                    workflow.logger.info(f"Stored {len(value)} cedant_records")
                else:
                    workflow.logger.error(f"cedant_records data must be a list, got {type(value)}")
                    return
            else:
                workflow.logger.error(f"Unknown data type: {data_type}")
                return
            
        except Exception as e:
            workflow.logger.error(f"Error storing extraction data: {str(e)}")

    @workflow.signal
    def child_message_added(self, signal_data: Dict[str, Any]) -> None:
        """Signal handler for receiving messages from child agent workflows."""
        child_workflow_id = signal_data.get('child_workflow_id', 'unknown')
        workflow.logger.debug(f"Signal received: child_message_added from {child_workflow_id}")
        workflow.logger.debug(f"Signal data: {signal_data}")
        
        # Track child that sends a message as the active child for user prompt routing
        # BUT NOT for cancellation messages - cancelled workflows should not receive new prompts
        actor = signal_data.get("actor", "agent")
        if actor not in ["user_cancelled_tool_run", "user_cancelled_completion"]:
            self.active_child_workflow_id = child_workflow_id
            workflow.logger.debug(f"Set active child workflow for routing: {child_workflow_id}")
        else:
            workflow.logger.debug(f"Cancellation message from {child_workflow_id} - NOT setting as active child")
        
        # Process flat message structure (consistent across all workflows)
        response = signal_data.get("response", "")
        
        workflow.logger.debug(f"Processing child message: actor={actor}, response_type={type(response)}, response_preview={str(response)[:100]}...")
        
        # Extract agent_type from the signal data
        child_agent_type = signal_data.get("agent_type")
        workflow.logger.debug(f"Child agent type: {child_agent_type}")
        
        # Track pending completion requests so we can route confirm_completion to the right workflow
        if actor == "agent" and isinstance(response, dict):
            if response.get("next") == "confirm_completion" and response.get("type") == "workflow_completion":
                # Use original_workflow_id if available (preserved through message chain), otherwise use child_workflow_id
                original_id = response.get("original_workflow_id") or child_workflow_id
                self.pending_completion_workflow_id = original_id
                workflow.logger.info(f"Tracking pending completion from workflow: {original_id} (agent_type: {child_agent_type})")
        
        # Convert agent message to frontend format
        if actor == "agent":
            # NOTE: We do NOT filter workflow completion messages here because this is the
            # BridgeWorkflow - completion messages from the direct child (Supervisor Agent)
            # SHOULD reach the frontend so the user can confirm workflow completion.
            # Nested child workflow completions are filtered in AgentGoalWorkflow.child_message_added()
            
            # Check if this is a tool confirmation message from child workflow
            if (isinstance(response, dict) and 
                response.get("next") == "confirm" and 
                response.get("tool")):
                # This is a tool confirmation - already tracked above for routing
                workflow.logger.debug(f"Processing child tool confirmation: {response.get('tool')} from {child_workflow_id}")
                self.add_frontend_message_with_agent_type("agent", response, child_agent_type)
            else:
                # Regular agent message - use the child workflow's agent type
                self.add_frontend_message_with_agent_type("agent", response, child_agent_type)
            workflow.logger.debug(f"Added child agent message to frontend messages. Total messages: {len(self.frontend_messages)}")
        elif actor == "tool_result":
            # Tool result format - extract tool name from response
            tool_name = response.get("tool", "unknown_tool") if isinstance(response, dict) else "unknown_tool"
            self.add_frontend_message_with_agent_type(
                "tool_result", 
                {"tool": tool_name, "result": response},
                child_agent_type,
                message_type="tool_result",
                tool_name=tool_name
            )
            workflow.logger.debug(f"Added child tool result message to frontend messages. Total messages: {len(self.frontend_messages)}")
        elif actor == "user_cancelled_tool_run":
            # Preserve the cancellation message structure for frontend polling detection
            self.add_frontend_message("user_cancelled_tool_run", response, message_type="user_cancelled_tool_run")
            workflow.logger.debug(f"Added child cancellation message to frontend messages. Total messages: {len(self.frontend_messages)}")
        elif actor == "user_confirmed_tool_run":
            # Preserve the confirmation message structure for frontend polling detection
            # But don't add it to the conversation display to avoid showing duplicate confirmations
            self.add_frontend_message("user_confirmed_tool_run", response, message_type="user_confirmed_tool_run")
            workflow.logger.debug(f"Added child confirmation message to frontend messages (hidden from conversation). Total messages: {len(self.frontend_messages)}")
        elif actor == "user_confirmed_completion":
            # Preserve the completion confirmation message structure for frontend polling detection
            # This allows the frontend to clear the workflow completion dialog
            workflow.logger.info(f"COMPLETION CONFIRM: Received user_confirmed_completion for {child_agent_type}")
            workflow.logger.info(f"COMPLETION CONFIRM: response = {response}")
            self.add_frontend_message_with_agent_type("user_confirmed_completion", response, child_agent_type, message_type="user_confirmed_completion")
            workflow.logger.info(f"COMPLETION CONFIRM: Added to frontend_messages. Total: {len(self.frontend_messages)}")
        elif actor == "user_cancelled_completion":
            # Preserve the completion cancellation message structure for frontend polling detection
            self.add_frontend_message_with_agent_type("user_cancelled_completion", response, child_agent_type, message_type="user_cancelled_completion")
            workflow.logger.debug(f"Added child completion cancellation message to frontend messages. Total messages: {len(self.frontend_messages)}")
        else:
            # Generic message
            self.add_frontend_message(actor, response)
            workflow.logger.debug(f"Added child generic message to frontend messages. Total messages: {len(self.frontend_messages)}")


    # Query handlers for frontend API
    @workflow.query
    def get_frontend_messages(self) -> List[Dict[str, Any]]:
        """Query handler for frontend messages."""
        workflow.logger.debug(f"get_frontend_messages called - returning {len(self.frontend_messages)} messages")
        return self.frontend_messages

    @workflow.query
    def get_extraction_data(self) -> dict:
        """Query handler for retrieving stored extraction data.
            
        Returns:
            Dictionary containing:
                - as_of_year: AsOfYear value if available, None otherwise
                - events: Events array if available, empty list otherwise
                - events_count: Number of events stored
                - historical_matches: Historical matches array if available
                - cedant_records: Cedant records array if available
        """
        try:
            result = {
                "as_of_year": self.as_of_year,
                "events": self.events,
                "events_count": len(self.events),
                "historical_matches": self.historical_matches,
                "historical_matches_count": len(self.historical_matches),
                "cedant_records": self.cedant_records,
                "cedant_records_count": len(self.cedant_records)
            }
            
            workflow.logger.info(f"Retrieved extraction data: AsOfYear={self.as_of_year}, Events={len(self.events)}, HistoricalMatches={len(self.historical_matches)}, CedantRecords={len(self.cedant_records)}")
            return result
            
        except Exception as e:
            workflow.logger.error(f"Error retrieving extraction data: {str(e)}")
            return {
                "as_of_year": None,
                "events": [],
                "events_count": 0,
                "error": str(e)
            }

    # Helper methods for message management
    def add_frontend_message(
        self,
        actor: str,
        content: Any,
        message_type: str = "agent_message",
        requires_confirmation: bool = False,
        tool_name: Optional[str] = None
    ) -> None:
        """Add a message to the frontend message list using the bridge's agent type."""
        self.add_frontend_message_with_agent_type(
            actor, content, self.agent_name, message_type, requires_confirmation, tool_name
        )

    def add_frontend_message_with_agent_type(
        self,
        actor: str,
        content: Any,
        agent_type: Optional[str] = None,
        message_type: str = "agent_message",
        requires_confirmation: bool = False,
        tool_name: Optional[str] = None
    ) -> None:
        """Add a message to the frontend message list with a specific agent type."""
        # Use provided agent_type or fall back to bridge's agent name
        effective_agent_type = agent_type or self.agent_name
        
        # Ensure proper initialization for agent messages
        if actor == "agent" and effective_agent_type is None:
            workflow.logger.warning("Agent type is None when adding frontend message - this indicates an initialization timing issue")
            raise RuntimeError("Agent type must be initialized before adding frontend messages")
            
        message = {
            "message_id": workflow.uuid4(),  # Use Temporal's deterministic UUID
            "actor": actor,
            "response": content,
            "timestamp": workflow.now().isoformat(),  # Use Temporal's deterministic time
            "type": message_type,
            "agent_type": effective_agent_type,  # Use the provided agent_type
            "requires_confirmation": requires_confirmation,
            "tool_name": tool_name
        }
        self.frontend_messages.append(message)
        workflow.logger.debug(f"Added frontend message: {actor} - {message_type} - {effective_agent_type}")

    async def start_agent_workflow(self) -> None:
        """Start the agent workflow as a child workflow."""
        try:
            from agents.core.agent_goal_workflow import AgentGoalWorkflow
            from models.requests import CombinedInput, AgentGoalWorkflowParams
            
            # Create agent workflow ID
            self.agent_workflow_id = f"{self.workflow_id}-agent"
            
            # Create tool params with parent workflow ID and bridge workflow ID
            # The bridge_workflow_id is this workflow's ID since BridgeWorkflow
            # is the root workflow that stores inter-agent data (events, as_of_year, etc.)
            tool_params = AgentGoalWorkflowParams(
                parent_workflow_id=self.workflow_id,  # Set bridge as parent
                bridge_workflow_id=self.workflow_id,  # This workflow stores the inter-agent data
                prompt_queue=[]
            )
            
            # DEBUG: Log goal state BEFORE passing to child workflow
            workflow.logger.info(f"BRIDGE START_AGENT: About to pass goal to child workflow")
            workflow.logger.info(f"BRIDGE START_AGENT: Goal '{self.goal.agent_name}' with {len(self.goal.tools)} tools")
            for tool in self.goal.tools:
                workflow.logger.info(f"BRIDGE START_AGENT: Tool '{tool.name}' execution_type={tool.execution_type}, activity_name={tool.activity_name}")
            
            # Create combined input for agent workflow
            combined_input = CombinedInput(
                agent_goal=self.goal,
                tool_params=tool_params
            )
            
            # Start agent workflow as child
            self.agent_workflow_handle = await workflow.start_child_workflow(
                AgentGoalWorkflow.run,
                combined_input,
                id=self.agent_workflow_id,
                task_queue="submission-pack-task-queue",
                task_timeout=timedelta(minutes=10),  # Workflow task timeout for LLM calls
            )
            
            workflow.logger.info(f"Started agent workflow: {self.agent_workflow_id} with parent_workflow_id: {self.workflow_id}")
            
        except Exception as e:
            workflow.logger.error(f"Failed to start agent workflow: {e}")
            raise


# Backwards compatibility alias
FrontendBridgeWorkflow = BridgeWorkflow
