"""Temporal workflow for managing AI agent goal execution with tool access."""

import asyncio
from collections import deque
from datetime import timedelta
from typing import Any, Deque, Dict, List, Optional, Union

from temporalio import workflow
from temporalio.common import RetryPolicy

from models.core import AgentGoal
from models.requests import (
    ConversationHistory,
    CurrentTool,
    ToolData,
)
from shared.config import (
    LLM_ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
    LLM_ACTIVITY_START_TO_CLOSE_TIMEOUT,
)

with workflow.unsafe.imports_passed_through():
    from agents.core.agent_activities import AgentActivities
    from models.requests import CombinedInput, ToolPromptInput
    from agents.core.agent_prompt_generators import generate_genai_prompt, generate_tool_completion_prompt


@workflow.defn
class AgentGoalWorkflow:
    """Workflow that manages tool execution with user confirmation and conversation history."""

    def __init__(self) -> None:
        """Initialize workflow state and conversation tracking."""
        # Core conversation state
        self.conversation_history: ConversationHistory = {"messages": []}
        self.prompt_queue: Deque[str] = deque()
        self.chat_ended: bool = False
        
        # Tool execution state
        self.tool_data: Optional[ToolData] = None
        self.waiting_for_confirm: bool = False
        self.confirmed: bool = False
        self.last_tool_result: Optional[Dict[str, Any]] = None  # Store last tool result for data injection
        
        # Workflow completion state
        self.pending_completion: bool = False
        self.completion_confirmed: bool = False
        self.agent_result: Optional[Dict[str, Any]] = None  # Store the workflow completion result
        
        # Agent configuration
        self.goal: Optional[AgentGoal] = None
        
        # Parent workflow tracking (for child workflows)
        self.parent_workflow_id: Optional[str] = None  # ID of parent workflow if this is a child
        self.bridge_workflow_id: Optional[str] = None  # ID of root BridgeWorkflow for inter-agent data store and direct frontend signaling

    @workflow.run
    async def run(self, combined_input: CombinedInput) -> Dict[str, Any]:
        """Main workflow execution method that handles the interactive loop.
        
        Returns:
            Dict containing conversation_history and last_tool_result for structured data access
        """
        # Setup phase - initialize with agent goal and any existing tool params
        params = combined_input.tool_params
        self.goal = combined_input.agent_goal
        
        workflow.logger.info(f"Starting workflow for '{self.goal.agent_name}' with {len(self.goal.tools)} tools")

        # Store parent workflow ID if provided (for child workflows)
        if params and hasattr(params, 'parent_workflow_id') and params.parent_workflow_id:
            self.parent_workflow_id = params.parent_workflow_id
        
        # Store bridge_workflow_id for inter-agent data store signaling
        if params and hasattr(params, 'bridge_workflow_id') and params.bridge_workflow_id:
            self.bridge_workflow_id = params.bridge_workflow_id

        # Initialize prompt queue if provided in params
        if params and params.prompt_queue:
            self.prompt_queue.extend(params.prompt_queue)

        current_tool: Optional[CurrentTool] = None

        # Main interactive loop - handles user input processing and tool execution
        while True:
            # Wait for input from signals with timeout to prevent deadlocks
            try:
                await workflow.wait_condition(
                    lambda: bool(self.prompt_queue) or self.chat_ended or self.confirmed or self.completion_confirmed,
                    timeout=timedelta(seconds=5)  # Increased timeout for stability
                )
            except asyncio.TimeoutError:
                # Yield control periodically to prevent deadlocks and allow signal processing
                await workflow.sleep(0.1)
                continue

            # Handle workflow completion confirmation (highest priority)
            if self.completion_confirmed:
                workflow.logger.info("Workflow completion confirmed")
                self.add_message("user_confirmed_completion", {"status": "workflow_completion_confirmed", "timestamp": workflow.now().isoformat()})
                self.add_message("agent", {"response": "Workflow completed successfully!", "status": "completed"})
                return {
                    "conversation_history": self.conversation_history,
                    "last_tool_result": self.last_tool_result,
                    "agent_result": self.agent_result
                }

            # Handle chat end signal
            if self.chat_ended:
                workflow.logger.info("Chat ended")
                return {
                    "conversation_history": self.conversation_history,
                    "last_tool_result": self.last_tool_result
                }

            # PRIORITY 1: Execute tool if ready and confirmed
            if self.ready_for_tool_execution():
                if current_tool is None and self.tool_data:
                    current_tool = self.tool_data.get("tool")
                
                if current_tool is not None:
                    await self.execute_tool(current_tool)
                    current_tool = None
                    continue
                else:
                    workflow.logger.warning(f"Ready for tool execution but current_tool is None")
            
            # SPECIAL CASE: Handle pending workflow completion confirmation
            elif self.pending_completion and self.confirmed:
                self.completion_confirmed = True
                continue

            # PRIORITY 2: Process prompts from the queue (only if no tool execution pending)
            if self.prompt_queue and not (self.ready_for_tool_execution()):
                prompt = self.prompt_queue.popleft()

                self.add_message("user", prompt)

                # Generate context and prompt for LLM
                context_instructions = generate_genai_prompt(
                    agent_goal=self.goal,
                    conversation_history=self.conversation_history,
                    raw_json=self.tool_data,
                )

                prompt_input = ToolPromptInput(
                    prompt=prompt, context_instructions=context_instructions
                )

                # Call LLM for tool planning
                tool_data = await workflow.execute_activity_method(
                    AgentActivities.agent_toolPlanner,
                    prompt_input,
                    schedule_to_close_timeout=LLM_ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
                    start_to_close_timeout=LLM_ACTIVITY_START_TO_CLOSE_TIMEOUT,
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=5), backoff_coefficient=1
                    ),
                )
                
                # Yield control after LLM activity to prevent workflow task timeout
                await workflow.sleep(0)

                tool_data["force_confirm"] = True
                self.tool_data = ToolData(**tool_data)

                # Process the tool as dictated by the LLM response
                next_step = tool_data.get("next")
                current_tool: Optional[CurrentTool] = tool_data.get("tool")

                # Handle tool confirmation workflow
                if next_step == "confirm" and current_tool:
                    workflow.logger.info(f"Tool selected: {current_tool}")
                    
                    self.waiting_for_confirm = True
                    self.confirmed = False

                # Handle conversation end - require user confirmation for workflow completion
                elif next_step == "done":
                    workflow.logger.info("Workflow completion requested")
                    
                    # Add the agent's results to the conversation
                    agent_result = tool_data.get('response', {})
                    self.agent_result = agent_result
                    if agent_result:
                        result_message = {
                            "response": "Analysis complete! Here are my findings:",
                            "result": agent_result,
                            "type": "workflow_result"
                        }
                        self.add_message("agent", result_message)
                    
                    # Set workflow completion state
                    self.pending_completion = True
                    self.completion_confirmed = False
                    
                    # Create completion confirmation message
                    completion_message = {
                        "response": "Do you want to finish the workflow and proceed with these results?",
                        "agent_result": agent_result,
                        "next": "confirm_completion",
                        "type": "workflow_completion",
                        "status": "pending_confirmation"
                    }
                    
                    self.add_message("agent", completion_message)
                
                # Always add tool_data message for non-completion cases
                if next_step != "done":
                    self.add_message("agent", tool_data)

    def ready_for_tool_execution(self) -> bool:
        """Check if workflow is ready for tool execution."""
        return (
            self.confirmed and self.waiting_for_confirm and self.tool_data is not None
        )

    async def execute_tool(self, current_tool: CurrentTool) -> None:
        """Execute the confirmed tool and handle the result."""
        workflow.logger.info(f"Executing tool: {current_tool}")
        
        # Reset confirmation state before execution
        self.confirmed = False
        self.waiting_for_confirm = False

        # Use tool definition metadata to determine execution
        tool_args = self.tool_data.get("args", {})
        execution_type = "activity"
        activity_name = current_tool
        
        # Look up execution metadata from tool definition
        if self.goal and self.goal.tools:
            for tool_def in self.goal.tools:
                if tool_def.name == current_tool:
                    execution_type = tool_def.execution_type
                    if tool_def.activity_name:
                        activity_name = tool_def.activity_name
                    elif execution_type == "activity":
                        # Convert PascalCase to snake_case
                        import re
                        activity_name = re.sub(r'(?<!^)(?=[A-Z])', '_', current_tool).lower()
                    else:
                        activity_name = current_tool
                    break
            else:
                workflow.logger.warning(f"No tool definition found for: {current_tool}")
        
        try:
            if execution_type == "agent":
                # Execute as agent workflow
                execution_msg = f"I'm executing the {current_tool} tool. Starting the {current_tool.replace('Agent', ' Agent')} workflow..."
                self.add_message("agent", execution_msg)
                
                result = await self._execute_child_workflow_tool(current_tool, tool_args)
            else:
                # Execute as Temporal activity
                execution_msg = f"I'm executing the {current_tool} tool..."
                self.add_message("agent", execution_msg)
                
                # Inject bridge_workflow_id into tool_args for activities that need it
                if self.bridge_workflow_id:
                    tool_args["bridge_workflow_id"] = self.bridge_workflow_id
                
                # Replace USE_PREVIOUS_RESULT placeholders with actual data from last_tool_result
                if self.last_tool_result and isinstance(self.last_tool_result, dict):
                    for key, value in list(tool_args.items()):
                        if value == "USE_PREVIOUS_RESULT":
                            if key in self.last_tool_result:
                                tool_args[key] = self.last_tool_result[key]
                            elif key == "events_data" and "processed_events" in self.last_tool_result:
                                tool_args[key] = self.last_tool_result["processed_events"]
                            elif key == "new_records" and "all_records" in self.last_tool_result:
                                tool_args[key] = self.last_tool_result["all_records"]
                            else:
                                workflow.logger.warning(f"Could not find {key} in last_tool_result")
                
                result = await workflow.execute_activity(
                    activity_name,
                    args=[tool_args],
                    schedule_to_close_timeout=timedelta(minutes=30),  # Increased for complex operations
                    start_to_close_timeout=timedelta(minutes=15),    # Increased for complex operations
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=1),
                        maximum_attempts=3,
                        backoff_coefficient=2.0,
                    ),
                )
            
            # Add the tool result to conversation
            self.add_message("agent", result)
            
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            workflow.logger.error(error_msg)
            
            # Create structured error result for agent analysis
            error_result = {
                "success": False, 
                "error": str(e),
                "tool": current_tool,
                "args": tool_args,
                "error_type": "execution_failure"
            }
            
            # Add the error to conversation
            self.add_message("agent", error_result)
            result = error_result
        
        # Store result for potential use by next tool
        self.last_tool_result = result
        
        # Clear tool data after execution to prevent re-execution
        self.tool_data = None
        
        # After tool execution, automatically generate next step
        tool_completion_prompt = generate_tool_completion_prompt(
            current_tool=current_tool,
            dynamic_result=result,
            agent_goal=self.goal
        )
        
        self.prompt_queue.append(tool_completion_prompt)

    async def _execute_child_workflow_tool(self, tool_name: str, tool_args: dict) -> dict:
        """Execute a tool as a child workflow using the goal registry.
        
        Args:
            tool_name: Name of the tool to execute as child workflow
            tool_args: Arguments to pass to the child workflow
            
        Returns:
            Dict containing the child workflow execution result
        """
        try:
            from agents.core.goal_registry import create_goal_for_tool
            from models.requests import CombinedInput, AgentGoalWorkflowParams
            
            # Create the appropriate agent goal using the registry
            child_goal = create_goal_for_tool(tool_name, tool_args)
            
            # Create tool params with the arguments and parent workflow ID
            # Propagate bridge_workflow_id to child workflows for inter-agent data store
            tool_params = AgentGoalWorkflowParams(
                parent_workflow_id=workflow.info().workflow_id,
                bridge_workflow_id=self.bridge_workflow_id,  # Propagate bridge workflow ID
                prompt_queue=[child_goal.starter_prompt] if child_goal.starter_prompt else []
            )
            
            # Create combined input for child workflow
            combined_input = CombinedInput(
                agent_goal=child_goal,
                tool_params=tool_params
            )
            
            # Generate unique child workflow ID
            child_workflow_id = f"{tool_name.lower()}-{workflow.uuid4()}"
            
            # Execute child workflow
            workflow.logger.info(f"Starting child workflow for {tool_name}")
            
            child_handle = await workflow.start_child_workflow(
                AgentGoalWorkflow.run,
                combined_input,
                id=child_workflow_id,
                task_queue="submission-pack-task-queue",
                task_timeout=timedelta(seconds=240),  # Workflow task timeout for LLM calls
                execution_timeout=timedelta(minutes=60),  # Increased from 30 to 60 minutes
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=5),
                    maximum_attempts=2,
                    backoff_coefficient=2.0,
                ),
            )
            
            # Wait for the child workflow to complete and get the result
            result = await child_handle
            
            workflow.logger.info(f"Child workflow completed for {tool_name}")
            
            # Extract the workflow completion result directly
            if isinstance(result, dict) and "agent_result" in result:
                return result["agent_result"]
            else:
                return result
                
        except Exception as e:
            workflow.logger.error(f"Child workflow execution failed for {tool_name}: {str(e)}")
            return {
                "success": False,
                "error": f"Child workflow execution failed: {str(e)}",
                "tool": tool_name
            }

    def add_message(self, actor: str, response: Union[str, Dict[str, Any]]) -> None:
        """Add a message to the conversation history."""
        # Generate unique message ID for deduplication
        message_id = str(workflow.uuid4())
        
        # Add agent identification for agent messages
        message = {"actor": actor, "response": response, "message_id": message_id}
        if actor == "agent":
            if self.goal is None:
                workflow.logger.error("Cannot add agent message without proper goal initialization")
                raise RuntimeError("Agent goal must be initialized before adding agent messages")
            
            # Determine agent type based on goal
            agent_type = self.goal.agent_name
            
            # Add agent_type to message
            message["agent_type"] = agent_type
            
            # Also modify the response to include agent identification for frontend compatibility
            if isinstance(response, dict):
                # For structured responses, add agent_type field
                if "agent_type" not in response:
                    response["agent_type"] = agent_type
            else:
                # For string responses, prepend agent identification
                message["response"] = f"**{agent_type}:** {response}"

        self.conversation_history["messages"].append(message)
        
        # Signal bridge workflow directly for user interaction
        if (actor == "agent" or actor == "tool_result") and self.bridge_workflow_id:
            asyncio.create_task(self._signal_bridge_with_message(message))

    async def _signal_bridge_with_message(self, message: Dict[str, Any]) -> None:
        """Signal bridge workflow directly with new agent message."""
        if not self.bridge_workflow_id:
            return
        
        try:
            bridge_handle = workflow.get_external_workflow_handle(self.bridge_workflow_id)
            
            # Prepare message data for frontend bridge
            original_child_id = message.get("response", {}).get("child_workflow_id") if isinstance(message.get("response"), dict) else None
            effective_child_id = original_child_id or workflow.info().workflow_id
            
            signal_data = {
                "child_workflow_id": effective_child_id,
                "agent_type": message.get("agent_type"),
                "actor": message.get("actor"),
                "response": message.get("response"),
                "message_id": message.get("message_id")
            }
            
            await bridge_handle.signal("child_message_added", signal_data)
            
        except Exception as e:
            workflow.logger.warning(f"Failed to signal bridge workflow: {str(e)}")

    # Signal handlers for user interaction

    @workflow.signal
    async def user_prompt(self, prompt: str) -> None:
        """Signal handler for receiving user prompts from API endpoints."""
        if self.chat_ended:
            return
        
        self.prompt_queue.append(prompt)

    @workflow.signal
    async def confirm_tool(self) -> None:
        """Signal handler for user confirmation of tool execution."""
        workflow.logger.info("Tool confirmation received")
        
        # Prevent multiple confirmations
        if self.confirmed:
            return
        
        # Find the most recent tool confirmation message and add confirmation
        messages = self.conversation_history["messages"]
        
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if (msg.get("actor") == "agent" and 
                isinstance(msg.get("response"), dict) and
                msg.get("response", {}).get("next") == "confirm"):
                tool_name = msg.get("response", {}).get("tool", "unknown")
                confirmed_msg = msg["response"].copy()
                confirmed_msg["next"] = "confirmed"
                confirmed_msg["status"] = "user_confirmed"
                self.add_message("user_confirmed_tool_run", confirmed_msg)
                
                # Signal confirmation to bridge
                if self.bridge_workflow_id:
                    confirmation_message = {
                        "actor": "user_confirmed_tool_run",
                        "response": confirmed_msg,
                        "child_workflow_id": workflow.info().workflow_id,
                        "agent_type": self.goal.agent_name if self.goal else "Agent",
                        "message_id": str(workflow.uuid4())
                    }
                    asyncio.create_task(self._signal_bridge_with_message(confirmation_message))
                break
        
        self.confirmed = True
        if self.prompt_queue:
            self.prompt_queue.clear()

    @workflow.signal
    async def confirm_completion(self) -> None:
        """Signal handler for user confirmation of workflow completion."""
        workflow.logger.info("Workflow completion confirmation received")
        
        agent_type = self.goal.agent_name if self.goal else "Agent"
        
        self.add_message("user_confirmed_completion", {
            "status": "workflow_completion_confirmed",
            "timestamp": workflow.now().isoformat(),
            "message": "User confirmed workflow completion",
            "agent_type": agent_type
        })
        
        # Signal bridge directly - await to ensure it's sent before workflow completes
        if self.bridge_workflow_id:
            completion_message = {
                "actor": "user_confirmed_completion",
                "response": {
                    "status": "workflow_completion_confirmed",
                    "timestamp": workflow.now().isoformat(),
                    "agent_type": agent_type
                },
                "child_workflow_id": workflow.info().workflow_id,
                "agent_type": agent_type,
                "message_id": str(workflow.uuid4())
            }
            await self._signal_bridge_with_message(completion_message)
        
        self.completion_confirmed = True
        self.pending_completion = False

    @workflow.signal
    async def cancel_completion(self) -> None:
        """Signal handler for user cancellation of workflow completion."""
        workflow.logger.info("Workflow completion cancelled")
        
        cancellation_data = {
            "status": "workflow_completion_cancelled",
            "timestamp": workflow.now().isoformat(),
            "message": "User cancelled workflow completion",
            "workflow_type": self.goal.agent_name if self.goal else "Agent"
        }
        
        self.add_message("user_cancelled_completion", cancellation_data)
        
        if self.bridge_workflow_id:
            cancellation_message = {
                "actor": "user_cancelled_completion",
                "response": cancellation_data,
                "child_workflow_id": workflow.info().workflow_id,
                "agent_type": self.goal.agent_name if self.goal else "Agent",
                "message_id": str(workflow.uuid4())
            }
            asyncio.create_task(self._signal_bridge_with_message(cancellation_message))
        
        self.pending_completion = False
        self.completion_confirmed = False
        self.confirmed = False
        
        if self.prompt_queue:
            self.prompt_queue.clear()

    @workflow.signal
    async def cancel_tool(self) -> None:
        """Signal handler for user cancellation of tool execution."""
        tool_name = self.tool_data.get("tool") if self.tool_data else "unknown"
        workflow.logger.info(f"Tool cancelled: {tool_name}")
        
        cancellation_data = {
            "tool": tool_name,
            "status": "user_cancelled",
            "timestamp": workflow.now().isoformat(),
            "message": f"Tool execution cancelled by user: {tool_name}"
        }
        
        self.add_message("user_cancelled_tool_run", cancellation_data)
        
        if self.bridge_workflow_id:
            cancellation_message = {
                "actor": "user_cancelled_tool_run",
                "response": cancellation_data,
                "child_workflow_id": workflow.info().workflow_id,
                "agent_type": self.goal.agent_name if self.goal else "Agent",
                "message_id": str(workflow.uuid4())
            }
            asyncio.create_task(self._signal_bridge_with_message(cancellation_message))
        
        self.confirmed = False
        self.waiting_for_confirm = False
        self.tool_data = None
        
        if self.prompt_queue:
            self.prompt_queue.clear()

    @workflow.signal
    async def end_chat(self) -> None:
        """Signal handler for ending the chat session."""
        workflow.logger.info("Chat session ending")
        self.chat_ended = True

    # Query handlers for retrieving workflow state

    @workflow.query
    def get_frontend_messages(self) -> List[Dict[str, Any]]:
        """Query handler for frontend messages - redirects to parent workflow."""
        if not self.parent_workflow_id:
            # Standalone workflow - convert conversation to frontend format
            frontend_messages = []
            for msg in self.conversation_history.get("messages", []):
                frontend_msg = {
                    "message_id": msg.get("message_id", str(workflow.uuid4())),
                    "actor": msg.get("actor", "unknown"),
                    "response": msg.get("response", ""),
                    "timestamp": workflow.now().isoformat(),
                    "type": "agent_message",
                    "agent_type": msg.get("agent_type", self.goal.agent_name if self.goal else "Agent"),
                    "requires_confirmation": False,
                    "tool_name": None
                }
                frontend_messages.append(frontend_msg)
            return frontend_messages
        
        # For child workflows, return empty list with warning
        return [{
            "message_id": str(workflow.uuid4()),
            "actor": "system",
            "response": f"This is a child workflow. Please query the parent workflow: {self.parent_workflow_id}",
            "timestamp": workflow.now().isoformat(),
            "type": "error",
            "agent_type": "System",
            "requires_confirmation": False,
            "tool_name": None
        }]