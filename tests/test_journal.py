"""Tests for the journal that goes out with the diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from modbus_connection import IllegalDataAddressError, ModbusTimeoutError

from custom_components.lg_heatpump.const import DOMAIN
from custom_components.lg_heatpump.diagnostics import async_get_config_entry_diagnostics
from custom_components.lg_heatpump.journal import Journal
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID

from . import MOCK_UNIT_ID

if TYPE_CHECKING:
    from modbus_connection.mock import MockModbusConnection
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

SHIFT = "number.lg_therma_v_circuit_1_setpoint_shift"


async def _journal(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    return (await async_get_config_entry_diagnostics(hass, entry))["journal"]


async def _poll_readings(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.readings.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)


def _events(journal: dict, kind: str) -> list[dict]:
    return [e for e in journal["events"] if e["event"] == kind]


async def test_the_setup_polls_and_requests_are_recorded(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Every request and both first polls are in the download, with durations."""
    journal = await _journal(hass, init_integration)

    assert [e["event"] for e in journal["events"]] == ["setup"]
    assert [p["table"] for p in journal["polls"]] == ["readings", "settings"]
    readings = journal["polls"][0]
    assert "sensors" in readings["updated"]
    assert "failed" not in readings
    assert isinstance(readings["ms"], int)
    assert journal["requests"]
    assert {r["outcome"] for r in journal["requests"]} == {"ok"}
    first = journal["requests"][0]
    assert first["request"].startswith("read_")
    assert {"time", "address", "count", "ms"} <= first.keys()


async def test_a_failing_and_recovering_subsystem_is_kept_as_events(
    hass: HomeAssistant,
    mock_connection: MockModbusConnection,
    init_integration: MockConfigEntry,
) -> None:
    """A refused block shows in the poll line and once as failed, then recovered."""
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    unit.fail_read(0, IllegalDataAddressError(), register_type="discrete_input")
    await _poll_readings(hass, init_integration)
    await _poll_readings(hass, init_integration)
    unit.fail_read(0, None, register_type="discrete_input")
    await _poll_readings(hass, init_integration)

    journal = await _journal(hass, init_integration)
    failed_polls = [p for p in journal["polls"] if "failed" in p]
    assert len(failed_polls) == 2
    assert failed_polls[0]["failed"]["states"].startswith("IllegalDataAddressError")
    assert [e["component"] for e in _events(journal, "failed")] == ["states"]
    assert _events(journal, "recovered") == [
        {**_events(journal, "recovered")[0], "component": "states", "after": 2}
    ]
    refused = [r for r in journal["requests"] if r["outcome"] != "ok"]
    assert refused
    assert refused[0]["request"] == "read_discrete_inputs"


async def test_a_silent_unit_shows_as_timeouts_and_a_link_error(
    hass: HomeAssistant,
    mock_connection: MockModbusConnection,
    init_integration: MockConfigEntry,
) -> None:
    """A poll nothing answered is a poll line with the error, and events."""
    mock_connection.for_unit(MOCK_UNIT_ID).fail_requests(ModbusTimeoutError("silent"))
    await _poll_readings(hass, init_integration)

    journal = await _journal(hass, init_integration)
    assert journal["polls"][-1]["error"] == "ModbusTimeoutError: silent"
    assert _events(journal, "timeout")
    assert _events(journal, "link_error")[0]["table"] == "readings"


async def test_a_write_is_kept_with_its_value(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Writes go into the requests and, being rare, into the events."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: SHIFT, ATTR_VALUE: -4},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    journal = await _journal(hass, init_integration)
    writes = _events(journal, "write")
    assert len(writes) == 1
    assert writes[0]["address"] == 4
    assert writes[0]["value"] == 0x10000 - 4
    assert writes[0]["outcome"] == "ok"
    assert any(r["request"].startswith("write_") for r in journal["requests"])


async def test_the_journal_survives_a_reload_and_goes_with_the_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A reload keeps what led to it; removing the entry drops it."""
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    journal = await _journal(hass, init_integration)
    assert [e["event"] for e in journal["events"]] == ["setup", "setup"]
    assert len(journal["polls"]) == 4

    await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert init_integration.entry_id not in hass.data.get(DOMAIN, {}).get("journal", {})


def test_the_buffers_are_bounded() -> None:
    """Old lines fall out; the journal never grows past its limits."""
    journal = Journal()
    for n in range(journal.events.maxlen + 5):
        journal.event("write", n=n)

    assert len(journal.events) == journal.events.maxlen
    assert journal.events[0]["n"] == 5
    assert journal.requests.maxlen == 2000
    assert journal.polls.maxlen == 1000
