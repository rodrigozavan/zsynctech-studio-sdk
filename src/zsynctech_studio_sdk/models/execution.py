"""
Execution models representing platform API responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .enums import ExecutionStatus

T = TypeVar("T")


class _PlatformModel(BaseModel):
    """Base Pydantic model configured to accept both camelCase aliases and
    snake_case field names, matching the platform's JSON convention."""

    model_config = ConfigDict(populate_by_name=True)


class Execution(_PlatformModel):
    """Represents an execution returned by the platform API.

    Attributes:
        id:                    Unique identifier (UUID v7).
        instance_id:           UUID of the automation instance.
        status:                Current lifecycle status.
        triggered_by:          UUID of the user who triggered the execution, or ``None``.
        triggered_by_api_token: UUID of the API token that triggered it, or ``None``.
        triggered_by_schedule: UUID of the schedule that triggered it, or ``None``.
        started_at:            Timestamp when the execution started, or ``None`` if pending.
        finished_at:           Timestamp when the execution ended, or ``None`` if running.
        observation:           Optional free-text note attached to the execution.
        created_at:            Record creation timestamp.
        updated_at:            Last update timestamp.
    """

    id: str
    instance_id: str = Field(alias="instanceId")
    status: ExecutionStatus
    triggered_by: str | None = Field(default=None, alias="triggeredBy")
    triggered_by_api_token: str | None = Field(default=None, alias="triggeredByApiToken")
    triggered_by_schedule: str | None = Field(default=None, alias="triggeredBySchedule")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    observation: str | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class PagedResponse(_PlatformModel, Generic[T]):
    """Generic paginated response envelope used by list endpoints.

    Attributes:
        data:        List of items on the current page.
        page:        Current page number (1-indexed).
        page_size:   Number of items per page.
        total_items: Total number of items across all pages.
        total_pages: Total number of pages.
        has_next_page:     Whether a next page exists.
        has_previous_page: Whether a previous page exists.
    """

    data: list[T]
    page: int
    page_size: int = Field(alias="pageSize")
    total_items: int = Field(alias="totalItems")
    total_pages: int = Field(alias="totalPages")
    has_next_page: bool = Field(alias="hasNextPage")
    has_previous_page: bool = Field(alias="hasPreviousPage")
