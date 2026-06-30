"""Shared test fixtures: fakes for the client and its HTTP session."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pybluebot import Device, LatestDatapoint


def make_device(
    device_id: str = "dev-1",
    serial: str = "BB0001",
    label: str | None = "Pool HX",
    *,
    category: str = "EndDevice",
    active: bool = True,
) -> Device:
    return Device(
        id=device_id,
        serial_number=serial,
        label=label,
        model="100-W",
        category=category,
        active=active,
        organization_id="org-1",
        network_unique_identifier=serial,
        timezone="America/New_York",
    )


def make_datapoint(
    *,
    age_seconds: float = 0.0,
    flow_rate: float = 6.5,
    quality: float = 99.0,
) -> LatestDatapoint:
    recorded = dt_util.utcnow() - timedelta(seconds=age_seconds)
    return LatestDatapoint(
        recorded_at=recorded,
        flow_rate=flow_rate,
        flow_amount=0.2,
        flow_duration=1800.0,
        quality=quality,
        signal_strength=80.0,
        network_rssi=-57.0,
        onboard_temperature=None,
    )


class FakeClient:
    """In-memory stand-in for ``BluebotClient`` used in HA-level tests."""

    def __init__(
        self,
        devices: list[Device] | None = None,
        latest: dict[str, LatestDatapoint | None] | None = None,
        totals: dict[str, float | None] | None = None,
    ) -> None:
        self.devices = devices if devices is not None else [make_device()]
        self.latest = latest if latest is not None else {}
        self.totals = totals if totals is not None else {}

    async def async_validate(self) -> str:
        return "org-1"

    async def async_get_devices(self) -> list[Device]:
        return list(self.devices)

    async def async_get_latest(self, ids):
        return {i: self.latest.get(i) for i in ids}

    async def async_get_total_volume(self, device_id: str):
        return self.totals.get(device_id)


class FakeResponse:
    def __init__(self, status: int, payload=None, text: str = "") -> None:
        self.status = status
        self._payload = payload
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class FakeSession:
    """Minimal aiohttp.ClientSession stand-in for client unit tests.

    ``handler(url, params, headers)`` returns a ``FakeResponse``. Captured calls
    are recorded in ``self.calls`` for assertions.
    """

    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self._handler(url, params, headers)
