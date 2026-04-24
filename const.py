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

# ── Problem-detection thresholds ────────────────────────────────────────────

# "More than two inverters not reporting" — strictly greater than this.
MAX_MISSING_INVERTERS: Final = 2

# A panel is underperforming if its power is below this ratio of the other
# panels' mean power. This is the default — the user can override it via
# the options flow (CONF_UNDERPERFORMANCE_PERCENT).
UNDERPERFORMANCE_RATIO: Final = 0.10

# Only compare panel power when the *others'* mean is at least this many
# watts, otherwise morning ramp-up / evening wind-down and shade produce
# meaningless ratios. The user-requested gate is "average higher than 25 W".
MIN_MEAN_POWER_FOR_RATIO_CHECK: Final = 25.0  # watts

# Daylight-window definition: we only flag "inverter offline" problems once
# the sun has climbed past this elevation OR it's been this long past
# sunrise — whichever comes first.
DAYLIGHT_ELEVATION_DEG: Final = 10.0
DAYLIGHT_POST_SUNRISE_MINUTES: Final = 60

# ── Options-flow keys ───────────────────────────────────────────────────────

# List of panel IDs excluded from both underperformance and missing-inverter
# checks. Typical use: a microinverter that physically only has one panel
# attached, so its unused channel reports 0 W permanently.
CONF_EXCLUDED_PANELS: Final = "excluded_panels"

# Underperformance threshold, expressed as a percent (1–100) in the UI —
# easier to reason about than a 0.0–1.0 ratio. Stored as an int; the
# binary sensor divides by 100 before comparing.
CONF_UNDERPERFORMANCE_PERCENT: Final = "underperformance_percent"
MIN_UNDERPERFORMANCE_PERCENT: Final = 1
MAX_UNDERPERFORMANCE_PERCENT: Final = 100
