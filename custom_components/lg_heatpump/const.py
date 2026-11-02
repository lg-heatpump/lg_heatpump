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

# Per-request timeout floor, in seconds, asked of the shared Modbus link.
#
# Home Assistant's modbus integration serialises every consumer of one gateway
# behind a single lock, so waiting time adds up instead of overlapping. The
# library default is 10 s. A reply that arrives after the client gave up is read
# as the answer to the NEXT request ("Received unexpected response with
# Transaction ID") and the link drops. 20 s is a floor, not an assignment: the
# link takes the largest value any unit on it asks for, so this never shortens
# anyone else's.
REQUEST_TIMEOUT: Final = 20.0
