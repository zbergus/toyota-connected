"""North American regional provider (USA, Canada, Mexico) for Toyota Connected Services."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .auth import ToyotaAuth
from .base_provider import ToyotaRegionProvider
from .brands import DEFAULT_BRAND, BrandConfig, get_brand
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
    """Regional backend provider for North America (Toyota, Lexus, and Subaru)."""

    def __init__(
        self,
        token_callback: Callable[[dict[str, Any]], None] | None = None,
        initial_tokens: dict[str, Any] | None = None,
        brand: BrandConfig | str = DEFAULT_BRAND,
    ) -> None:
        self.brand = get_brand(brand)
        self.auth = ToyotaAuth(
            token_callback=token_callback,
            initial_tokens=initial_tokens,
            auth_host=self.brand.auth_host,
        )
        self.rest = ToyotaRestClient(self.auth, brand=self.brand)
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
        tokens = self.auth.get_tokens()
        tokens["brand"] = self.brand.brand_id
        return tokens

    def set_tokens(self, tokens: dict[str, Any]) -> None:
        self.auth.set_tokens(tokens)

    async def get_user_vehicles(self) -> list[VehicleStatus]:
        raw_list = await self.rest.get_vehicle_list()

        # Handle empty vehicle discovery bootstrap (Subaru Solterra accounts)
        if not raw_list and self.brand.bootstrap_on_empty:
            _LOGGER.info("Subaru vehicle list empty; running v4/account bootstrap")
            await self.rest.bootstrap_account()
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
                model_name=item.get("modelName") or f"{self.brand.name} Vehicle",
                model_year=str(item.get("modelYear") or "2024"),
                generation=gen,
                region=region,
                manufacturer=self.brand.manufacturer,
                subscribed=sub_status,
                is_electric=is_ev,
                backdoor_type=item.get("backdoorType") or "hatch",
            )
            vehicles.append(v)

        return vehicles

    async def update_vehicle_status(self, vehicle: VehicleStatus) -> VehicleStatus:
        # For 24MM (bZ4X/Solterra) or 21MM, AppSync query returns complete telemetry & state
        if vehicle.generation in (VehicleGeneration.MM25, VehicleGeneration.MM24, VehicleGeneration.MM21, VehicleGeneration.CY17PLUS):
            try:
                result = await execute_graphql(
                    self.auth,
                    GET_VEHICLE_STATUS_QUERY,
                    {"vin": vehicle.vin},
                    vin=vehicle.vin,
                    region=vehicle.region,
                    brand_code=self.brand.code,
                    user_agent=self.brand.user_agent,
                )
                if result:
                    parse_appsync_vehicle_status(result, vehicle)
            except Exception as e:
                _LOGGER.debug("AppSync GetVehicleStatus query failed for %s: %s", vehicle.vin, e)

        # Telemetry enrichment
        try:
            telemetry = await self.rest.get_telemetry(vehicle.vin, vehicle.generation.value, vehicle.region)
            if telemetry:
                if vehicle.odometer_km is None and telemetry.get("odometer") is not None:
                    vehicle.odometer_km = float(telemetry["odometer"])
                if vehicle.fuel_level_percent is None and telemetry.get("fuelLevel") is not None:
                    vehicle.fuel_level_percent = float(telemetry["fuelLevel"])
                if vehicle.fuel_range_km is None and telemetry.get("distanceToEmpty") is not None:
                    vehicle.fuel_range_km = float(telemetry["distanceToEmpty"])
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
            brand_code=self.brand.code,
            user_agent=self.brand.user_agent,
        )

    async def set_charge_limit(self, vin: str, target_percent: int) -> dict[str, Any]:
        variables = {"chargingTargetLimit": target_percent}
        return await execute_graphql(
            self.auth,
            POST_CHARGE_SETTINGS_MUTATION,
            variables,
            vin=vin,
            region="CA",
            brand_code=self.brand.code,
            user_agent=self.brand.user_agent,
        )

    async def set_ac_current_limit(self, vin: str, max_amps: int) -> dict[str, Any]:
        variables = {"currentCharge": max_amps}
        return await execute_graphql(
            self.auth,
            POST_CHARGE_SETTINGS_MUTATION,
            variables,
            vin=vin,
            region="CA",
            brand_code=self.brand.code,
            user_agent=self.brand.user_agent,
        )

    async def start_realtime_listener(
        self,
        vins: list[str],
        callback: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self.ws = ToyotaAppSyncWebSocket(self.auth, callback, brand_code=self.brand.code)
        await self.ws.start(vins, region="CA")

    async def stop_realtime_listener(self) -> None:
        if self.ws:
            await self.ws.stop()
            self.ws = None
