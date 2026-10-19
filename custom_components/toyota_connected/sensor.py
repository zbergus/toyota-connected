"""Sensor platform for Toyota Connected Services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from toyota_connected.models import ChargingStatus, VehicleGeneration, VehicleStatus

from .base_entity import ToyotaBaseEntity
from .const import DOMAIN


@dataclass(frozen=True)
class ToyotaSensorEntityDescription(SensorEntityDescription):
    """Describes a Toyota sensor entity with value extractor."""

    value_fn: Callable[[VehicleStatus], float | int | str | None] = lambda _: None
    is_ev_only: bool = False
    is_fuel_only: bool = False
    generation_filter: tuple[VehicleGeneration, ...] | None = None


SENSOR_DESCRIPTIONS: tuple[ToyotaSensorEntityDescription, ...] = (
    # EV Battery Sensors (bZ4X)
    ToyotaSensorEntityDescription(
        key="battery_level",
        name="Battery Level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.electric.battery_level if v.electric else None,
        is_ev_only=True,
    ),
    ToyotaSensorEntityDescription(
        key="usable_battery_level",
        name="Usable Battery Capacity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.electric.charge_remaining_amount if v.electric else None,
        is_ev_only=True,
    ),
    ToyotaSensorEntityDescription(
        key="ev_range",
        name="EV Range (AC Off)",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: (
            round(v.electric.range_km, 1) if (v.electric and v.electric.range_km) else None
        ),
        is_ev_only=True,
    ),
    ToyotaSensorEntityDescription(
        key="ev_range_ac_on",
        name="EV Range (AC On)",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: (
            round(v.electric.range_ac_on_km, 1)
            if (v.electric and v.electric.range_ac_on_km)
            else None
        ),
        is_ev_only=True,
    ),
    ToyotaSensorEntityDescription(
        key="charging_power",
        name="Charging Power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: (
            v.electric.charging_power_kw
            if (v.electric and v.electric.charging_power_kw is not None)
            else (
                0.0
                if (v.electric and v.electric.charging_status != ChargingStatus.CHARGING)
                else (
                    round(
                        (max(1.0, 100.0 - (v.electric.battery_level or 50.0)) / 100.0 * 65.0)
                        / (v.electric.time_to_full_minutes / 60.0),
                        1,
                    )
                    if (
                        v.electric
                        and v.electric.charging_status == ChargingStatus.CHARGING
                        and v.electric.time_to_full_minutes
                        and v.electric.time_to_full_minutes > 0
                    )
                    else (
                        6.6
                        if (v.electric and v.electric.charging_status == ChargingStatus.CHARGING)
                        else None
                    )
                )
            )
        ),
        is_ev_only=True,
    ),
    ToyotaSensorEntityDescription(
        key="time_to_full",
        name="Remaining Charge Time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: (
            v.electric.time_to_full_minutes
            if (v.electric and v.electric.time_to_full_minutes is not None)
            else (
                0
                if (v.electric and v.electric.charging_status != ChargingStatus.CHARGING)
                else None
            )
        ),
        is_ev_only=True,
    ),
    ToyotaSensorEntityDescription(
        key="time_to_80_percent",
        name="Remaining Charge Time to 80%",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.electric.time_to_80_minutes if v.electric else None,
        is_ev_only=True,
        generation_filter=(VehicleGeneration.MM24, VehicleGeneration.MM25),
    ),
    # Fuel Telemetry (Gasoline & Hybrid vehicles)
    ToyotaSensorEntityDescription(
        key="fuel_level",
        name="Fuel Level",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:gas-station",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.fuel_level_percent,
        is_fuel_only=True,
    ),
    ToyotaSensorEntityDescription(
        key="fuel_range",
        name="Distance to Empty",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: round(v.fuel_range_km, 1) if v.fuel_range_km is not None else None,
        is_fuel_only=True,
    ),
    # Odometer & Telemetry
    ToyotaSensorEntityDescription(
        key="odometer",
        name="Odometer",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda v: round(v.odometer_km, 1) if v.odometer_km is not None else None,
    ),
    # Tire Pressure (kPa for Canada)
    ToyotaSensorEntityDescription(
        key="tire_front_left",
        name="Front Left Tire Pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.tire_front_left.kpa,
    ),
    ToyotaSensorEntityDescription(
        key="tire_front_right",
        name="Front Right Tire Pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.tire_front_right.kpa,
    ),
    ToyotaSensorEntityDescription(
        key="tire_rear_left",
        name="Rear Left Tire Pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.tire_rear_left.kpa,
    ),
    ToyotaSensorEntityDescription(
        key="tire_rear_right",
        name="Rear Right Tire Pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.tire_rear_right.kpa,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toyota sensor entities from a config entry."""
    coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]] = hass.data[DOMAIN][
        entry.entry_id
    ]["coordinator"]

    entities: list[ToyotaSensor] = []
    for vin, vehicle in (coordinator.data or {}).items():
        for description in SENSOR_DESCRIPTIONS:
            if description.is_ev_only and not vehicle.is_electric:
                continue
            if description.is_fuel_only and vehicle.is_electric:
                continue
            if (
                description.generation_filter
                and vehicle.generation not in description.generation_filter
            ):
                continue
            entities.append(ToyotaSensor(coordinator, vin, description))

    async_add_entities(entities)


class ToyotaSensor(ToyotaBaseEntity, SensorEntity):
    """Representation of a Toyota sensor."""

    entity_description: ToyotaSensorEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        vin: str,
        description: ToyotaSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, vin, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        """Return sensor value extracted from current vehicle snapshot."""
        if not self.vehicle:
            return None
        return self.entity_description.value_fn(self.vehicle)
