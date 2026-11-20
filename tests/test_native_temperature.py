"""Tests for the native temperature members Home Assistant 2026.11 introduced."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from custom_components.lg_heatpump.climate import LgHeatPumpClimate
from custom_components.lg_heatpump.water_heater import LgHeatPumpWaterHeater
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.water_heater import DOMAIN as WATER_HEATER_DOMAIN
from homeassistant.const import UnitOfTemperature

if TYPE_CHECKING:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

# Deprecated name and its replacement. Home Assistant 2026.11 logs no warning for
# a class that provides both; releases before it only know the deprecated name.
PAIRS = (
    ("_attr_temperature_unit", "_attr_native_temperature_unit"),
    ("current_temperature", "native_current_temperature"),
    ("target_temperature", "native_target_temperature"),
)


@pytest.mark.parametrize("cls", [LgHeatPumpClimate, LgHeatPumpWaterHeater])
def test_each_deprecated_name_comes_with_its_native_one(cls: type) -> None:
    """Both names are defined on the class itself, so neither shadows the other."""
    for legacy, native in PAIRS:
        assert legacy in vars(cls)
        assert native in vars(cls)


@pytest.mark.parametrize(
    ("domain", "entity_id"),
    [
        (CLIMATE_DOMAIN, "climate.lg_therma_v_circuit_1"),
        (WATER_HEATER_DOMAIN, "water_heater.lg_therma_v_hot_water"),
    ],
)
async def test_the_native_members_report_the_same_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    domain: str,
    entity_id: str,
) -> None:
    """The native members return what the deprecated ones return."""
    entity = hass.data[domain].get_entity(entity_id)

    assert entity is not None
    assert entity.native_current_temperature == entity.current_temperature
    assert entity.native_target_temperature == entity.target_temperature
    assert entity.native_current_temperature is not None
    assert entity.native_target_temperature is not None
    # Read as the attribute: releases before 2026.11 have no native property.
    assert entity._attr_native_temperature_unit == UnitOfTemperature.CELSIUS
    assert entity.temperature_unit == UnitOfTemperature.CELSIUS
