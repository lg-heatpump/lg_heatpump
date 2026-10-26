"""Climate platform for the LG Heat Pump integration.

One thermostat per water circuit. Which temperature the thermostat controls
follows the heat pump's own control method: on room-air control it is the room
setpoint, otherwise it is the water target temperature.
"""

from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LgHeatPumpConfigEntry
from .entity import (
    LgHeatPumpEntityDescription,
    LgHeatPumpSpanningEntity,
    build_entities,
)
from .lg_heatpump_modbus import ControlMethod, OperationMode
from .lg_heatpump_modbus.subsystems.controls import (
    ROOM_SETPOINT_MAX,
    ROOM_SETPOINT_MIN,
    WATER_SETPOINT_MAX,
    WATER_SETPOINT_MIN,
)

PARALLEL_UPDATES = 1

_TO_HVAC = {
    # Cool mode is disabled until it has been verified on a real device (#24).
    # OperationMode.COOL: HVACMode.COOL,
    OperationMode.AUTO: HVACMode.AUTO,
    OperationMode.HEAT: HVACMode.HEAT,
}
_FROM_HVAC = {hvac: mode for mode, hvac in _TO_HVAC.items()}

# The measurement each circuit's water temperature is read from.
_WATER_TEMPERATURE = {
    1: "water_outlet_temperature",
    2: "water_outlet_temperature_circuit_2",
}


@dataclass(frozen=True, kw_only=True)
class LgHeatPumpClimateDescription(
    ClimateEntityDescription, LgHeatPumpEntityDescription
):
    """Describe one water circuit as a thermostat."""

    circuit: int


CLIMATE_DESCRIPTIONS: tuple[LgHeatPumpClimateDescription, ...] = tuple(
    LgHeatPumpClimateDescription(
        key=f"circuit_{circuit}",
        translation_key="circuit",
        translation_placeholders={"circuit": str(circuit)},
        component="controls",
        attribute=f"target_temperature_circuit_{circuit}",
        circuit=circuit,
    )
    for circuit in (1, 2)
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LgHeatPumpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a thermostat per water circuit."""
    async_add_entities(
        build_entities(entry.runtime_data, LgHeatPumpClimate, CLIMATE_DESCRIPTIONS)
    )


class LgHeatPumpClimate(LgHeatPumpSpanningEntity, ClimateEntity):
    """One water circuit of the heat pump, as a thermostat."""

    entity_description: LgHeatPumpClimateDescription

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    # HVACMode.COOL is disabled until it has been verified on a real device (#24).
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
        # HVACMode.COOL,
        HVACMode.AUTO,
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 0.5

    @property
    @override
    def _components(self) -> frozenset[str]:
        """Return the sub-systems this thermostat reads."""
        return frozenset({"controls", "switches", "sensors", "states"})

    @property
    def _circuit(self) -> int:
        """Return the circuit number this thermostat drives."""
        return self.entity_description.circuit

    @property
    def _on_room_air(self) -> bool:
        """Return whether the heat pump regulates on room air temperature."""
        return self.device.controls.control_method is ControlMethod.ROOM_AIR

    @property
    @override
    def current_temperature(self) -> float | None:
        """Return the temperature the heat pump is regulating on."""
        sensors = self.device.sensors
        if self._on_room_air:
            return getattr(sensors, f"room_air_temperature_circuit_{self._circuit}")
        return getattr(sensors, _WATER_TEMPERATURE[self._circuit])

    @property
    @override
    def target_temperature(self) -> float | None:
        """Return the setpoint the heat pump is aiming for."""
        controls = self.device.controls
        if self._on_room_air:
            return controls.room_air_setpoint(self._circuit)
        return controls.target_temperature(self._circuit)

    @property
    @override
    def min_temp(self) -> float:
        """Return the lowest settable temperature."""
        return ROOM_SETPOINT_MIN if self._on_room_air else WATER_SETPOINT_MIN

    @property
    @override
    def max_temp(self) -> float:
        """Return the highest settable temperature."""
        return ROOM_SETPOINT_MAX if self._on_room_air else WATER_SETPOINT_MAX

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        if (heating_circuit := self.device.switches.heating_circuit) is None:
            return None
        if not heating_circuit:
            return HVACMode.OFF
        mode = self.device.controls.operation_mode
        return _TO_HVAC.get(mode) if mode is not None else None

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        """Return what the heat pump is doing right now."""
        states = self.device.states
        if self.device.switches.heating_circuit is False:
            return HVACAction.OFF
        if states.defrosting:
            return HVACAction.DEFROSTING
        if (compressor := states.compressor) is None:
            return None
        if not compressor or states.dhw_heating or states.dhw_disinfection:
            return HVACAction.IDLE
        if self.device.controls.operation_mode is OperationMode.COOL:
            return HVACAction.COOLING
        return HVACAction.HEATING

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write a new setpoint for this circuit."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        controls = self.device.controls
        if self._on_room_air:
            await controls.set_room_air_setpoint(self._circuit, temperature)
        else:
            await controls.set_target_temperature(self._circuit, temperature)
        await self._async_refresh()

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch the heat pump off, or on into the requested mode."""
        if hvac_mode is HVACMode.OFF:
            await self.device.switches.set_heating_circuit(False)
        else:
            await self.device.controls.set_operation_mode(_FROM_HVAC[hvac_mode])
            await self.device.switches.set_heating_circuit(True)
        await self._async_refresh()

    @override
    async def async_turn_on(self) -> None:
        """Switch the heat pump on."""
        await self.device.switches.set_heating_circuit(True)
        await self._async_refresh()

    @override
    async def async_turn_off(self) -> None:
        """Switch the heat pump off."""
        await self.device.switches.set_heating_circuit(False)
        await self._async_refresh()
