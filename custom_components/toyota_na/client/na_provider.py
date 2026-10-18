"""North American regional provider (USA, Canada, Mexico) for Toyota Connected Services."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .auth import ToyotaAuth
from .base_provider import ToyotaRegionProvider
from .graphql import (
    GET_VEHICLE_STATUS_QUERY,
    POST_CHARGE_SETTINGS_MUTATION,
    SEND_REMOTE_COMMAND_MUTATION,
    ToyotaAppSyncWebSocket,
    execute_graphql,
    parse_appsync_vehicle_status,
)
from .models import (
    RemoteCommand,
    VehicleGeneration,
    VehicleStatus,
)
from .rest import ToyotaRestClient

_LOGGER = logging.getLogger(__name__)


class NorthAmericaProvider(ToyotaRegionProvider):
    """Regional backend provider for North America (specifically targeting Canada and USA)."""

    def __init__(
        self,
        token_callback: Callable[[dict[str, Any]], None] | None = None,
        initial_tokens: dict[str, Any] | None = None,
    ) -> None:
        self.auth = ToyotaAuth(token_callback=token_callback, initial_tokens=initial_tokens)
        self.rest = ToyotaRestClient(self.auth)
        self.ws: ToyotaAppSyncWebSocket | None = None

    @property
    def region_code(self) -> str:
        return "na"

    async def login(
        self,
        username: str,
        password: str | None = None,
        otp: str | None = None,
    ) -> str | dict[str, Any] | None:
        return await self.auth.authorize(username, password, otp=otp)

    async def request_tokens(self, code: str) -> None:
        await self.auth.request_tokens(code)

    async def check_tokens(self) -> None:
        await self.auth.check_tokens()

    def get_tokens(self) -> dict[str, Any]:
        return self.auth.get_tokens()

    def set_tokens(self, tokens: dict[str, Any]) -> None:
        self.auth.set_tokens(tokens)

    async def get_user_vehicles(self) -> list[VehicleStatus]:
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
        # For 24MM (bZ4X) or 21MM, AppSync query returns complete telemetry & state
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

        # Telemetry enrichment
        try:
            telemetry = await self.rest.get_telemetry(vehicle.vin, vehicle.generation.value, vehicle.region)
            if telemetry and vehicle.odometer_km is None:
                odo = telemetry.get("odometer")
                if odo is not None:
                    vehicle.odometer_km = float(odo)
        except Exception as e:
            _LOGGER.debug("Telemetry fetch failed: %s", e)

        return vehicle

    async def send_remote_command(self, vin: str, command: RemoteCommand) -> dict[str, Any]:
        variables = {
            "command": command.value,
            "autoFixCommands": [],
        }
        return await execute_graphql(
            self.auth,
            SEND_REMOTE_COMMAND_MUTATION,
            variables,
            vin=vin,
            region="CA",
        )

    async def set_charge_limit(self, vin: str, target_percent: int) -> dict[str, Any]:
        variables = {"chargingTargetLimit": target_percent}
        return await execute_graphql(
            self.auth,
            POST_CHARGE_SETTINGS_MUTATION,
            variables,
            vin=vin,
            region="CA",
        )

    async def set_ac_current_limit(self, vin: str, max_amps: int) -> dict[str, Any]:
        variables = {"currentCharge": max_amps}
        return await execute_graphql(
            self.auth,
            POST_CHARGE_SETTINGS_MUTATION,
            variables,
            vin=vin,
            region="CA",
        )

    async def start_realtime_listener(
        self,
        vins: list[str],
        callback: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self.ws = ToyotaAppSyncWebSocket(self.auth, callback)
        await self.ws.start(vins, region="CA")

    async def stop_realtime_listener(self) -> None:
        if self.ws:
            await self.ws.stop()
            self.ws = None
