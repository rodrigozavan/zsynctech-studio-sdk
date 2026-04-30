"""
Low-level HTTP client for the ZSyncTech Studio platform.

Wraps ``httpx.Client`` with:
- Automatic ``Authorization: Bearer`` header injection.
- JSON response deserialisation.
- Platform error translation into SDK-specific exceptions.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..exceptions import ApiError, AuthenticationError, NotFoundError

logger = logging.getLogger(__name__)

# Default timeout for all requests (seconds).
_DEFAULT_TIMEOUT = 30.0


class HttpClient:
    """Synchronous HTTP client pre-configured for the ZSyncTech platform API.

    All requests are sent with an ``Authorization: Bearer <token>`` header.
    HTTP error responses are translated into typed SDK exceptions before they
    propagate to the caller.

    Args:
        base_url:  Root URL of the platform API (e.g. ``http://localhost:3000``).
        api_token: Robot API token issued by the platform (``zst_...``).
        timeout:   Request timeout in seconds. Defaults to 30.

    Example::

        client = HttpClient("http://localhost:3000", "zst_abc123")
        data = client.get("/executions/pending/some-uuid")
        client.close()
    """

    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    # -- Public interface ------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform a GET request and return the decoded JSON body.

        Args:
            path:   Path relative to the base URL (e.g. ``/executions``).
            params: Optional query string parameters.

        Returns:
            Decoded JSON response body (``dict``, ``list``, or ``None``).

        Raises:
            AuthenticationError: On 401 responses.
            NotFoundError:       On 404 responses.
            ApiError:            On any other 4xx/5xx response.
        """
        response = self._client.get(path, params=params)
        return self._handle(response)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Perform a POST request and return the decoded JSON body.

        Args:
            path: Path relative to the base URL.
            body: Optional JSON payload.

        Returns:
            Decoded JSON response body.

        Raises:
            AuthenticationError: On 401 responses.
            NotFoundError:       On 404 responses.
            ApiError:            On any other 4xx/5xx response.
        """
        response = self._client.post(path, json=body)
        return self._handle(response)

    def put(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Perform a PUT request and return the decoded JSON body.

        Args:
            path: Path relative to the base URL.
            body: Optional JSON payload.

        Returns:
            Decoded JSON response body.

        Raises:
            AuthenticationError: On 401 responses.
            NotFoundError:       On 404 responses.
            ApiError:            On any other 4xx/5xx response.
        """
        response = self._client.put(path, json=body)
        return self._handle(response)

    def close(self) -> None:
        """Release the underlying ``httpx`` connection pool."""
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # -- Internal helpers ------------------------------------------------------

    @staticmethod
    def _handle(response: httpx.Response) -> Any:
        """Validate *response* and return its JSON body.

        Translates HTTP error status codes into typed SDK exceptions.

        Args:
            response: The ``httpx`` response to inspect.

        Returns:
            Parsed JSON body, or ``None`` for empty 2xx responses.

        Raises:
            AuthenticationError: On 401.
            NotFoundError:       On 404.
            ApiError:            On any other non-2xx status.
        """
        logger.debug("%s %s -> %d", response.request.method, response.request.url, response.status_code)

        if response.status_code == 401:
            raise AuthenticationError(
                "Authentication failed. Check that your API token is valid and has not expired."
            )

        if response.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {response.request.method} {response.request.url}"
            )

        if response.status_code >= 400:
            detail = _extract_error_detail(response)
            raise ApiError(
                f"API error {response.status_code}: {detail}",
                status_code=response.status_code,
                detail=detail,
            )

        if not response.content:
            return None

        return response.json()


def _extract_error_detail(response: httpx.Response) -> str:
    """Extract a human-readable error message from an HTTP error response.

    Args:
        response: The failed HTTP response.

    Returns:
        A string error message, falling back to the raw response text.
    """
    try:
        body = response.json()
        return str(body.get("message", body))
    except Exception:
        return response.text or "unknown error"
