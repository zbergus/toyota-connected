"""Diagnostics support for Toyota Connected Services with strict credential redaction."""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {
    "access_token",
    "refresh_token",
    "id_token",
    "tokens",
    "guid",
    "device_id",
    "password",
    "username",
    "latitude",
    "longitude",
    "last_parked_latitude",
    "last_parked_longitude",
    "title",
    "unique_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry with sensitive credentials redacted."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    vehicles_data = {}
    if coordinator.data:
        for vin, v in coordinator.data.items():
            vehicles_data[vin[:8] + "..." + vin[-4:]] = {
                "model_name": v.model_name,
                "model_year": v.model_year,
                "generation": v.generation.value,
                "region": v.region,
                "subscribed": v.subscribed,
                "is_electric": v.is_electric,
                "odometer_km": v.odometer_km,
                "climate_active": v.climate_active,
                "electric": dataclasses.asdict(v.electric) if v.electric else None,
            }

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "vehicles": async_redact_data(vehicles_data, TO_REDACT),
    }
