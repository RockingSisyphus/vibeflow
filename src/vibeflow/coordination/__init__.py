"""Explicit local workflow communication; no process ownership or run groups."""
from .client import WorkflowClient
from .server import WorkflowServer
from .protocol import CoordinationError

__all__ = ["WorkflowClient", "WorkflowServer", "CoordinationError"]
