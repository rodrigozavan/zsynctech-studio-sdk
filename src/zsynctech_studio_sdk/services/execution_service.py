"""
Execution service - wraps all ``/executions`` REST endpoints.

Each method corresponds to one platform endpoint and returns a typed model.
All HTTP errors are translated by :class:`~zsynctech_studio_sdk.http.HttpClient`
into SDK exceptions before reaching this layer.
"""

from __future__ import annotations

import logging
from typing import Any

from ..http.client import HttpClient
from ..models.enums import ExecutionStatus
from ..models.execution import Execution, PagedResponse

logger = logging.getLogger(__name__)


class ExecutionService:
    """High-level service for execution lifecycle operations.

    Provides methods for starting, claiming, finishing, and querying
    executions via the ZSyncTech platform REST API.

    Args:
        http: Pre-configured :class:`~zsynctech_studio_sdk.http.HttpClient`.

    Example::

        service = ExecutionService(http_client)
        pending = service.get_pending("instance-uuid")
        if pending:
            execution = service.claim(pending.id)
    """

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    # -- Robot-facing methods --------------------------------------------------

    def get_pending(self, instance_id: str) -> Execution | None:
        """Return the pending execution for an instance, if any.

        Polls the ``GET /executions/pending/{instanceId}`` endpoint.
        Returns ``None`` when there is no pending execution rather than raising.

        Args:
            instance_id: UUID of the automation instance to check.

        Returns:
            The pending :class:`~zsynctech_studio_sdk.models.Execution`, or
            ``None`` if none exists.

        Raises:
            AuthenticationError: If the API token is invalid.
            NotFoundError:       If the instance UUID does not exist on the platform.
            ApiError:            On unexpected platform errors.
        """
        data = self._http.get(f"/executions/pending/{instance_id}")

        if data is None:
            return None

        return Execution.model_validate(data)

    def claim(self, execution_id: str) -> Execution:
        """Transition a PENDING execution to RUNNING and return it.

        Calls ``POST /executions/{id}/claim``.

        Args:
            execution_id: UUID of the execution to claim.

        Returns:
            The updated :class:`~zsynctech_studio_sdk.models.Execution` with
            ``status == ExecutionStatus.RUNNING``.

        Raises:
            NotFoundError:  If no execution with *execution_id* exists.
            ApiError:       If the execution cannot be claimed (e.g. already running).
        """
        data = self._http.post(f"/executions/{execution_id}/claim")
        return Execution.model_validate(data)

    def finish(self, execution_id: str, observation: str | None = None, status: ExecutionStatus | None = None) -> Execution:
        """Mark a running execution as finished.

        Calls ``POST /executions/{id}/finish``. The final status is determined
        by the platform based on task outcomes unless *status* is provided
        explicitly, in which case it overrides automatic determination.

        Args:
            execution_id: UUID of the execution to finish.
            observation:  Optional free-text note to attach (e.g. summary or error).
            status:       Optional explicit terminal status to set
                          (COMPLETED, FAILED, or CANCELLED). When omitted the
                          platform decides automatically.

        Returns:
            The updated :class:`~zsynctech_studio_sdk.models.Execution`.

        Raises:
            NotFoundError: If no execution with *execution_id* exists.
            ApiError:      On unexpected platform errors.
        """
        body: dict[str, Any] = {}
        if observation is not None:
            body["observation"] = observation
        if status is not None:
            body["status"] = status.value

        data = self._http.post(f"/executions/{execution_id}/finish", body or None)
        return Execution.model_validate(data)

    def cancel(self, execution_id: str) -> Execution:
        """Cancel a running or pending execution.

        Calls ``POST /executions/{id}/cancel``.

        Args:
            execution_id: UUID of the execution to cancel.

        Returns:
            The updated :class:`~zsynctech_studio_sdk.models.Execution` with
            ``status == ExecutionStatus.CANCELLED``.

        Raises:
            NotFoundError: If no execution with *execution_id* exists.
            ApiError:      If the execution is already finished.
        """
        data = self._http.post(f"/executions/{execution_id}/cancel")
        logger.info("Execution %s cancelled.", execution_id)
        return Execution.model_validate(data)

    # -- Query methods ---------------------------------------------------------

    def get(self, execution_id: str) -> Execution:
        """Fetch a single execution by its ID.

        Calls ``GET /executions/{id}``.

        Args:
            execution_id: UUID of the execution to retrieve.

        Returns:
            The :class:`~zsynctech_studio_sdk.models.Execution`.

        Raises:
            NotFoundError: If no execution with *execution_id* exists.
            ApiError:      On unexpected platform errors.
        """
        data = self._http.get(f"/executions/{execution_id}")
        return Execution.model_validate(data)

    def list(
        self,
        instance_id: str | None = None,
        automation_id: str | None = None,
        status: ExecutionStatus | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PagedResponse[Execution]:
        """List executions with optional filters.

        Calls ``GET /executions`` with query parameters.

        Args:
            instance_id:   Filter by instance UUID.
            automation_id: Filter by automation UUID.
            status:        Filter by execution status.
            from_date:     ISO 8601 start date for the filter range.
            to_date:       ISO 8601 end date for the filter range.
            page:          Page number (1-indexed). Defaults to 1.
            page_size:     Items per page (1–200). Defaults to 20.

        Returns:
            A :class:`~zsynctech_studio_sdk.models.PagedResponse` of
            :class:`~zsynctech_studio_sdk.models.Execution` objects.

        Raises:
            ApiError: On unexpected platform errors.
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}

        if instance_id is not None:
            params["instanceId"] = instance_id
        if automation_id is not None:
            params["automationId"] = automation_id
        if status is not None:
            params["status"] = str(status)
        if from_date is not None:
            params["fromDate"] = from_date
        if to_date is not None:
            params["toDate"] = to_date

        data = self._http.get("/executions", params=params)
        return PagedResponse[Execution].model_validate(data)

    def start(self, instance_id: str) -> Execution:
        """Start a new RUNNING execution immediately for a given instance.

        Calls ``POST /executions``. Prefer :meth:`schedule` for robot-driven
        workflows; this method is primarily for manual or programmatic triggers.

        Args:
            instance_id: UUID of the automation instance to run.

        Returns:
            The newly created :class:`~zsynctech_studio_sdk.models.Execution`.

        Raises:
            ApiError: If the instance is not active or already has a running execution.
        """
        data = self._http.post("/executions", {"instanceId": instance_id})
        return Execution.model_validate(data)

    def schedule(self, instance_id: str) -> Execution:
        """Schedule a PENDING execution for a given instance.

        Calls ``POST /executions/schedule``. The robot will pick it up on its
        next poll via :meth:`get_pending` + :meth:`claim`.

        Args:
            instance_id: UUID of the automation instance to schedule.

        Returns:
            The newly created :class:`~zsynctech_studio_sdk.models.Execution`
            with ``status == ExecutionStatus.PENDING``.

        Raises:
            ApiError: If the instance is not active or already has a pending execution.
        """
        data = self._http.post("/executions/schedule", {"instanceId": instance_id})
        return Execution.model_validate(data)
