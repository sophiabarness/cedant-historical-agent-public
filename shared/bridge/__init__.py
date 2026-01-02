"""Bridge package for managing communication between workflows and frontend.

This package contains the BridgeWorkflow that manages frontend state
via Temporal signals and queries.
"""

from .workflow import BridgeWorkflow

__all__ = [
    'BridgeWorkflow',
]
