"""Exceptions for the Bluebot cloud client."""

from __future__ import annotations


class BluebotError(Exception):
    """Base error for all Bluebot client failures."""


class BluebotConnectionError(BluebotError):
    """Raised on transport failures and retryable server responses.

    Covers timeouts, connection drops, HTTP 429 (rate limited) and 5xx — i.e.
    conditions that may succeed on a later poll, so the coordinator should keep
    the previous data and mark entities unavailable rather than treat them as
    fatal.
    """


class BluebotAuthError(BluebotError):
    """Raised when the API key is rejected (HTTP 401 / 403).

    The integration maps this to ``ConfigEntryAuthFailed`` so Home Assistant
    starts the reauth flow.
    """
