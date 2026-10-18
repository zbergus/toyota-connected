"""Lock platform for Toyota Connected Services."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from toyota_connected import ToyotaRegionProvider
from toyota_connected.models import RemoteCommand, VehicleStatus

from .base_entity import ToyotaBaseEntity
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
        self._is_locking: bool = False
        self._is_unlocking: bool = False
        self._refresh_task: asyncio.Task[None] | None = None

    @property
    def is_locked(self) -> bool:
        if self._optimistic_locked is not None:
            return self._optimistic_locked
        v = self.vehicle
        if not v:
            return False
        known_locks = [
            d.locked
            for d in (
                v.driver_door,
                v.passenger_door,
                v.rear_driver_door,
                v.rear_passenger_door,
            )
            if d.locked is not None
        ]
        if not known_locks:
            return False
        return all(known_locks)

    @property
    def is_locking(self) -> bool:
        return self._is_locking

    @property
    def is_unlocking(self) -> bool:
        return self._is_unlocking

    def _set_vehicle_door_locks(self, locked: bool) -> None:
        """Update door lock states in the cached vehicle status object."""
        v = self.vehicle
        if v:
            v.driver_door.locked = locked
            v.passenger_door.locked = locked
            v.rear_driver_door.locked = locked
            v.rear_passenger_door.locked = locked
            v.hatch.locked = locked

    async def async_lock(self, **kwargs: Any) -> None:
        self._is_locking = True
        self.async_write_ha_state()
        try:
            _LOGGER.info("Sending door lock command for %s", self._vin)
            await self._provider.send_remote_command(self._vin, RemoteCommand.DOOR_LOCK)
            self._optimistic_locked = True
            self._set_vehicle_door_locks(True)
        except Exception:
            self._optimistic_locked = None
            raise
        finally:
            self._is_locking = False
            self.async_write_ha_state()

        # Schedule background refresh to allow the car's cellular DCM to sync with cloud
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

        async def _delayed_refresh() -> None:
            try:
                await asyncio.sleep(10)
                await self.coordinator.async_request_refresh()
            except asyncio.CancelledError:
                pass
            finally:
                self._optimistic_locked = None
                self.async_write_ha_state()

        if hasattr(self, "hass") and self.hass:
            self._refresh_task = self.hass.async_create_background_task(
                _delayed_refresh(), f"toyota_lock_refresh_{self._vin}"
            )
        else:
            self._refresh_task = asyncio.create_task(_delayed_refresh())

    async def async_unlock(self, **kwargs: Any) -> None:
        self._is_unlocking = True
        self.async_write_ha_state()
        try:
            _LOGGER.info("Sending door unlock command for %s", self._vin)
            await self._provider.send_remote_command(self._vin, RemoteCommand.DOOR_UNLOCK)
            self._optimistic_locked = False
            self._set_vehicle_door_locks(False)
        except Exception:
            self._optimistic_locked = None
            raise
        finally:
            self._is_unlocking = False
            self.async_write_ha_state()

        # Schedule background refresh to allow the car's cellular DCM to sync with cloud
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

        async def _delayed_refresh() -> None:
            try:
                await asyncio.sleep(10)
                await self.coordinator.async_request_refresh()
            except asyncio.CancelledError:
                pass
            finally:
                self._optimistic_locked = None
                self.async_write_ha_state()

        if hasattr(self, "hass") and self.hass:
            self._refresh_task = self.hass.async_create_background_task(
                _delayed_refresh(), f"toyota_unlock_refresh_{self._vin}"
            )
        else:
            self._refresh_task = asyncio.create_task(_delayed_refresh())
