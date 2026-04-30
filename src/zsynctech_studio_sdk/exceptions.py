"""
Custom exceptions for the ZSyncTech Studio SDK.

Exception hierarchy::

    SDKError
    ├-- ConfigurationError   - invalid or missing configuration
    ├-- AuthenticationError  - API token rejected by the platform
    ├-- NotFoundError        - requested resource does not exist
    ├-- ApiError             - generic HTTP 4xx/5xx from the platform
    ├-- TaskError            - task register/update operation failed
    └-- ExecutionError       - execution lifecycle operation failed
"""

from __future__ import annotations


class SDKError(Exception):
    """Base class for all ZSyncTech SDK exceptions."""


class ConfigurationError(SDKError):
    """Raised when SDK configuration is invalid or missing.

    Args:
        message: Human-readable description of the missing/invalid field.
    """


class AuthenticationError(SDKError):
    """Raised when the platform rejects the API token (HTTP 401).

    Check that the token is valid and has not been revoked.
    """


class NotFoundError(SDKError):
    """Raised when the requested resource does not exist (HTTP 404).

    Args:
        message: Describes which resource was not found.
    """


class ApiError(SDKError):
    """Raised for unexpected HTTP 4xx/5xx responses from the platform.

    Attributes:
        status_code: The HTTP status code returned by the platform.
        detail:      Error message extracted from the response body.
    """

    def __init__(self, message: str, status_code: int, detail: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class TaskError(SDKError):
    """Raised when a task register or update operation fails at the SDK level."""


class ExecutionError(SDKError):
    """Raised when an execution lifecycle operation fails at the SDK level."""
