"""Diagnostics support for the LG Heat Pump integration."""

from typing import Any

from modbus_connection import ModbusError

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import LgHeatPumpConfigEntry

TO_REDACT = {CONF_HOST}


def _scrub(value: Any, host: str) -> Any:
    """Return ``value`` with the gateway's address replaced in every string.

    ``async_redact_data`` only blanks values by key. The address also turns up
    inside error texts ("could not connect to <host>:<port>"), which the journal
    keeps for hours and the raw dump carries when the link is down.
    """
    if isinstance(value, str):
        return value.replace(host, REDACTED)
    if isinstance(value, dict):
        return {key: _scrub(item, host) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, host) for item in value]
    return value


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

    diagnostics = async_redact_data(
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
    host = entry.data.get(CONF_HOST)
    return _scrub(diagnostics, host) if host else diagnostics
