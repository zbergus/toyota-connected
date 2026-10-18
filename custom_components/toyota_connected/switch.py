"""Switch platform for Toyota Connected Services."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from toyota_connected import ToyotaRegionProvider
from toyota_connected.models import ChargingStatus, RemoteCommand, VehicleStatus

from .base_entity import ToyotaBaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toyota switch entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    provider: ToyotaRegionProvider = entry_data["provider"]
    coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]] = entry_data["coordinator"]

    entities: list[SwitchEntity] = []
    for vin, vehicle in (coordinator.data or {}).items():
        if vehicle.is_electric:
            entities.append(ToyotaChargingSwitch(coordinator, provider, vin))
        entities.append(ToyotaClimateSwitch(coordinator, provider, vin))
        entities.append(ToyotaHazardSwitch(coordinator, provider, vin))

    async_add_entities(entities)


class ToyotaChargingSwitch(ToyotaBaseEntity, SwitchEntity):
    """Switch to start or stop EV charging immediately."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        provider: ToyotaRegionProvider,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "immediate_charge")
        self._provider = provider
        self._attr_name = "Immediate Charging"

    @property
    def is_on(self) -> bool:
        v = self.vehicle
        return (
            (v.electric.charging_status == ChargingStatus.CHARGING) if (v and v.electric) else False
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        _LOGGER.info("Sending immediate charging start command for %s", self._vin)
        await self._provider.send_remote_command(self._vin, RemoteCommand.IMMEDIATE_CHARGE)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        _LOGGER.info("Sending charge stop command for %s", self._vin)
        await self._provider.send_remote_command(self._vin, RemoteCommand.CHARGE_STOP)
        await self.coordinator.async_request_refresh()


class ToyotaClimateSwitch(ToyotaBaseEntity, SwitchEntity):
    """Switch to toggle remote start / cabin climate."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:air-conditioner"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        provider: ToyotaRegionProvider,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "remote_start")
        self._provider = provider
        self._attr_name = "Remote Start"

    @property
    def is_on(self) -> bool:
        v = self.vehicle
        return bool(v.climate_active) if v else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        _LOGGER.info("Activating remote start for %s", self._vin)
        await self._provider.send_remote_command(self._vin, RemoteCommand.ENGINE_START)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        _LOGGER.info("Stopping remote start for %s", self._vin)
        await self._provider.send_remote_command(self._vin, RemoteCommand.ENGINE_STOP)
        await self.coordinator.async_request_refresh()


class ToyotaHazardSwitch(ToyotaBaseEntity, SwitchEntity):
    """Switch to trigger hazard flasher lights."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:car-emergency"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        provider: ToyotaRegionProvider,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "hazard_lights")
        self._provider = provider
        self._attr_name = "Hazard Lights"
        self._is_active = False

    @property
    def is_on(self) -> bool:
        return self._is_active

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_active = True
        self.async_write_ha_state()
        await self._provider.send_remote_command(self._vin, RemoteCommand.HAZARD_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_active = False
        self.async_write_ha_state()
        await self._provider.send_remote_command(self._vin, RemoteCommand.HAZARD_OFF)
