"""Select platform for Toyota Connected Services EV settings."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaBaseEntity
from .client import ToyotaRegionProvider
from .client.models import VehicleStatus
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TARGET_LIMIT_OPTIONS = ["50%", "60%", "70%", "80%", "90%", "100%"]
AC_CURRENT_OPTIONS = ["8 A", "16 A", "32 A", "Max"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toyota select entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    provider: ToyotaRegionProvider = entry_data["provider"]
    coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]] = entry_data["coordinator"]

    entities: list[SelectEntity] = []
    for vin, vehicle in (coordinator.data or {}).items():
        if vehicle.is_electric:
            entities.append(ToyotaTargetChargeLimitSelect(coordinator, provider, vin))
            entities.append(ToyotaACCurrentLimitSelect(coordinator, provider, vin))

    async_add_entities(entities)


class ToyotaTargetChargeLimitSelect(ToyotaBaseEntity, SelectEntity):
    """Select entity for EV target charge limit percentage (e.g. 80%)."""

    _attr_icon = "mdi:battery-charging-high"
    _attr_options = TARGET_LIMIT_OPTIONS

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        provider: ToyotaRegionProvider,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "target_charge_limit")
        self._provider = provider
        self._attr_name = "Target Charge Limit"

    @property
    def current_option(self) -> str | None:
        v = self.vehicle
        if not v or not v.electric or v.electric.target_charge_limit is None:
            return None
        return f"{v.electric.target_charge_limit}%"

    async def async_select_option(self, option: str) -> None:
        percent = int(option.replace("%", "").strip())
        _LOGGER.info("Setting target charge limit for %s to %d%%", self._vin, percent)
        await self._provider.set_charge_limit(self._vin, percent)
        await self.coordinator.async_request_refresh()


class ToyotaACCurrentLimitSelect(ToyotaBaseEntity, SelectEntity):
    """Select entity for max AC charging amperage."""

    _attr_icon = "mdi:current-ac"
    _attr_options = AC_CURRENT_OPTIONS

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        provider: ToyotaRegionProvider,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "ac_current_limit")
        self._provider = provider
        self._attr_name = "AC Charging Current Limit"

    @property
    def current_option(self) -> str | None:
        v = self.vehicle
        if not v or not v.electric or v.electric.max_ac_current_amps is None:
            return None
        val = v.electric.max_ac_current_amps
        return "Max" if val >= 127 else f"{val} A"

    async def async_select_option(self, option: str) -> None:
        amps = 127 if option == "Max" else int(option.replace("A", "").strip())
        _LOGGER.info("Setting max AC current limit for %s to %s", self._vin, option)
        await self._provider.set_ac_current_limit(self._vin, amps)
        await self.coordinator.async_request_refresh()
