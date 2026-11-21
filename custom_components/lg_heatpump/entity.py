"""Base entity for the LG Heat Pump integration.

Every entity names the library sub-system it reads from. That decides which
coordinator drives it and whether it is available: a sub-system that failed the
last poll keeps its previous values, and its entities say so.
"""

import asyncio
from dataclasses import dataclass
import math
from typing import Any, override

from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import LOGGER, WRITE_CONFIRM_DELAYS
from .coordinator import LgHeatPumpCoordinator, LgHeatPumpRuntimeData


@dataclass(frozen=True, kw_only=True)
class LgHeatPumpEntityDescription(EntityDescription):
    """Describe an entity reading one attribute of one sub-system."""

    component: str
    """Attribute name on ``LgHeatPump``, e.g. 'sensors' or 'controls'."""

    attribute: str
    """Attribute name on that sub-system, i.e. the library datapoint."""


class LgHeatPumpEntity(CoordinatorEntity[LgHeatPumpCoordinator]):
    """Common identity and device info for every LG heat pump entity."""

    _attr_has_entity_name = True
    entity_description: LgHeatPumpEntityDescription
    _confirm_task: asyncio.Task[None] | None = None

    def __init__(
        self,
        runtime_data: LgHeatPumpRuntimeData,
        description: LgHeatPumpEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(runtime_data.coordinator_for(description.component))
        self.entity_description = description
        self.runtime_data = runtime_data
        entry = self.coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = self.coordinator.device_info

    @property
    def device(self) -> Any:
        """Return the library heat pump object."""
        return self.runtime_data.device

    @property
    def _subsystem(self) -> Any:
        """Return the library sub-system this entity reads from."""
        return getattr(self.coordinator.device, self.entity_description.component)

    @property
    def _value(self) -> Any:
        """Return the current value of this entity's datapoint."""
        subsystem = self._subsystem
        if hasattr(subsystem, self.entity_description.attribute):
            return getattr(subsystem, self.entity_description.attribute)
        return getattr(self.device, self.entity_description.attribute)

    async def _async_write_and_refresh(self, value: Any) -> None:
        """Write this entity's datapoint, refresh, and confirm in the background.

        The refresh is the one the platforms always did. If it does not show the
        written value yet, the entity reads again a few seconds later instead of
        waiting for the next scheduled poll; see ``WRITE_CONFIRM_DELAYS``.
        """
        attribute = self.entity_description.attribute
        await self._subsystem.write(attribute, value)
        await self.coordinator.async_request_refresh()
        if self._confirm_task is not None and not self._confirm_task.done():
            # A newer write supersedes what the older one was waiting for.
            self._confirm_task.cancel()
            self._confirm_task = None
        if self._reads(attribute, value):
            return
        self._confirm_task = self.coordinator.config_entry.async_create_background_task(
            self.hass,
            self._async_confirm_write(attribute, value),
            f"{self.entity_id} confirm write",
        )

    def _reads(self, attribute: str, value: Any) -> bool:
        """Return whether the sub-system currently reports ``value``."""
        reported = getattr(self._subsystem, attribute, None)
        if isinstance(value, float) and isinstance(reported, (int, float)):
            # A decoded tenth of a kilowatt need not be the same float.
            return math.isclose(reported, value, abs_tol=1e-6)
        return reported == value

    async def _async_confirm_write(self, attribute: str, value: Any) -> None:
        """Re-read until the written value shows, or give up after the last try."""
        journal = self.runtime_data.journal
        for attempt, delay in enumerate(WRITE_CONFIRM_DELAYS, start=1):
            await asyncio.sleep(delay)
            await self.coordinator.async_refresh()
            if self._reads(attribute, value):
                journal.event(
                    "write_confirmed", attribute=attribute, value=value, rereads=attempt
                )
                return
        journal.event(
            "write_unconfirmed",
            attribute=attribute,
            value=value,
            reads=getattr(self._subsystem, attribute, None),
            rereads=len(WRITE_CONFIRM_DELAYS),
        )
        LOGGER.warning(
            "%s: wrote %s = %s, but the device still reports %s after %d re-reads",
            self.coordinator.name,
            attribute,
            value,
            getattr(self._subsystem, attribute, None),
            len(WRITE_CONFIRM_DELAYS),
        )

    @property
    @override
    def available(self) -> bool:
        """Return whether this entity's sub-system answered the last poll."""
        if not super().available:
            return False
        return self.entity_description.component not in self.coordinator.data.failed


def served(runtime_data: LgHeatPumpRuntimeData, attribute: str) -> bool:
    """Return whether the configured model serves ``attribute``."""
    return runtime_data.device.serves(attribute)


class LgHeatPumpSpanningEntity(LgHeatPumpEntity):
    """An entity whose state spans both the readings and the settings polls.

    A thermostat reads a measurement and a setpoint, and those sit in different
    Modbus tables on different intervals. The entity follows its own
    coordinator as usual and subscribes to the other one as well, so a fresh
    measurement is not held back by the slower settings poll.
    """

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe to the coordinator this entity is not driven by."""
        await super().async_added_to_hass()
        other = (
            self.runtime_data.settings
            if self.coordinator is self.runtime_data.readings
            else self.runtime_data.readings
        )
        self.async_on_remove(other.async_add_listener(self.async_write_ha_state))

    @property
    @override
    def available(self) -> bool:
        """Return whether every sub-system this entity reads answered."""
        readings = self.runtime_data.readings
        settings = self.runtime_data.settings
        if not (readings.last_update_success and settings.last_update_success):
            return False
        failed = set(readings.data.failed) | set(settings.data.failed)
        return not failed & self._components

    @property
    def _components(self) -> frozenset[str]:
        """Return the sub-systems this entity's state depends on."""
        return frozenset({self.entity_description.component})

    async def _async_refresh(self) -> None:
        """Refresh both polls, so a write is reflected as soon as it lands."""
        await self.runtime_data.settings.async_request_refresh()
        await self.runtime_data.readings.async_request_refresh()


def build_entities[E, D: LgHeatPumpEntityDescription](
    runtime_data: LgHeatPumpRuntimeData,
    entity_class: type[E],
    descriptions: tuple[D, ...],
) -> list[E]:
    """Build one entity per description the configured model actually serves."""
    return [
        entity_class(runtime_data, description)  # type: ignore[call-arg]
        for description in descriptions
        if served(runtime_data, description.attribute)
    ]
