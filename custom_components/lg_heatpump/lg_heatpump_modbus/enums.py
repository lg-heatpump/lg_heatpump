"""Enumerated register values.

Only codes that the validated register map documents are declared. An undocumented code decodes to ``None`` rather than
being guessed at, so a device that reports something unexpected is visible instead of silently mislabeled.
"""

from __future__ import annotations

from enum import IntEnum


class OperationMode(IntEnum):
    """
    Requested operation mode (holding register 0).

    Used in controls.py in Controls.operation_mode.
    """

    COOL = 0  # TODO verify; not tested; G-nn-r cannot set this mode (also not on the remote control)
    AUTO = 3  # tested by G-nn-r
    HEAT = 4  # tested by G-nn-r


class OduOperationCycle(IntEnum):
    """Outdoor-unit operation cycle reported by the sensor block."""

    STANDBY = 0  # when heating_circuit and dhw are False, tested by G-nn-r
    COOLING = 1  # TODO verify, not tested yet, see here: https://community.simon42.com/t/lg-therma-v-modbus-anbindung/13357/109
    HEATING = 2  # when either dhw or heating_circuit is True (regardless if compressor actually runs), tested by G-nn-r


class ControlMethod(IntEnum):
    """
    Which temperature the controller regulates on (holding register 1).

    Used in controls.py in Controls.control_method.
    """

    WATER_OUTLET = 0  # tested by G-nn-r
    WATER_INLET = 1   # tested by G-nn-r
    ROOM_AIR = 2      # TODO verify; not tested; G-nn-r cannot set this mode (also not on the remote control)


class EnergyState(IntEnum):
    """
    Smart-grid energy state (input register 11 / holding register 9).

    Used in controls.py in Controls.energy_state.
    """

    # TODO verify
    NOT_USED = 0                  # tested by G-nn-r
    FORCED_OFF = 1                # not tested
    NORMAL = 2                    # not tested
    ON_RECOMMENDATION = 3         # not tested
    ON_COMMAND = 4                # not tested
    ON_COMMAND_STEP_2 = 5         # not tested
    ON_RECOMMENDATION_STEP_1 = 6  # not tested
    ENERGY_SAVING = 7             # not tested
    SUPER_ENERGY_SAVING = 8       # not tested


class Circuit(IntEnum):
    """The two water circuits a heat pump can drive."""

    # TODO verify
    # TODO is this even used anywhere?
    CIRCUIT_1 = 1
    CIRCUIT_2 = 2
