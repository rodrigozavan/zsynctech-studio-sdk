"""
SDK configuration model.

Settings are loaded from environment variables by default.
They can also be supplied programmatically for testing or advanced scenarios.
"""

from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field, field_validator

from .exceptions import ConfigurationError

# Environment variable names
_ENV_BASE_URL = "BASE_URL"
_ENV_API_TOKEN = "API_TOKEN"
_ENV_INSTANCE_ID = "INSTANCE_ID"

# Suffix that must be present at the end of base_url (no trailing slash).
_API_SUFFIX = "/api/v1"
_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def _normalize_base_url(value: str) -> str:
    """Return a canonical API base URL.

    Normalisation steps applied in order:
    1. Strip surrounding whitespace.
    2. Remove one or more trailing slashes.
    3. Collapse any ``//`` sequences inside the path (after the scheme).
    4. Ensure the URL ends with ``/api/v1`` (appended if absent).
    5. Validate that the result looks like a valid HTTP/HTTPS URL.

    Args:
        value: Raw URL string supplied by the caller.

    Returns:
        Normalised URL string always ending with ``/api/v1``.

    Raises:
        ValueError: If the resulting URL is not a valid HTTP/HTTPS URL.
    """
    url = value.strip().rstrip("/")

    # Collapse accidental double-slashes in the path (preserving scheme://)
    scheme, _, rest = url.partition("://")
    rest = re.sub(r"/+", "/", rest)
    url = f"{scheme}://{rest}"

    # Append /api/v1 only when not already present
    if not url.endswith(_API_SUFFIX):
        url = url + _API_SUFFIX

    if not _URL_RE.match(url):
        raise ValueError(
            f"Invalid base_url {value!r}. "
            "Expected a valid HTTP or HTTPS URL, e.g. 'http://localhost:3000'."
        )

    return url


class SDKConfig(BaseModel):
    """Immutable configuration for a ZSyncTech SDK robot session.

    Attributes:
        base_url:      Root URL of the ZSyncTech platform server. Accepts the
                       bare server URL (e.g. ``http://localhost:3000``) or the
                       full versioned path (``http://localhost:3000/api/v1``).
                       Trailing slashes, duplicate slashes, and a missing
                       ``/api/v1`` suffix are all handled automatically.
        api_token:     Robot API token issued by the platform (``zst_...``).
        instance_id:   UUID of the robot instance registered in the platform.
        poll_interval: Seconds between polling attempts for pending executions.
                       Defaults to 5 seconds.
    """

    base_url: str = Field(
        default="http://localhost:3000",
        validate_default=True,
        description="ZSyncTech platform server URL. /api/v1 is appended automatically if absent.",
    )
    api_token: str = Field(
        description="Robot API token (zst_...).",
    )
    instance_id: str = Field(
        description="UUID of the robot instance.",
    )
    poll_interval: float = Field(
        default=5.0,
        ge=1.0,
        description="Seconds between polls for pending executions.",
    )

    @field_validator("base_url", mode="before")
    @classmethod
    def normalise_base_url(cls, value: object) -> str:
        """Normalise and validate the platform base URL.

        Ensures the URL:
        - Has no trailing slashes
        - Has no duplicate slashes in the path
        - Ends with ``/api/v1``
        - Is a valid HTTP or HTTPS address
        """
        if not isinstance(value, str):
            raise ValueError("base_url must be a string.")
        return _normalize_base_url(value)

    # -- Factory ---------------------------------------------------------------

    @classmethod
    def from_env(cls) -> SDKConfig:
        """Build configuration from environment variables.

        Required variables:
            ``API_TOKEN``    - robot API token issued by the platform.
            ``INSTANCE_ID``  - UUID of the registered robot instance.

        Optional variables:
            ``BASE_URL``     - server root URL; defaults to
                               ``http://localhost:3000``. The ``/api/v1``
                               prefix is appended automatically.

        Returns:
            A fully validated :class:`SDKConfig` instance.

        Raises:
            ConfigurationError: If a required variable is absent or empty.
        """
        api_token = os.environ.get(_ENV_API_TOKEN, "").strip()
        instance_id = os.environ.get(_ENV_INSTANCE_ID, "").strip()

        if not api_token:
            raise ConfigurationError(
                f"The {_ENV_API_TOKEN!r} environment variable is required. "
                "Generate a robot token in the ZSyncTech Studio dashboard."
            )
        if not instance_id:
            raise ConfigurationError(
                f"The {_ENV_INSTANCE_ID!r} environment variable is required. "
                "Find the instance UUID in the ZSyncTech Studio dashboard."
            )

        return cls(
            base_url=os.environ.get(_ENV_BASE_URL, "http://localhost:3000").strip(),
            api_token=api_token,
            instance_id=instance_id,
        )
