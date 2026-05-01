"""
Robot runner - HTTP polling loop for ZSyncTech Studio robots.

The :class:`RobotRunner` is the heart of the SDK.  It:

1. Creates an :class:`~zsynctech_studio_sdk.http.HttpClient` authenticated
   with the robot's API token.
2. Polls ``GET /executions/pending/{instanceId}`` at a configurable interval.
3. When a pending execution is found, claims it (PENDING -> RUNNING).
4. Injects an :class:`~zsynctech_studio_sdk.context.ExecutionContext` into the
   calling context so that ``@task``-decorated functions can report progress.
5. Calls the user-supplied execution function.
6. Finishes the execution (COMPLETED or FAILED depending on task outcomes).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import httpx

from .config import SDKConfig
from .context import ExecutionContext, _reset_context, _set_context
from .exceptions import ApiError, AuthenticationError, NotFoundError
from .http.client import HttpClient
from .models.enums import ExecutionStatus
from .services.execution_service import ExecutionService
from .services.task_service import TaskService

logger = logging.getLogger(__name__)

# Type alias for the user's execution entry-point
type ExecutionFunc = Callable[[], None]

# Type alias for an execution status mapper (mirrors the one in decorators.py)
type ExecutionStatusMapper = dict[type[BaseException], ExecutionStatus]

# How long to wait before retrying after a connection error (seconds).
_RECONNECT_WAIT_S = 10.0


class RobotRunner:
    """Polling-based runner that dispatches pending executions to a handler function.

    Each iteration of the loop checks for a pending execution assigned to the
    configured instance. When found, it is claimed and the handler function is
    called synchronously within an active :class:`ExecutionContext`.

    Args:
        config:   SDK configuration (base URL, API token, instance ID, poll interval).
        handler:  Zero-argument callable that implements the robot's business logic.

    Example::

        def run_robot():
            fetch_data()
            process_data()

        runner = RobotRunner(SDKConfig.from_env(), run_robot)
        runner.run()   # blocks until Ctrl+C
    """

    def __init__(
        self,
        config: SDKConfig,
        handler: ExecutionFunc,
        status_mapper: ExecutionStatusMapper | None = None,
    ) -> None:
        self._config = config
        self._handler = handler
        self._status_mapper = status_mapper
        self._http = HttpClient(config.base_url, config.api_token)
        self._execution_service = ExecutionService(self._http)
        self._task_service = TaskService(self._http)

    # -- Public API ------------------------------------------------------------

    def run(self) -> None:
        """Start the polling loop and block until a ``KeyboardInterrupt`` is raised.

        Continuously polls for pending executions.  When one is found it is
        claimed, executed, and finished before the next poll cycle begins.

        Raises:
            KeyboardInterrupt: Propagated from Ctrl+C; the HTTP client is
                               closed before the exception propagates.
        """
        logger.info(
            "[bold green]Robot started.[/bold green] Polling every [cyan]%.1f s[/cyan] — instance [dim]%s[/dim]",
            self._config.poll_interval,
            self._config.instance_id,
        )
        try:
            self._loop()
        finally:
            self._http.close()
            logger.info("[bold]Robot stopped.[/bold]")

    # -- Internal helpers ------------------------------------------------------

    def _loop(self) -> None:
        """Main polling loop. Blocks until interrupted.

        Handles transient network errors (connection refused, timeout) by
        logging a warning and waiting :data:`_RECONNECT_WAIT_S` before
        retrying, so the robot never crashes when the platform is temporarily
        unavailable.
        """
        while True:
            try:
                pending = self._execution_service.get_pending(self._config.instance_id)
            except AuthenticationError:
                logger.error(
                    "Authentication failed. Check that API_TOKEN is set and the token "
                    "is active and not expired."
                )
                return
            except NotFoundError:
                logger.error(
                    "Instance '%s' not found on the platform. "
                    "Check that INSTANCE_ID is correct and the instance is registered.",
                    self._config.instance_id,
                )
                return
            except ApiError as exc:
                if exc.status_code == 403:
                    logger.error(
                        "Permission denied: %s. "
                        "Check that the API token has access to this automation.",
                        exc.detail,
                    )
                    return
                logger.error(
                    "API error while polling for executions: %s. Retrying in %.0f s...",
                    exc,
                    _RECONNECT_WAIT_S,
                )
                time.sleep(_RECONNECT_WAIT_S)
                continue
            except httpx.ConnectError:
                logger.warning(
                    "Could not connect to the platform at %s. "
                    "Retrying in %.0f s...",
                    self._config.base_url,
                    _RECONNECT_WAIT_S,
                )
                time.sleep(_RECONNECT_WAIT_S)
                continue
            except httpx.TimeoutException:
                logger.warning(
                    "Request to the platform timed out. Retrying in %.0f s...",
                    _RECONNECT_WAIT_S,
                )
                time.sleep(_RECONNECT_WAIT_S)
                continue
            except Exception as exc:
                logger.error("Unexpected error while polling for executions: %s. Retrying in %.0f s...", exc, _RECONNECT_WAIT_S)
                time.sleep(_RECONNECT_WAIT_S)
                continue

            if pending is not None:
                self._process(pending.id)
            else:
                logger.debug("No pending executions. Waiting %.1f s.", self._config.poll_interval)
                time.sleep(self._config.poll_interval)

    def _process(self, execution_id: str) -> None:
        """Claim and execute a single pending execution.

        Creates the :class:`ExecutionContext`, invokes the handler, and
        finishes the execution regardless of whether the handler succeeded.

        Args:
            execution_id: UUID of the execution to process.
        """
        logger.info("Claiming execution [dim]%s[/dim].", execution_id)

        try:
            self._execution_service.claim(execution_id)
        except Exception as exc:
            logger.error("Failed to claim execution [dim]%s[/dim]: %s. Skipping.", execution_id, exc)
            return

        ctx = ExecutionContext(
            execution_id=execution_id,
            execution_service=self._execution_service,
            task_service=self._task_service,
        )
        token = _set_context(ctx)

        observation: str | None = None
        override_status: ExecutionStatus | None = None

        try:
            logger.info("Running execution [dim]%s[/dim].", execution_id)
            self._handler()
        except Exception as exc:
            if self._status_mapper:
                for exc_type, mapped_status in self._status_mapper.items():
                    if isinstance(exc, exc_type):
                        override_status = mapped_status
                        if mapped_status == ExecutionStatus.COMPLETED:
                            logger.info(
                                "Execution [dim]%s[/dim]: %s mapped to COMPLETED, finishing cleanly.",
                                execution_id,
                                type(exc).__name__,
                            )
                        else:
                            logger.warning(
                                "Execution [dim]%s[/dim]: %s mapped to %s.",
                                execution_id,
                                type(exc).__name__,
                                mapped_status.value,
                            )
                            observation = str(exc)
                        break
                else:
                    logger.error("Execution %s failed: %s", execution_id, exc)
                    observation = str(exc)
            else:
                logger.error("Execution %s failed: %s", execution_id, exc)
                observation = str(exc)
        finally:
            _reset_context(token)

        try:
            finished = self._execution_service.finish(execution_id, observation, override_status)
            status = finished.status.value if hasattr(finished.status, "value") else str(finished.status)
            color = "green" if "COMPLETED" in status else "red"
            logger.info(
                "Execution [dim]%s[/dim] finished with status [bold %s]%s[/bold %s].",
                execution_id,
                color,
                status,
                color,
            )
        except Exception as exc:
            logger.error("Failed to finish execution [dim]%s[/dim]: %s", execution_id, exc)
