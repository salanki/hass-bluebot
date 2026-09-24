"""Cloud connectivity and water-flow binary sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BluebotConfigEntry
from .const import CLOUD_OFFLINE_AFTER, FLOW_EPSILON
from .coordinator import BluebotFlowCoordinator
from .entity import BluebotEntity, BluebotLiveEntity
from .pybluebot import Device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BluebotConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities(
        entity
        for device in data.devices
        for entity in (
            BluebotOnlineBinarySensor(data.flow, device),
            BluebotFlowingBinarySensor(data.flow, device),
        )
    )


class BluebotOnlineBinarySensor(BluebotEntity, BinarySensorEntity):
    """FloDash cloud reporting status, not local network reachability."""

    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BluebotFlowCoordinator, device: Device) -> None:
        super().__init__(coordinator, device, "online")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.is_online(self._device.id)

    @property
    def extra_state_attributes(self):
        dp = (self.coordinator.data or {}).get(self._device.id)
        return {
            "last_datapoint": dp.recorded_at.isoformat()
            if dp is not None and dp.recorded_at is not None
            else None,
            "offline_after_seconds": int(CLOUD_OFFLINE_AFTER.total_seconds()),
        }


class BluebotFlowingBinarySensor(BluebotLiveEntity, BinarySensorEntity):
    """On while water is actively flowing through the meter."""

    _attr_translation_key = "flowing"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: BluebotFlowCoordinator, device: Device) -> None:
        super().__init__(coordinator, device, "flowing")

    @property
    def is_on(self) -> bool | None:
        datapoint = (self.coordinator.data or {}).get(self._device.id)
        if datapoint is None or datapoint.recorded_at is None:
            return None
        return (
            datapoint.flow_rate > FLOW_EPSILON
            if datapoint.flow_rate is not None
            else None
        )
