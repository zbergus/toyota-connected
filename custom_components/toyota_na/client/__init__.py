"""Modern, unified Toyota Connected Services API client."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .auth import ToyotaAuth
from .graphql import (
    GET_VEHICLE_STATUS_QUERY,
    POST_CHARGE_SETTINGS_MUTATION,
    SEND_REMOTE_COMMAND_MUTATION,
    ToyotaAppSyncWebSocket,
    execute_graphql,
    parse_appsync_vehicle_status,
)
from .models import (
    ChargingStatus,
    ElectricVehicleStatus,
    OpeningState,
    RemoteCommand,
    TirePressure,
    VehicleGeneration,
    VehicleStatus,
)
from .rest import ToyotaRestClient

_LOGGER = logging.getLogger(__name__)


class ToyotaClient:
    """Unified client for interacting with Toyota Connected Services."""

    def __init__(self, auth: ToyotaAuth) -> None:
        self.auth = auth
        self.rest = ToyotaRestClient(auth)
        self.ws: ToyotaAppSyncWebSocket | None = None

    async def get_user_vehicles(self) -> list[VehicleStatus]:
        """Fetch vehicles registered to account and initialize their models."""
        raw_list = await self.rest.get_vehicle_list()
        vehicles: list[VehicleStatus] = []

        for item in raw_list:
            vin = item.get("vin")
            if not vin:
                continue

            gen_str = item.get("generation", "UNKNOWN")
            try:
                gen = VehicleGeneration(gen_str)
            except ValueError:
                gen = VehicleGeneration.UNKNOWN

            region = item.get("region") or "CA"
            is_ev = bool(item.get("evVehicle") or item.get("fuelType") in ("E", "I"))
            sub_status = item.get("remoteSubscriptionStatus") == "ACTIVE" or item.get("subscriptionStatus") == "ACTIVE"

            v = VehicleStatus(
                vin=vin,
                model_name=item.get("modelName") or "Toyota Vehicle",
                model_year=str(item.get("modelYear") or "2024"),
                generation=gen,
                region=region,
                subscribed=sub_status,
                is_electric=is_ev,
                backdoor_type=item.get("backdoorType") or "hatch",
            )
            vehicles.append(v)

        return vehicles

    async def update_vehicle_status(self, vehicle: VehicleStatus) -> VehicleStatus:
        """Fetch latest vehicle state via AppSync GraphQL (for 24MM) and telemetry."""
        # For 24MM (e.g. bZ4X) or 21MM, AppSync query returns complete telemetry & state
        if vehicle.generation in (VehicleGeneration.MM24, VehicleGeneration.MM21, VehicleGeneration.CY17PLUS):
            try:
                result = await execute_graphql(
                    self.auth,
                    GET_VEHICLE_STATUS_QUERY,
                    {"vin": vehicle.vin},
                    vin=vehicle.vin,
                    region=vehicle.region,
                )
                if result:
                    parse_appsync_vehicle_status(result, vehicle)
            except Exception as e:
                _LOGGER.debug("AppSync GetVehicleStatus query failed for %s: %s", vehicle.vin, e)

        # Telemetry fallback/enrichment
        try:
            telemetry = await self.rest.get_telemetry(vehicle.vin, vehicle.generation.value, vehicle.region)
            if telemetry and vehicle.odometer_km is None:
                odo = telemetry.get("odometer")
                if odo is not None:
                    vehicle.odometer_km = float(odo)
        except Exception as e:
            _LOGGER.debug("Telemetry fetch failed: %s", e)

        return vehicle

    async def send_remote_command(self, vin: str, command: RemoteCommand, region: str = "CA") -> dict[str, Any]:
        """Dispatch remote vehicle command via AppSync GraphQL mutation."""
        variables = {
            "command": command.value,
            "autoFixCommands": [],
        }
        return await execute_graphql(
            self.auth,
            SEND_REMOTE_COMMAND_MUTATION,
            variables,
            vin=vin,
            region=region,
        )

    async def set_charge_limit(self, vin: str, target_percent: int, region: str = "CA") -> dict[str, Any]:
        """Update EV charge limit target percentage (bZ4X)."""
        variables = {
            "chargingTargetLimit": target_percent,
        }
        return await execute_graphql(
            self.auth,
            POST_CHARGE_SETTINGS_MUTATION,
            variables,
            vin=vin,
            region=region,
        )

    async def set_ac_current_limit(self, vin: str, max_amps: int, region: str = "CA") -> dict[str, Any]:
        """Update EV max AC charging current amperage (bZ4X)."""
        variables = {
            "currentCharge": max_amps,
        }
        return await execute_graphql(
            self.auth,
            POST_CHARGE_SETTINGS_MUTATION,
            variables,
            vin=vin,
            region=region,
        )
