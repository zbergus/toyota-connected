"""Constants for Toyota Connected Services integration."""

from __future__ import annotations

DOMAIN = "toyota_connected"
NAME = "Toyota, Lexus & Solterra Connected Services"

# Services
SERVICE_DOOR_LOCK = "door_lock"
SERVICE_DOOR_UNLOCK = "door_unlock"
SERVICE_REFRESH = "refresh"
SERVICE_START_CHARGE = "start_charging"
SERVICE_STOP_CHARGE = "stop_charging"
SERVICE_SET_CHARGE_LIMIT = "set_charge_limit"
SERVICE_CLIMATE_START = "climate_start"
SERVICE_CLIMATE_STOP = "climate_stop"

# Polling Intervals
UPDATE_INTERVAL_SECONDS = 300  # 5 minutes passive poll
