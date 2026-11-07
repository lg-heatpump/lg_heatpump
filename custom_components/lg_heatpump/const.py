"""Constants for the LG Heat Pump custom integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "lg_heatpump"
LOGGER: Final = logging.getLogger(__package__)

CONF_UNIT_ID: Final = "unit_id"
CONF_MODEL: Final = "model"
CONF_DEBUG: Final = "debug"

DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1

MANUFACTURER: Final = "LG"

# A heat pump changes slowly, but the compressor and the pumps do not: poll the
# measurements often and the setpoints rarely.
SCAN_INTERVAL: Final = timedelta(seconds=10)
SETTINGS_SCAN_INTERVAL: Final = timedelta(seconds=60)
