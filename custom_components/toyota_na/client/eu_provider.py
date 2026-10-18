"""European regional provider (EU, UK) for Toyota Connected Services."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
import math
import secrets
import time
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

import aiohttp
import jwt

from .auth import AuthError, LoginError, NotLoggedIn, TokenExpired
from .base_provider import ToyotaRegionProvider
from .models import (
    ChargingStatus,
    ElectricVehicleStatus,
    OpeningState,
    RemoteCommand,
    TirePressure,
    VehicleGeneration,
    VehicleStatus,
)

_LOGGER = logging.getLogger(__name__)

EU_AUTH_HOST = "https://b2c-login.toyota-europe.com"
EU_AUTHENTICATE_URL = f"{EU_AUTH_HOST}/json/realms/root/realms/tme/authenticate?authIndexType=service&authIndexValue=oneapp"
EU_AUTHORIZE_URL = f"{EU_AUTH_HOST}/oauth2/realms/root/realms/tme/authorize"
EU_ACCESS_TOKEN_URL = f"{EU_AUTH_HOST}/oauth2/realms/root/realms/tme/access_token"
EU_API_GATEWAY = "https://ctpa-oneapi.tceu-ctp-prd.toyotaconnectedeurope.io"

EU_CLIENT_ID = "oneapp"
EU_REDIRECT_URI = "com.toyota.oneapp:/oauth2Callback"
EU_BASIC_AUTH = "Basic b25lYXBwOm9uZWFwcA=="
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)


class EuropeProvider(ToyotaRegionProvider):
    """Regional backend provider for Europe (TME ctpa-oneapi)."""

    def __init__(
        self,
        token_callback: Callable[[dict[str, Any]], None] | None = None,
        initial_tokens: dict[str, Any] | None = None,
    ) -> None:
        self._token_callback = token_callback
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._id_token: str | None = None
        self._guid: str | None = None
        self._expires_at: float | None = None
        self._updated_at: float | None = None
        self._token_lock = asyncio.Lock()

        if initial_tokens:
            self.set_tokens(initial_tokens)

    @property
    def region_code(self) -> str:
        return "eu"

    def get_tokens(self) -> dict[str, Any]:
        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "id_token": self._id_token,
            "guid": self._guid,
            "expires_at": self._expires_at,
            "updated_at": self._updated_at,
            "clock": "unix",
            "region": "eu",
        }

    def set_tokens(self, tokens: dict[str, Any]) -> None:
        self._access_token = tokens.get("access_token")
        self._refresh_token = tokens.get("refresh_token")
        self._id_token = tokens.get("id_token")
        self._guid = tokens.get("guid")
        self._expires_at = float(tokens.get("expires_at") or 0.0)
        self._updated_at = float(tokens.get("updated_at") or time.time())

    async def check_tokens(self) -> None:
        async with self._token_lock:
            if not self._expires_at:
                raise NotLoggedIn("European session not initialized")
            now = time.time()
            if now >= (self._expires_at - 300):
                await self._refresh_tokens()

    async def _refresh_tokens(self) -> None:
        if not self._refresh_token:
            raise NotLoggedIn("No refresh token available")

        headers = {
            "Authorization": EU_BASIC_AUTH,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "client_id": EU_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.post(EU_ACCESS_TOKEN_URL, headers=headers, data=data) as resp:
                if resp.status != 200:
                    raise TokenExpired(f"EU token refresh failed HTTP {resp.status}")
                self._extract_tokens(await resp.json())

    def _extract_tokens(self, data: dict[str, Any]) -> None:
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token") or self._refresh_token
        id_token = data.get("id_token") or self._id_token

        lifetime = float(data.get("expires_in", 3600))
        now = time.time()
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._id_token = id_token
        self._expires_at = now + lifetime
        self._updated_at = now

        if id_token:
            try:
                decoded = jwt.decode(
                    id_token,
                    algorithms=["RS256"],
                    options={"verify_signature": False},
                )
                self._guid = decoded.get("sub")
            except Exception:
                pass

        if self._token_callback:
            try:
                self._token_callback(self.get_tokens())
            except Exception:
                _LOGGER.exception("EU token callback failed")

    async def login(
        self,
        username: str,
        password: str | None = None,
        otp: str | None = None,
    ) -> str | dict[str, Any] | None:
        """Authenticate with Toyota Europe ForgeRock OpenAM."""
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            headers = {"Accept-API-Version": "resource=2.1, protocol=1.0", "Content-Type": "application/json"}
            data: dict[str, Any] = {}

            # Initial handshake
            async with session.post(EU_AUTHENTICATE_URL, json=data, headers=headers) as resp:
                if resp.status != 200:
                    raise LoginError(f"EU authenticate handshake failed: {resp.status}")
                data = await resp.json()

            # Fill username and password callbacks
            for cb in data.get("callbacks", []):
                cb_type = cb.get("type")
                if cb_type == "NameCallback":
                    cb["input"][0]["value"] = username
                elif cb_type == "PasswordCallback" and password:
                    cb["input"][0]["value"] = password

            async with session.post(EU_AUTHENTICATE_URL, json=data, headers=headers) as resp:
                if resp.status != 200:
                    raise LoginError("EU authentication credentials rejected")
                data = await resp.json()

            token_id = data.get("tokenId")
            if not token_id:
                raise LoginError("EU OpenAM did not return tokenId")

            # Authorize code redirect
            auth_params = {
                "client_id": EU_CLIENT_ID,
                "scope": "openid profile write",
                "response_type": "code",
                "redirect_uri": EU_REDIRECT_URI,
                "code_challenge": "plain",
                "code_challenge_method": "plain",
            }
            req_headers = {"Cookie": f"iPlanetDirectoryPro={token_id}"}
            auth_url = f"{EU_AUTHORIZE_URL}?{urlencode(auth_params)}"

            async with session.get(auth_url, headers=req_headers, allow_redirects=False) as resp:
                if resp.status not in (301, 302, 303, 307, 308):
                    raise LoginError(f"EU authorize redirect returned HTTP {resp.status}")
                location = resp.headers.get("Location", "")
                parsed = urlparse(location)
                codes = parse_qs(parsed.query).get("code", [])
                if not codes:
                    raise LoginError("Missing code in EU authorization redirect")
                return codes[0]

    async def request_tokens(self, code: str) -> None:
        headers = {
            "Authorization": EU_BASIC_AUTH,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "client_id": EU_CLIENT_ID,
            "redirect_uri": EU_REDIRECT_URI,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": "plain",
        }

        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.post(EU_ACCESS_TOKEN_URL, headers=headers, data=data) as resp:
                if resp.status != 200:
                    raise LoginError(f"EU token request failed HTTP {resp.status}")
                self._extract_tokens(await resp.json())

    async def _api_request(self, method: str, endpoint: str, vin: str = "", json_data: dict[str, Any] | None = None) -> Any:
        await self.check_tokens()
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "x-correlationid": str(uuid4()),
        }
        if vin:
            headers["vin"] = vin

        url = f"{EU_API_GATEWAY}{endpoint}"
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.request(method, url, headers=headers, json=json_data) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    _LOGGER.error("EU API error HTTP %d: %s", resp.status, text[:200])
                    resp.raise_for_status()
                data = await resp.json()
                if isinstance(data, dict) and "payload" in data:
                    return data["payload"]
                return data

    async def get_user_vehicles(self) -> list[VehicleStatus]:
        result = await self._api_request("GET", "/v2/vehicle/guid")
        vehicles: list[VehicleStatus] = []
        for item in (result if isinstance(result, list) else []):
            vin = item.get("vin")
            if not vin:
                continue
            is_ev = bool(item.get("evVehicle") or item.get("fuelType") in ("E", "I"))
            v = VehicleStatus(
                vin=vin,
                model_name=item.get("modelName") or "Toyota Vehicle",
                model_year=str(item.get("modelYear") or "2024"),
                generation=VehicleGeneration.MM24 if is_ev else VehicleGeneration.MM21,
                region="EU",
                subscribed=item.get("remoteSubscriptionStatus") == "ACTIVE",
                is_electric=is_ev,
                backdoor_type=item.get("backdoorType") or "hatch",
            )
            vehicles.append(v)
        return vehicles

    async def update_vehicle_status(self, vehicle: VehicleStatus) -> VehicleStatus:
        # Status (doors, windows, locks)
        try:
            status_res = await self._api_request("GET", "/v1/vehicle/status", vin=vehicle.vin)
            if status_res:
                self._parse_eu_vehicle_status(status_res, vehicle)
        except Exception as e:
            _LOGGER.debug("EU /v1/vehicle/status failed for %s: %s", vehicle.vin, e)

        # Electric Status (EV/PHEV)
        if vehicle.is_electric:
            try:
                ev_res = await self._api_request("GET", "/v1/vehicle/electric/status", vin=vehicle.vin)
                if ev_res:
                    self._parse_eu_electric_status(ev_res, vehicle)
            except Exception as e:
                _LOGGER.debug("EU /v1/vehicle/electric/status failed for %s: %s", vehicle.vin, e)

        # Telemetry (Odometer & Fuel)
        try:
            telemetry = await self._api_request("GET", "/v3/telemetry", vin=vehicle.vin)
            if telemetry:
                odo = telemetry.get("odometer") or {}
                if odo.get("value") is not None:
                    vehicle.odometer_km = float(odo["value"])
                fuel = telemetry.get("fuelLevel") or {}
                if fuel.get("value") is not None:
                    vehicle.fuel_level_percent = float(fuel["value"])
                dte = telemetry.get("distanceToEmpty") or {}
                if dte.get("value") is not None:
                    vehicle.fuel_range_km = float(dte["value"])
        except Exception as e:
            _LOGGER.debug("EU /v3/telemetry failed: %s", e)

        # Location
        try:
            loc = await self._api_request("GET", "/v1/location", vin=vehicle.vin)
            if loc and loc.get("latitude") and loc.get("longitude"):
                vehicle.last_parked_latitude = float(loc["latitude"])
                vehicle.last_parked_longitude = float(loc["longitude"])
        except Exception as e:
            _LOGGER.debug("EU /v1/location failed: %s", e)

        return vehicle

    def _parse_eu_vehicle_status(self, data: dict[str, Any], vehicle: VehicleStatus) -> None:
        state = data.get("vehicleStatus") or data
        doors = state.get("doors") or {}
        windows = state.get("windows") or {}

        def parse_door(d: dict[str, Any] | None) -> OpeningState:
            if not d:
                return OpeningState()
            return OpeningState(
                closed=str(d.get("position", "")).lower() == "closed",
                locked=str(d.get("lock", "")).lower() == "locked",
            )

        vehicle.driver_door = parse_door(doors.get("driverSide"))
        vehicle.passenger_door = parse_door(doors.get("passengerSide"))
        vehicle.rear_driver_door = parse_door(doors.get("rearDriverSide"))
        vehicle.rear_passenger_door = parse_door(doors.get("rearPassengerSide"))
        vehicle.hatch = parse_door(state.get("hatch"))

        vehicle.driver_window_closed = str((windows.get("driverSide") or {}).get("position", "")).lower() == "closed"
        vehicle.passenger_window_closed = str((windows.get("passengerSide") or {}).get("position", "")).lower() == "closed"

    def _parse_eu_electric_status(self, data: dict[str, Any], vehicle: VehicleStatus) -> None:
        battery_level = data.get("batteryLevel")
        ev_range = (data.get("evRange") or {}).get("value")
        ev_range_ac = (data.get("evRangeWithAc") or {}).get("value")
        charging_status_str = str(data.get("chargingStatus", "")).lower()

        status_enum = ChargingStatus.UNKNOWN
        if "charg" in charging_status_str:
            status_enum = ChargingStatus.CHARGING
        elif "stop" in charging_status_str:
            status_enum = ChargingStatus.STOPPED
        elif "comp" in charging_status_str:
            status_enum = ChargingStatus.COMPLETE

        vehicle.electric = ElectricVehicleStatus(
            battery_level=float(battery_level) if battery_level is not None else None,
            range_km=float(ev_range) if ev_range is not None else None,
            range_ac_on_km=float(ev_range_ac) if ev_range_ac is not None else None,
            charging_status=status_enum,
            time_to_full_minutes=data.get("remainingChargeTime"),
            plug_connected=status_enum == ChargingStatus.CHARGING or bool(data.get("canSetNextChargingEvent")),
        )

    async def send_remote_command(self, vin: str, command: RemoteCommand) -> dict[str, Any]:
        if command in (RemoteCommand.ENGINE_START, RemoteCommand.ENGINE_STOP):
            # Unified V2 climate control endpoint
            payload = {
                "command": "start" if command == RemoteCommand.ENGINE_START else "stop",
                "targetTemperature": 21.0,
            }
            return await self._api_request("POST", "/v2/remote/climate-control", vin=vin, json_data=payload)

        # Standard door lock/unlock command
        cmd_name = "door-lock" if command == RemoteCommand.DOOR_LOCK else "door-unlock"
        payload = {"command": cmd_name}
        return await self._api_request("POST", "/v1/global/remote/command", vin=vin, json_data=payload)

    async def set_charge_limit(self, vin: str, target_percent: int) -> dict[str, Any]:
        _LOGGER.info("Setting charge limit in Europe is managed through vehicle dashboard or schedules")
        return {"status": "ok"}

    async def set_ac_current_limit(self, vin: str, max_amps: int) -> dict[str, Any]:
        return {"status": "ok"}

    async def start_realtime_listener(
        self,
        vins: list[str],
        callback: Callable[[str, dict[str, Any]], None],
    ) -> None:
        # Europe does not provide AppSync WebSockets; rely on passive coordinator polling
        pass

    async def stop_realtime_listener(self) -> None:
        pass
