"""REST client for Toyota Connected Services API Gateway."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .auth import ToyotaAuth
from .brands import DEFAULT_BRAND, BrandConfig, get_brand
from .graphql import RESOLVER_API_KEY
from .models import (
    ChargingStatus,
    ElectricVehicleStatus,
    OpeningState,
    TirePressure,
    VehicleStatus,
)

_LOGGER = logging.getLogger(__name__)

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)


class ToyotaRestClient:
    """Communicates with Toyota OneApp REST API gateway for Toyota, Lexus, and Subaru."""

    def __init__(
        self,
        auth: ToyotaAuth,
        brand: BrandConfig | str = DEFAULT_BRAND,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._auth = auth
        self._brand = get_brand(brand)
        self._session = session

    @asynccontextmanager
    async def _request_session(self):
        """Yield shared session if provided, otherwise yield an ephemeral session."""
        if self._session is not None and not self._session.closed:
            yield self._session
        else:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                yield session

    @property
    def brand(self) -> BrandConfig:
        return self._brand

    async def _headers(self, vin: str = "", region: str = "CA") -> dict[str, str]:
        token = await self._auth.get_access_token()
        guid = await self._auth.get_guid()
        corr_id = str(uuid.uuid4())
        headers = {
            "AUTHORIZATION": f"Bearer {token}",
            "X-API-KEY": RESOLVER_API_KEY,
            "X-GUID": guid,
            "X-CHANNEL": "ONEAPP",
            "x-region": region,
            "X-APPVERSION": "3.10.0",
            "X-LOCALE": "en-US",
            "X-CorrelationId": corr_id,
            "X-CORRELATIONID": corr_id,
            "x-correlationId": corr_id,
            "User-Agent": self._brand.user_agent,
            "Accept": "application/json",
        }
        headers.update(self._brand.headers())
        if vin:
            headers["VIN"] = vin
        return headers

    async def request(
        self,
        method: str,
        endpoint: str,
        vin: str = "",
        region: str = "CA",
        json_data: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """Issue HTTP request against API Gateway with automatic authentication."""
        headers = await self._headers(vin=vin, region=region)
        if extra_headers:
            headers.update(extra_headers)

        url = urljoin(API_GATEWAY, endpoint.lstrip("/"))

        async with (
            self._request_session() as session,
            session.request(method, url, headers=headers, json=json_data) as resp,
        ):
            if resp.status >= 400:
                text = await resp.text()
                # Log 502/503/504 as warnings to avoid error spam during upstream cloud gateway issues
                if resp.status in (502, 503, 504):
                    _LOGGER.warning(
                        "Toyota REST API gateway issue %d for %s: %s",
                        resp.status,
                        endpoint,
                        text[:300],
                    )
                else:
                    _LOGGER.error(
                        "Toyota REST API error %d for %s: %s", resp.status, endpoint, text[:300]
                    )
                resp.raise_for_status()

            data = await resp.json()
            if isinstance(data, dict) and "payload" in data:
                return data["payload"]
            return data

    async def get_vehicle_list(self) -> list[dict[str, Any]]:
        """Fetch list of user's registered vehicles."""
        result = await self.request("GET", "v2/vehicle/guid")
        if isinstance(result, list):
            return result
        return []

    async def bootstrap_account(self) -> dict[str, Any] | None:
        """Bootstrap account profile for Subaru accounts if initial vehicle list returns empty."""
        try:
            _LOGGER.debug("Bootstrapping account profile via v4/account")
            return await self.request("GET", "v4/account")
        except (aiohttp.ClientError, KeyError, ValueError) as e:
            _LOGGER.warning("Account bootstrap call failed: %s", e)
            return None

    async def get_vehicle_status(self, vin: str, region: str = "CA") -> dict[str, Any] | None:
        """Fetch remote vehicle status (openings, locks, hood, hatch) via OneAPI."""
        try:
            return await self.request("GET", "v1/global/remote/status", vin=vin, region=region)
        except (aiohttp.ClientError, KeyError, ValueError) as e:
            _LOGGER.debug("Failed to fetch vehicle status for %s: %s", vin, e)
            return None

    async def get_electric_status(
        self, vin: str, region: str = "CA", generation: str = "21MM"
    ) -> dict[str, Any] | None:
        """Fetch EV electric status (battery SoC, range, charge status).

        Attempts the modern OneAPI v3 endpoint first; falls back to legacy v2 if
        the vehicle generation or cloud service requires it.
        """
        extra = {"X-GENERATION": generation}
        for endpoint in ("v3/electric/status", "v2/electric/status"):
            try:
                res = await self.request(
                    "GET", endpoint, vin=vin, region=region, extra_headers=extra
                )
                if (
                    res
                    and isinstance(res, dict)
                    and (res.get("vehicleInfo") or res.get("chargeInfo"))
                ):
                    return res
            except (aiohttp.ClientError, KeyError, ValueError) as e:
                _LOGGER.debug("Failed electric status %s for %s: %s", endpoint, vin, e)
        return None

    async def get_telemetry(
        self, vin: str, generation: str = "24MM", region: str = "CA"
    ) -> dict[str, Any] | None:
        """Fetch vehicle telemetry data."""
        try:
            extra = {"GENERATION": generation, "X-BRAND": self._brand.code}
            return await self.request(
                "GET", "v2/telemetry", vin=vin, region=region, extra_headers=extra
            )
        except (aiohttp.ClientError, KeyError, ValueError) as e:
            _LOGGER.debug("Failed to fetch telemetry for %s: %s", vin, e)
            return None

    async def send_remote_command(
        self, vin: str, command: str, region: str = "CA", generation: str = "21MM"
    ) -> dict[str, Any]:
        """Send remote command (lock, unlock, etc.) via REST API route."""
        corr_id = str(uuid.uuid4())
        extra = {
            "X-GENERATION": generation,
            "X-BRAND": self._brand.code,
            "X-CorrelationId": corr_id,
            "X-CORRELATIONID": corr_id,
            "x-correlationId": corr_id,
        }
        body = {"command": command, "autoFixPopup": False}
        return await self.request(
            "POST",
            "v1/global/remote/command",
            vin=vin,
            region=region,
            json_data=body,
            extra_headers=extra,
        )


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def parse_rest_vehicle_status(data: dict[str, Any], vehicle: VehicleStatus) -> None:
    """Parse OneAPI v1/global/remote/status payload into VehicleStatus."""
    payload = data.get("payload") if isinstance(data, dict) and "payload" in data else data
    if not isinstance(payload, dict):
        return

    status_list = payload.get("vehicleStatus")
    if not isinstance(status_list, list):
        return

    for cat in status_list:
        cat_name = str(cat.get("category", ""))
        sections = cat.get("sections") or []
        for sec in sections:
            sec_name = str(sec.get("section", ""))
            vals = sec.get("values") or []
            closed: bool | None = None
            locked: bool | None = None
            for v in vals:
                txt = str(v.get("value", "")).lower()
                if "close" in txt:
                    closed = True
                elif "open" in txt:
                    closed = False
                if "lock" in txt and "unlock" not in txt:
                    locked = True
                elif "unlock" in txt:
                    locked = False

            if cat_name == "Driver Side":
                if sec_name == "Door":
                    vehicle.driver_door = OpeningState(
                        closed=closed if closed is not None else True, locked=locked
                    )
                elif sec_name == "Rear Door":
                    vehicle.rear_driver_door = OpeningState(
                        closed=closed if closed is not None else True, locked=locked
                    )
                elif sec_name == "Window" and closed is not None:
                    vehicle.driver_window_closed = closed
                elif sec_name == "Rear Window" and closed is not None:
                    vehicle.rear_driver_window_closed = closed

            elif cat_name == "Passenger Side":
                if sec_name == "Door":
                    vehicle.passenger_door = OpeningState(
                        closed=closed if closed is not None else True, locked=locked
                    )
                elif sec_name == "Rear Door":
                    vehicle.rear_passenger_door = OpeningState(
                        closed=closed if closed is not None else True, locked=locked
                    )
                elif sec_name == "Window" and closed is not None:
                    vehicle.passenger_window_closed = closed
                elif sec_name == "Rear Window" and closed is not None:
                    vehicle.rear_passenger_window_closed = closed

            elif cat_name == "Other":
                if sec_name == "Hatch":
                    vehicle.hatch = OpeningState(
                        closed=closed if closed is not None else True, locked=locked
                    )
                elif sec_name == "Hood" and closed is not None:
                    vehicle.hood = OpeningState(closed=closed, locked=None)

    # Telemetry inside status payload
    telemetry = payload.get("telemetry") or {}
    odo = telemetry.get("odo") or {}
    if isinstance(odo, dict) and odo.get("value") is not None:
        vehicle.odometer_km = _safe_float(odo["value"])

    if payload.get("latitude") is not None:
        vehicle.last_parked_latitude = _safe_float(payload["latitude"])
    if payload.get("longitude") is not None:
        vehicle.last_parked_longitude = _safe_float(payload["longitude"])


def parse_rest_electric_status(data: dict[str, Any], vehicle: VehicleStatus) -> None:
    """Parse OneAPI v2/electric/status payload into VehicleStatus."""
    payload = data.get("payload") if isinstance(data, dict) and "payload" in data else data
    veh_info = payload.get("vehicleInfo") if isinstance(payload, dict) else data
    if not isinstance(veh_info, dict):
        return

    charge_info = veh_info.get("chargeInfo") or {}
    hvac_info = veh_info.get("remoteHvacInfo") or {}

    # Battery State of Charge
    soc = _safe_float(charge_info.get("chargeRemainingAmount"))

    # Driving Range
    dist_unit = str(charge_info.get("evDistanceUnit", "km")).lower()
    dist = _safe_float(charge_info.get("evDistance") or charge_info.get("evTravelableDistance"))
    range_km = round(dist * 1.60934, 1) if dist is not None and "mi" in dist_unit else dist

    dist_ac = _safe_float(charge_info.get("evDistanceAC"))
    range_ac_km = (
        round(dist_ac * 1.60934, 1) if dist_ac is not None and "mi" in dist_unit else dist_ac
    )

    # Plug and charging status
    plug_val = str(charge_info.get("plugStatus", "")).lower()
    conn_val = str(charge_info.get("connectorStatus", "")).lower()

    is_charging = plug_val in ("40", "56", "charging")
    is_plugged = is_charging or (
        plug_val not in ("12", "unplugged") and conn_val in ("1", "plugged")
    )

    if is_charging:
        charge_status = ChargingStatus.CHARGING
    elif is_plugged:
        charge_status = ChargingStatus.COMPLETE
    else:
        charge_status = ChargingStatus.STOPPED

    rem_time = _safe_int(charge_info.get("remainingChargeTime"))
    if rem_time == 65535:
        rem_time = None

    if not vehicle.electric:
        vehicle.electric = ElectricVehicleStatus()

    if soc is not None:
        vehicle.electric.battery_level = soc
        vehicle.electric.charge_remaining_amount = soc
    if range_km is not None:
        vehicle.electric.range_km = range_km
    if range_ac_km is not None:
        vehicle.electric.range_ac_on_km = range_ac_km

    vehicle.electric.charging_status = charge_status
    vehicle.electric.plug_connected = is_plugged
    vehicle.electric.time_to_full_minutes = rem_time

    # Active charging rate (kW)
    if charge_status == ChargingStatus.CHARGING:
        api_rate = _safe_float(
            (charge_info.get("actualChargingRate") or {}).get("value")
            if isinstance(charge_info.get("actualChargingRate"), dict)
            else charge_info.get("chargingRate") or charge_info.get("chargingPower")
        )
        if api_rate is not None and api_rate > 0:
            vehicle.electric.charging_power_kw = api_rate
        elif rem_time and rem_time > 0:
            current_soc = soc if soc is not None else 50.0
            remaining_pct = max(1.0, 100.0 - current_soc)
            # bZ4X nominal usable capacity ~65.0 kWh
            energy_kwh = (remaining_pct / 100.0) * 65.0
            hours_remaining = rem_time / 60.0
            vehicle.electric.charging_power_kw = round(energy_kwh / hours_remaining, 1)
        elif plug_val == "56":
            vehicle.electric.charging_power_kw = 50.0
        else:
            vehicle.electric.charging_power_kw = 6.6
    else:
        vehicle.electric.charging_power_kw = 0.0

    # Climate
    if hvac_info.get("settingTemperature") is not None:
        vehicle.climate_target_temp_c = _safe_float(hvac_info["settingTemperature"])
    hvac_mode = hvac_info.get("remoteHvacMode")
    blower = hvac_info.get("blowerStatus")
    if hvac_mode is not None or blower is not None:
        vehicle.climate_active = bool(hvac_mode == 1 or blower == 1)


def parse_rest_telemetry(telemetry: dict[str, Any], vehicle: VehicleStatus) -> None:
    """Parse OneAPI v2/telemetry payload into VehicleStatus."""
    payload = (
        telemetry.get("payload")
        if isinstance(telemetry, dict) and "payload" in telemetry
        else telemetry
    )
    if not isinstance(payload, dict):
        return

    # Odometer
    odo_raw = payload.get("odometer")
    if odo_raw is not None:
        if isinstance(odo_raw, dict):
            val = _safe_float(odo_raw.get("value"))
            unit = str(odo_raw.get("unit", "")).lower()
            if val is not None:
                vehicle.odometer_km = round(val * 1.60934, 1) if "mi" in unit else val
        else:
            val = _safe_float(odo_raw)
            if val is not None:
                vehicle.odometer_km = val

    # Tire pressures
    def _extract_tire(t_data: Any) -> TirePressure:
        if isinstance(t_data, dict):
            val = _safe_float(t_data.get("value"))
            unit = str(t_data.get("unit", "")).lower()
            low = bool(t_data.get("displayLowTirePressureWarning", False))
            if val is not None:
                if "kpa" in unit:
                    return TirePressure(
                        kpa=val, psi=round(val / 6.89476, 1), low_pressure_warning=low
                    )
                return TirePressure(psi=val, kpa=round(val * 6.89476, 1), low_pressure_warning=low)
        return TirePressure()

    if "flTirePressure" in payload:
        vehicle.tire_front_left = _extract_tire(payload["flTirePressure"])
    if "frTirePressure" in payload:
        vehicle.tire_front_right = _extract_tire(payload["frTirePressure"])
    if "rlTirePressure" in payload:
        vehicle.tire_rear_left = _extract_tire(payload["rlTirePressure"])
    if "rrTirePressure" in payload:
        vehicle.tire_rear_right = _extract_tire(payload["rrTirePressure"])

    # Location
    loc = payload.get("vehicleLocation") or {}
    if isinstance(loc, dict):
        if loc.get("latitude") is not None:
            vehicle.last_parked_latitude = _safe_float(loc["latitude"])
        if loc.get("longitude") is not None:
            vehicle.last_parked_longitude = _safe_float(loc["longitude"])

    # Fuel Level
    if payload.get("fuelLevel") is not None:
        vehicle.fuel_level_percent = _safe_float(payload["fuelLevel"])
    if payload.get("distanceToEmpty") is not None:
        dist_val = payload["distanceToEmpty"]
        if isinstance(dist_val, dict):
            vehicle.fuel_range_km = _safe_float(dist_val.get("value"))
        else:
            vehicle.fuel_range_km = _safe_float(dist_val)
