"""Sensors for Bluebot meters: flow rate, cumulative volume, diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import BluebotConfigEntry
from .const import FRESHNESS_POLL_FACTOR, MIN_FRESHNESS
from .coordinator import BluebotFlowCoordinator, BluebotTotalsCoordinator
from .entity import BluebotEntity
from .pybluebot import Device, LatestDatapoint


@dataclass(frozen=True, kw_only=True)
class BluebotDiagDescription(SensorEntityDescription):
    """Diagnostic sensor backed by a field of the latest datapoint."""

    value_fn: Callable[[LatestDatapoint], float | datetime | None]


DIAG_SENSORS: tuple[BluebotDiagDescription, ...] = (
    BluebotDiagDescription(
        key="quality",
        translation_key="quality",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dp: dp.quality,
    ),
    BluebotDiagDescription(
        key="signal_strength",
        translation_key="signal_strength",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda dp: dp.signal_strength,
    ),
    BluebotDiagDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda dp: dp.network_rssi,
    ),
    BluebotDiagDescription(
        key="last_datapoint",
        translation_key="last_datapoint",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dp: dp.recorded_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BluebotConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    entities: list[SensorEntity] = []
    for device in data.devices:
        entities.append(BluebotFlowRateSensor(data.flow, device))
        entities.append(BluebotTotalVolumeSensor(data.totals, device))
        entities.append(BluebotTodayVolumeSensor(data.totals, device))
        entities.extend(
            BluebotDiagSensor(data.flow, device, desc) for desc in DIAG_SENSORS
        )
    async_add_entities(entities)


class BluebotFlowRateSensor(BluebotEntity, SensorEntity):
    """Real-time flow rate in gallons/minute.

    Reports the latest datapoint's rate while it is fresh; once the newest
    datapoint ages past the freshness window the meter is idle, so the value is
    0. On a failed poll the entity goes unavailable (handled by the coordinator)
    rather than publishing a misleading 0.
    """

    _attr_translation_key = "flow_rate"
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.GALLONS_PER_MINUTE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BluebotFlowCoordinator, device: Device) -> None:
        super().__init__(coordinator, device, "flow_rate")

    @property
    def _freshness(self):
        interval = self.coordinator.update_interval or MIN_FRESHNESS
        return max(MIN_FRESHNESS, FRESHNESS_POLL_FACTOR * interval)

    @property
    def native_value(self) -> float | None:
        datapoint = (self.coordinator.data or {}).get(self._device.id)
        if datapoint is None or datapoint.recorded_at is None:
            return None
        age = dt_util.utcnow() - datapoint.recorded_at
        if age > self._freshness:
            return 0.0
        return datapoint.flow_rate


class BluebotTotalVolumeSensor(BluebotEntity, SensorEntity):
    """Lifetime cumulative volume — feeds HA water statistics."""

    _attr_translation_key = "total_volume"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BluebotTotalsCoordinator, device: Device) -> None:
        super().__init__(coordinator, device, "total_volume")

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> float | None:
        totals = (self.coordinator.data or {}).get(self._device.id)
        return totals.total if totals else None


class BluebotTodayVolumeSensor(BluebotEntity, SensorEntity):
    """Gallons used since local midnight — the meter's own daily rollup.

    Sourced from the Bluebot ``resolution=day`` API in the meter's timezone, so
    it matches Bluebot's app, resets at local midnight, and survives restarts.
    """

    _attr_translation_key = "today_volume"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BluebotTotalsCoordinator, device: Device) -> None:
        super().__init__(coordinator, device, "today_volume")

    @property
    def native_value(self) -> float | None:
        totals = (self.coordinator.data or {}).get(self._device.id)
        return totals.today if totals else None


class BluebotDiagSensor(BluebotEntity, SensorEntity):
    """Diagnostic value from the latest datapoint (quality/signal/rssi/time)."""

    entity_description: BluebotDiagDescription

    def __init__(
        self,
        coordinator: BluebotFlowCoordinator,
        device: Device,
        description: BluebotDiagDescription,
    ) -> None:
        super().__init__(coordinator, device, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | datetime | None:
        datapoint = (self.coordinator.data or {}).get(self._device.id)
        if datapoint is None:
            return None
        return self.entity_description.value_fn(datapoint)
