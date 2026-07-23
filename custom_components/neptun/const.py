"""Constants for the Neptun water leak protection integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "neptun"

CONF_COUNTERS = "counters"
CONF_LINES = "lines"
CONF_RETRIES = "retries"
CONF_WIRELESS_RECORD_SIZE = "wireless_record_size"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

ATTRIBUTION = "Data provided by Neptun water leak detector"

PLATFORMS = ["binary_sensor", "sensor", "switch"]

# Used when the controller cannot be reached during start-up and we have no
# status to derive the entity list from.
FALLBACK_LINES = 4
FALLBACK_COUNTERS = 0
