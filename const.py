"""Constants for the Zonnepanelen integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "zonnepanelen"
DEFAULT_NAME: Final = "Zonnepanelen"
DEFAULT_SCAN_INTERVAL: Final = 300  # seconds
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 3600

MANUFACTURER: Final = "APsystems"
MODEL_ECU: Final = "ECU-3"
MODEL_INVERTER: Final = "Microinverter"

# Keys stored at the top level of the coordinator data dict that represent
# the whole system (rather than a single panel/inverter).
GLOBAL_KEYS: Final = frozenset({"state", "lifetime", "day", "online", "signal"})

# HTTP timeout for requests against the ECU web interface.
REQUEST_TIMEOUT: Final = 10  # seconds
