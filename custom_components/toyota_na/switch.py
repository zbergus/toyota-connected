"""Switch platform for Toyota Connected Services."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaBaseEntity
from .client import ToyotaClient
from .client.models import ChargingStatus, RemoteCommand, VehicleStatus
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toyota switch entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: ToyotaClient = entry_data["client"]
    coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]] = entry_data["coordinator"]

    entities: list[SwitchEntity] = []
    for vin, vehicle in (coordinator.data or {}).items():
        if vehicle.is_electric:
            entities.append(ToyotaChargingSwitch(coordinator, client, vin))
        entities.append(ToyotaClimateSwitch(coordinator, client, vin))
        entities.append(ToyotaHazardSwitch(coordinator, client, vin))

    async_add_entities(entities)


class ToyotaChargingSwitch(ToyotaBaseEntity, SwitchEntity):
    """Switch to start or stop EV charging immediately."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        client: ToyotaClient,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "immediate_charge")
        self._client = client
        self._attr_name = "Immediate Charging"

    @property
    def is_on(self) -> bool:
        v = self.vehicle
        return (v.electric.charging_status == ChargingStatus.CHARGING) if (v and v.electric) else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        v = self.vehicle
        reg = v.region if v else "CA"
        _LOGGER.info("Sending immediate charging start command for %s", self._vin)
        await self._client.send_remote_command(self._vin, RemoteCommand.IMMEDIATE_CHARGE, region=reg)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        v = self.vehicle
        reg = v.region if v else "CA"
        _LOGGER.info("Sending charge stop command for %s", self._vin)
        await self._client.send_remote_command(self._vin, RemoteCommand.CHARGE_STOP, region=reg)
        await self.coordinator.async_request_refresh()


class ToyotaClimateSwitch(ToyotaBaseEntity, SwitchEntity):
    """Switch to toggle remote cabin pre-conditioning."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:air-conditioner"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        client: ToyotaClient,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "climate_preconditioning")
        self._client = client
        self._attr_name = "Climate Pre-conditioning"

    @property
    def is_on(self) -> bool:
        v = self.vehicle
        return bool(v.climate_active) if v else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        v = self.vehicle
        reg = v.region if v else "CA"
        _LOGGER.info("Activating remote climate pre-conditioning for %s", self._vin)
        await self._client.send_remote_command(self._vin, RemoteCommand.ENGINE_START, region=reg)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        v = self.vehicle
        reg = v.region if v else "CA"
        _LOGGER.info("Stopping remote climate pre-conditioning for %s", self._vin)
        await self._client.send_remote_command(self._vin, RemoteCommand.ENGINE_STOP, region=reg)
        await self.coordinator.async_request_refresh()


class ToyotaHazardSwitch(ToyotaBaseEntity, SwitchEntity):
    """Switch to trigger hazard flasher lights."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:car-emergency"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        client: ToyotaClient,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "hazard_lights")
        self._client = client
        self._attr_name = "Hazard Lights"
        self._is_active = False

    @property
    def is_on(self) -> bool:
        return self._is_active

    async def async_turn_on(self, **kwargs: Any) -> None:
        v = self.vehicle
        reg = v.region if v else "CA"
        self._is_active = True
        self.async_write_ha_state()
        await self._client.send_remote_command(self._vin, RemoteCommand.HAZARD_ON, region=reg)

    async def async_turn_off(self, **kwargs: Any) -> None:
        v = self.vehicle
        reg = v.region if v else "CA"
        self._is_active = False
        self.async_write_ha_state()
        await self._client.send_remote_command(self._vin, RemoteCommand.HAZARD_OFF, region=reg)
