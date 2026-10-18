"""Lock platform for Toyota Connected Services."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaBaseEntity
from .client import ToyotaRegionProvider
from .client.models import RemoteCommand, VehicleStatus
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toyota door lock entity from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    provider: ToyotaRegionProvider = entry_data["provider"]
    coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]] = entry_data["coordinator"]

    entities: list[LockEntity] = []
    for vin, vehicle in (coordinator.data or {}).items():
        if vehicle.subscribed:
            entities.append(ToyotaDoorLock(coordinator, provider, vin))

    async_add_entities(entities)


class ToyotaDoorLock(ToyotaBaseEntity, LockEntity):
    """Representation of vehicle door locks."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        provider: ToyotaRegionProvider,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "door_lock")
        self._provider = provider
        self._attr_name = "Door Lock"
        self._optimistic_locked: bool | None = None

    @property
    def is_locked(self) -> bool:
        if self._optimistic_locked is not None:
            return self._optimistic_locked
        v = self.vehicle
        if not v:
            return False
        # Consider locked if driver and passenger doors are locked
        return bool(v.driver_door.locked and v.passenger_door.locked)

    async def async_lock(self, **kwargs: Any) -> None:
        self._optimistic_locked = True
        self.async_write_ha_state()
        try:
            _LOGGER.info("Sending door lock command for %s", self._vin)
            await self._provider.send_remote_command(self._vin, RemoteCommand.DOOR_LOCK)
        finally:
            self._optimistic_locked = None
            await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        self._optimistic_locked = False
        self.async_write_ha_state()
        try:
            _LOGGER.info("Sending door unlock command for %s", self._vin)
            await self._provider.send_remote_command(self._vin, RemoteCommand.DOOR_UNLOCK)
        finally:
            self._optimistic_locked = None
            await self.coordinator.async_request_refresh()
