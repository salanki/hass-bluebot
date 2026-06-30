"""Async client package for the Bluebot water-flow-meter cloud API."""

from .client import (
    API_KEY_HEADER,
    BASE_URL,
    LATEST_BATCH_SIZE,
    BluebotClient,
    normalize_api_key,
)
from .exceptions import BluebotAuthError, BluebotConnectionError, BluebotError
from .models import Device, DeviceState, LatestDatapoint
from .util import parse_timestamp, to_bool, to_float

__all__ = [
    "API_KEY_HEADER",
    "BASE_URL",
    "LATEST_BATCH_SIZE",
    "BluebotAuthError",
    "BluebotClient",
    "BluebotConnectionError",
    "BluebotError",
    "Device",
    "DeviceState",
    "LatestDatapoint",
    "normalize_api_key",
    "parse_timestamp",
    "to_bool",
    "to_float",
]
