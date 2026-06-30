"""Constants for the Bluebot integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "bluebot"
MANUFACTURER = "Bluebot"

CONF_API_KEY = "api_key"
CONF_FLOW_SCAN_INTERVAL = "flow_scan_interval"
CONF_TOTALS_SCAN_INTERVAL = "totals_scan_interval"

# Real-time flow poll (one /flow/latest call for all meters) and the slower
# cumulative-total poll (per-meter resolution=total).
DEFAULT_FLOW_SCAN_INTERVAL = timedelta(seconds=30)
DEFAULT_TOTALS_SCAN_INTERVAL = timedelta(minutes=5)

FLOW_SCAN_MIN = 10
FLOW_SCAN_MAX = 600
TOTALS_SCAN_MIN = 60
TOTALS_SCAN_MAX = 3600

# Meters emit datapoints only while water flows; once the newest datapoint is
# older than the freshness window we report 0 GPM. Scaled to the poll interval
# (>= 3 polls) but never below 90 s.
MIN_FRESHNESS = timedelta(seconds=90)
FRESHNESS_POLL_FACTOR = 3

# Below this rate (gal/min) the meter is treated as not flowing — avoids a
# flapping binary sensor around residual near-zero readings.
FLOW_EPSILON = 0.05
