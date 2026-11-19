"""Tests for the journal that goes out with the diagnostics."""

from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING

from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusTimeoutError,
    ModbusUnit,
)
import pytest

from custom_components.lg_heatpump.const import DOMAIN
from custom_components.lg_heatpump.diagnostics import (
    _scrub,
    async_get_config_entry_diagnostics,
)
from custom_components.lg_heatpump.journal import (
    RECORDED_REQUESTS,
    UNRECORDED_REQUESTS,
    Journal,
    RecordingUnit,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID

from . import MOCK_HOST, MOCK_UNIT_ID

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


async def test_the_gateway_address_is_redacted_inside_error_texts(
    hass: HomeAssistant,
    mock_connection: MockModbusConnection,
    init_integration: MockConfigEntry,
) -> None:
    """A link error names the gateway; the download must not."""
    mock_connection.for_unit(MOCK_UNIT_ID).fail_requests(
        ModbusConnectionError(f"could not connect to {MOCK_HOST}:502")
    )
    await _poll_readings(hass, init_integration)

    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)
    assert MOCK_HOST not in json.dumps(diagnostics)
    assert diagnostics["journal"]["polls"][-1]["error"] == (
        "ModbusConnectionError: could not connect to **REDACTED**:502"
    )
    assert diagnostics["raw"] == ("unavailable: could not connect to **REDACTED**:502")


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


async def test_the_journal_belongs_to_the_loaded_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """It lives in the runtime data, so a reload starts it afresh."""
    before = init_integration.runtime_data.journal
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    journal = await _journal(hass, init_integration)
    assert init_integration.runtime_data.journal is not before
    assert [e["event"] for e in journal["events"]] == ["setup"]
    assert DOMAIN not in hass.data or "journal" not in hass.data[DOMAIN]


def test_the_buffers_are_bounded() -> None:
    """Old lines fall out; the journal never grows past its limits."""
    journal = Journal()
    for n in range(journal.events.maxlen + 5):
        journal.event("write", n=n)

    assert len(journal.events) == journal.events.maxlen
    assert journal.events[0]["n"] == 5
    assert journal.requests.maxlen == 2000
    assert journal.polls.maxlen == 1000


def test_every_request_of_the_protocol_is_either_recorded_or_passed_on() -> None:
    """A request added to ``ModbusUnit`` fails here instead of bypassing the journal."""
    protocol = {
        name
        for name, member in inspect.getmembers(ModbusUnit, inspect.isfunction)
        if name.startswith(("read_", "write_", "mask_write_"))
    }

    assert protocol == RECORDED_REQUESTS | UNRECORDED_REQUESTS
    assert not RECORDED_REQUESTS & UNRECORDED_REQUESTS
    for name in RECORDED_REQUESTS:
        assert name in vars(RecordingUnit), name
        assert inspect.signature(
            getattr(RecordingUnit, name), eval_str=True
        ) == inspect.signature(getattr(ModbusUnit, name), eval_str=True), name


async def test_a_request_records_only_its_own_fields(
    mock_connection: MockModbusConnection,
) -> None:
    """The fields are fixed per request; nothing can overwrite the journal's keys."""
    journal = Journal()
    unit = RecordingUnit(mock_connection.for_unit(MOCK_UNIT_ID), journal)

    await unit.read_holding_registers(0, 2)
    await unit.write_registers(0, [1, 2])

    read, write = journal.requests
    assert read.keys() == {"time", "request", "address", "count", "ms", "outcome"}
    assert (read["request"], read["address"], read["count"]) == (
        "read_holding_registers",
        0,
        2,
    )
    assert write.keys() == {"time", "request", "address", "values", "ms", "outcome"}
    assert write["values"] == [1, 2]
    assert [e["event"] for e in journal.events] == ["write"]


@pytest.mark.parametrize(
    ("request_name", "args", "fields"),
    [
        ("read_coils", (0, 2), {"address": 0, "count": 2}),
        ("read_discrete_inputs", (0, 2), {"address": 0, "count": 2}),
        ("read_holding_registers", (0, 2), {"address": 0, "count": 2}),
        ("read_input_registers", (0, 2), {"address": 0, "count": 2}),
        ("write_coil", (1, True), {"address": 1, "value": True}),
        ("write_coils", (0, [True, False]), {"address": 0, "values": [True, False]}),
        ("write_register", (4, 7), {"address": 4, "value": 7}),
        ("write_registers", (4, [7, 8]), {"address": 4, "values": [7, 8]}),
        (
            "mask_write_register",
            (4, 0xFF00, 0x0001),
            {"address": 4, "and_mask": 0xFF00, "or_mask": 0x0001},
        ),
    ],
)
async def test_each_recorded_request_keeps_its_fields(
    mock_connection: MockModbusConnection,
    request_name: str,
    args: tuple,
    fields: dict,
) -> None:
    """Every recorded request reaches the unit and leaves one line with its fields."""
    journal = Journal()
    unit = RecordingUnit(mock_connection.for_unit(MOCK_UNIT_ID), journal)

    await getattr(unit, request_name)(*args)

    (entry,) = journal.requests
    assert entry["request"] == request_name
    assert {k: entry[k] for k in fields} == fields
    assert entry["outcome"] == "ok"
    assert len(journal.events) == (0 if request_name.startswith("read_") else 1)


def test_anything_else_goes_straight_to_the_unit(
    mock_connection: MockModbusConnection,
) -> None:
    """``require_timeout`` and the unrecorded requests are the unit's own."""
    inner = mock_connection.for_unit(MOCK_UNIT_ID)
    unit = RecordingUnit(inner, Journal())

    assert unit.require_timeout == inner.require_timeout
    assert unit.read_device_identification == inner.read_device_identification


def test_the_address_is_scrubbed_from_keys_and_tuples() -> None:
    """Keys and tuples are scrubbed like everything else."""
    scrubbed = _scrub(
        {MOCK_HOST: (f"{MOCK_HOST}:502", 1), "list": [MOCK_HOST]}, MOCK_HOST
    )

    assert scrubbed == {
        "**REDACTED**": ["**REDACTED**:502", 1],
        "list": ["**REDACTED**"],
    }
