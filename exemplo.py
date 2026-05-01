"""
exemplo.py — Example robot using the ZSyncTech Studio SDK.

This file demonstrates the two core decorators (@task and @execution) and
how to start the polling listener.

Environment variables required:
    API_TOKEN   — robot API token (zst_...)
    INSTANCE_ID — UUID of the registered robot instance
    BASE_URL    — platform URL (defaults to http://localhost:3000)
"""

import time

from zsynctech_studio_sdk import ExecutionStatus, TaskStatus, execution, task
from zsynctech_studio_sdk.config import SDKConfig


@task(name="Inicializar conexão")
def initialize() -> None:
    """Simulate an initialization step."""
    time.sleep(0.5)


@task(name="Buscar dados")
def fetch_data() -> None:
    """Simulate fetching data from a remote source."""
    time.sleep(1)


@task(name="Processar dados")
def process_data() -> None:
    """Simulate a data processing step."""
    time.sleep(0.8)


# RuntimeError is mapped to WARNING: the task finishes with WARNING status and
# the execution continues normally (exception is NOT re-raised).
@task(
    name="Gravar resultados",
    status_mapper={RuntimeError: TaskStatus.ERROR},
)
def save_results() -> None:
    """Simulate persisting the processed data."""
    time.sleep(0.3)


# If the execution function itself raises an unhandled exception, the mapper
# controls the final execution status.  Mapping to COMPLETED suppresses the
# error and finishes cleanly; any other status records the error observation.
@execution(
    status_mapper={
        RuntimeError: ExecutionStatus.FAILED,
    }
)
def my_execution() -> None:
    """Full robot execution: initialize → fetch → process → save."""
    initialize()
    fetch_data()
    process_data()
    save_results()

if __name__ == "__main__":
    my_execution.listener(
        config=SDKConfig(
            api_token="zst_wez2HUYi_gsIoE6Ra-7JqasNxEoyD3E8DiXCbzqtT-g",
            instance_id="019de071-a3d4-7fc5-99e2-db357e6d8240",
            poll_interval=5.0,
        )
    )
