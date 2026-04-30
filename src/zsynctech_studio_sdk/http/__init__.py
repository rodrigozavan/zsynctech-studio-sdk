"""
HTTP package for the ZSyncTech Studio SDK.

Provides the low-level :class:`HttpClient` that wraps ``httpx`` and handles
authentication, error translation, and JSON serialisation.
"""

from .client import HttpClient

__all__ = ["HttpClient"]
