"""Switch platform for the LG Heat Pump integration."""

from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LgHeatPumpConfigEntry
from .entity import LgHeatPumpEntity, LgHeatPumpEntityDescription, build_entities

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class LgHeatPumpSwitchDescription(SwitchEntityDescription, LgHeatPumpEntityDescription):
    """Describe an LG heat pump switch."""


SWITCH_DESCRIPTIONS: tuple[LgHeatPumpSwitchDescription, ...] = (
    LgHeatPumpSwitchDescription(
        key="heating_circuit",
        translation_key="heating_circuit",
        component="switches",
        attribute="heating_circuit",
        device_class=SwitchDeviceClass.SWITCH,
    ),
    LgHeatPumpSwitchDescription(
        key="silent_mode",
        translation_key="silent_mode",
        component="switches",
        attribute="silent_mode",
        device_class=SwitchDeviceClass.SWITCH,
    ),
    LgHeatPumpSwitchDescription(
        key="dhw_disinfection",
        translation_key="dhw_disinfection",
        component="switches",
        attribute="dhw_disinfection",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
    ),
    # Emergency switches are disabled until tested (required for the HACS default
    # repository list). Re-enable them together with the issue #23 clean-up.
    # LgHeatPumpSwitchDescription(
    #     key="emergency_stop",
    #     translation_key="emergency_stop",
    #     component="switches",
    #     attribute="emergency_stop",
    #     device_class=SwitchDeviceClass.SWITCH,
    #     entity_category=EntityCategory.CONFIG,
    #     entity_registry_enabled_default=False,
    # ),
    # LgHeatPumpSwitchDescription(
    #     key="trigger_emergency_operation",
    #     translation_key="trigger_emergency_operation",
    #     component="switches",
    #     attribute="trigger_emergency_operation",
    #     device_class=SwitchDeviceClass.SWITCH,
    #     entity_category=EntityCategory.CONFIG,
    #     entity_registry_enabled_default=False,
    # ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LgHeatPumpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LG heat pump switch platform."""
    async_add_entities(
        build_entities(entry.runtime_data, LgHeatPumpSwitch, SWITCH_DESCRIPTIONS)
    )


class LgHeatPumpSwitch(LgHeatPumpEntity, SwitchEntity):
    """A single writable coil on the heat pump."""

    entity_description: LgHeatPumpSwitchDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return whether the coil is set."""
        return self._value

    async def _async_write(self, value: bool) -> None:
        """Write the coil and refresh so the state follows the device."""
        await self._subsystem.write(self.entity_description.attribute, value)
        await self.coordinator.async_request_refresh()

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the coil."""
        await self._async_write(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear the coil."""
        await self._async_write(False)
