"""Diagnostics support for the LG Heat Pump integration."""

from typing import Any

from modbus_connection import ModbusError

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import LgHeatPumpConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LgHeatPumpConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = entry.runtime_data
    device = runtime_data.device
    # Taken before the raw dump, whose own requests would otherwise fill it.
    journal = runtime_data.journal.as_dict()
    try:
        raw: dict[str, Any] | str = await device.async_read_raw()
    except ModbusError as err:
        raw = f"unavailable: {err}"

    return async_redact_data(
        {
            "config": dict(entry.data),
            "model": device.model.key,
            "excluded_datapoints": sorted(device.excluded_datapoints),
            "readings": {
                "updated": runtime_data.readings.data.updated,
                "failed": sorted(runtime_data.readings.data.failed),
            },
            "settings": {
                "updated": runtime_data.settings.data.updated,
                "failed": sorted(runtime_data.settings.data.failed),
            },
            "values": {
                name: getattr(device, name).values() for name in device.component_names
            },
            "raw": raw,
            "journal": journal,
        },
        TO_REDACT,
    )
