"""Binary sensor: whether a Bluebot meter is currently passing water."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import BluebotConfigEntry
from .const import FLOW_EPSILON, FRESHNESS_POLL_FACTOR, MIN_FRESHNESS
from .coordinator import BluebotFlowCoordinator
from .entity import BluebotEntity
from .pybluebot import Device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BluebotConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities(
        BluebotFlowingBinarySensor(data.flow, device) for device in data.devices
    )


class BluebotFlowingBinarySensor(BluebotEntity, BinarySensorEntity):
    """On while water is actively flowing through the meter."""

    _attr_translation_key = "flowing"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: BluebotFlowCoordinator, device: Device) -> None:
        super().__init__(coordinator, device, "flowing")

    @property
    def _freshness(self):
        interval = self.coordinator.update_interval or MIN_FRESHNESS
        return max(MIN_FRESHNESS, FRESHNESS_POLL_FACTOR * interval)

    @property
    def is_on(self) -> bool | None:
        datapoint = (self.coordinator.data or {}).get(self._device.id)
        if datapoint is None or datapoint.recorded_at is None:
            return None
        age = dt_util.utcnow() - datapoint.recorded_at
        if age > self._freshness:
            return False
        return (datapoint.flow_rate or 0.0) > FLOW_EPSILON
