"""The Bluebot water-flow-meter integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_FLOW_SCAN_INTERVAL,
    CONF_TOTALS_SCAN_INTERVAL,
    DEFAULT_FLOW_SCAN_INTERVAL,
    DEFAULT_TOTALS_SCAN_INTERVAL,
)
from .coordinator import BluebotFlowCoordinator, BluebotTotalsCoordinator
from .pybluebot import (
    BluebotAuthError,
    BluebotClient,
    BluebotConnectionError,
    BluebotError,
    Device,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


@dataclass
class BluebotRuntimeData:
    client: BluebotClient
    devices: list[Device]
    flow: BluebotFlowCoordinator
    totals: BluebotTotalsCoordinator


BluebotConfigEntry: TypeAlias = ConfigEntry[BluebotRuntimeData]


def _interval(entry: ConfigEntry, key: str, default: timedelta) -> timedelta:
    seconds = entry.options.get(key)
    return timedelta(seconds=seconds) if seconds else default


async def async_setup_entry(hass: HomeAssistant, entry: BluebotConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = BluebotClient(entry.data[CONF_API_KEY], session)

    try:
        all_devices = await client.async_get_devices()
    except BluebotAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (BluebotConnectionError, BluebotError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    devices = [d for d in all_devices if d.is_meter]
    if not devices:
        _LOGGER.warning("Bluebot account has no active flow meters")

    flow = BluebotFlowCoordinator(
        hass, entry, client, devices,
        _interval(entry, CONF_FLOW_SCAN_INTERVAL, DEFAULT_FLOW_SCAN_INTERVAL),
    )
    totals = BluebotTotalsCoordinator(
        hass, entry, client, devices,
        _interval(entry, CONF_TOTALS_SCAN_INTERVAL, DEFAULT_TOTALS_SCAN_INTERVAL),
    )
    await flow.async_config_entry_first_refresh()
    await totals.async_config_entry_first_refresh()

    entry.runtime_data = BluebotRuntimeData(
        client=client, devices=devices, flow=flow, totals=totals
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BluebotConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: BluebotConfigEntry
) -> None:
    """Reload when options (scan intervals) change."""
    await hass.config_entries.async_reload(entry.entry_id)
