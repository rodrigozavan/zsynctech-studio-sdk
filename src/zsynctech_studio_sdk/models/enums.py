"""
Enumeration types used across executions and tasks.
"""

from __future__ import annotations

from enum import StrEnum


class ExecutionStatus(StrEnum):
    """Lifecycle states for a full execution run.

    States:
        PENDING:   Scheduled but not yet claimed by a robot.
        RUNNING:   Actively being processed by a robot.
        COMPLETED: Finished successfully (all tasks passed).
        FAILED:    Finished with one or more task errors.
        CANCELLED: Manually cancelled before completion.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatus(StrEnum):
    """Lifecycle states for a single task within an execution.

    States:
        PENDING: Created but not yet started.
        RUNNING: Currently being executed.
        SUCCESS: Completed without errors.
        WARNING: Completed with non-fatal issues.
        ERROR:   Failed with an error.
        SKIPPED: Intentionally bypassed.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
