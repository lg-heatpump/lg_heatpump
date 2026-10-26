"""The LG Heat Pump custom integration.

Reads and controls LG heat pumps (Therma V and siblings) over Modbus TCP,
backed by the vendored ``lg_heatpump_modbus`` device library.

For more details, see https://github.com/lg-heatpump/lg_heatpump
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import Platform

from .connection import create_modbus_params
from .const import (
    CONF_DEBUG,
    CONF_MODEL,
    CONF_UNIT_ID,
    SCAN_INTERVAL,
    SETTINGS_SCAN_INTERVAL,
)
from .coordinator import LgHeatPumpCoordinator, LgHeatPumpRuntimeData
from .lg_heatpump_modbus import LgHeatPump

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import LgHeatPumpConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LgHeatPumpConfigEntry,
) -> bool:
    """Set up an LG heat pump from a config entry."""
    unit = async_get_unit(
        hass,
        entry,
        create_modbus_params(entry.data),
        entry.data[CONF_UNIT_ID],
    )
    device = LgHeatPump(
        unit,
        model=entry.data[CONF_MODEL],
        debug=entry.data.get(CONF_DEBUG, False),
    )

    readings = LgHeatPumpCoordinator(
        hass, entry, device, device.async_update_readings, SCAN_INTERVAL
    )
    settings = LgHeatPumpCoordinator(
        hass, entry, device, device.async_update_settings, SETTINGS_SCAN_INTERVAL
    )

    await readings.async_config_entry_first_refresh()
    await settings.async_config_entry_first_refresh()

    entry.runtime_data = LgHeatPumpRuntimeData(device, readings, settings)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: LgHeatPumpConfigEntry,
) -> bool:
    """Unload a config entry; the shared connection closes with its last holder."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
