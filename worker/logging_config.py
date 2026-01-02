"""Logging configuration for Temporal worker to reduce noise and improve debugging."""

import logging
import sys
from typing import Dict, Any


def setup_logging(log_level: str = "INFO", reduce_temporal_noise: bool = True) -> None:
    """Configure logging with reduced Temporal SDK noise.
    
    Args:
        log_level: The logging level (DEBUG, INFO, WARNING, ERROR)
        reduce_temporal_noise: Whether to reduce noisy Temporal SDK logs
    """
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    if reduce_temporal_noise:
        # Reduce noise from Temporal SDK components
        temporal_loggers = [
            'temporal_sdk_core',
            'temporal_sdk_core.worker',
            'temporal_sdk_core.worker.workflow',
            'temporalio.bridge',
            'temporalio.worker._worker',
            'temporalio.client._client',
        ]
        
        for logger_name in temporal_loggers:
            logger = logging.getLogger(logger_name)
            # Set to ERROR to only show actual errors, not warnings
            logger.setLevel(logging.ERROR)
    
    # Keep our application logs at the requested level
    app_logger = logging.getLogger(__name__.split('.')[0])  # Get root module name
    app_logger.setLevel(getattr(logging, log_level.upper()))


def get_worker_logger(name: str) -> logging.Logger:
    """Get a properly configured logger for worker components.
    
    Args:
        name: The logger name (usually __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Logging configuration for different environments
LOGGING_CONFIGS: Dict[str, Dict[str, Any]] = {
    "development": {
        "log_level": "INFO",
        "reduce_temporal_noise": True,
    },
    "production": {
        "log_level": "WARNING", 
        "reduce_temporal_noise": True,
    },
    "debug": {
        "log_level": "DEBUG",
        "reduce_temporal_noise": False,
    }
}


def setup_environment_logging(environment: str = "development") -> None:
    """Setup logging for a specific environment.
    
    Args:
        environment: The environment name (development, production, debug)
    """
    config = LOGGING_CONFIGS.get(environment, LOGGING_CONFIGS["development"])
    setup_logging(**config)