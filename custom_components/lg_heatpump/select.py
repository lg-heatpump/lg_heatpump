"""Select platform for the LG Heat Pump integration."""

from dataclasses import dataclass
from enum import IntEnum
from typing import override

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LgHeatPumpConfigEntry
from .entity import LgHeatPumpEntity, LgHeatPumpEntityDescription, build_entities
from .lg_heatpump_modbus import ControlMethod

PARALLEL_UPDATES = 1


def _options(enum_type: type[IntEnum]) -> list[str]:
    """Return the select options a device enum maps onto."""
    return [member.name.lower() for member in enum_type]


@dataclass(frozen=True, kw_only=True)
class LgHeatPumpSelectDescription(SelectEntityDescription, LgHeatPumpEntityDescription):
    """Describe an LG heat pump select."""

    options_enum: type[IntEnum]


SELECT_DESCRIPTIONS: tuple[LgHeatPumpSelectDescription, ...] = (
    LgHeatPumpSelectDescription(
        key="control_method",
        translation_key="control_method",
        component="controls",
        attribute="control_method",
        # ROOM_AIR is disabled until it has been tested on real hardware. See issue #25
        options=[
            option for option in _options(ControlMethod) if option != "room_air"
        ],
        # options=_options(ControlMethod),
        options_enum=ControlMethod,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LgHeatPumpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LG heat pump select platform."""
    async_add_entities(
        build_entities(entry.runtime_data, LgHeatPumpSelect, SELECT_DESCRIPTIONS)
    )


class LgHeatPumpSelect(LgHeatPumpEntity, SelectEntity):
    """A single enumerated register on the heat pump."""

    entity_description: LgHeatPumpSelectDescription

    @property
    @override
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        value: IntEnum | None = self._value
        return value.name.lower() if value is not None else None

    @override
    async def async_select_option(self, option: str) -> None:
        """Write the selected option and refresh."""
        value = self.entity_description.options_enum[option.upper()]
        await self._subsystem.write(self.entity_description.attribute, value)
        await self.coordinator.async_request_refresh()
