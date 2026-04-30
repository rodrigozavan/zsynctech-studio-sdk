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

from zsynctech_studio_sdk import execution, task
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


@task(name="Gravar resultados")
def save_results() -> None:
    """Simulate persisting the processed data."""
    time.sleep(0.3)


@execution
def my_execution() -> None:
    """Full robot execution: initialize → fetch → process → save."""
    initialize()
    fetch_data()
    process_data()
    save_results()


if __name__ == "__main__":
    my_execution.listener(
        config=SDKConfig(
            api_token="zst_CQwafL3MEnFBeucoKe0pGlNte-PZ3vC5hUOjp3cueNk",
            instance_id="019de071-a3d4-7fc5-99e2-db357e6d8240",
            poll_interval=5.0,
        )
    )
