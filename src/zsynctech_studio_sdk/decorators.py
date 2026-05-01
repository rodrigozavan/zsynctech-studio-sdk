"""
``@task`` and ``@execution`` decorators.

Design
------
Both decorators return typed wrapper classes that preserve the original
function's signature via ``ParamSpec`` and ``functools.update_wrapper``.

``@task``
~~~~~~~~~
When called **inside** an active execution (detected via the
:data:`~zsynctech_studio_sdk.context._execution_context_var` ContextVar),
the wrapper:

1. Registers the task with the platform via :class:`~zsynctech_studio_sdk.services.TaskService`.
2. Marks it as ``RUNNING``.
3. Calls the original function.
4. Marks it as ``SUCCESS`` (or ``ERROR`` on exception).

When called **outside** an execution the function is invoked normally,
enabling unit-testing without a live platform connection.

``@execution``
~~~~~~~~~~~~~~
Adds a :meth:`ExecutionWrapper.listener` method that:

1. Loads :class:`~zsynctech_studio_sdk.config.SDKConfig` from environment
   variables (or accepts an explicit override).
2. Creates a :class:`~zsynctech_studio_sdk.runner.RobotRunner`.
3. Blocks until interrupted with Ctrl+C, claiming and running every pending
   execution that arrives via HTTP polling.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Generic, ParamSpec, TypeVar, overload

from rich.logging import RichHandler
from rich.markup import escape as markup_escape

from .config import SDKConfig
from .context import get_current_context
from .models.enums import ExecutionStatus, TaskStatus

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

# -- Type aliases for status mappers ------------------------------------------

type TaskStatusMapper = dict[type[BaseException], TaskStatus]
type ExecutionStatusMapper = dict[type[BaseException], ExecutionStatus]


# -- Utilities -----------------------------------------------------------------


def _validate_task_mapper(mapper: object, func_name: str) -> None:
    """Raise ``TypeError`` if *mapper* contains invalid keys or values."""
    if not isinstance(mapper, dict):
        raise TypeError(
            f"{func_name}: status_mapper must be a dict, got {type(mapper).__name__!r}"
        )
    for key, value in mapper.items():  # type: ignore[union-attr]
        if not (isinstance(key, type) and issubclass(key, BaseException)):
            raise TypeError(
                f"{func_name}: status_mapper key {key!r} is not an exception class"
            )
        if not isinstance(value, TaskStatus):
            raise TypeError(
                f"{func_name}: status_mapper value for {key.__name__!r} must be a "
                f"TaskStatus member, got {value!r}. "
                f"Use TaskStatus.{value.upper() if isinstance(value, str) else '...'} instead."
            )


def _validate_execution_mapper(mapper: object, func_name: str) -> None:
    """Raise ``TypeError`` if *mapper* contains invalid keys or values."""
    if not isinstance(mapper, dict):
        raise TypeError(
            f"{func_name}: status_mapper must be a dict, got {type(mapper).__name__!r}"
        )
    for key, value in mapper.items():  # type: ignore[union-attr]
        if not (isinstance(key, type) and issubclass(key, BaseException)):
            raise TypeError(
                f"{func_name}: status_mapper key {key!r} is not an exception class"
            )
        if not isinstance(value, ExecutionStatus):
            raise TypeError(
                f"{func_name}: status_mapper value for {key.__name__!r} must be an "
                f"ExecutionStatus member, got {value!r}. "
                f"Use ExecutionStatus.{value.upper() if isinstance(value, str) else '...'} instead."
            )


def _resolve_mapped_status(
    exc: BaseException,
    mapper: dict[type[BaseException], TaskStatus] | dict[type[BaseException], ExecutionStatus],
) -> TaskStatus | ExecutionStatus | None:
    """Return the first matching status for *exc* from *mapper*, or ``None``.

    Iterates the mapper in insertion order and returns the status for the
    first entry whose key is a superclass of (or equal to) the exception type.
    """
    for exc_type, status in mapper.items():
        if isinstance(exc, exc_type):
            return status
    return None


def _name_from_function(func_name: str) -> str:
    """Convert ``snake_case`` to a human-readable label.

    Example:
        ``fetch_data`` -> ``Fetch data``

    Args:
        func_name: Name of the Python function.

    Returns:
        Capitalised, space-separated label.
    """
    return func_name.replace("_", " ").capitalize()


def _setup_logging() -> None:
    """Configure a sensible default logging format for the SDK entry point.

    Only activates when the root logger has no handlers configured, so
    applications that set up their own logging are not affected.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    handler = RichHandler(
        show_path=False,
        rich_tracebacks=True,
        markup=True,
        log_time_format="%H:%M:%S",
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


# -- TaskWrapper ---------------------------------------------------------------


class TaskWrapper(Generic[P, R]):
    """Callable wrapper produced by the :func:`task` decorator.

    Outside an execution context the underlying function is called directly.
    Inside an execution context the task is registered and tracked on the
    ZSyncTech platform via synchronous HTTP calls.

    Args:
        func: The original function to wrap.
        name: Human-readable task name shown in the platform UI.
    """

    def __init__(
        self,
        func: Callable[P, R],
        name: str,
        status_mapper: TaskStatusMapper | None = None,
    ) -> None:
        if status_mapper is not None:
            _validate_task_mapper(status_mapper, func.__name__)
        self._func = func
        self._name = name
        self._status_mapper = status_mapper
        self._offline_counter: int = 0
        functools.update_wrapper(self, func)

    @property
    def task_name(self) -> str:
        """Human-readable task name used when registering with the platform."""
        return self._name

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Invoke the wrapped function, tracking it on the platform if inside an execution.

        Args:
            *args:   Positional arguments forwarded to the wrapped function.
            **kwargs: Keyword arguments forwarded to the wrapped function.

        Returns:
            The return value of the wrapped function.

        Raises:
            Exception: Any exception raised by the wrapped function is re-raised
                       after the task status has been updated to ``ERROR``.
        """
        ctx = get_current_context()

        if ctx is None:
            return self._run_offline(*args, **kwargs)

        return self._run_tracked(ctx, *args, **kwargs)

    # -- Private helpers -------------------------------------------------------

    def _run_offline(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Execute the function without platform tracking (no active context).

        Args:
            *args:   Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The return value of the wrapped function.
        """
        order = self._offline_counter
        self._offline_counter += 1
        logger.info("  [%d] [cyan]▶[/cyan]  %s", order + 1, markup_escape(self._name))
        try:
            result: R = self._func(*args, **kwargs)
        except Exception as exc:
            mapped = _resolve_mapped_status(exc, self._status_mapper) if self._status_mapper else None
            task_status = mapped if mapped is not None else TaskStatus.ERROR
            if task_status == TaskStatus.ERROR:
                logger.error("  [%d] [bold red]✘[/bold red]  %s — %s", order + 1, markup_escape(self._name), markup_escape(str(exc)))
                raise
            logger.warning("  [%d] [yellow]⚠[/yellow]  %s — %s [%s]", order + 1, markup_escape(self._name), markup_escape(str(exc)), task_status.value)
            return None  # type: ignore[return-value]
        logger.info("  [%d] [green]✔[/green]  %s", order + 1, markup_escape(self._name))
        return result

    def _run_tracked(self, ctx: object, *args: P.args, **kwargs: P.kwargs) -> R:
        """Execute the function with full platform tracking.

        Registers the task, marks it RUNNING, executes the function, and
        marks it SUCCESS or ERROR depending on the outcome.

        Args:
            ctx:     Active :class:`~zsynctech_studio_sdk.context.ExecutionContext`.
            *args:   Positional arguments forwarded to the wrapped function.
            **kwargs: Keyword arguments forwarded to the wrapped function.

        Returns:
            The return value of the wrapped function.

        Raises:
            Exception: Re-raised after the task is marked ERROR.
        """
        from .context import ExecutionContext

        assert isinstance(ctx, ExecutionContext)

        order = ctx.next_task_order()

        # Register the task
        try:
            task = ctx.task_service.register(ctx.execution_id, self._name, order)
        except Exception as exc:
            logger.error(
                "Could not register task '%s': %s - running without tracking.",
                self._name,
                exc,
            )
            return self._func(*args, **kwargs)

        logger.info("  [%d] [cyan]▶[/cyan]  %s", order + 1, markup_escape(self._name))

        # Mark as RUNNING
        try:
            ctx.task_service.update(ctx.execution_id, task.id, status=TaskStatus.RUNNING)
        except Exception as exc:
            logger.warning("Could not mark task '%s' as RUNNING: %s", self._name, exc)

        # Execute
        try:
            result: R = self._func(*args, **kwargs)
        except Exception as exc:
            mapped = _resolve_mapped_status(exc, self._status_mapper) if self._status_mapper else None
            task_status = mapped if mapped is not None else TaskStatus.ERROR
            if task_status == TaskStatus.ERROR:
                logger.error("  [%d] [bold red]✘[/bold red]  %s — %s", order + 1, markup_escape(self._name), markup_escape(str(exc)))
            else:
                logger.warning("  [%d] [yellow]⚠[/yellow]  %s — %s [%s]", order + 1, markup_escape(self._name), markup_escape(str(exc)), task_status.value)
            try:
                ctx.task_service.update(
                    ctx.execution_id,
                    task.id,
                    status=task_status,
                    observation=str(exc),
                )
            except Exception:
                pass
            if task_status == TaskStatus.ERROR:
                raise
            return None  # type: ignore[return-value]

        # Mark as SUCCESS
        try:
            ctx.task_service.update(ctx.execution_id, task.id, status=TaskStatus.SUCCESS)
        except Exception as exc:
            logger.warning("Could not mark task '%s' as SUCCESS: %s", self._name, exc)

        logger.info("  [%d] [green]✔[/green]  %s", order + 1, markup_escape(self._name))
        return result


# -- ExecutionWrapper ----------------------------------------------------------


class ExecutionWrapper(Generic[P, R]):
    """Callable wrapper produced by the :func:`execution` decorator.

    In addition to behaving like the original function when called directly,
    it exposes a :meth:`listener` method that starts the robot polling loop
    and dispatches incoming executions to the wrapped function.

    Args:
        func:   The original execution function to wrap.
        config: Optional pre-built :class:`SDKConfig`. Takes precedence over
                environment variables when :meth:`listener` is called.
    """

    def __init__(
        self,
        func: Callable[P, R],
        config: SDKConfig | None = None,
        status_mapper: ExecutionStatusMapper | None = None,
    ) -> None:
        if status_mapper is not None:
            _validate_execution_mapper(status_mapper, func.__name__)
        self._func = func
        self._config = config
        self._status_mapper = status_mapper
        functools.update_wrapper(self, func)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Invoke the execution function in offline mode (no platform connection).

        Useful for local testing without a running platform.

        Args:
            *args:   Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The return value of the wrapped function.
        """
        _setup_logging()
        logger.warning(
            "Offline mode - execution is running locally and will not update the platform."
        )
        return self._func(*args, **kwargs)

    def listener(self, config: SDKConfig | None = None) -> None:
        """Connect to the platform and start the robot polling loop.

        Loads ``.env`` if *python-dotenv* is installed, then reads
        :class:`~zsynctech_studio_sdk.config.SDKConfig` from environment
        variables unless a *config* object is provided explicitly.

        Blocks until the process is interrupted with ``Ctrl+C``.

        Args:
            config: Optional explicit configuration. Takes precedence over
                    the decorator-level config and environment variables.
        """
        _setup_logging()

        try:
            from dotenv import load_dotenv  # type: ignore[import-untyped]

            load_dotenv()
        except ImportError:
            pass

        from .runner import RobotRunner

        cfg = config or self._config or SDKConfig.from_env()
        runner = RobotRunner(cfg, self._func, status_mapper=self._status_mapper)

        try:
            runner.run()
        except KeyboardInterrupt:
            logger.info("Listener stopped.")


# -- Decorator factories -------------------------------------------------------


@overload
def task(func: Callable[P, R]) -> TaskWrapper[P, R]: ...


@overload
def task(
    *,
    name: str | None = None,
    status_mapper: TaskStatusMapper | None = None,
) -> Callable[[Callable[P, R]], TaskWrapper[P, R]]: ...


def task(
    func: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    status_mapper: TaskStatusMapper | None = None,
) -> TaskWrapper[P, R] | Callable[[Callable[P, R]], TaskWrapper[P, R]]:
    """Decorator that registers and tracks a function as a platform task.

    Can be used with or without arguments::

        @task
        def fetch_data():
            ...

        @task(name="Fetch remote data")
        def fetch_data():
            ...

    When called inside a :func:`execution` listener, the function is
    automatically registered on the platform and its status is updated
    throughout its lifecycle.  Outside a listener it runs as-is.

    Args:
        func:          The function to decorate (when used without parentheses).
        name:          Custom display name for the platform UI. Defaults to a
                       human-readable version of the function name.
        status_mapper: Optional mapping of exception types to :class:`TaskStatus`
                       values. When an exception occurs whose type matches a key
                       (checked via ``isinstance``), the task is finished with
                       the mapped status instead of the default ``ERROR``. For
                       any status other than ``ERROR`` the exception is swallowed
                       and the execution continues normally.

    Returns:
        A :class:`TaskWrapper` instance wrapping *func*.
    """
    if func is not None:
        # @task without arguments
        return TaskWrapper(func, name or _name_from_function(func.__name__))

    # @task(name=..., status_mapper=...) - return a decorator
    def decorator(fn: Callable[P, R]) -> TaskWrapper[P, R]:
        return TaskWrapper(fn, name or _name_from_function(fn.__name__), status_mapper=status_mapper)

    return decorator


@overload
def execution(func: Callable[P, R]) -> ExecutionWrapper[P, R]: ...


@overload
def execution(
    *,
    config: SDKConfig | None = None,
    status_mapper: ExecutionStatusMapper | None = None,
) -> Callable[[Callable[P, R]], ExecutionWrapper[P, R]]: ...


def execution(
    func: Callable[P, R] | None = None,
    *,
    config: SDKConfig | None = None,
    status_mapper: ExecutionStatusMapper | None = None,
) -> ExecutionWrapper[P, R] | Callable[[Callable[P, R]], ExecutionWrapper[P, R]]:
    """Decorator that registers a function as the entry-point for a robot execution.

    Can be used with or without arguments::

        @execution
        def run():
            fetch_data()

        @execution(config=SDKConfig.from_env())
        def run():
            fetch_data()

    Call ``.listener()`` on the decorated function to start the robot loop::

        run.listener()          # reads config from env vars
        run.listener(config=SDKConfig(...))   # explicit config

    Args:
        func:          The function to decorate (when used without parentheses).
        config:        Optional pre-built configuration.
        status_mapper: Optional mapping of exception types to
                       :class:`ExecutionStatus` values. When an uncaught
                       exception escapes the execution function and its type
                       matches a key (checked via ``isinstance``), the
                       execution is finished with the mapped status. Mapping
                       to ``COMPLETED`` suppresses the error and finishes
                       cleanly; any other status causes the execution to
                       finish with the error observation recorded.

    Returns:
        An :class:`ExecutionWrapper` instance wrapping *func*.
    """
    if func is not None:
        return ExecutionWrapper(func, config)

    def decorator(fn: Callable[P, R]) -> ExecutionWrapper[P, R]:
        return ExecutionWrapper(fn, config, status_mapper=status_mapper)

    return decorator
