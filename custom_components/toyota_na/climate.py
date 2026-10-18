"""Climate platform for Toyota Connected Services."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaBaseEntity
from .client import ToyotaClient
from .client.models import RemoteCommand, VehicleStatus
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toyota climate entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: ToyotaClient = entry_data["client"]
    coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]] = entry_data["coordinator"]

    entities: list[ClimateEntity] = []
    for vin, vehicle in (coordinator.data or {}).items():
        if vehicle.subscribed:
            entities.append(ToyotaClimate(coordinator, client, vin))

    async_add_entities(entities)


class ToyotaClimate(ToyotaBaseEntity, ClimateEntity):
    """Climate entity for vehicle pre-conditioning."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_min_temp = 16.0
    _attr_max_temp = 28.0
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        client: ToyotaClient,
        vin: str,
    ) -> None:
        super().__init__(coordinator, vin, "climate")
        self._client = client
        self._attr_name = "Climate"
        self._target_temp: float = 21.0

    @property
    def hvac_mode(self) -> HVACMode:
        v = self.vehicle
        return HVACMode.HEAT_COOL if (v and v.climate_active) else HVACMode.OFF

    @property
    def target_temperature(self) -> float:
        return self._target_temp

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get("temperature")
        if temp is not None:
            self._target_temp = float(temp)
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        v = self.vehicle
        reg = v.region if v else "CA"
        if hvac_mode == HVACMode.HEAT_COOL:
            _LOGGER.info("Starting climate pre-conditioning for %s", self._vin)
            await self._client.send_remote_command(self._vin, RemoteCommand.ENGINE_START, region=reg)
        else:
            _LOGGER.info("Stopping climate pre-conditioning for %s", self._vin)
            await self._client.send_remote_command(self._vin, RemoteCommand.ENGINE_STOP, region=reg)
        await self.coordinator.async_request_refresh()
