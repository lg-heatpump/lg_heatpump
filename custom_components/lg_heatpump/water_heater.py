"""Water heater platform for the LG Heat Pump integration."""

from typing import Any, override

from homeassistant.components.water_heater import (
    STATE_ON,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LgHeatPumpConfigEntry
from .entity import (
    LgHeatPumpEntityDescription,
    LgHeatPumpSpanningEntity,
    build_entities,
)
from .lg_heatpump_modbus.subsystems.controls import DHW_SETPOINT_MAX, DHW_SETPOINT_MIN

PARALLEL_UPDATES = 1

WATER_HEATER_DESCRIPTIONS: tuple[LgHeatPumpEntityDescription, ...] = (
    LgHeatPumpEntityDescription(
        key="dhw",
        translation_key="dhw",
        component="controls",
        attribute="dhw_target_temperature",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LgHeatPumpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the domestic hot water entity."""
    async_add_entities(
        build_entities(
            entry.runtime_data, LgHeatPumpWaterHeater, WATER_HEATER_DESCRIPTIONS
        )
    )


class LgHeatPumpWaterHeater(LgHeatPumpSpanningEntity, WaterHeaterEntity):
    """The domestic hot water tank."""

    # Home Assistant 2026.11 renamed the temperature members to native_*; the old
    # names stop working in 2027.11. This class provides both until the minimum
    # version reaches 2026.11: older releases read the old names, newer ones the
    # native ones, and a class providing both logs no deprecation warning.
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.ON_OFF
    )
    _attr_operation_list = [STATE_ON, STATE_OFF]
    _attr_min_temp = DHW_SETPOINT_MIN
    _attr_max_temp = DHW_SETPOINT_MAX

    @property
    @override
    def _components(self) -> frozenset[str]:
        """Return the sub-systems the hot water tank reads."""
        return frozenset({"controls", "switches", "sensors"})

    @property
    @override
    def current_temperature(self) -> float | None:
        """Return the hot water tank temperature."""
        return self.device.sensors.dhw_tank_temperature

    @property
    @override
    def target_temperature(self) -> float | None:
        """Return the hot water setpoint."""
        return self.device.controls.dhw_target_temperature

    @property
    def native_current_temperature(self) -> float | None:
        """Return the hot water tank temperature."""
        return self.current_temperature

    @property
    def native_target_temperature(self) -> float | None:
        """Return the hot water setpoint."""
        return self.target_temperature

    @property
    @override
    def current_operation(self) -> str | None:
        """Return whether hot water production is enabled."""
        if (enabled := self.device.switches.dhw) is None:
            return None
        return STATE_ON if enabled else STATE_OFF

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write a new hot water setpoint."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.device.controls.set_dhw_target_temperature(temperature)
        await self._async_refresh()

    @override
    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Enable or disable hot water production."""
        await self.device.switches.set_dhw(operation_mode == STATE_ON)
        await self._async_refresh()

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable hot water production."""
        await self.device.switches.set_dhw(True)
        await self._async_refresh()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable hot water production."""
        await self.device.switches.set_dhw(False)
        await self._async_refresh()
