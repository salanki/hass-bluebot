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
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
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

    async def _async_update_data(self) -> dict[str, LatestDatapoint | None]:
        try:
            return await self.client.async_get_latest(self._device_ids)
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
