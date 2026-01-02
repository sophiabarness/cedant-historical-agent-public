"""Health monitoring and recovery for Temporal worker."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable

from temporalio.client import Client
from temporalio.worker import Worker

logger = logging.getLogger(__name__)


class WorkerHealthMonitor:
    """Monitor worker health and handle recovery."""
    
    def __init__(
        self,
        client: Client,
        worker: Worker,
        check_interval: int = 30,
        max_consecutive_failures: int = 3
    ):
        """Initialize health monitor.
        
        Args:
            client: Temporal client instance
            worker: Worker instance to monitor
            check_interval: Health check interval in seconds
            max_consecutive_failures: Max failures before triggering recovery
        """
        self.client = client
        self.worker = worker
        self.check_interval = check_interval
        self.max_consecutive_failures = max_consecutive_failures
        
        self.consecutive_failures = 0
        self.last_successful_check: Optional[datetime] = None
        self.is_monitoring = False
        self.recovery_callback: Optional[Callable[[], Awaitable[None]]] = None
    
    def set_recovery_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Set callback function to call when recovery is needed."""
        self.recovery_callback = callback
    
    async def start_monitoring(self) -> None:
        """Start health monitoring in background."""
        if self.is_monitoring:
            logger.warning("Health monitoring already started")
            return
            
        self.is_monitoring = True
        logger.info(f"Starting health monitoring with {self.check_interval}s interval")
        
        # Start monitoring task
        asyncio.create_task(self._monitor_loop())
    
    async def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        self.is_monitoring = False
        logger.info("Health monitoring stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                await asyncio.sleep(self.check_interval)
                
                if not self.is_monitoring:
                    break
                    
                await self._perform_health_check()
                
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retrying
    
    async def _perform_health_check(self) -> None:
        """Perform a health check on the worker and client."""
        try:
            # Check client connection
            await self._check_client_health()
            
            # Check worker health (basic check - worker should be running)
            await self._check_worker_health()
            
            # Reset failure count on success
            if self.consecutive_failures > 0:
                logger.info("Health check successful - resetting failure count")
                self.consecutive_failures = 0
            
            self.last_successful_check = datetime.now()
            
        except Exception as e:
            self.consecutive_failures += 1
            logger.warning(
                f"Health check failed ({self.consecutive_failures}/{self.max_consecutive_failures}): {e}"
            )
            
            if self.consecutive_failures >= self.max_consecutive_failures:
                logger.error("Max consecutive failures reached - triggering recovery")
                await self._trigger_recovery()
    
    async def _check_client_health(self) -> None:
        """Check if Temporal client is healthy."""
        try:
            # Simple health check - try to get service info
            await self.client.workflow_service.get_system_info()
        except Exception as e:
            raise Exception(f"Client health check failed: {e}")
    
    async def _check_worker_health(self) -> None:
        """Check if worker is healthy."""
        # For now, just check if worker exists
        # In future versions, we could add more sophisticated checks
        if not self.worker:
            raise Exception("Worker instance is None")
    
    async def _trigger_recovery(self) -> None:
        """Trigger recovery process."""
        logger.error("Triggering worker recovery process")
        
        if self.recovery_callback:
            try:
                await self.recovery_callback()
                logger.info("Recovery callback completed")
                # Reset failure count after successful recovery
                self.consecutive_failures = 0
            except Exception as e:
                logger.error(f"Recovery callback failed: {e}")
        else:
            logger.warning("No recovery callback set - manual intervention required")


async def create_health_monitor(
    client: Client,
    worker: Worker,
    recovery_callback: Optional[Callable[[], Awaitable[None]]] = None
) -> WorkerHealthMonitor:
    """Create and configure a health monitor.
    
    Args:
        client: Temporal client
        worker: Worker instance
        recovery_callback: Optional recovery callback
        
    Returns:
        Configured health monitor
    """
    monitor = WorkerHealthMonitor(client, worker)
    
    if recovery_callback:
        monitor.set_recovery_callback(recovery_callback)
    
    return monitor