"""Parallel event processing tools using Temporal child workflows."""

from typing import Dict, Any, List, Optional
import asyncio
import uuid
from datetime import timedelta

from temporalio import activity
from temporalio.exceptions import FailureError
from shared.config import get_temporal_client, TEMPORAL_TASK_QUEUE


async def _retrieve_events_from_bridge_workflow(bridge_workflow_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Retrieve events data from the bridge workflow (BridgeWorkflow).
    
    This is used when events_data is empty, allowing the tool to automatically
    retrieve the events that were stored by the Submission Pack Parser activities.
    
    Args:
        bridge_workflow_id: The workflow ID of the BridgeWorkflow
        
    Returns:
        List of events if found, None otherwise
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(bridge_workflow_id)
        
        # Query the extraction data from the bridge workflow
        result = await handle.query("get_extraction_data")
        
        if result and isinstance(result, dict):
            events = result.get("events", [])
            events_count = result.get("events_count", 0)
            
            if events and events_count > 0:
                print(f"Retrieved {events_count} events from bridge workflow {bridge_workflow_id}")
                return events
            else:
                print(f"No events found in bridge workflow {bridge_workflow_id}")
                return None
        else:
            print(f"Invalid result from bridge workflow query: {result}")
            return None
            
    except Exception as e:
        print(f"Failed to retrieve events from bridge workflow {bridge_workflow_id}: {str(e)}")
        return None


@activity.defn(name="process_events_parallel")
async def process_events_parallel(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process multiple catastrophe events in parallel using Temporal child workflows.
    
    This tool creates child workflows for each event, allowing them to be processed
    individually and in parallel for better performance and fault isolation.
    
    Events are automatically retrieved from the bridge workflow's data store
    using the bridge_workflow_id (injected by the workflow).
    
    Args:
        args: Dict containing:
            - program_id: The program ID for tracking
            - bridge_workflow_id: Workflow ID to retrieve events from (injected automatically)
        
    Returns:
        Dict containing processing results and summary with historical matches
    """
    try:
        # Unpack arguments from dict (workflow passes args=[tool_args])
        program_id = args.get("program_id")
        bridge_workflow_id = args.get("bridge_workflow_id")
        
        # Validate inputs
        if not program_id:
            return {
                "success": False,
                "error": "Program ID is required",
                "result": "Failed to process events: missing program_id"
            }
        
        if not bridge_workflow_id:
            return {
                "success": False,
                "error": "bridge_workflow_id is required (should be injected by workflow)",
                "result": "Failed to process events: missing bridge_workflow_id. This is an internal error."
            }
        
        # Retrieve events from bridge workflow's data store
        print(f"Retrieving events from bridge workflow: {bridge_workflow_id}")
        events_data = await _retrieve_events_from_bridge_workflow(bridge_workflow_id)
        
        if not events_data:
            return {
                "success": False,
                "error": "Could not retrieve events from bridge workflow",
                "result": "Failed to process events: no events available. Ensure SubmissionPackParserAgent completed successfully."
            }
        
        print(f"Successfully retrieved {len(events_data)} events from bridge workflow")
        
        # Limit the number of events to prevent overwhelming the system
        # Increased to 200 to handle real submission packs (some have 70-100+ events)
        # Child workflows handle parallel processing efficiently
        max_events = 200
        if len(events_data) > max_events:
            return {
                "success": False,
                "error": f"Too many events. Maximum allowed: {max_events}, provided: {len(events_data)}",
                "result": f"Failed to process events: too many events ({len(events_data)} > {max_events})"
            }
        
        # Execute the parallel processing workflow
        return await _execute_parallel_workflow(program_id, events_data, bridge_workflow_id)
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "result": f"Failed to initiate parallel event processing: {str(e)}"
        }


async def _execute_parallel_workflow(
    program_id: str, 
    events_data: List[Dict[str, Any]],
    bridge_workflow_id: str = None
) -> Dict[str, Any]:
    """
    Execute the ParallelHistoricalMatchingWorkflow and return results.
    
    This function handles workflow execution, timeout management, error handling,
    and result formatting to ensure compatibility with PopulateCedantData.
    
    Args:
        program_id: The program ID for tracking
        events_data: List of event dictionaries to process
        bridge_workflow_id: Optional workflow ID to store results in
        
    Returns:
        Dict containing workflow execution results with historical matches
    """
    # Import here to avoid circular dependency
    from agents.supervisor.tools.historical_matcher.event_processing_workflow import ParallelHistoricalMatchingWorkflow
    
    workflow_id = None
    try:
        # Get Temporal client
        client = await get_temporal_client()
        
        # Generate unique workflow ID
        workflow_id = f"parallel-hist-match-{program_id}-{uuid.uuid4().hex[:8]}"
        
        # Start the workflow and wait for completion
        handle = await client.start_workflow(
            ParallelHistoricalMatchingWorkflow.run,
            args=[events_data, program_id],
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
            execution_timeout=timedelta(minutes=30)  # Allow up to 30 minutes for processing
        )
        
        # Wait for the workflow to complete and get the result
        result = await handle.result()
        
        # Validate and enhance the workflow result
        processed_result = _process_workflow_result(result, workflow_id, program_id, events_data)
        
        # Store historical_matches in bridge workflow for downstream tools
        if bridge_workflow_id and processed_result.get("success"):
            try:
                bridge_handle = client.get_workflow_handle(bridge_workflow_id)
                await bridge_handle.signal(
                    "store_extraction_data",
                    {
                        "type": "historical_matches",
                        "value": processed_result.get("historical_matches", [])
                    }
                )
                print(f"Stored {len(processed_result.get('historical_matches', []))} historical matches in bridge workflow {bridge_workflow_id}")
            except Exception as store_error:
                print(f"Warning: Failed to store historical_matches in bridge workflow: {store_error}")
        
        return processed_result
        
    except FailureError as e:
        # Handle workflow execution failures
        error_msg = f"Workflow execution failed: {str(e)}"
        return _create_error_response(
            error_msg, workflow_id, program_id, events_data, "workflow_execution_failed"
        )
    except asyncio.TimeoutError as e:
        # Handle timeout errors specifically
        error_msg = f"Workflow execution timed out after 30 minutes: {str(e)}"
        return _create_error_response(
            error_msg, workflow_id, program_id, events_data, "workflow_timeout"
        )
    except Exception as e:
        # Handle any other unexpected errors
        error_msg = f"Failed to execute workflow: {str(e)}"
        return _create_error_response(
            error_msg, workflow_id, program_id, events_data, "unexpected_error"
        )


def _process_workflow_result(
    result: Any, 
    workflow_id: str, 
    program_id: str, 
    events_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Process and validate workflow result, ensuring proper format for downstream tools.
    
    Args:
        result: Raw result from workflow execution
        workflow_id: The workflow ID that was executed
        program_id: The program ID for tracking
        events_data: Original events data for context
        
    Returns:
        Dict containing processed and validated results
    """
    if not isinstance(result, dict):
        # Handle unexpected result format
        return _create_error_response(
            "Workflow returned unexpected result format",
            workflow_id, program_id, events_data, "invalid_result_format"
        )
    
    # Add workflow metadata
    result["workflow_id"] = workflow_id
    result["processing_method"] = "temporal_child_workflows"
    
    # Ensure required fields exist with defaults
    result.setdefault("success", False)
    result.setdefault("program_id", program_id)
    result.setdefault("total_events", len(events_data))
    result.setdefault("successful_matches", 0)
    result.setdefault("failed_matches", len(events_data))
    result.setdefault("historical_matches", [])
    result.setdefault("processing_stats", {})
    
    # Validate and format historical matches for PopulateCedantData
    historical_matches = result.get("historical_matches", [])
    if not isinstance(historical_matches, list):
        historical_matches = []
        result["historical_matches"] = historical_matches
    
    # Ensure each historical match has the required structure
    validated_matches = []
    for match in historical_matches:
        if isinstance(match, dict):
            validated_match = {
                "event_data": match.get("event_data", {}),
                "historical_match": match.get("historical_match"),
                "match_found": match.get("match_found", False),
                "match_confidence": match.get("match_confidence", 0.0),
                "processed_at": match.get("processed_at")
            }
            validated_matches.append(validated_match)
    
    result["historical_matches"] = validated_matches
    
    # Add events preview for debugging (first 5 events)
    result["events_preview"] = [
        {
            "loss_description": event.get("loss_description", "Unknown"),
            "loss_year": event.get("loss_year", "Unknown"),
            "original_loss_gross": event.get("original_loss_gross", 0)
        }
        for event in events_data[:5]
    ]
    
    # Generate comprehensive result message
    if result.get("success"):
        successful = result.get("successful_matches", 0)
        failed = result.get("failed_matches", 0)
        total = result.get("total_events", len(events_data))
        matches_found = len([m for m in validated_matches if m.get("match_found")])
        
        result["result"] = (
            f"Successfully processed {total} events in parallel using Temporal child workflows. "
            f"Results: {successful} successful, {failed} failed. "
            f"Historical matches found: {matches_found}/{total} events."
        )
    else:
        error = result.get("error", "Unknown error")
        result["result"] = f"Parallel processing completed with errors: {error}"
    
    # Enhance processing statistics
    stats = result.get("processing_stats", {})
    if isinstance(stats, dict):
        stats.setdefault("total_events_processed", len(events_data))
        stats.setdefault("historical_matches_found", len([m for m in validated_matches if m.get("match_found")]))
        stats.setdefault("processing_method", "temporal_parallel_child_workflows")
        result["processing_stats"] = stats
    
    return result


def _create_error_response(
    error_msg: str, 
    workflow_id: str, 
    program_id: str, 
    events_data: List[Dict[str, Any]], 
    error_type: str
) -> Dict[str, Any]:
    """
    Create a standardized error response for workflow execution failures.
    
    Args:
        error_msg: The error message to include
        workflow_id: The workflow ID (may be None if workflow wasn't started)
        program_id: The program ID for tracking
        events_data: Original events data for context
        error_type: Type of error for categorization
        
    Returns:
        Dict containing standardized error response
    """
    return {
        "success": False,
        "error": error_msg,
        "error_type": error_type,
        "program_id": program_id,
        "total_events": len(events_data),
        "successful_matches": 0,
        "failed_matches": len(events_data),
        "historical_matches": [],  # Empty list for failed processing
        "workflow_id": workflow_id or "unknown",
        "processing_method": "temporal_child_workflows",
        "processing_stats": {
            "started_at": None,
            "completed_at": None,
            "duration_seconds": 0,
            "total_events_processed": 0,
            "historical_matches_found": 0,
            "processing_method": "temporal_parallel_child_workflows",
            "error_type": error_type
        },
        "result": f"Parallel processing failed: {error_msg}"
    }
