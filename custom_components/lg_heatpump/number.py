"""Number platform for the LG Heat Pump integration.

The weather-compensation setpoint shifts are plain numbers: they are neither a
temperature the heat pump aims for nor a mode, so they belong here rather than
on the climate entities.
"""

from dataclasses import dataclass
from typing import override

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LgHeatPumpConfigEntry
from .entity import LgHeatPumpEntity, LgHeatPumpEntityDescription, build_entities
from .lg_heatpump_modbus.subsystems.controls import SHIFT_MAX, SHIFT_MIN

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class LgHeatPumpNumberDescription(NumberEntityDescription, LgHeatPumpEntityDescription):
    """Describe an LG heat pump number."""


def _shift(circuit: int) -> LgHeatPumpNumberDescription:
    """Describe the auto-mode setpoint shift of one circuit."""
    attribute = f"shift_in_auto_mode_circuit_{circuit}"
    return LgHeatPumpNumberDescription(
        key=attribute,
        translation_key="shift_in_auto_mode",
        translation_placeholders={"circuit": str(circuit)},
        component="controls",
        attribute=attribute,
        native_min_value=SHIFT_MIN,
        native_max_value=SHIFT_MAX,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.KELVIN,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    )


NUMBER_DESCRIPTIONS: tuple[LgHeatPumpNumberDescription, ...] = (
    _shift(1),
    _shift(2),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LgHeatPumpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LG heat pump number platform."""
    async_add_entities(
        build_entities(entry.runtime_data, LgHeatPumpNumber, NUMBER_DESCRIPTIONS)
    )


class LgHeatPumpNumber(LgHeatPumpEntity, NumberEntity):
    """A single writable numeric register on the heat pump."""

    entity_description: LgHeatPumpNumberDescription

    @property
    @override
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._value

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write a new value and refresh so the state follows the device."""
        await self._async_write_and_refresh(int(value))
