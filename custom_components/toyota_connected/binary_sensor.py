"""Binary sensor platform for Toyota Connected Services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from toyota_connected.models import ChargingStatus, VehicleStatus

from .base_entity import ToyotaBaseEntity
from .const import DOMAIN


@dataclass(frozen=True)
class ToyotaBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Toyota binary sensor entity."""

    is_on_fn: Callable[[VehicleStatus], bool | None] = lambda _: None
    is_ev_only: bool = False


BINARY_SENSOR_DESCRIPTIONS: tuple[ToyotaBinarySensorEntityDescription, ...] = (
    # EV Charging & Plug
    ToyotaBinarySensorEntityDescription(
        key="charging_active",
        name="Battery Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        is_on_fn=lambda v: (
            (v.electric.charging_status == ChargingStatus.CHARGING) if v.electric else False
        ),
        is_ev_only=True,
    ),
    ToyotaBinarySensorEntityDescription(
        key="plug_connected",
        name="Charge Plug Connected",
        device_class=BinarySensorDeviceClass.PLUG,
        is_on_fn=lambda v: v.electric.plug_connected if v.electric else False,
        is_ev_only=True,
    ),
    # Doors
    ToyotaBinarySensorEntityDescription(
        key="driver_door",
        name="Front Driver Door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda v: not v.driver_door.closed,
    ),
    ToyotaBinarySensorEntityDescription(
        key="passenger_door",
        name="Front Passenger Door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda v: not v.passenger_door.closed,
    ),
    ToyotaBinarySensorEntityDescription(
        key="rear_driver_door",
        name="Rear Driver Door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda v: not v.rear_driver_door.closed,
    ),
    ToyotaBinarySensorEntityDescription(
        key="rear_passenger_door",
        name="Rear Passenger Door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda v: not v.rear_passenger_door.closed,
    ),
    ToyotaBinarySensorEntityDescription(
        key="hatch",
        name="Hatch Door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda v: not v.hatch.closed,
    ),
    ToyotaBinarySensorEntityDescription(
        key="hood",
        name="Hood",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda v: not v.hood.closed,
    ),
    # Windows
    ToyotaBinarySensorEntityDescription(
        key="driver_window",
        name="Front Driver Window",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_on_fn=lambda v: not v.driver_window_closed,
    ),
    ToyotaBinarySensorEntityDescription(
        key="passenger_window",
        name="Front Passenger Window",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_on_fn=lambda v: not v.passenger_window_closed,
    ),
    ToyotaBinarySensorEntityDescription(
        key="rear_driver_window",
        name="Rear Driver Window",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_on_fn=lambda v: not v.rear_driver_window_closed,
    ),
    ToyotaBinarySensorEntityDescription(
        key="rear_passenger_window",
        name="Rear Passenger Window",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_on_fn=lambda v: not v.rear_passenger_window_closed,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toyota binary sensor entities from a config entry."""
    coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]] = hass.data[DOMAIN][
        entry.entry_id
    ]["coordinator"]

    entities: list[ToyotaBinarySensor] = []
    for vin, vehicle in (coordinator.data or {}).items():
        for description in BINARY_SENSOR_DESCRIPTIONS:
            if description.is_ev_only and not vehicle.is_electric:
                continue
            entities.append(ToyotaBinarySensor(coordinator, vin, description))

    async_add_entities(entities)


class ToyotaBinarySensor(ToyotaBaseEntity, BinarySensorEntity):
    """Representation of a Toyota binary sensor."""

    entity_description: ToyotaBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        vin: str,
        description: ToyotaBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, vin, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return binary sensor state from current vehicle snapshot."""
        if not self.vehicle:
            return None
        return self.entity_description.is_on_fn(self.vehicle)
