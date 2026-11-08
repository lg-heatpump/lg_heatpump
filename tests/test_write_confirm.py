"""A write is confirmed by reading it back, again if the first read was stale.

On 08.11.2026 the refresh right after a shift write came back with the old value
(answered in 1 ms, three seconds after the previous identical read) and the
entity showed the old shift until the next settings poll, 60 s later. These
tests replay that with a unit that keeps the old value until the entity waits.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_ON

from . import MOCK_UNIT_ID

if TYPE_CHECKING:
    from modbus_connection.mock import MockModbusConnection, MockModbusUnit
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

SHIFT = "number.lg_therma_v_circuit_1_setpoint_shift"
SHIFT_REGISTER = 4
SHIFT_STALE = 0x10000 - 2  # -2, the shift the mock unit starts with
SILENT_MODE = "switch.lg_therma_v_silent_mode"
SILENT_MODE_COIL = 2
ASYNCIO = "custom_components.lg_heatpump.entity.asyncio"


class _StaleUntilSleep:
    """A unit whose register keeps the old value until the entity waits.

    The write lands, but the register is put back to ``stale`` at once, as a
    cached answer would show it. Each wait of the re-read loop counts down; when
    ``waits`` reaches zero the register holds what was written. Stands in for
    ``asyncio`` in the entity module only, so only the re-read loop's waits count.
    """

    def __init__(
        self, unit: MockModbusUnit, space: str, address: int, stale: Any, waits: int
    ) -> None:
        self._store = getattr(unit, space)
        self._address = address
        self.stale = stale
        self._written: Any = None
        self.waits = waits
        self.slept = 0
        self.gate: asyncio.Event | None = None
        unit.on_write(self._on_write)

    def _on_write(self, event: Any) -> None:
        if event.address == self._address:
            self._written = self._store[self._address]
            self._store[self._address] = self.stale

    async def sleep(self, _delay: float) -> None:
        if self.gate is not None:
            await self.gate.wait()
        self.slept += 1
        self.waits -= 1
        if self.waits <= 0 and self._written is not None:
            self._store[self._address] = self._written
        await asyncio.sleep(0)

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)


async def _settle(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Let the optional-register probes finish before a test writes.

    The mock unit serves the optional limits, and each one the probe finds
    reloads the entry. A write made before that is confirmed by an entity the
    reload has already replaced, whose coordinator no longer polls.
    """
    for _ in range(3):
        await entry.runtime_data.settings.async_refresh()
        await hass.async_block_till_done(wait_background_tasks=True)


async def _set_shift(hass: HomeAssistant, value: int) -> None:
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: SHIFT, ATTR_VALUE: value},
        blocking=True,
    )


def _events(entry: MockConfigEntry, kind: str) -> list[dict]:
    return [e for e in entry.runtime_data.journal.events if e["event"] == kind]


def _pending(entry: MockConfigEntry) -> list[asyncio.Task]:
    return [
        t for t in entry._background_tasks if t.get_name().endswith("confirm write")
    ]


async def test_a_write_that_reads_back_at_once_needs_no_reread(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """The usual case: nothing waits, nothing is journalled."""
    await _settle(hass, init_integration)
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    fake = _StaleUntilSleep(unit, "holding", 99, 0, waits=0)
    with patch(ASYNCIO, fake):
        await _set_shift(hass, 3)
        await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(SHIFT).state == "3"
    assert fake.slept == 0
    assert _events(init_integration, "write_confirmed") == []
    assert _events(init_integration, "write_unconfirmed") == []


async def test_a_stale_read_after_a_write_is_read_again(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """The first refresh still shows -2; the re-read shows the written 3."""
    await _settle(hass, init_integration)
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    fake = _StaleUntilSleep(unit, "holding", SHIFT_REGISTER, SHIFT_STALE, waits=1)
    with patch(ASYNCIO, fake):
        await _set_shift(hass, 3)
        await hass.async_block_till_done(wait_background_tasks=True)

    assert unit.holding[SHIFT_REGISTER] == 3
    assert hass.states.get(SHIFT).state == "3"
    (confirmed,) = _events(init_integration, "write_confirmed")
    assert confirmed["attribute"] == "shift_in_auto_mode_circuit_1"
    assert confirmed["value"] == 3
    assert confirmed["rereads"] == 1


async def test_the_service_call_does_not_wait_for_the_reread(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """An automation that writes is not held up: the re-read runs afterwards."""
    await _settle(hass, init_integration)
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    fake = _StaleUntilSleep(unit, "holding", SHIFT_REGISTER, SHIFT_STALE, waits=1)
    fake.gate = asyncio.Event()
    with patch(ASYNCIO, fake):
        await _set_shift(hass, 3)
        # The call returned while the re-read is still waiting.
        assert hass.states.get(SHIFT).state == "-2"
        assert len(_pending(init_integration)) == 1
        fake.gate.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(SHIFT).state == "3"


async def test_a_value_the_device_never_takes_is_reported(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
    caplog: Any,
) -> None:
    """Like holding 5 on the reference unit: acknowledged, never taken."""
    await _settle(hass, init_integration)
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    fake = _StaleUntilSleep(unit, "holding", SHIFT_REGISTER, SHIFT_STALE, waits=99)
    with patch(ASYNCIO, fake):
        await _set_shift(hass, 3)
        await hass.async_block_till_done(wait_background_tasks=True)

    assert fake.slept == 2
    assert hass.states.get(SHIFT).state == "-2"
    (unconfirmed,) = _events(init_integration, "write_unconfirmed")
    assert unconfirmed["value"] == 3
    assert unconfirmed["reads"] == -2
    assert unconfirmed["rereads"] == 2
    assert "still reports -2 after 2 re-reads" in caplog.text


async def test_a_newer_write_supersedes_the_pending_confirmation(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """Only the latest value is waited for: the older confirmation is cancelled."""
    await _settle(hass, init_integration)
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    fake = _StaleUntilSleep(unit, "holding", SHIFT_REGISTER, SHIFT_STALE, waits=1)
    fake.gate = asyncio.Event()
    with patch(ASYNCIO, fake):
        await _set_shift(hass, 3)  # stays stale: a confirmation is now pending
        (older,) = _pending(init_integration)
        await _set_shift(hass, 4)  # stale again, so a new confirmation starts
        fake.gate.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert older.cancelled()
    assert hass.states.get(SHIFT).state == "4"
    assert [e["value"] for e in _events(init_integration, "write_confirmed")] == [4]
    assert _events(init_integration, "write_unconfirmed") == []


async def test_a_switch_write_is_confirmed_the_same_way(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """Coils go through the same path: a stale coil read is read again."""
    await _settle(hass, init_integration)
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    assert hass.states.get(SILENT_MODE).state == "off"
    fake = _StaleUntilSleep(unit, "coil", SILENT_MODE_COIL, False, waits=1)
    with patch(ASYNCIO, fake):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: SILENT_MODE}, blocking=True
        )
        await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(SILENT_MODE).state == "on"
    (confirmed,) = _events(init_integration, "write_confirmed")
    assert confirmed["attribute"] == "silent_mode"
    assert confirmed["rereads"] == 1
