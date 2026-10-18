"""Base entity for Toyota Connected Services."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from toyota_connected.models import VehicleStatus

from .const import DOMAIN


class ToyotaBaseEntity(CoordinatorEntity[DataUpdateCoordinator[dict[str, VehicleStatus]]]):
    """Base class for all Toyota entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, VehicleStatus]],
        vin: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._vin = vin
        self._attr_unique_id = f"{DOMAIN}_{vin}_{unique_suffix}"

    @property
    def vehicle(self) -> VehicleStatus | None:
        """Return the current vehicle status snapshot."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._vin)

    @property
    def device_info(self) -> DeviceInfo:
        """Link entity to vehicle device registry entry."""
        v = self.vehicle
        model = v.model_name if v else "Vehicle"
        year = v.model_year if v else "2024"
        mfg = v.manufacturer if v else "Toyota"
        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            name=f"{year} {model}",
            manufacturer=mfg,
            model=model,
            serial_number=self._vin,
        )
