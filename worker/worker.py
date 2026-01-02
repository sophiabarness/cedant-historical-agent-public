"""Temporal worker for the supervisor agent with workflow and activity registration.

This worker registers all workflows and activities from the new agent hierarchy structure:

Agent Hierarchy:
- Supervisor Agent (agents/supervisor/)
  - Workflows: AgentGoalWorkflow
  - Tools:
    - Submission Pack Parser Agent (agents/supervisor/tools/submission_pack_parser/)
      - Activities: extract_as_of_year, llm_extract_catastrophe_data_activity, locate_submission_pack_activity
      - Sub-tools:
        - Sheet Identification Agent (agents/supervisor/tools/submission_pack_parser/tools/sheet_identification/)
          - Activities: get_sheet_names_activity, read_sheet_activity
    - Historical Matcher Agent (agents/supervisor/tools/historical_matcher/)
      - Workflows: HistoricalEventMatchingWorkflow, ParallelHistoricalMatchingWorkflow
      - Activities: match_historical_events, match_single_event_activity
    - Supervisor Tools (agents/supervisor/tools/):
      - cedant_activities.py: populate_cedant_data, compare_to_existing_cedant_data

Core Agent Activities (agents/core/):
- agents/core/agent_activities.py: AgentActivities class (agent_toolPlanner)

Shared Utilities (shared/utils/):
- Data loaders, column mapping, fuzzy matching, data cleaners

All activities and workflows are properly registered with the Temporal worker for execution.
"""

import asyncio
import logging
import signal
import sys
import os
from datetime import timedelta
from typing import Optional

# CRITICAL: Set NumPy environment variables BEFORE any imports that might use NumPy
# This prevents the "CPU dispatcher tracer already initlized" error in child workflows
os.environ.setdefault('NUMPY_DISABLE_CPU_FEATURES', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')

from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

# Import configuration management
from shared.config import init_config, AppConfig

# Import workflows from new agent hierarchy
from agents.core.agent_goal_workflow import AgentGoalWorkflow
from agents.supervisor.tools.historical_matcher.event_processing_workflow import (
    HistoricalEventMatchingWorkflow,
    ParallelHistoricalMatchingWorkflow
)
from shared.bridge.workflow import BridgeWorkflow

# Import core agent activities
from agents.core.agent_activities import AgentActivities

# Import submission pack parser activities (from new structure)
from agents.supervisor.tools.submission_pack_parser.activities.submission_pack_activities import (
    extract_as_of_year,
    locate_submission_pack_activity,
    llm_extract_catastrophe_data_activity
)

# Import sheet identification activities (from new structure)
from agents.supervisor.tools.submission_pack_parser.tools.sheet_identification.activities import (
    get_sheet_names_activity,
    read_sheet_activity
)

# Import historical matcher activities (from new structure)
from agents.supervisor.tools.historical_matcher.matching_activities import (
    match_historical_events,
    match_single_event_activity
)

# Import parallel processor activity
from agents.supervisor.tools.historical_matcher.parallel_processor import (
    process_events_parallel
)

# Import cedant activities
from agents.supervisor.tools.cedant_activities import populate_cedant_data, compare_to_existing_cedant_data

# Configure logging with reduced Temporal noise
import logging
import os

# Set up logging with explicit format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Get temporal log level from environment (default to CRITICAL to suppress warnings)
temporal_log_level = os.getenv('TEMPORAL_LOG_LEVEL', 'CRITICAL').upper()
log_level = getattr(logging, temporal_log_level, logging.CRITICAL)

# Completely suppress Temporal SDK warnings and noise
temporal_loggers = [
    'temporal_sdk_core',
    'temporal_sdk_core.worker',
    'temporal_sdk_core.worker.workflow',
    'temporalio.worker',
]

for logger_name in temporal_loggers:
    temporal_logger = logging.getLogger(logger_name)
    temporal_logger.setLevel(log_level)

# Suppress LiteLLM verbose logging but keep errors
logging.getLogger('LiteLLM').setLevel(logging.WARNING)
logging.getLogger('litellm').setLevel(logging.WARNING)

# Ensure our application loggers are visible
logging.getLogger('__main__').setLevel(logging.INFO)

# Get workflow log level from environment (default to INFO)
# Set to DEBUG to see verbose message routing logs
workflow_log_level = os.getenv('WORKFLOW_LOG_LEVEL', 'INFO').upper()
workflow_level = getattr(logging, workflow_log_level, logging.INFO)

# IMPORTANT: Re-enable workflow and activity logging after suppressing temporal core
# These need to be set AFTER the temporal_loggers loop
workflow_logger = logging.getLogger('temporalio.workflow')
workflow_logger.setLevel(workflow_level)
workflow_logger.propagate = True

activity_logger = logging.getLogger('temporalio.activity')
activity_logger.setLevel(logging.INFO)
activity_logger.propagate = True

logger = logging.getLogger(__name__)

# Test that logging is working
logger.info("=" * 60)
logger.info("Worker logging initialized")
logger.info(f"Workflow log level: {workflow_log_level}")
logger.info("=" * 60)


class TemporalWorker:
    """Temporal worker class for managing workflow and activity registration."""

    def __init__(self, config: AppConfig):
        """Initialize the worker with validated configuration."""
        self.config = config
        self.client: Optional[Client] = None
        self.worker: Optional[Worker] = None
        
        logger.info(f"Initializing worker with task queue: {config.temporal.task_queue}")
        logger.info(f"Temporal server: {config.temporal.address}")
        logger.info(f"Namespace: {config.temporal.namespace}")

    async def connect_client(self) -> None:
        """Connect to the Temporal server using configuration."""
        try:
            # Use the get_temporal_client function from config for proper authentication
            from shared.config import get_temporal_client
            self.client = await get_temporal_client()
            logger.info(f"Connected to Temporal server at {self.config.temporal.address}")
            
            # Test connection with a simple health check
            await self._test_connection()
            
        except Exception as e:
            logger.error(f"Failed to connect to Temporal server: {e}")
            raise

    async def _test_connection(self) -> None:
        """Test the Temporal connection to ensure it's working properly."""
        try:
            # Simple connection test - get workflow service info
            # This is a lighter test that doesn't require iteration
            service_info = await self.client.workflow_service.get_system_info()
            logger.info("Temporal connection test successful")
        except Exception as e:
            logger.warning(f"Connection test warning (may be normal): {e}")
            # Don't fail on this - some deployments restrict permissions

    async def create_worker(self) -> None:
        """Create and configure the Temporal worker with workflows and activities."""
        if not self.client:
            raise RuntimeError("Client not connected. Call connect_client() first.")

        # Create activities instance
        activities_instance = AgentActivities()

        try:
            self.worker = Worker(
                self.client,
                task_queue=self.config.temporal.task_queue,
                workflows=[
                    # Supervisor agent workflows
                    AgentGoalWorkflow,
                    
                    # Shared workflows
                    BridgeWorkflow,
                    # Historical matcher workflows
                    HistoricalEventMatchingWorkflow,
                    ParallelHistoricalMatchingWorkflow,
                ],
                activities=[
                    # Core agent activities (instance methods)
                    activities_instance.agent_toolPlanner,
                    
                    # Submission pack parser activities (new structure)
                    extract_as_of_year,
                    locate_submission_pack_activity,
                    llm_extract_catastrophe_data_activity,
                    
                    # Sheet identification activities (new structure)
                    get_sheet_names_activity,
                    read_sheet_activity,
                    
                    # Historical matcher activities (from new structure)
                    match_historical_events,
                    match_single_event_activity,
                    process_events_parallel,
                    
                    # Cedant activities
                    populate_cedant_data,
                    compare_to_existing_cedant_data,
                ],
                max_concurrent_activities=self.config.temporal.max_concurrent_activities,
                # Add worker identity to prevent task conflicts
                identity=f"worker-{self.config.temporal.task_queue}-{id(self)}",
                # Configure graceful shutdown
                graceful_shutdown_timeout=timedelta(seconds=30),
                # Reduce task polling to prevent conflicts
                max_cached_workflows=100,
                # Increase sticky timeout to give workflows more time to process
                # This helps prevent "task not found" warnings when LLM calls take time
                sticky_queue_schedule_to_start_timeout=timedelta(seconds=60),
                # Limit concurrent workflow tasks to reduce race conditions
                max_concurrent_workflow_tasks=10,
            )
            logger.info("Worker created successfully with workflows and activities registered")
            
            # Log registered components with updated structure
            logger.info("Registered workflows:")
            logger.info("  - AgentGoalWorkflow (supervisor)")
            logger.info("  - BridgeWorkflow (shared/bridge)")
            logger.info("  - HistoricalEventMatchingWorkflow (historical matcher)")
            logger.info("  - ParallelHistoricalMatchingWorkflow (historical matcher)")
            
            logger.info("Registered activities:")
            logger.info("  Core agent activities (agents/core/):")
            logger.info("    - agent_toolPlanner")
            logger.info("  Submission pack parser activities:")
            logger.info("    - extract_as_of_year, locate_submission_pack_activity")
            logger.info("    - llm_extract_catastrophe_data_activity")
            logger.info("  Sheet identification activities:")
            logger.info("    - get_sheet_names_activity, read_sheet_activity")
            logger.info("  Historical matcher activities:")
            logger.info("    - match_historical_events, match_single_event_activity")
            logger.info("  Cedant activities (agents/supervisor/tools/):")
            logger.info("    - populate_cedant_data, compare_to_existing_cedant_data")
            
        except Exception as e:
            logger.error(f"Failed to create worker: {e}")
            raise

    async def start(self) -> None:
        """Start the worker and begin processing tasks."""
        if not self.worker:
            raise RuntimeError("Worker not created. Call create_worker() first.")

        try:
            logger.info(f"Starting worker on task queue: {self.config.temporal.task_queue}")
            logger.info("Worker is ready to process workflows and activities")
            
            # Start the worker with proper error handling
            await self.worker.run()
            
        except KeyboardInterrupt:
            logger.info("Worker interrupted by user")
            raise
        except Exception as e:
            logger.error(f"Worker execution failed: {e}")
            # Attempt graceful cleanup before re-raising
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        """Gracefully shutdown the worker and close connections."""
        logger.info("Shutting down worker...")
        
        if self.worker:
            try:
                # Give worker time to complete current tasks
                logger.info("Waiting for worker to complete current tasks...")
                # The worker.run() method will handle graceful shutdown when cancelled
                logger.info("Worker stopped")
            except Exception as e:
                logger.warning(f"Error during worker shutdown: {e}")
        
        if self.client:
            try:
                # Properly close client connection
                await self.client.close()
                logger.info("Temporal client connection closed")
            except Exception as e:
                logger.warning(f"Error closing client connection: {e}")


# Global worker instance for signal handling
worker_instance: Optional[TemporalWorker] = None


def signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    if worker_instance:
        # Create a new event loop for shutdown if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(worker_instance.shutdown())
    
    sys.exit(0)


async def main() -> None:
    """Main function to initialize and run the Temporal worker."""
    global worker_instance
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Load and validate configuration
        logger.info("Loading configuration...")
        config = init_config(print_summary=True)
        
        # Create and initialize worker
        worker_instance = TemporalWorker(config)
        
        # Connect to Temporal server
        await worker_instance.connect_client()
        
        # Create worker with registered workflows and activities
        await worker_instance.create_worker()
        
        # Start processing tasks
        logger.info("Supervisor agent worker is ready and running...")
        await worker_instance.start()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Worker failed with error: {e}")
        raise
    finally:
        if worker_instance:
            await worker_instance.shutdown()


if __name__ == "__main__":
    """Entry point for running the worker directly."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Failed to start worker: {e}")
        sys.exit(1)