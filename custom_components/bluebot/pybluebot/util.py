"""Small parsing helpers shared by the client and models."""

from __future__ import annotations

from datetime import UTC, datetime


def to_float(value: object) -> float | None:
    """Coerce a JSON number/string to float, or None if not numeric."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def to_bool(value: object) -> bool | None:
    """Coerce common truthy/falsey JSON values to bool, or None if unknown."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return None


def parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp (e.g. ``2026-06-30T13:08:03.522Z``) to UTC.

    Returns None for missing or unparseable values rather than raising, so one
    malformed row never fails a whole poll.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
