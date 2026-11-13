"""Tests for the LG Heat Pump config-entry setup."""

from unittest.mock import patch

from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lg_heatpump.const import (
    CONF_MODEL,
    CONF_UNIT_ID,
    DOMAIN,
    REQUEST_TIMEOUT,
)
from custom_components.lg_heatpump.diagnostics import async_get_config_entry_diagnostics
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import MOCK_UNIT_ID, MOCK_USER_INPUT, seed_heat_pump
from .conftest import CREATE_CONNECTION


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry loads, registers a device and unloads again."""
    assert init_integration.state is ConfigEntryState.LOADED

    devices = dr.async_entries_for_config_entry(
        dr.async_get(hass), init_integration.entry_id
    )
    assert len(devices) == 1
    device = devices[0]
    assert (DOMAIN, init_integration.entry_id) in device.identifiers
    assert device.manufacturer == "LG"
    assert device.model == "LG Therma V"

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


needs_require_timeout = pytest.mark.skipif(
    not hasattr(MockModbusUnit, "require_timeout"),
    reason="modbus-connection < 4.12.3 has no require_timeout",
)


@needs_require_timeout
async def test_setup_asks_the_link_for_a_timeout_floor(
    mock_connection: MockModbusConnection,
    init_integration: MockConfigEntry,
) -> None:
    """The unit asks for the request timeout floor the shared link needs."""
    assert mock_connection.for_unit(MOCK_UNIT_ID).required_timeout == REQUEST_TIMEOUT


@needs_require_timeout
async def test_the_timeout_floor_never_shortens_another_units_requirement(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_connection: MockModbusConnection,
    patched_connection: None,
) -> None:
    """A unit asking for more than the floor keeps what it asked for."""
    other_unit = mock_connection.for_unit(MOCK_UNIT_ID + 1)
    other_unit.require_timeout(REQUEST_TIMEOUT + 10)
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert other_unit.required_timeout == REQUEST_TIMEOUT + 10
    # The link resolves to the largest requirement of any unit on it.
    assert mock_connection._timeout == REQUEST_TIMEOUT + 10


async def test_setup_works_without_require_timeout(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patched_connection: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older modbus-connection without the method still sets the entry up."""
    monkeypatch.delattr(MockModbusUnit, "require_timeout", raising=False)
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_unload_closes_the_connection(
    hass: HomeAssistant,
    mock_connection: MockModbusConnection,
    init_integration: MockConfigEntry,
) -> None:
    """The shared connection closes once its last holder unloads."""
    assert not mock_connection.close.called

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert mock_connection.close.called


async def test_entries_on_one_gateway_share_a_connection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """A second consumer of the same gateway reuses the open connection."""
    mock_config_entry.add_to_hass(hass)
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        title="LG Therma V (second unit)",
        data={**MOCK_USER_INPUT, CONF_UNIT_ID: MOCK_UNIT_ID + 1},
    )
    other_entry.add_to_hass(hass)
    seed_heat_pump(mock_connection.for_unit(MOCK_UNIT_ID + 1))

    with patch(CREATE_CONNECTION, return_value=mock_connection) as create_connection:
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

        assert create_connection.call_count == 1

        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        assert not mock_connection.close.called

        assert await hass.config_entries.async_unload(other_entry.entry_id)
        assert mock_connection.close.called


async def test_a_failed_setup_still_closes_the_connection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_connection: MockModbusConnection,
    patched_connection: None,
) -> None:
    """A connection opened for a setup that never completes is not leaked."""
    mock_connection.for_unit(MOCK_UNIT_ID).fail_requests(ModbusTimeoutError())
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_connection.close.called


async def test_setup_retries_when_the_heat_pump_is_silent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_connection: MockModbusConnection,
    patched_connection: None,
) -> None:
    """A heat pump that answers nothing leaves the entry retrying."""
    mock_connection.for_unit(MOCK_UNIT_ID).fail_requests(ModbusTimeoutError())
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_entities_are_created_across_every_platform(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Every platform contributes entities to the heat pump device."""
    entities = er.async_entries_for_config_entry(
        er.async_get(hass), init_integration.entry_id
    )
    domains = {entity.domain for entity in entities}

    assert domains == {
        "binary_sensor",
        "button",
        "climate",
        "number",
        "select",
        "sensor",
        "switch",
        "water_heater",
    }


async def test_a_model_without_a_second_circuit_creates_fewer_entities(
    hass: HomeAssistant,
    mock_connection: MockModbusConnection,
    patched_connection: None,
) -> None:
    """The configured model decides which entities exist."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LG Therma V (single circuit)",
        data={**MOCK_USER_INPUT, CONF_MODEL: "therma_v_single_circuit"},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    registry = er.async_get(hass)
    unique_ids = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    assert f"{entry.entry_id}_circuit_1" in unique_ids
    assert f"{entry.entry_id}_circuit_2" not in unique_ids
    assert f"{entry.entry_id}_solar_pump" not in unique_ids
    assert f"{entry.entry_id}_dhw" in unique_ids  # hot water is still fitted


async def test_a_failed_subsystem_makes_only_its_entities_unavailable(
    hass: HomeAssistant,
    mock_connection: MockModbusConnection,
    init_integration: MockConfigEntry,
) -> None:
    """One refused block does not take the whole integration with it."""
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    unit.fail_read(0, IllegalDataAddressError(), register_type="discrete_input")

    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert init_integration.state is ConfigEntryState.LOADED
    outdoor = hass.states.get("sensor.lg_therma_v_outdoor_temperature")
    assert outdoor is not None
    assert outdoor.state == "-4.2"
    compressor = hass.states.get("binary_sensor.lg_therma_v_compressor")
    assert compressor is not None
    assert compressor.state == "unavailable"


async def test_update_problem_sensors_report_a_partial_failure(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_connection: MockModbusConnection,
    init_integration: MockConfigEntry,
) -> None:
    """The debug sensors stay available and flag the failing sub-system."""
    entity_ids = (
        "binary_sensor.lg_therma_v_measurement_update_problem",
        "binary_sensor.lg_therma_v_settings_update_problem",
    )
    for entity_id in entity_ids:
        entity = entity_registry.async_get(entity_id)
        assert entity is not None
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        entity_registry.async_update_entity(entity_id, disabled_by=None)
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    unit.fail_read(0, IllegalDataAddressError(), register_type="discrete_input")

    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    readings = hass.states.get(entity_ids[0])
    assert readings is not None
    assert readings.state == "on"
    assert readings.attributes["failed_components"] == ["states"]
    settings = hass.states.get(entity_ids[1])
    assert settings is not None
    assert settings.state == "off"


async def test_last_poll_sensors_keep_reporting_when_a_poll_fails(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_connection: MockModbusConnection,
    init_integration: MockConfigEntry,
) -> None:
    """The timestamp sensors stay available and advance on a failed poll."""
    entity_ids = (
        "sensor.lg_therma_v_last_measurement_poll",
        "sensor.lg_therma_v_last_settings_poll",
    )
    for entity_id in entity_ids:
        entity = entity_registry.async_get(entity_id)
        assert entity is not None
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        entity_registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    runtime_data = init_integration.runtime_data
    first_poll = runtime_data.readings.last_poll_time
    assert first_poll is not None
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state not in {"unavailable", "unknown"}

    mock_connection.for_unit(MOCK_UNIT_ID).fail_requests(ModbusTimeoutError())
    await runtime_data.readings.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert not runtime_data.readings.last_update_success
    assert runtime_data.readings.last_poll_time > first_poll
    state = hass.states.get(entity_ids[0])
    assert state is not None
    assert (
        state.state
        == runtime_data.readings.last_poll_time.replace(microsecond=0).isoformat()
    )


async def test_diagnostics_include_the_raw_register_map(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Diagnostics dump every register, with the host redacted."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert diagnostics["config"]["host"] == "**REDACTED**"
    assert diagnostics["model"] == "therma_v"
    assert diagnostics["raw"]["input"][12] == 0x10000 - 42
    assert diagnostics["raw"]["holding"][8] == 500
    assert diagnostics["values"]["sensors"]["outdoor_temperature"] == -4.2
