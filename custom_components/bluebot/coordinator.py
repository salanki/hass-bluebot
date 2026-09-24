"""Polling coordinators for the Bluebot integration.

Two coordinators with different cadences share one client:

* :class:`BluebotFlowCoordinator` — fast (~30 s). A single ``/flow/latest`` call
  returns the latest datapoint for *all* meters, so real-time flow stays cheap.
* :class:`BluebotTotalsCoordinator` — slow (~5 min). Cumulative lifetime volume
  is one ``resolution=total`` call per meter; requests are issued sequentially
  to avoid bursting the cloud API.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CLOUD_OFFLINE_AFTER, DOMAIN
from .pybluebot import (
    BluebotAuthError,
    BluebotClient,
    BluebotConnectionError,
    BluebotError,
    Device,
    LatestDatapoint,
    MeterTotals,
)

_LOGGER = logging.getLogger(__name__)


class BluebotFlowCoordinator(DataUpdateCoordinator[dict[str, LatestDatapoint | None]]):
    """Polls the latest datapoint for every meter in one request."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BluebotClient,
        devices: list[Device],
        interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_flow",
            update_interval=interval,
            always_update=False,
        )
        self.client = client
        self._device_ids = [d.id for d in devices]
        self._cancel_expiry: Callable[[], None] | None = None
        entry.async_on_unload(self._async_cancel_expiry)

    def is_online(self, device_id: str) -> bool | None:
        """Match FloDash's timestamp rule; no timestamp means unknown."""
        datapoint = (self.data or {}).get(device_id)
        if datapoint is None or datapoint.recorded_at is None:
            return None
        return dt_util.utcnow() - datapoint.recorded_at < CLOUD_OFFLINE_AFTER

    @callback
    def _async_cancel_expiry(self) -> None:
        if self._cancel_expiry is not None:
            self._cancel_expiry()
            self._cancel_expiry = None

    @callback
    def _async_schedule_expiry(
        self, data: dict[str, LatestDatapoint | None]
    ) -> None:
        """Expire cached readings even when successful polls return identical data."""
        self._async_cancel_expiry()
        now = dt_util.utcnow()
        deadlines = [
            dp.recorded_at + CLOUD_OFFLINE_AFTER
            for dp in data.values()
            if dp is not None
            and dp.recorded_at is not None
            and dp.recorded_at + CLOUD_OFFLINE_AFTER > now
        ]
        if deadlines:
            self._cancel_expiry = async_track_point_in_utc_time(
                self.hass, self._async_expire, min(deadlines)
            )

    @callback
    def _async_expire(self, _now: datetime) -> None:
        self._cancel_expiry = None
        self.async_update_listeners()
        self._async_schedule_expiry(self.data or {})

    async def _async_update_data(self) -> dict[str, LatestDatapoint | None]:
        try:
            data = await self.client.async_get_latest(self._device_ids)
            self._async_schedule_expiry(data)
            return data
        except BluebotAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (BluebotConnectionError, BluebotError) as err:
            raise UpdateFailed(str(err)) from err


class BluebotTotalsCoordinator(DataUpdateCoordinator[dict[str, MeterTotals]]):
    """Polls cumulative lifetime + today's volume per meter (sequentially).

    ``today`` comes from the server-side ``resolution=day`` rollup in each
    meter's own timezone — authoritative, resets at local midnight, and survives
    restarts (no HA-side metering needed).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BluebotClient,
        devices: list[Device],
        interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_totals",
            update_interval=interval,
            always_update=False,
        )
        self.client = client
        self._devices = devices
        # Previous values, so a transient per-meter failure or a cloud recompute
        # doesn't drop a sensor to None / a misleading value.
        self._last: dict[str, MeterTotals] = {}

    def _today_start_iso(self, device: Device) -> str:
        """Local-midnight-today ISO timestamp in the meter's timezone."""
        tz = dt_util.get_time_zone(device.timezone) if device.timezone else None
        now_local = dt_util.now(tz)
        start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.isoformat()

    async def _async_update_data(self) -> dict[str, MeterTotals]:
        result: dict[str, MeterTotals] = dict(self._last)
        errors = 0
        for device in self._devices:
            try:
                total = await self.client.async_get_total_volume(device.id)
                today = await self.client.async_get_today_volume(
                    device.id, device.timezone, self._today_start_iso(device)
                )
            except BluebotAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (BluebotConnectionError, BluebotError) as err:
                errors += 1
                _LOGGER.debug("totals fetch failed for %s: %s", device.id, err)
                continue
            previous = self._last.get(device.id)
            if (
                total is not None
                and previous is not None
                and previous.total is not None
                and total < previous.total - 1.0
            ):
                _LOGGER.warning(
                    "Bluebot meter %s total volume dropped %.1f -> %.1f gal "
                    "(meter replacement or cloud recompute?)",
                    device.id,
                    previous.total,
                    total,
                )
            result[device.id] = MeterTotals(total=total, today=today)
        if errors == len(self._devices) and self._devices:
            raise UpdateFailed("all totals requests failed")
        self._last = result
        return result
