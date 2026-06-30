"""Base entity wiring for Bluebot meters."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    BaseCoordinatorEntity,
    CoordinatorEntity,
)

from .const import DOMAIN, MANUFACTURER
from .pybluebot import Device


def device_info(device: Device) -> DeviceInfo:
    """HA device registry entry for a meter."""
    return DeviceInfo(
        identifiers={(DOMAIN, device.id)},
        name=device.name,
        manufacturer=MANUFACTURER,
        model=device.model,
        serial_number=device.serial_number,
    )


class BluebotEntity(CoordinatorEntity[BaseCoordinatorEntity]):
    """Common device + unique-id wiring for all Bluebot entities.

    ``unique_id`` is keyed on the meter serial (physically stable across
    re-provisioning), falling back to the device UUID.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, device: Device, key: str) -> None:
        super().__init__(coordinator)
        self._device = device
        base = device.serial_number or device.id
        self._attr_unique_id = f"{base}_{key}"
        self._attr_device_info = device_info(device)
