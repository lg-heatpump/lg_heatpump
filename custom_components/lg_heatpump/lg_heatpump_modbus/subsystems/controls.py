"""Setpoints and operating modes (holding registers: read 0x03, single-write 0x06, multi-write 0x10).

These are the values a controller writes. Reading them back is how the heat
pump reports what it is currently configured to do.

Some manuals have the address tables listed as input registers (0x04), that is wrong, those would be read-only.
"""

from __future__ import annotations

from ..data_model import LgComponent, enum_value, integer, temperature
from ..enums import ControlMethod, EnergyState, OperationMode

#: Protocol limits for the water setpoints, in degrees Celsius. The range an
#: installation actually accepts is narrower and set by the installer.
# TODO verify
WATER_SETPOINT_MIN = 15.0
WATER_SETPOINT_MAX = 65.0

#: Protocol limits for the room air setpoints, in degrees Celsius.
# TODO verify
ROOM_SETPOINT_MIN = 16.0
ROOM_SETPOINT_MAX = 30.0
# actually this works up to ~ +/- 2500 °C, but seems to have no meaning, see below

#: Protocol limits for the domestic hot water setpoint, in degrees Celsius.
# verified by G-nn-r, actual range from LG ThinQ app
DHW_SETPOINT_MIN = 30.0
DHW_SETPOINT_MAX = 80.0

#: Protocol limits for the auto-mode setpoint shift, in kelvin.
# verified by G-nn-r, actual range from LG ThinQ app and on the indoor display unit
SHIFT_MIN = -5
SHIFT_MAX = 5

KELVIN = "K"


class Controls(LgComponent):
    """Operating mode, control method and every writable setpoint."""

    register_space = "holding"
    register_ranges = ((0, 9),)

    operation_mode = enum_value(
        0,
        OperationMode,
        writable=True,
        description="Requested operation mode",
    )
    """Requested operation mode."""

    # TODO verify - verification in ControlMethod class
    control_method = enum_value(
        1,
        ControlMethod,
        writable=True,
        description="Temperature the controller of the heating circuit regulates on",
    )
    """Temperature the controller of the heating circuit regulates on."""

    # verified by G-nn-r: 20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0
    target_temperature_circuit_1 = temperature(
        2,
        writable=True,
        min_value=WATER_SETPOINT_MIN,
        max_value=WATER_SETPOINT_MAX,
        description="Water target temperature for circuit 1",
    )
    """Water target temperature of circuit 1."""

    # TODO verify with control_method = ROOM_AIR
    # this was always 0.0 for G-nn-r, has no effect on water-based control
    room_air_setpoint_circuit_1 = temperature(
        3,
        writable=True,
        min_value=ROOM_SETPOINT_MIN,
        max_value=ROOM_SETPOINT_MAX,
        description="Room air target temperature for circuit 1",
    )
    """Room air target temperature of circuit 1."""

    # verified by G-nn-r: -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5
    shift_in_auto_mode_circuit_1 = integer(
        4,
        signed=True,
        unit=KELVIN,
        writable=True,
        min_value=SHIFT_MIN,
        max_value=SHIFT_MAX,
        description="Weather-compensation setpoint shift for circuit 1",
    )
    """Weather-compensation setpoint shift of circuit 1."""

    # verified by G-nn-r: 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0, 31.0, 32.0, 33.0
    target_temperature_circuit_2 = temperature(
        5,
        writable=True,
        min_value=WATER_SETPOINT_MIN,
        max_value=WATER_SETPOINT_MAX,
        description="Water target temperature for circuit 2",
    )
    """Water target temperature of circuit 2."""

    # TODO verify
    # this was always 0.0 for G-nn-r, maybe test with "AI" mode off?
    room_air_setpoint_circuit_2 = temperature(
        6,
        writable=True,
        min_value=ROOM_SETPOINT_MIN,
        max_value=ROOM_SETPOINT_MAX,
        description="Room air target temperature for circuit 2",
    )
    """Room air target temperature of circuit 2."""

    # verified by G-nn-r: -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5
    shift_in_auto_mode_circuit_2 = integer(
        7,
        signed=True,
        unit=KELVIN,
        writable=True,
        min_value=SHIFT_MIN,
        max_value=SHIFT_MAX,
        description="Weather-compensation setpoint shift for circuit 2",
    )
    """Weather-compensation setpoint shift of circuit 2."""

    # verified by G-nn-r: 43, 45, 48, 50, 60 LG ThinQ: Warmwasser -> Heizwasser -> Soll-Heißwassertemperatur
    dhw_target_temperature = temperature(
        8,
        writable=True,
        min_value=DHW_SETPOINT_MIN,
        max_value=DHW_SETPOINT_MAX,
        description="Domestic hot water target temperature",
    )
    """Domestic hot water target temperature."""

    # TODO verify
    # verified by G-nn-r: 0
    energy_state = enum_value(
        9, EnergyState, description="Smart-grid energy state as configured"
    )
    """Smart-grid energy state as configured."""

    # verified by G-nn-r
    def target_temperature(self, circuit: int) -> float | None:
        """Return the water target temperature of ``circuit`` (1 or 2)."""
        return getattr(self, f"target_temperature_circuit_{_check(circuit)}")

    # TODO verify
    def room_air_setpoint(self, circuit: int) -> float | None:
        """Return the room air target temperature of ``circuit`` (1 or 2)."""
        return getattr(self, f"room_air_setpoint_circuit_{_check(circuit)}")

    # verified by G-nn-r
    def shift_in_auto_mode(self, circuit: int) -> int | None:
        """Return the setpoint shift of ``circuit`` (1 or 2)."""
        return getattr(self, f"shift_in_auto_mode_circuit_{_check(circuit)}")

    # TODO verify
    async def set_target_temperature(self, circuit: int, value: float) -> None:
        """Write the water target temperature of ``circuit`` (1 or 2)."""
        await self.write(f"target_temperature_circuit_{_check(circuit)}", value)

    # TODO verify
    async def set_room_air_setpoint(self, circuit: int, value: float) -> None:
        """Write the room air target temperature of ``circuit`` (1 or 2)."""
        await self.write(f"room_air_setpoint_circuit_{_check(circuit)}", value)

    # TODO verify
    async def set_shift_in_auto_mode(self, circuit: int, value: int) -> None:
        """Write the setpoint shift of ``circuit`` (1 or 2)."""
        await self.write(f"shift_in_auto_mode_circuit_{_check(circuit)}", value)

    async def set_operation_mode(self, mode: OperationMode) -> None:
        """Write the requested operation mode."""
        await self.write("operation_mode", mode)

    # TODO verify
    async def set_control_method(self, method: ControlMethod) -> None:
        """Write the temperature the controller regulates on."""
        await self.write("control_method", method)

    # TODO verify
    async def set_dhw_target_temperature(self, value: float) -> None:
        """Write the domestic hot water target temperature."""
        await self.write("dhw_target_temperature", value)


def _check(circuit: int) -> int:
    """Return ``circuit`` if it names a circuit this device can have."""
    if circuit not in (1, 2):
        raise ValueError(f"Circuit must be 1 or 2, got {circuit}")
    return circuit
