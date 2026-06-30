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

from .const import DOMAIN
from .pybluebot import (
    BluebotAuthError,
    BluebotClient,
    BluebotConnectionError,
    BluebotError,
    Device,
    LatestDatapoint,
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


class BluebotTotalsCoordinator(DataUpdateCoordinator[dict[str, float | None]]):
    """Polls cumulative lifetime volume per meter (sequentially)."""

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
        self._device_ids = [d.id for d in devices]
        # Previous totals, so a transient per-meter failure or a cloud recompute
        # doesn't drop the sensor to None / a misleading value.
        self._last: dict[str, float | None] = {}

    async def _async_update_data(self) -> dict[str, float | None]:
        totals: dict[str, float | None] = dict(self._last)
        errors = 0
        for device_id in self._device_ids:
            try:
                value = await self.client.async_get_total_volume(device_id)
            except BluebotAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (BluebotConnectionError, BluebotError) as err:
                errors += 1
                _LOGGER.debug("total volume fetch failed for %s: %s", device_id, err)
                continue
            previous = self._last.get(device_id)
            if (
                value is not None
                and previous is not None
                and value < previous - 1.0
            ):
                _LOGGER.warning(
                    "Bluebot meter %s total volume dropped %.1f -> %.1f gal "
                    "(meter replacement or cloud recompute?)",
                    device_id,
                    previous,
                    value,
                )
            if value is not None:
                totals[device_id] = value
        if errors == len(self._device_ids) and self._device_ids:
            raise UpdateFailed("all total-volume requests failed")
        self._last = totals
        return totals
