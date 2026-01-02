"""Child workflow for processing individual catastrophe events."""

from datetime import timedelta
from typing import Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class HistoricalEventMatchingWorkflow:
    """Child workflow that processes a single catastrophe event and matches it against historical data."""

    @workflow.run
    async def run(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single catastrophe event and match it against historical database.
        
        Args:
            event_data: Single event data containing loss_description, loss_year, etc.
            
        Returns:
            Dict containing the processed event with historical match data
        """
        event_description = event_data.get('loss_description', 'Unknown') if event_data else 'Unknown'
        workflow.logger.info(f"Processing event: {event_description}")
        
        # Input validation
        if not event_data:
            error_msg = "Event data is empty or None"
            workflow.logger.error(error_msg)
            return {
                "event_data": event_data,
                "historical_match": None,
                "error": error_msg,
                "error_type": "validation_error",
                "status": "failed",
                "processed_at": workflow.now().isoformat()
            }
        
        if not isinstance(event_data, dict):
            error_msg = f"Event data must be a dictionary, got {type(event_data)}"
            workflow.logger.error(error_msg)
            return {
                "event_data": event_data,
                "historical_match": None,
                "error": error_msg,
                "error_type": "validation_error",
                "status": "failed",
                "processed_at": workflow.now().isoformat()
            }
        
        # Validate required fields
        required_fields = ['loss_description']
        missing_fields = [field for field in required_fields if not event_data.get(field)]
        if missing_fields:
            error_msg = f"Missing required fields: {missing_fields}"
            workflow.logger.error(error_msg)
            return {
                "event_data": event_data,
                "historical_match": None,
                "error": error_msg,
                "error_type": "validation_error",
                "status": "failed",
                "processed_at": workflow.now().isoformat()
            }
        
        try:
            # Step 1: Match with historical database using the dedicated activity
            workflow.logger.info(f"Starting historical matching for: {event_description}")
            
            # Get timeout and retry configuration (hardcoded to avoid config import in workflow)
            historical_timeout_minutes = 2
            retry_initial_interval = 5
            retry_max_attempts = 3
            retry_backoff_coefficient = 2.0
            retry_max_interval_minutes = 2
            
            historical_match = await workflow.execute_activity(
                "match_single_event_activity",
                {
                    "event_data": event_data,
                    "historical_db_path": None  # Activity will use config default
                },
                start_to_close_timeout=timedelta(minutes=historical_timeout_minutes),
                schedule_to_close_timeout=timedelta(minutes=historical_timeout_minutes * 2),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=retry_initial_interval),
                    maximum_attempts=retry_max_attempts,
                    backoff_coefficient=retry_backoff_coefficient,
                    maximum_interval=timedelta(minutes=retry_max_interval_minutes),
                    non_retryable_error_types=["validation_error"]
                )
            )
            
            # Yield control after activity completes
            await workflow.sleep(0)
            
            # Validate activity result
            if not isinstance(historical_match, dict):
                error_msg = f"Activity returned invalid result type: {type(historical_match)}"
                workflow.logger.error(error_msg)
                return {
                    "event_data": event_data,
                    "historical_match": None,
                    "error": error_msg,
                    "error_type": "activity_error",
                    "status": "failed",
                    "processed_at": workflow.now().isoformat()
                }
            
            # Check if activity reported success
            activity_success = historical_match.get('success', False)
            if not activity_success:
                activity_error = historical_match.get('error', 'Unknown activity error')
                workflow.logger.warning(f"Activity reported failure for {event_description}: {activity_error}")
                # Still return success status since the workflow completed, but include the activity error
                return {
                    "event_data": event_data,
                    "historical_match": historical_match,
                    "status": "success",
                    "activity_warning": activity_error,
                    "processed_at": workflow.now().isoformat()
                }
            
            # Combine event data with historical match results
            result = {
                "event_data": event_data,
                "historical_match": historical_match,
                "status": "success",
                "processed_at": workflow.now().isoformat()
            }
            
            workflow.logger.info(f"Successfully processed: {event_description}")
            return result
            
        except Exception as e:
            error_type = "unknown_error"
            error_msg = str(e)
            
            # Categorize error types for better handling
            if "timeout" in error_msg.lower():
                error_type = "timeout_error"
            elif "activity" in error_msg.lower():
                error_type = "activity_error"
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                error_type = "network_error"
            
            workflow.logger.error(f"Failed to process event {event_description}: {error_msg} (type: {error_type})")
            
            # Return structured error result with detailed information
            return {
                "event_data": event_data,
                "historical_match": None,
                "error": error_msg,
                "error_type": error_type,
                "status": "failed",
                "processed_at": workflow.now().isoformat(),
                "retry_info": {
                    "max_attempts": 3,
                    "backoff_coefficient": 2.0,
                    "timeout_minutes": 2
                }
            }


@workflow.defn
class ParallelHistoricalMatchingWorkflow:
    """Parent workflow that creates multiple child workflows for parallel historical matching."""

    @workflow.run
    async def run(self, events_data: list, program_id: str) -> Dict[str, Any]:
        """
        Create child workflows for each event and process them in parallel.
        
        Args:
            events_data: List of event dictionaries to process
            program_id: Program ID for tracking and logging
            
        Returns:
            Dict containing aggregated results from all child workflows
        """
        workflow.logger.info(f"Starting parallel historical matching for program {program_id} with {len(events_data)} events")
        
        # Input validation
        if not events_data or not isinstance(events_data, list):
            error_msg = "Events data must be a non-empty list"
            workflow.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "program_id": program_id,
                "total_events": 0,
                "successful_matches": 0,
                "failed_matches": 0,
                "historical_matches": [],
                "processing_stats": {
                    "started_at": workflow.now().isoformat(),
                    "completed_at": workflow.now().isoformat(),
                    "duration_seconds": 0
                }
            }
        
        if not program_id:
            error_msg = "Program ID is required"
            workflow.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "program_id": program_id,
                "total_events": len(events_data),
                "successful_matches": 0,
                "failed_matches": len(events_data),
                "historical_matches": [],
                "processing_stats": {
                    "started_at": workflow.now().isoformat(),
                    "completed_at": workflow.now().isoformat(),
                    "duration_seconds": 0
                }
            }
        
        # Get configuration for parallel processing limits
        # Note: Using hardcoded values to avoid importing config in workflow context
        # Increased to 200 to handle real submission packs (some have 70-100+ events)
        max_events = 200
        
        if len(events_data) > max_events:
            error_msg = f"Too many events. Maximum allowed: {max_events}, provided: {len(events_data)}"
            workflow.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "program_id": program_id,
                "total_events": len(events_data),
                "successful_matches": 0,
                "failed_matches": len(events_data),
                "historical_matches": [],
                "processing_stats": {
                    "started_at": workflow.now().isoformat(),
                    "completed_at": workflow.now().isoformat(),
                    "duration_seconds": 0
                }
            }
        
        start_time = workflow.now()
        workflow.logger.info(f"Processing {len(events_data)} events in parallel for program {program_id}")
        
        try:
            # Initialize result tracking
            processed_events = []
            successful_matches = 0
            failed_matches = 0
            historical_matches = []
            failed_to_start = []
            child_workflow_handles = []
            child_workflow_metadata = []
            
            # Phase 1: Start all child workflows simultaneously (no await)
            workflow.logger.info(f"Starting all {len(events_data)} child workflows simultaneously...")
            
            for i, event in enumerate(events_data):
                # Generate unique workflow ID for each child
                event_desc = event.get('loss_description', 'unknown').replace(' ', '-').replace('/', '-')[:50]
                event_year = event.get('loss_year', 'unknown')
                child_id = f"hist-match-{program_id}-{event_year}-{event_desc}-{i}"
                
                try:
                    workflow.logger.info(f"Starting child workflow {i+1}/{len(events_data)}: {event.get('loss_description', 'Unknown')}")
                    
                    # Get retry policy configuration (hardcoded to avoid config import in workflow)
                    retry_initial_interval = 5
                    retry_max_attempts = 3
                    retry_backoff_coefficient = 2.0
                    retry_max_interval_minutes = 2
                    child_timeout_minutes = 10
                    
                    # Start child workflow without awaiting (truly parallel)
                    child_handle = await workflow.start_child_workflow(
                        HistoricalEventMatchingWorkflow.run,
                        args=[event],
                        id=child_id,
                        retry_policy=RetryPolicy(
                            initial_interval=timedelta(seconds=retry_initial_interval),
                            maximum_attempts=retry_max_attempts,
                            backoff_coefficient=retry_backoff_coefficient,
                            maximum_interval=timedelta(minutes=retry_max_interval_minutes)
                        )
                    )
                    
                    # Store handle and metadata for later processing
                    child_workflow_handles.append(child_handle)
                    child_workflow_metadata.append({
                        "index": i,
                        "event": event,
                        "child_id": child_id,
                        "handle": child_handle
                    })
                    
                    workflow.logger.info(f"✓ Started child workflow: {child_id}")
                    
                except Exception as e:
                    error_msg = f"Failed to start child workflow for event {i+1}: {str(e)}"
                    workflow.logger.error(error_msg)
                    failed_to_start.append({
                        "event_data": event,
                        "error": error_msg,
                        "error_type": "child_workflow_creation_failed",
                        "status": "failed",
                        "processed_at": workflow.now().isoformat()
                    })
            
            workflow.logger.info(f"All child workflows started! Now waiting for {len(child_workflow_handles)} workflows to complete...")
            
            # Phase 2: Wait for all child workflows to complete
            for metadata in child_workflow_metadata:
                try:
                    result = await metadata["handle"]
                    
                    # Process result
                    if not isinstance(result, dict):
                        error_msg = f"Child workflow {metadata['child_id']} returned invalid result type: {type(result)}"
                        workflow.logger.error(error_msg)
                        failed_to_start.append({
                            "event_data": metadata["event"],
                            "error": error_msg,
                            "error_type": "invalid_result",
                            "status": "failed",
                            "processed_at": workflow.now().isoformat()
                        })
                        continue
                    
                    # Add to processed events
                    processed_events.append(result)
                    
                    if result.get("status") == "success":
                        successful_matches += 1
                        historical_match = result.get("historical_match")
                        if historical_match and isinstance(historical_match, dict):
                            # Check if a match was actually found (hist_event_id is not None)
                            has_match = historical_match.get("hist_event_id") is not None
                            match_with_context = {
                                "event_data": result.get("event_data", metadata["event"]),
                                "historical_match": historical_match,
                                "match_found": has_match,
                                "match_confidence": historical_match.get("match_confidence", "none"),
                                "processed_at": result.get("processed_at")
                            }
                            historical_matches.append(match_with_context)
                    else:
                        failed_matches += 1
                    
                    workflow.logger.info(f"✓ Completed child workflow: {metadata['child_id']}")
                    
                except Exception as e:
                    error_msg = f"Failed to get result from child workflow {metadata['child_id']}: {str(e)}"
                    workflow.logger.error(error_msg)
                    failed_to_start.append({
                        "event_data": metadata["event"],
                        "error": error_msg,
                        "error_type": "child_workflow_execution_failed",
                        "status": "failed",
                        "processed_at": workflow.now().isoformat()
                    })
            
            # Add failed-to-start events to processed_events
            processed_events.extend(failed_to_start)
            
            workflow.logger.info(f"Processed {len(events_data)} events: {successful_matches} successful, {failed_matches} failed")
            
            # Calculate final statistics
            end_time = workflow.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            # Count how many events actually found historical matches
            matches_found_count = sum(1 for m in historical_matches if m.get("match_found", False))
            
            # Determine overall success based on whether any events were processed successfully
            overall_success = successful_matches > 0 or (successful_matches == 0 and failed_matches == 0)
            
            workflow.logger.info(f"Parallel processing completed: {successful_matches} successful, {failed_matches} failed, {matches_found_count} historical matches found")
            
            return {
                "success": overall_success,
                "program_id": program_id,
                "total_events": len(events_data),
                "successful_matches": successful_matches,
                "failed_matches": failed_matches,
                "historical_matches": historical_matches,
                "processed_events": processed_events,
                "child_workflows_started": len(events_data) - len(failed_to_start),
                "child_workflows_failed_to_start": len(failed_to_start),
                "processing_stats": {
                    "started_at": start_time.isoformat(),
                    "completed_at": end_time.isoformat(),
                    "duration_seconds": duration_seconds,
                    "events_per_second": len(events_data) / duration_seconds if duration_seconds > 0 else 0,
                    "success_rate": successful_matches / len(events_data) if len(events_data) > 0 else 0,
                    "historical_matches_found": matches_found_count
                }
            }
            
        except Exception as e:
            error_msg = f"Parallel processing failed: {str(e)}"
            workflow.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "program_id": program_id,
                "total_events": len(events_data),
                "successful_matches": 0,
                "failed_matches": len(events_data),
                "historical_matches": [],
                "processing_stats": {
                    "started_at": start_time.isoformat(),
                    "completed_at": workflow.now().isoformat(),
                    "duration_seconds": (workflow.now() - start_time).total_seconds()
                }
            }
