"""FastAPI server for temporal supervisor agent user interaction."""

import asyncio
import uuid
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from models.requests import CombinedInput
from shared.bridge.workflow import BridgeWorkflow
from agents.core.goal_registry import get_agent_goal_by_name
from shared.config import get_temporal_client, TEMPORAL_TASK_QUEUE


# Pydantic models for API requests
class SendPromptRequest(BaseModel):
    """Request model for sending user prompts."""
    prompt: str
    workflow_id: str


class ConfirmRequest(BaseModel):
    """Request model for confirming tool execution."""
    workflow_id: str


class CancelToolRequest(BaseModel):
    """Request model for cancelling tool execution."""
    workflow_id: str


class StartWorkflowRequest(BaseModel):
    """Request model for starting a new workflow."""
    workflow_id: Optional[str] = None
    agent_name: Optional[str] = "Supervisor Agent"


# Response models
class ApiResponse(BaseModel):
    """Standard API response model."""
    success: bool
    message: str
    data: Dict[str, Any] = {}


# Global Temporal client - will be initialized on startup
temporal_client: Client = None


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    global temporal_client
    # Startup
    try:
        temporal_client = await get_temporal_client()
        print(f"Successfully connected to Temporal server")
    except Exception as e:
        print(f"Failed to connect to Temporal server: {e}")
        raise
    
    yield


# Initialize FastAPI app with lifespan handler
app = FastAPI(
    title="Temporal Supervisor Agent API",
    description="API for interacting with the temporal supervisor agent",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)


@app.post("/send-prompt", response_model=ApiResponse)
async def send_prompt(request: SendPromptRequest) -> ApiResponse:
    """Send a user prompt directly to the workflow via signal."""
    try:
        if not temporal_client:
            raise HTTPException(
                status_code=503,
                detail="Temporal client not initialized"
            )
        
        # Get workflow handle
        handle = temporal_client.get_workflow_handle(request.workflow_id)
        
        # Verify workflow is running
        try:
            await handle.describe()
        except Exception:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow with ID {request.workflow_id} not found"
            )
        
        # Send prompt signal to workflow
        await handle.signal("user_prompt", request.prompt)
        
        return ApiResponse(
            success=True,
            message=f"Prompt sent to workflow {request.workflow_id}",
            data={"workflow_id": request.workflow_id, "prompt": request.prompt}
        )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send prompt: {str(e)}"
        )


@app.get("/get-conversation-history/{workflow_id}", response_model=ApiResponse)
async def get_conversation_history(workflow_id: str) -> ApiResponse:
    """Get conversation history by querying the workflow directly."""
    try:
        if not temporal_client:
            raise HTTPException(
                status_code=503,
                detail="Temporal client not initialized"
            )
        
        # Get workflow handle
        handle = temporal_client.get_workflow_handle(workflow_id)
        
        # Query the workflow for frontend messages
        try:
            messages = await asyncio.wait_for(
                handle.query("get_frontend_messages"),
                timeout=30.0
            )
            
            return ApiResponse(
                success=True,
                message="Conversation history retrieved",
                data={
                    "workflow_id": workflow_id,
                    "conversation_history": {"messages": messages}
                }
            )
            
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Query timed out - workflow may be unavailable"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get conversation history: {str(e)}"
        )



@app.post("/confirm-tool", response_model=ApiResponse)
async def confirm_tool_execution(request: ConfirmRequest) -> ApiResponse:
    """
    Confirm tool execution for the supervisor agent workflow.
    
    This endpoint sends confirmation to proceed with tool execution
    via the confirm signal and returns the updated conversation history.
    """
    try:
        if not temporal_client:
            raise HTTPException(
                status_code=503,
                detail="Temporal client not initialized"
            )
            
        # Get workflow handle
        handle = temporal_client.get_workflow_handle(request.workflow_id)
        
        # Verify workflow is running before sending signal
        try:
            await handle.describe()
        except Exception:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow with ID {request.workflow_id} not found"
            )
        
        # Get initial message count from frontend_messages
        try:
            initial_messages = await handle.query("get_frontend_messages")
            initial_length = len(initial_messages) if initial_messages else 0
        except Exception:
            initial_length = 0
        
        # Send confirm_tool signal to workflow
        await handle.signal("confirm_tool")
        
        # Poll for conversation update with timeout
        max_wait = 60  # Maximum 60 seconds for tool execution
        poll_interval = 0.5  # Check every 0.5 seconds
        elapsed = 0
        messages = None
        
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            try:
                messages = await handle.query("get_frontend_messages")
                current_length = len(messages) if messages else 0
                
                # Check if conversation has been updated (tool execution adds messages)
                if current_length > initial_length:
                    break
            except Exception:
                # Query failed, continue polling
                continue
        
        if messages is None:
            messages = []
        
        return ApiResponse(
            success=True,
            message="Tool execution confirmed",
            data={
                "workflow_id": request.workflow_id,
                "conversation_history": {"messages": messages}
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to confirm tool execution: {str(e)}"
        )


@app.post("/cancel-tool", response_model=ApiResponse)
async def cancel_tool_execution(request: CancelToolRequest) -> ApiResponse:
    """
    Cancel tool execution for the supervisor agent workflow.
    
    This endpoint sends cancellation signal to stop tool execution
    via the cancel_tool signal and returns the updated conversation history.
    """
    try:
        if not temporal_client:
            raise HTTPException(
                status_code=503,
                detail="Temporal client not initialized"
            )
            
        # Get workflow handle
        handle = temporal_client.get_workflow_handle(request.workflow_id)
        
        # Verify workflow is running before sending signal
        try:
            await handle.describe()
        except Exception:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow with ID {request.workflow_id} not found"
            )
        
        # Send cancel signal to workflow
        await handle.signal("cancel_tool")
        
        return ApiResponse(
            success=True,
            message="Tool execution cancelled",
            data={"workflow_id": request.workflow_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel tool execution: {str(e)}"
        )


@app.post("/confirm-completion", response_model=ApiResponse)
async def confirm_workflow_completion(request: ConfirmRequest) -> ApiResponse:
    """
    Confirm workflow completion for the agent workflow.
    
    This endpoint sends confirmation to proceed with workflow completion
    via the confirm_completion signal.
    """
    try:
        if not temporal_client:
            raise HTTPException(
                status_code=503,
                detail="Temporal client not initialized"
            )
            
        # Get workflow handle
        handle = temporal_client.get_workflow_handle(request.workflow_id)
        
        # Verify workflow is running before sending signal
        try:
            await handle.describe()
        except Exception:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow with ID {request.workflow_id} not found"
            )
        
        # Send confirm completion signal to workflow
        await handle.signal("confirm_completion")
        
        return ApiResponse(
            success=True,
            message="Workflow completion confirmed",
            data={"workflow_id": request.workflow_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to confirm workflow completion: {str(e)}"
        )


@app.post("/cancel-completion", response_model=ApiResponse)
async def cancel_workflow_completion(request: CancelToolRequest) -> ApiResponse:
    """
    Cancel workflow completion for the agent workflow.
    
    This endpoint sends cancellation signal to stop workflow completion
    via the cancel_completion signal.
    """
    try:
        if not temporal_client:
            raise HTTPException(
                status_code=503,
                detail="Temporal client not initialized"
            )
            
        # Get workflow handle
        handle = temporal_client.get_workflow_handle(request.workflow_id)
        
        # Verify workflow is running before sending signal
        try:
            await handle.describe()
        except Exception:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow with ID {request.workflow_id} not found"
            )
        
        # Send cancel completion signal to workflow
        await handle.signal("cancel_completion")
        
        return ApiResponse(
            success=True,
            message="Workflow completion cancelled",
            data={"workflow_id": request.workflow_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel workflow completion: {str(e)}"
        )


@app.post("/start-workflow", response_model=ApiResponse)
async def start_workflow(request: StartWorkflowRequest) -> ApiResponse:
    """
    Start a new agent workflow instance.
    
    This endpoint creates a new workflow instance with the specified agent goal.
    If no workflow_id is provided, one will be generated.
    Supports: "Supervisor Agent", "Submission Pack Parser"
    """
    try:
        if not temporal_client:
            raise HTTPException(
                status_code=503,
                detail="Temporal client not initialized"
            )
            
        # Generate workflow ID if not provided
        workflow_id = request.workflow_id
        if not workflow_id:
            agent_prefix = request.agent_name.lower().replace(" ", "-") if request.agent_name else "reinsurance-agent"
            workflow_id = f"{agent_prefix}-{uuid.uuid4()}"
        
        # Get the agent goal configuration
        agent_goal = get_agent_goal_by_name(request.agent_name)
        if not agent_goal:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown agent: {request.agent_name}. Available agents: Supervisor Agent, Submission Pack Parser"
            )
        
        # Create combined input for workflow
        combined_input = CombinedInput(agent_goal=agent_goal)
        
        # Start the workflow
        try:
            handle = await temporal_client.start_workflow(
                BridgeWorkflow.run,
                combined_input,
                id=workflow_id,
                task_queue=TEMPORAL_TASK_QUEUE
            )
            
            return ApiResponse(
                success=True,
                message="Workflow started successfully",
                data={
                    "workflow_id": workflow_id,
                    "workflow_run_id": handle.result_run_id,
                    "agent_goal": agent_goal.agent_name,
                    "workflow_type": "bridge"
                }
            )
            
        except WorkflowAlreadyStartedError:
            # Return the existing workflow info if it's already running
            handle = temporal_client.get_workflow_handle(workflow_id)
            
            return ApiResponse(
                success=True,
                message="Workflow already exists and is running",
                data={
                    "workflow_id": workflow_id,
                    "workflow_run_id": handle.result_run_id,
                    "agent_goal": agent_goal.agent_name,
                    "workflow_type": "bridge"
                }
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow: {str(e)}"
        )


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    temporal_status = "connected" if temporal_client else "disconnected"
    return {
        "status": "healthy", 
        "service": "temporal-reinsurance-agent-api",
        "temporal_client": temporal_status
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)