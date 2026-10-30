"""North American regional provider (USA, Canada, Mexico) for Toyota Connected Services."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .auth import ToyotaAuth
from .base_provider import ToyotaRegionProvider
from .brands import DEFAULT_BRAND, BrandConfig, get_brand
from .graphql import (
    CONFIRM_SUBSCRIPTION_MUTATION,
    GET_VEHICLE_STATUS_QUERY,
    POST_CHARGE_SETTINGS_MUTATION,
    PRE_WAKE_MUTATION,
    REFRESH_STATUS_MUTATION,
    SEND_REMOTE_COMMAND_MUTATION,
    ToyotaAppSyncWebSocket,
    VehicleNotFoundOnAppSync,
    execute_graphql,
    parse_appsync_vehicle_status,
)
from .models import (
    RemoteCommand,
    VehicleGeneration,
    VehicleStatus,
)
from .rest import (
    ToyotaRestClient,
    parse_rest_electric_status,
    parse_rest_telemetry,
    parse_rest_vehicle_status,
)

_LOGGER = logging.getLogger(__name__)


# Capability reporting for vehicle-support triage. Strictly allow-listed: only booleans, 0/1
# flags and the fixed strings ACTIVE, INACTIVE, E and I are ever logged, so VINs, GUIDs, names
# and coordinates cannot leak.
_CAPABILITY_SECTIONS = ("features", "extendedCapabilities", "remoteServiceCapabilities")
_CAPABILITY_TOP_LEVEL = ("evVehicle", "fuelType", "remoteSubscriptionStatus", "subscriptionStatus")


def _is_flag(value: Any) -> bool:
    return isinstance(value, bool) or (isinstance(value, int) and value in (0, 1))


def summarize_capabilities(item: dict[str, Any]) -> dict[str, Any]:
    """Return a log-safe summary of the capability flags Toyota reports for a vehicle."""
    summary: dict[str, Any] = {}
    for key, value in item.items():
        if key.endswith("Capable") and _is_flag(value):
            summary[key] = value
    for key in _CAPABILITY_TOP_LEVEL:
        value = item.get(key)
        if _is_flag(value) or (
            isinstance(value, str) and value in ("ACTIVE", "INACTIVE", "E", "I")
        ):
            summary[key] = value
    for section in _CAPABILITY_SECTIONS:
        data = item.get(section)
        if isinstance(data, dict):
            flags = {k: v for k, v in data.items() if _is_flag(v)}
            if flags:
                summary[section] = flags
    return summary


class NorthAmericaProvider(ToyotaRegionProvider):
    """Regional backend provider for North America (Toyota, Lexus, and Subaru)."""

    def __init__(
        self,
        token_callback: Callable[[dict[str, Any]], None] | None = None,
        initial_tokens: dict[str, Any] | None = None,
        brand: BrandConfig | str = DEFAULT_BRAND,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.brand = get_brand(brand)
        self._session = session
        self.auth = ToyotaAuth(
            token_callback=token_callback,
            initial_tokens=initial_tokens,
            auth_host=self.brand.auth_host,
            session=session,
        )
        self.rest = ToyotaRestClient(self.auth, brand=self.brand, session=session)
        self.ws: ToyotaAppSyncWebSocket | None = None
        self._vin_regions: dict[str, str] = {}

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
                _LOGGER.warning(
                    "Unrecognised vehicle generation %r (model year %s); loading as UNKNOWN. "
                    "Please open a vehicle support issue with this line.",
                    gen_str,
                    item.get("modelYear"),
                )
                gen = VehicleGeneration.UNKNOWN

            region = item.get("region") or "CA"
            self._vin_regions[vin] = region
            _LOGGER.debug(
                "Vehicle capabilities (generation=%s, model_year=%s): %s",
                gen.value,
                item.get("modelYear"),
                summarize_capabilities(item),
            )
            is_ev = bool(item.get("evVehicle") or item.get("fuelType") in ("E", "I"))
            sub_status = (
                item.get("remoteSubscriptionStatus") == "ACTIVE"
                or item.get("subscriptionStatus") == "ACTIVE"
            )

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
        # AppSync GraphQL is used for MM24 and MM25 vehicles that support Stencil.
        # For 21MM and earlier generations, OneAPI REST is the native provider.
        uses_appsync = vehicle.generation in (VehicleGeneration.MM25, VehicleGeneration.MM24)
        if uses_appsync:
            try:
                result = await execute_graphql(
                    self.auth,
                    GET_VEHICLE_STATUS_QUERY,
                    {"vin": vehicle.vin},
                    vin=vehicle.vin,
                    region=vehicle.region,
                    brand_code=self.brand.code,
                    user_agent=self.brand.user_agent,
                    session=self._session,
                )
                if result:
                    parse_appsync_vehicle_status(result, vehicle)
            except VehicleNotFoundOnAppSync:
                _LOGGER.debug(
                    "Vehicle %s not on AppSync Stencil, switching to REST OneAPI", vehicle.vin
                )
                uses_appsync = False
            except (aiohttp.ClientError, RuntimeError, KeyError, ValueError, TypeError) as e:
                _LOGGER.debug("AppSync GetVehicleStatus query failed for %s: %s", vehicle.vin, e)
                uses_appsync = False

        if not uses_appsync:
            # 1. Fetch remote vehicle status (doors, windows, locks, hood, hatch)
            try:
                status_res = await self.rest.get_vehicle_status(vehicle.vin, region=vehicle.region)
                if status_res:
                    parse_rest_vehicle_status(status_res, vehicle)
            except Exception as e:
                _LOGGER.debug("REST vehicle status failed for %s: %s", vehicle.vin, e)

            # 2. Fetch EV electric status (battery SoC, range, charge status, plug)
            if vehicle.is_electric:
                try:
                    elec_res = await self.rest.get_electric_status(
                        vehicle.vin,
                        region=vehicle.region,
                        generation=vehicle.generation.value,
                    )
                    if elec_res:
                        parse_rest_electric_status(elec_res, vehicle)
                except Exception as e:
                    _LOGGER.debug("REST electric status failed for %s: %s", vehicle.vin, e)

        # Telemetry enrichment (odometer, tire pressures, GPS location)
        try:
            telemetry = await self.rest.get_telemetry(
                vehicle.vin, vehicle.generation.value, vehicle.region
            )
            if telemetry:
                parse_rest_telemetry(telemetry, vehicle)
        except Exception as e:
            _LOGGER.debug("Telemetry fetch failed: %s", e)

        return vehicle

    async def send_remote_command(
        self, vin: str, command: RemoteCommand, region: str | None = None
    ) -> dict[str, Any]:
        target_region = region or self._vin_regions.get(vin, "CA")
        try:
            variables: dict[str, Any] = {
                "command": command.value,
                "autoFixCommands": [],
            }
            return await execute_graphql(
                self.auth,
                SEND_REMOTE_COMMAND_MUTATION,
                variables,
                vin=vin,
                region=target_region,
                brand_code=self.brand.code,
                user_agent=self.brand.user_agent,
                session=self._session,
            )
        except (VehicleNotFoundOnAppSync, RuntimeError) as e:
            _LOGGER.debug("AppSync remote command failed, falling back to REST: %s", e)
            return await self.rest.send_remote_command(
                vin, command.value, region=target_region, generation="21MM"
            )

    async def set_charge_limit(
        self, vin: str, target_percent: int, region: str | None = None
    ) -> dict[str, Any]:
        target_region = region or self._vin_regions.get(vin, "CA")
        variables = {"chargingTargetLimit": target_percent}
        return await execute_graphql(
            self.auth,
            POST_CHARGE_SETTINGS_MUTATION,
            variables,
            vin=vin,
            region=target_region,
            brand_code=self.brand.code,
            user_agent=self.brand.user_agent,
            session=self._session,
        )

    async def set_ac_current_limit(
        self, vin: str, max_amps: int, region: str | None = None
    ) -> dict[str, Any]:
        target_region = region or self._vin_regions.get(vin, "CA")
        variables = {"currentCharge": max_amps}
        return await execute_graphql(
            self.auth,
            POST_CHARGE_SETTINGS_MUTATION,
            variables,
            vin=vin,
            region=target_region,
            brand_code=self.brand.code,
            user_agent=self.brand.user_agent,
            session=self._session,
        )

    async def start_realtime_listener(
        self,
        vins: list[str],
        callback: Callable[[str, dict[str, Any]], None],
        region: str | None = None,
    ) -> None:
        target_region = region or (self._vin_regions.get(vins[0]) if vins else "CA") or "CA"
        self.ws = ToyotaAppSyncWebSocket(self.auth, callback, brand_code=self.brand.code)
        await self.ws.start(vins, region=target_region)

    async def stop_realtime_listener(self) -> None:
        if self.ws:
            await self.ws.stop()
            self.ws = None

    async def confirm_subscription(self, vin: str, region: str | None = None) -> dict[str, Any]:
        """Confirm active subscription status for vehicle telematics."""
        target_region = region or self._vin_regions.get(vin, "CA")
        return await execute_graphql(
            self.auth,
            CONFIRM_SUBSCRIPTION_MUTATION,
            {"vin": vin},
            vin=vin,
            region=target_region,
            brand_code=self.brand.code,
            user_agent=self.brand.user_agent,
            session=self._session,
        )

    async def send_pre_wake(self, guid: str | None = None, region: str = "CA") -> dict[str, Any]:
        """Dispatch pre-wake cellular handshake to vehicle prior to remote operations."""
        user_guid = guid or await self.auth.get_guid()
        return await execute_graphql(
            self.auth,
            PRE_WAKE_MUTATION,
            {"guid": user_guid},
            region=region,
            brand_code=self.brand.code,
            user_agent=self.brand.user_agent,
            session=self._session,
        )

    async def refresh_status(self, vin: str, region: str | None = None) -> dict[str, Any]:
        """Request on-demand cellular telematics refresh from vehicle DCM."""
        target_region = region or self._vin_regions.get(vin, "CA")
        return await execute_graphql(
            self.auth,
            REFRESH_STATUS_MUTATION,
            {"vin": vin},
            vin=vin,
            region=target_region,
            brand_code=self.brand.code,
            user_agent=self.brand.user_agent,
            session=self._session,
        )
