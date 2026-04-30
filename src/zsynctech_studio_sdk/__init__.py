"""
ZSyncTech Studio SDK
====================

Python SDK for building robots that integrate with the ZSyncTech Studio
automation platform via its REST API.

Quickstart::

    from zsynctech_studio_sdk import task, execution
    from zsynctech_studio_sdk.config import SDKConfig

    @task
    def fetch_data():
        ...

    @task(name="Process records")
    def process():
        ...

    @execution
    def run():
        fetch_data()
        process()

    if __name__ == "__main__":
        run.listener()                        # reads API_TOKEN, INSTANCE_ID from env
        # or:
        run.listener(config=SDKConfig(...))   # explicit config

Advanced usage::

    from zsynctech_studio_sdk.services import ExecutionService, TaskService
    from zsynctech_studio_sdk.http import HttpClient
    from zsynctech_studio_sdk.models import ExecutionStatus, TaskStatus

    with HttpClient("http://localhost:3000", "zst_token") as http:
        svc = ExecutionService(http)
        executions = svc.list(status=ExecutionStatus.RUNNING)
"""

from .config import SDKConfig
from .context import ExecutionContext, get_current_context
from .decorators import ExecutionWrapper, TaskWrapper, execution, task
from .exceptions import (
    ApiError,
    AuthenticationError,
    ConfigurationError,
    ExecutionError,
    NotFoundError,
    SDKError,
    TaskError,
)
from .http import HttpClient
from .models import ExecutionStatus, TaskStatus
from .runner import RobotRunner
from .services import ExecutionService, TaskService

__all__ = [
    # Decorators
    "task",
    "execution",
    "TaskWrapper",
    "ExecutionWrapper",
    # Runner
    "RobotRunner",
    # HTTP
    "HttpClient",
    # Services
    "ExecutionService",
    "TaskService",
    # Config
    "SDKConfig",
    # Context
    "ExecutionContext",
    "get_current_context",
    # Models / Enums
    "TaskStatus",
    "ExecutionStatus",
    # Exceptions
    "SDKError",
    "ConfigurationError",
    "AuthenticationError",
    "NotFoundError",
    "ApiError",
    "ExecutionError",
    "TaskError",
]

