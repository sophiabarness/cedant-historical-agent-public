"""Configuration management for the temporal supervisor agent."""

import os
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional, Dict, Any

# Note: NumPy environment variables moved inside functions to comply with Temporal restrictions

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.service import TLSConfig

# Load environment variables with override
load_dotenv(override=True)

# Data directory configuration - centralized path for all data files
DATA_DIR = os.getenv("DATA_DIR", "data")





@dataclass
class TemporalConfig:
    """Configuration for Temporal connection and worker settings."""
    
    # Connection settings
    address: str
    namespace: str
    task_queue: str
    
    # Authentication settings
    tls_cert: Optional[str] = None
    tls_key: Optional[str] = None
    api_key: Optional[str] = None
    
    # Worker settings
    max_concurrent_activities: int = 10
    max_concurrent_workflows: int = 10
    
    # Parallel processing configuration
    max_parallel_events: int = 50
    child_workflow_timeout_minutes: int = 10
    batch_processing_timeout_minutes: int = 30
    historical_matching_timeout_minutes: int = 2
    
    # Retry policy configuration
    retry_initial_interval_seconds: int = 5
    retry_maximum_attempts: int = 3
    retry_backoff_coefficient: float = 2.0
    retry_maximum_interval_minutes: int = 2


@dataclass
class LLMConfig:
    """Configuration for LLM service integration."""
    
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class AgentConfig:
    """Configuration for agent behavior and features."""
    
    show_tool_confirmation: bool = True
    max_conversation_turns: int = 250
    default_reinsurance_response: str = "sunny"
    tool_execution_timeout: int = 30


@dataclass
class APIConfig:
    """Configuration for API server settings."""
    
    host: str = "0.0.0.0"
    port: int = 8000
    enable_cors: bool = True
    cors_origins: Optional[List[str]] = None





@dataclass
class LoggingConfig:
    """Configuration for logging and debugging."""
    
    log_level: str = "INFO"
    debug: bool = False
    print_config_summary: bool = False


@dataclass
class AppConfig:
    """Main application configuration containing all sub-configurations."""
    
    temporal: TemporalConfig
    llm: LLMConfig
    agent: AgentConfig
    api: APIConfig
    logging: LoggingConfig



def load_temporal_config() -> TemporalConfig:
    """Load Temporal configuration from environment variables."""
    return TemporalConfig(
        address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "submission-pack-task-queue"),
        tls_cert=os.getenv("TEMPORAL_TLS_CERT"),
        tls_key=os.getenv("TEMPORAL_TLS_KEY"),
        api_key=os.getenv("TEMPORAL_API_KEY"),
        max_concurrent_activities=int(os.getenv("MAX_CONCURRENT_ACTIVITIES", "10")),
        max_concurrent_workflows=int(os.getenv("MAX_CONCURRENT_WORKFLOWS", "10")),
        # Parallel processing configuration
        max_parallel_events=int(os.getenv("MAX_PARALLEL_EVENTS", "50")),
        child_workflow_timeout_minutes=int(os.getenv("CHILD_WORKFLOW_TIMEOUT_MINUTES", "10")),
        batch_processing_timeout_minutes=int(os.getenv("BATCH_PROCESSING_TIMEOUT_MINUTES", "30")),
        historical_matching_timeout_minutes=int(os.getenv("HISTORICAL_MATCHING_TIMEOUT_MINUTES", "2")),
        # Retry policy configuration
        retry_initial_interval_seconds=int(os.getenv("RETRY_INITIAL_INTERVAL_SECONDS", "5")),
        retry_maximum_attempts=int(os.getenv("RETRY_MAXIMUM_ATTEMPTS", "3")),
        retry_backoff_coefficient=float(os.getenv("RETRY_BACKOFF_COEFFICIENT", "2.0")),
        retry_maximum_interval_minutes=int(os.getenv("RETRY_MAXIMUM_INTERVAL_MINUTES", "2")),
    )


def load_llm_config() -> LLMConfig:
    """Load LLM configuration from environment variables."""
    return LLMConfig(
        model=os.getenv("LLM_MODEL", "openai/gpt-5"),
        api_key=os.getenv("LLM_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
    )


def load_agent_config() -> AgentConfig:
    """Load agent configuration from environment variables."""
    max_turns = int(os.getenv("MAX_CONVERSATION_TURNS", "250"))
    default_reinsurance = os.getenv("DEFAULT_REINSURANCE_RESPONSE", "sunny")
    tool_timeout = int(os.getenv("TOOL_EXECUTION_TIMEOUT", "30"))
    
    return AgentConfig(
        show_tool_confirmation=True,  # Tool confirmation is always required
        max_conversation_turns=max_turns,
        default_reinsurance_response=default_reinsurance,
        tool_execution_timeout=tool_timeout,
    )


def load_api_config() -> APIConfig:
    """Load API server configuration from environment variables."""
    cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080")
    cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]
    
    return APIConfig(
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        enable_cors=os.getenv("ENABLE_CORS", "true").lower() == "true",
        cors_origins=cors_origins,
    )





def load_logging_config() -> LoggingConfig:
    """Load logging configuration from environment variables."""
    return LoggingConfig(
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        print_config_summary=os.getenv("PRINT_CONFIG_SUMMARY", "false").lower() == "true",
    )


def load_config() -> AppConfig:
    """Load complete application configuration from environment variables."""
    return AppConfig(
        temporal=load_temporal_config(),
        llm=load_llm_config(),
        agent=load_agent_config(),
        api=load_api_config(),
        logging=load_logging_config(),

    )


def validate_config(config: AppConfig) -> None:
    """
    Validate the application configuration and raise errors for missing required values.
    
    Args:
        config: The application configuration to validate
        
    Raises:
        ValueError: If required configuration values are missing or invalid
    """
    errors = []
    
    # Validate Temporal configuration
    if not config.temporal.address:
        errors.append("TEMPORAL_ADDRESS is required")
    
    if not config.temporal.namespace:
        errors.append("TEMPORAL_NAMESPACE is required")
    
    if not config.temporal.task_queue:
        errors.append("TEMPORAL_TASK_QUEUE is required")
    
    # Validate worker limits
    if config.temporal.max_concurrent_activities <= 0:
        errors.append("MAX_CONCURRENT_ACTIVITIES must be greater than 0")
    
    if config.temporal.max_concurrent_workflows <= 0:
        errors.append("MAX_CONCURRENT_WORKFLOWS must be greater than 0")
    
    # Validate parallel processing configuration
    if config.temporal.max_parallel_events <= 0:
        errors.append("MAX_PARALLEL_EVENTS must be greater than 0")
    
    if config.temporal.child_workflow_timeout_minutes <= 0:
        errors.append("CHILD_WORKFLOW_TIMEOUT_MINUTES must be greater than 0")
    
    if config.temporal.batch_processing_timeout_minutes <= 0:
        errors.append("BATCH_PROCESSING_TIMEOUT_MINUTES must be greater than 0")
    
    if config.temporal.historical_matching_timeout_minutes <= 0:
        errors.append("HISTORICAL_MATCHING_TIMEOUT_MINUTES must be greater than 0")
    
    # Validate retry policy configuration
    if config.temporal.retry_initial_interval_seconds <= 0:
        errors.append("RETRY_INITIAL_INTERVAL_SECONDS must be greater than 0")
    
    if config.temporal.retry_maximum_attempts <= 0:
        errors.append("RETRY_MAXIMUM_ATTEMPTS must be greater than 0")
    
    if config.temporal.retry_backoff_coefficient <= 1.0:
        errors.append("RETRY_BACKOFF_COEFFICIENT must be greater than 1.0")
    
    if config.temporal.retry_maximum_interval_minutes <= 0:
        errors.append("RETRY_MAXIMUM_INTERVAL_MINUTES must be greater than 0")
    
    # Validate LLM configuration
    if not config.llm.model:
        errors.append("LLM_MODEL is required")
    
    # For OpenAI models, API key is required
    if config.llm.model.startswith("openai/") and not config.llm.api_key:
        errors.append("LLM_KEY is required for OpenAI models")
    
    # Validate agent configuration
    if config.agent.max_conversation_turns <= 0:
        errors.append("MAX_CONVERSATION_TURNS must be greater than 0")
    
    if config.agent.tool_execution_timeout <= 0:
        errors.append("TOOL_EXECUTION_TIMEOUT must be greater than 0")
    
    if not config.agent.default_reinsurance_response:
        errors.append("DEFAULT_REINSURANCE_RESPONSE cannot be empty")
    
    # Validate API configuration
    if config.api.port <= 0 or config.api.port > 65535:
        errors.append("API_PORT must be between 1 and 65535")
    
    if not config.api.host:
        errors.append("API_HOST cannot be empty")
    
    # Validate logging configuration
    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.logging.log_level not in valid_log_levels:
        errors.append(f"LOG_LEVEL must be one of: {', '.join(valid_log_levels)}")
    
    # Validate TLS configuration consistency
    temporal_config = config.temporal
    if (temporal_config.tls_cert and not temporal_config.tls_key) or \
       (temporal_config.tls_key and not temporal_config.tls_cert):
        errors.append("Both TEMPORAL_TLS_CERT and TEMPORAL_TLS_KEY must be provided together")
    

    if errors:
        error_message = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
        raise ValueError(error_message)


def print_config_summary(config: AppConfig) -> None:
    """Print a summary of the loaded configuration for debugging."""
    print("=== Configuration Summary ===")
    print("Temporal Configuration:")
    print(f"  Address: {config.temporal.address}")
    print(f"  Namespace: {config.temporal.namespace}")
    print(f"  Task Queue: {config.temporal.task_queue}")
    print(f"  Max Concurrent Activities: {config.temporal.max_concurrent_activities}")
    print(f"  Max Concurrent Workflows: {config.temporal.max_concurrent_workflows}")
    print(f"  Max Parallel Events: {config.temporal.max_parallel_events}")
    print(f"  Child Workflow Timeout: {config.temporal.child_workflow_timeout_minutes} minutes")
    print(f"  Batch Processing Timeout: {config.temporal.batch_processing_timeout_minutes} minutes")
    print(f"  Historical Matching Timeout: {config.temporal.historical_matching_timeout_minutes} minutes")
    print(f"  Retry Initial Interval: {config.temporal.retry_initial_interval_seconds} seconds")
    print(f"  Retry Maximum Attempts: {config.temporal.retry_maximum_attempts}")
    print(f"  Retry Backoff Coefficient: {config.temporal.retry_backoff_coefficient}")
    print(f"  Retry Maximum Interval: {config.temporal.retry_maximum_interval_minutes} minutes")
    
    print("LLM Configuration:")
    print(f"  Model: {config.llm.model}")
    print(f"  Base URL: {config.llm.base_url or 'Default'}")
    
    print("Agent Configuration:")
    print(f"  Show Tool Confirmation: {config.agent.show_tool_confirmation}")
    print(f"  Max Conversation Turns: {config.agent.max_conversation_turns}")
    print(f"  Default Reinsurance Response: {config.agent.default_reinsurance_response}")
    print(f"  Tool Execution Timeout: {config.agent.tool_execution_timeout}s")
    
    print("API Configuration:")
    print(f"  Host: {config.api.host}")
    print(f"  Port: {config.api.port}")
    print(f"  CORS Enabled: {config.api.enable_cors}")
    print(f"  CORS Origins: {', '.join(config.api.cors_origins) if config.api.cors_origins else 'None'}")
    
    print("Logging Configuration:")
    print(f"  Log Level: {config.logging.log_level}")
    print(f"  Debug Mode: {config.logging.debug}")
    

    # Security-sensitive information
    print("Security Status:")
    print(f"  Has Temporal API Key: {'Yes' if config.temporal.api_key else 'No'}")
    print(f"  Has TLS Cert: {'Yes' if config.temporal.tls_cert else 'No'}")
    print(f"  Has LLM Key: {'Yes' if config.llm.api_key else 'No'}")
    print("=============================")


# Legacy compatibility - maintain existing variables for backward compatibility
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "reinsurance-agent-task-queue")
TEMPORAL_TLS_CERT = os.getenv("TEMPORAL_TLS_CERT", "")
TEMPORAL_TLS_KEY = os.getenv("TEMPORAL_TLS_KEY", "")
TEMPORAL_API_KEY = os.getenv("TEMPORAL_API_KEY", "")


async def get_temporal_client() -> Client:
    """
    Creates a Temporal client based on environment configuration.
    Supports local server, mTLS, and API key authentication methods.
    
    Returns:
        Client: Configured Temporal client instance
    """
    # Default to no TLS for local development
    tls_config = False
    print(f"Address: {TEMPORAL_ADDRESS}, Namespace {TEMPORAL_NAMESPACE}")
    print("(If unset, then will try to connect to local server)")

    # Configure mTLS if certificate and key are provided
    if TEMPORAL_TLS_CERT and TEMPORAL_TLS_KEY:
        print(f"TLS cert: {TEMPORAL_TLS_CERT}")
        print(f"TLS key: {TEMPORAL_TLS_KEY}")
        with open(TEMPORAL_TLS_CERT, "rb") as f:
            client_cert = f.read()
        with open(TEMPORAL_TLS_KEY, "rb") as f:
            client_key = f.read()
        tls_config = TLSConfig(
            client_cert=client_cert,
            client_private_key=client_key,
        )

    # Use API key authentication if provided
    if TEMPORAL_API_KEY:
        print("Using API key authentication")
        return await Client.connect(
            TEMPORAL_ADDRESS,
            namespace=TEMPORAL_NAMESPACE,
            api_key=TEMPORAL_API_KEY,
            tls=True,  # Always use TLS with API key
        )

    # Use mTLS or local connection
    return await Client.connect(
        TEMPORAL_ADDRESS,
        namespace=TEMPORAL_NAMESPACE,
        tls=tls_config,
    )

def get_validated_config() -> AppConfig:
    """
    Load and validate the complete application configuration.
    
    This is the main entry point for getting configuration in the application.
    It loads all configuration from environment variables and validates it.
    
    Returns:
        AppConfig: Validated application configuration
        
    Raises:
        ValueError: If configuration validation fails
        SystemExit: If critical configuration is missing
    """
    try:
        config = load_config()
        validate_config(config)
        return config
    except ValueError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        print("\nPlease check your .env file and ensure all required values are set.", file=sys.stderr)
        print("See .env.example for reference.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)


def init_config(print_summary: bool = None) -> AppConfig:
    """
    Initialize and return validated configuration.
    
    This function should be called at application startup to ensure
    configuration is loaded and validated before any other operations.
    
    Args:
        print_summary: Whether to print configuration summary for debugging.
                      If None, uses the PRINT_CONFIG_SUMMARY environment variable.
        
    Returns:
        AppConfig: Validated application configuration
    """
    config = get_validated_config()
    
    # Use environment variable if print_summary not explicitly provided
    should_print = print_summary if print_summary is not None else config.logging.print_config_summary
    
    if should_print:
        print_config_summary(config)
    
    return config


def get_parallel_processing_config() -> dict:
    """
    Get parallel processing configuration values for use in workflows.
    
    This function provides a convenient way for workflows to access
    configuration without importing the full config system.
    
    Returns:
        dict: Configuration values for parallel processing
    """
    return {
        "max_parallel_events": int(os.getenv("MAX_PARALLEL_EVENTS", "50")),
        "child_workflow_timeout_minutes": int(os.getenv("CHILD_WORKFLOW_TIMEOUT_MINUTES", "10")),
        "batch_processing_timeout_minutes": int(os.getenv("BATCH_PROCESSING_TIMEOUT_MINUTES", "30")),
        "historical_matching_timeout_minutes": int(os.getenv("HISTORICAL_MATCHING_TIMEOUT_MINUTES", "2")),
        "retry_initial_interval_seconds": int(os.getenv("RETRY_INITIAL_INTERVAL_SECONDS", "5")),
        "retry_maximum_attempts": int(os.getenv("RETRY_MAXIMUM_ATTEMPTS", "3")),
        "retry_backoff_coefficient": float(os.getenv("RETRY_BACKOFF_COEFFICIENT", "2.0")),
        "retry_maximum_interval_minutes": int(os.getenv("RETRY_MAXIMUM_INTERVAL_MINUTES", "2")),
    }




# Timeout constants for LLM activities
# These are used for activities that involve LLM API calls which can take longer
LLM_ACTIVITY_START_TO_CLOSE_TIMEOUT = timedelta(minutes=15)
LLM_ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT = timedelta(minutes=30)


# Data path helper functions
def get_data_path(relative_path: str = "") -> str:
    """
    Get the full path to a file in the data directory.
    
    Args:
        relative_path: Path relative to the data directory (e.g., "Cedant Loss Data.xlsx")
        
    Returns:
        Full path combining DATA_DIR and relative_path
    """
    if relative_path:
        return os.path.join(DATA_DIR, relative_path)
    return DATA_DIR


def get_cedant_data_path() -> str:
    """Get the path to the Cedant Loss Data file."""
    return get_data_path("Cedant Loss Data.xlsx")


def get_historical_db_path() -> str:
    """Get the path to the Historical Event DB file."""
    return get_data_path("Historical Event DB.csv")


def get_mapping_file_path() -> str:
    """Get the path to the Loss Data ProgramID Map file."""
    return get_data_path("Loss Data ProgramID Map.xlsx")


def get_submission_packs_dir() -> str:
    """Get the path to the Submission Packs directory."""
    return get_data_path("Submission Packs")
