"""Tests for the LG Heat Pump entity platforms."""

from modbus_connection.mock import MockModbusConnection
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.water_heater import (
    ATTR_OPERATION_MODE,
    DOMAIN as WATER_HEATER_DOMAIN,
    SERVICE_SET_OPERATION_MODE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from . import MOCK_UNIT_ID


@pytest.mark.parametrize(
    ("entity_id", "expected"),
    [
        ("sensor.lg_therma_v_outdoor_temperature", "-4.2"),
        ("sensor.lg_therma_v_water_inlet_temperature", "31.5"),
        ("sensor.lg_therma_v_water_outlet_temperature", "35.2"),
        ("sensor.lg_therma_v_hot_water_tank_temperature", "48.2"),
        ("sensor.lg_therma_v_water_flow_rate", "17.2"),
        ("sensor.lg_therma_v_energy_state", "normal"),
        ("sensor.lg_therma_v_error_code", "0"),
    ],
)
async def test_sensor_states(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id: str,
    expected: str,
) -> None:
    """Each seeded register surfaces as the documented sensor state."""
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    assert state.state == expected


async def test_odu_operation_cycle_sensor(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """The operation cycle sensor exposes the decoded enum value."""
    entity_id = "sensor.lg_therma_v_outdoor_unit_operation_cycle"
    entity_registry.async_get_or_create(
        "sensor",
        "lg_heatpump",
        f"{init_integration.entry_id}_odu_operation_cycle",
        suggested_object_id="lg_therma_v_outdoor_unit_operation_cycle",
        disabled_by=None,
    )
    entity_registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "heating"


async def test_derived_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Sensors the library derives from several registers report a value."""
    for entity_id in (
        "sensor.lg_therma_v_compressor_speed",
        "sensor.lg_therma_v_water_temperature_difference",
        "sensor.lg_therma_v_circuit_1_water_outlet_temperature",
    ):
        entity_registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get("sensor.lg_therma_v_compressor_speed").state == "3720"
    assert (
        hass.states.get("sensor.lg_therma_v_water_temperature_difference").state
        == "3.7"
    )
    assert (
        hass.states.get("sensor.lg_therma_v_circuit_1_water_outlet_temperature").state
        == "35.2"
    )


@pytest.mark.parametrize(
    ("entity_id", "expected"),
    [
        ("binary_sensor.lg_therma_v_compressor", STATE_ON),
        ("binary_sensor.lg_therma_v_water_pump", STATE_ON),
        ("binary_sensor.lg_therma_v_defrosting", STATE_OFF),
        ("binary_sensor.lg_therma_v_error", STATE_OFF),
        ("binary_sensor.lg_therma_v_water_flow", STATE_ON),
    ],
)
async def test_binary_sensor_states(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id: str,
    expected: str,
) -> None:
    """Each seeded discrete input surfaces as the documented binary state."""
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    assert state.state == expected


async def test_switch_states_and_writes(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """A switch reflects its coil and writes it back."""
    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    assert hass.states.get("switch.lg_therma_v_silent_mode").state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.lg_therma_v_silent_mode"},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert unit.coils[2] is True
    assert hass.states.get("switch.lg_therma_v_silent_mode").state == STATE_ON

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.lg_therma_v_silent_mode"},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert unit.coils[2] is False


async def test_climate_state(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The thermostat follows the water setpoint on water-outlet control."""
    state = hass.states.get("climate.lg_therma_v_circuit_1")

    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 40.0
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 35.2
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING


async def test_climate_set_temperature(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """Setting the thermostat writes the circuit's water setpoint."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "climate.lg_therma_v_circuit_1", ATTR_TEMPERATURE: 43.5},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_connection.for_unit(MOCK_UNIT_ID).holding[2] == 435


async def test_climate_off_clears_the_heating_circuit_coil(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """Switching the thermostat off switches the heat pump off."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: "climate.lg_therma_v_circuit_1", ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    assert unit.coils[0] is False
    state = hass.states.get("climate.lg_therma_v_circuit_1")
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF


@pytest.mark.skip(reason="Cool mode is disabled until verified on a real device (#24)")
async def test_climate_cool_writes_mode_and_heating_circuit(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """Selecting cool writes the operation mode and switches the heat pump on."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {
            ATTR_ENTITY_ID: "climate.lg_therma_v_circuit_1",
            ATTR_HVAC_MODE: HVACMode.COOL,
        },
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    unit = mock_connection.for_unit(MOCK_UNIT_ID)
    assert unit.holding[0] == 0  # OperationMode.COOL
    assert unit.coils[0] is True


async def test_climate_follows_room_air_control(
    hass: HomeAssistant,
    mock_connection: MockModbusConnection,
    mock_config_entry: MockConfigEntry,
    patched_connection: None,
) -> None:
    """On room-air control the thermostat controls the room setpoint."""
    mock_connection.for_unit(MOCK_UNIT_ID).holding[1] = 2  # ControlMethod.ROOM_AIR
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get("climate.lg_therma_v_circuit_1")

    assert state.attributes[ATTR_TEMPERATURE] == 21.0  # room setpoint
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 21.4  # room temperature
    assert state.attributes["max_temp"] == 30.0


async def test_water_heater(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """The hot water tank reports its setpoint and writes a new one."""
    state = hass.states.get("water_heater.lg_therma_v_hot_water")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_TEMPERATURE] == 50.0
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 48.2

    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {
            ATTR_ENTITY_ID: "water_heater.lg_therma_v_hot_water",
            ATTR_TEMPERATURE: 55.0,
        },
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_connection.for_unit(MOCK_UNIT_ID).holding[8] == 550


async def test_water_heater_operation_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """Turning hot water off clears its coil."""
    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        {
            ATTR_ENTITY_ID: "water_heater.lg_therma_v_hot_water",
            ATTR_OPERATION_MODE: STATE_OFF,
        },
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_connection.for_unit(MOCK_UNIT_ID).coils[1] is False


async def test_number_writes_the_setpoint_shift(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """The setpoint shift reads back signed and writes two's complement."""
    state = hass.states.get("number.lg_therma_v_circuit_1_setpoint_shift")
    assert state.state == "-2"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.lg_therma_v_circuit_1_setpoint_shift",
            ATTR_VALUE: -4,
        },
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_connection.for_unit(MOCK_UNIT_ID).holding[4] == 0x10000 - 4


async def test_number_rejects_an_out_of_range_value(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """A shift beyond the documented range never reaches the heat pump."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.lg_therma_v_circuit_1_setpoint_shift",
                ATTR_VALUE: 9,
            },
            blocking=True,
        )

    assert mock_connection.for_unit(MOCK_UNIT_ID).holding[4] == 0x10000 - 2


async def test_select_control_method(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """The control method select reads and writes the enum register."""
    state = hass.states.get("select.lg_therma_v_control_method")
    assert state.state == "water_outlet"

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.lg_therma_v_control_method",
            ATTR_OPTION: "room_air",
        },
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_connection.for_unit(MOCK_UNIT_ID).holding[1] == 2


async def test_refresh_button_polls_both_coordinators(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Pressing the refresh button polls the measurements and the settings."""
    runtime_data = init_integration.runtime_data
    readings_before = runtime_data.readings.last_poll_time
    settings_before = runtime_data.settings.last_poll_time

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.lg_therma_v_refresh_data_now"},
        blocking=True,
    )

    assert runtime_data.readings.last_poll_time > readings_before
    assert runtime_data.settings.last_poll_time > settings_before
