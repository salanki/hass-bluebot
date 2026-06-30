"""Data models for the Bluebot cloud client.

Frozen dataclasses parsed from the REST JSON. Field names are normalised to
snake_case; the upstream API mixes snake_case (``/flow/datapoints``) and
camelCase (``/flow/latest``), so parsing is centralised here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .util import parse_timestamp, to_float


@dataclass(frozen=True)
class Device:
    """A Bluebot meter as returned by ``GET /device``."""

    id: str
    serial_number: str
    label: str | None
    model: str | None
    category: str | None
    active: bool
    organization_id: str | None
    network_unique_identifier: str | None
    timezone: str | None

    @property
    def name(self) -> str:
        """Human label, falling back to the serial number."""
        return self.label or self.serial_number

    @property
    def is_meter(self) -> bool:
        """True for installed end-meters that report flow.

        Filters out non-metering hardware (e.g. gateways) and inactive units so
        the integration only creates entities for things that produce data.
        """
        return self.active and (self.category or "EndDevice") == "EndDevice"

    @classmethod
    def from_json(cls, data: dict) -> Device:
        return cls(
            id=str(data["id"]),
            serial_number=str(data.get("serialNumber") or data["id"]),
            label=data.get("label"),
            model=data.get("model"),
            category=data.get("category"),
            active=bool(data.get("active", True)),
            organization_id=data.get("organizationId"),
            network_unique_identifier=data.get("networkUniqueIdentifier"),
            timezone=data.get("deviceTimeZone"),
        )


@dataclass(frozen=True)
class LatestDatapoint:
    """Most recent raw datapoint for a meter (from ``GET /flow/latest``).

    ``flow_rate`` is US gallons/minute, ``flow_amount`` is US gallons, and
    ``flow_duration`` is milliseconds. The meter only emits datapoints while
    water is moving, so a stale ``recorded_at`` means "no flow".
    """

    recorded_at: datetime | None
    flow_rate: float | None
    flow_amount: float | None
    flow_duration: float | None
    quality: float | None
    signal_strength: float | None
    network_rssi: float | None
    onboard_temperature: float | None

    @classmethod
    def from_json(cls, data: dict) -> LatestDatapoint:
        return cls(
            recorded_at=parse_timestamp(data.get("recordedAt")),
            flow_rate=to_float(data.get("flowRate")),
            flow_amount=to_float(data.get("flowAmount")),
            flow_duration=to_float(data.get("flowDuration")),
            quality=to_float(data.get("quality")),
            signal_strength=to_float(data.get("signalStrength")),
            network_rssi=to_float(data.get("networkRssi")),
            onboard_temperature=to_float(data.get("onboardTemperature")),
        )


@dataclass(frozen=True)
class DeviceState:
    """Per-meter snapshot the coordinators expose to entities.

    ``latest`` is the newest datapoint (may be None if the meter has never
    reported); ``total_volume`` is the lifetime cumulative gallons from
    ``resolution=total`` (filled by the totals coordinator, None until first
    fetched).
    """

    latest: LatestDatapoint | None = None
    total_volume: float | None = None


__all__ = ["Device", "LatestDatapoint", "DeviceState"]
