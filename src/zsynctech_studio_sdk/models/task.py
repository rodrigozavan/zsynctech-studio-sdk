"""
Task models representing platform API request payloads and responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import TaskStatus


class _PlatformModel(BaseModel):
    """Base Pydantic model configured to accept both camelCase aliases and
    snake_case field names, matching the platform's JSON convention."""

    model_config = ConfigDict(populate_by_name=True)


class Task(_PlatformModel):
    """Represents a task returned by the platform API.

    Attributes:
        id:           Unique identifier (UUID v7).
        execution_id: UUID of the parent execution.
        name:         Human-readable label for the task step.
        status:       Current lifecycle status.
        order:        Zero-based execution sequence index.
        started_at:   Timestamp when the task started, or ``None``.
        finished_at:  Timestamp when the task finished, or ``None``.
        observation:  Optional free-text note (e.g. error message).
        metadata:     Arbitrary JSON data attached by the robot (e.g. stack trace).
        created_at:   Record creation timestamp.
        updated_at:   Last update timestamp.
    """

    id: str
    execution_id: str = Field(alias="executionId")
    name: str
    status: TaskStatus
    order: int
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    observation: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class RegisterTaskRequest(_PlatformModel):
    """Request payload for registering a new task inside a running execution.

    Attributes:
        name:  Human-readable label for the task step (1–255 characters).
        order: Zero-based sequence index. Omit to let the service assign it.
    """

    name: str
    order: int | None = None


class UpdateTaskRequest(_PlatformModel):
    """Request payload for updating a task's status and result.

    All fields are optional; only provided fields are sent to the platform.

    Attributes:
        status:      New lifecycle status for the task.
        observation: Free-text note, typically an error message.
        metadata:    Arbitrary JSON data (stack trace, output, etc.).
    """

    status: TaskStatus | None = None
    observation: str | None = None
    metadata: dict[str, Any] | None = None


class TaskSummary(_PlatformModel):
    """Task counts and timing metrics for a single execution.

    Attributes:
        total:    Total number of tasks.
        pending:  Tasks still waiting.
        running:  Tasks currently in progress.
        success:  Tasks completed successfully.
        warning:  Tasks completed with warnings.
        error:    Tasks that failed.
        skipped:  Tasks that were skipped.
    """

    total: int
    pending: int
    running: int
    success: int
    warning: int
    error: int
    skipped: int
