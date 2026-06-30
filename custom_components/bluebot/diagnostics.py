"""Diagnostics for the Bluebot integration (with secrets redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import BluebotConfigEntry
from .const import CONF_API_KEY

TO_REDACT = {CONF_API_KEY, "serial_number", "serialNumber", "networkUniqueIdentifier"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BluebotConfigEntry
) -> dict[str, Any]:
    data = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "unique_id": entry.unique_id,
        },
        "devices": [
            async_redact_data(
                {
                    "id": d.id,
                    "serial_number": d.serial_number,
                    "label": d.label,
                    "model": d.model,
                    "category": d.category,
                    "active": d.active,
                },
                TO_REDACT,
            )
            for d in data.devices
        ],
        "flow_last_update_success": data.flow.last_update_success,
        "totals_last_update_success": data.totals.last_update_success,
        "totals": data.totals.data,
    }
