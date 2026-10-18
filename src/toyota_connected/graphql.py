"""AWS AppSync GraphQL HTTP and WebSocket client for 24MM generation vehicles (e.g. 2024 Toyota bZ4X)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from typing import Any

import aiohttp

from .auth import ToyotaAuth
from .models import (
    ChargingStatus,
    ElectricVehicleStatus,
    OpeningState,
    TirePressure,
    VehicleStatus,
)

_LOGGER = logging.getLogger(__name__)

GRAPHQL_HTTP_ENDPOINT = "https://oa-api.telematicsct.com/graphql"
GRAPHQL_WS_ENDPOINT = "wss://oa-api.telematicsct.com/graphql/realtime"
GRAPHQL_HOST = "oa-api.telematicsct.com"
APPSYNC_API_KEY = os.getenv("TOYOTA_APPSYNC_API_KEY", "da2-zgeayo2qh5eo7cj6pmdwhwugze")
RESOLVER_API_KEY = os.getenv("TOYOTA_RESOLVER_API_KEY", "pypIHG015k4ABHWbcI4G0a94F7cC0JDo1OynpAsG")
USER_AGENT = "ToyotaOneApp/3.10.0 (com.toyota.oneapp; build:3100; Android 14) okhttp/4.12.0"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)

__all__ = [
    "APPSYNC_API_KEY",
    "CONFIRM_SUBSCRIPTION_MUTATION",
    "GET_VEHICLE_STATUS_QUERY",
    "GRAPHQL_HOST",
    "GRAPHQL_HTTP_ENDPOINT",
    "GRAPHQL_VEHICLE_STATUS_FIELDS",
    "GRAPHQL_WS_ENDPOINT",
    "POST_CHARGE_SETTINGS_MUTATION",
    "PRE_WAKE_MUTATION",
    "RECEIVE_REMOTE_COMMAND_STATUS_SUBSCRIPTION",
    "RECEIVE_VEHICLE_STATUS_SUBSCRIPTION",
    "REFRESH_STATUS_MUTATION",
    "RESOLVER_API_KEY",
    "SEND_REMOTE_COMMAND_MUTATION",
    "ToyotaAppSyncWebSocket",
    "execute_graphql",
    "parse_appsync_vehicle_status",
]

# --- GraphQL Queries, Mutations, and Subscriptions ---

GRAPHQL_VEHICLE_STATUS_FIELDS = """
    vin lastUpdateDateTime
    vehicleState {
      lastUpdateDateTime driverPosition
      doors {
        driverSide { lock { status } position { status } }
        passengerSide { lock { status } position { status } }
        rearDriverSide { lock { status } position { status } }
        rearPassengerSide { lock { status } position { status } }
      }
      windows {
        driverSide { position { status } }
        passengerSide { position { status } }
        rearDriverSide { position { status } }
        rearPassengerSide { position { status } }
      }
      hatch { lock { status } position { status } }
      hood { position { status } }
      moonroof { position { status } }
      tires {
        frontLeft { psi kpa bar displayLowTirePressureWarning }
        frontRight { psi kpa bar displayLowTirePressureWarning }
        rearLeft { psi kpa bar displayLowTirePressureWarning }
        rearRight { psi kpa bar displayLowTirePressureWarning }
        spare { psi kpa bar displayLowTirePressureWarning }
      }
      engine { running status startTime stopTime }
    }
    location { latitude longitude lastUpdateDateTime }
    telemetry {
      odo { unit value }
      range { unit value }
    }
    electric {
      lastUpdateDateTime
      battery {
        stateOfChargeDisplay { unit value }
        plugInEnergy { unit value }
        chargeRemainingAmount { unit value }
        travelableDistance { unit value }
        travelableDistanceAC { unit value }
        powerSupplyPossibleTime { unit value }
      }
      charging {
        chargingStatus
        chargingState
        chargeType
        actualChargingRate { unit value }
        remainingChargeTime { unit value }
        remainingChargeTimeTo80Percent { unit value }
        connector { status plugInInfo plugStatus }
        chargeSettings {
          targetLimit { value unit }
          maxACCurrent { value setting }
          maxDCPower { value setting }
          electricSupplyModeLimit { value setting }
          schedules {
            settingId enabled startTime endTime daysOfTheWeek
          }
        }
      }
    }
"""

GET_VEHICLE_STATUS_QUERY = f"""
query GetVehicleStatus($vin: String!) {{
  getVehicleStatus(vin: $vin) {{
    {GRAPHQL_VEHICLE_STATUS_FIELDS}
  }}
}}
"""

RECEIVE_VEHICLE_STATUS_SUBSCRIPTION = f"""
subscription ReceiveVehicleStatus($vin: String!) {{
  onVehicleStatusUpdated(vin: $vin) {{
    {GRAPHQL_VEHICLE_STATUS_FIELDS}
  }}
}}
"""

RECEIVE_REMOTE_COMMAND_STATUS_SUBSCRIPTION = """
subscription ReceiveRemoteCommandStatus($vin: String!) {
  onPostRemoteCallback(vin: $vin) {
    appRequestNo type category remoteCommandType message status vin command commandEnded
  }
}
"""

SEND_REMOTE_COMMAND_MUTATION = """
mutation SendRemoteCommand($command: String!, $autoFixCommands: [String]!) {
  executeRemoteCommand(commandInputBody: {
    command: $command
    autofixCommands: $autoFixCommands
  }) {
    payload { requestNo correlationId returnCode }
    status { messages { responseCode description } }
  }
}
"""

POST_CHARGE_SETTINGS_MUTATION = """
mutation PostChargeSettings($chargingTargetLimit: Int, $quickChargePowerLimit: Int, $currentCharge: Int) {
  postChargeSettings(postChargeSettingsInputBody: {
    chargingTargetLimit: $chargingTargetLimit
    quickChargePowerLimit: $quickChargePowerLimit
    currentCharge: $currentCharge
  }) {
    payload { correlationId returnCode message }
    status { messages { responseCode description } }
  }
}
"""

PRE_WAKE_MUTATION = """
mutation SendPreWakeCommand($guid: String!) {
  postPreWake(guid: $guid) {
    timestamp
    status { messages { responseCode } }
  }
}
"""

CONFIRM_SUBSCRIPTION_MUTATION = """
mutation ConfirmSubscriptionStatus($vin: String!) {
  confirmSubscriptionActive(vin: $vin, payload: {
    vehicleCapabilities: { backdoorType: "hatch" }
  }) { vin }
}
"""

REFRESH_STATUS_MUTATION = """
mutation RefreshVehicleStatus($vin: String!) {
  postRefreshStatus(vin: $vin) {
    payload { correlationId appRequestNo }
    status { messages { responseCode description } }
    timestamp
  }
}
"""


def _parse_door(door_dict: dict[str, Any] | None) -> OpeningState:
    """Parse door position and lock state."""
    if not door_dict:
        return OpeningState()
    pos = (door_dict.get("position") or {}).get("status", "").lower() == "closed"
    locked = (door_dict.get("lock") or {}).get("status", "").lower() == "locked"
    return OpeningState(closed=pos, locked=locked)


def _is_win_closed(win_dict: dict[str, Any] | None) -> bool:
    """Check if window position is closed."""
    return ((win_dict or {}).get("position") or {}).get("status", "").lower() == "closed"


def _parse_tire(t_data: dict[str, Any] | None) -> TirePressure:
    """Parse tire pressure reading and warning."""
    if not t_data:
        return TirePressure()
    return TirePressure(
        psi=t_data.get("psi"),
        kpa=t_data.get("kpa"),
        bar=t_data.get("bar"),
        low_pressure_warning=bool(t_data.get("displayLowTirePressureWarning")),
    )


def _safe_float(val: Any) -> float | None:
    """Safely convert value to float or return None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    """Safely convert value to int or return None."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _distance_to_km(dist_dict: dict[str, Any] | None) -> float | None:
    """Convert distance dict (with unit mi or km) to km float."""
    if not dist_dict or dist_dict.get("value") is None:
        return None
    v = float(dist_dict["value"])
    u = str(dist_dict.get("unit", "")).lower()
    return v * 1.60934 if "mi" in u else v


def parse_appsync_vehicle_status(data: dict[str, Any], existing: VehicleStatus) -> VehicleStatus:
    """Parse GraphQL response dictionary into a typed VehicleStatus instance."""
    status_node = data.get("getVehicleStatus") or data.get("onVehicleStatusUpdated") or data

    state = status_node.get("vehicleState") or {}
    doors = state.get("doors") or {}
    windows = state.get("windows") or {}
    tires = state.get("tires") or {}
    engine = state.get("engine") or {}
    telemetry = status_node.get("telemetry") or {}
    location = status_node.get("location") or {}
    electric = status_node.get("electric") or {}

    # Doors
    existing.driver_door = _parse_door(doors.get("driverSide"))
    existing.passenger_door = _parse_door(doors.get("passengerSide"))
    existing.rear_driver_door = _parse_door(doors.get("rearDriverSide"))
    existing.rear_passenger_door = _parse_door(doors.get("rearPassengerSide"))

    # Hatch / Hood / Moonroof
    hatch_data = state.get("hatch") or {}
    existing.hatch = _parse_door(hatch_data)

    hood_pos = (state.get("hood") or {}).get("position") or {}
    existing.hood = OpeningState(closed=hood_pos.get("status", "").lower() == "closed")

    moonroof_pos = (state.get("moonroof") or {}).get("position") or {}
    existing.moonroof = OpeningState(closed=moonroof_pos.get("status", "").lower() == "closed")

    # Windows
    existing.driver_window_closed = _is_win_closed(windows.get("driverSide"))
    existing.passenger_window_closed = _is_win_closed(windows.get("passengerSide"))
    existing.rear_driver_window_closed = _is_win_closed(windows.get("rearDriverSide"))
    existing.rear_passenger_window_closed = _is_win_closed(windows.get("rearPassengerSide"))

    # Tires
    existing.tire_front_left = _parse_tire(tires.get("frontLeft"))
    existing.tire_front_right = _parse_tire(tires.get("frontRight"))
    existing.tire_rear_left = _parse_tire(tires.get("rearLeft"))
    existing.tire_rear_right = _parse_tire(tires.get("rearRight"))

    # Engine / Pre-conditioning
    existing.climate_active = bool(engine.get("running"))

    # Telemetry
    odo = telemetry.get("odo") or {}
    if odo.get("value") is not None:
        val = float(odo["value"])
        unit = odo.get("unit", "").lower()
        existing.odometer_km = val * 1.60934 if "mi" in unit else val

    range_info = telemetry.get("range") or {}
    if range_info.get("value") is not None:
        r_val = float(range_info["value"])
        r_unit = range_info.get("unit", "").lower()
        existing.fuel_range_km = r_val * 1.60934 if "mi" in r_unit else r_val

    fuel_info = telemetry.get("fuelLevel") or {}
    if isinstance(fuel_info, dict) and fuel_info.get("value") is not None:
        existing.fuel_level_percent = float(fuel_info["value"])
    elif isinstance(telemetry.get("fuelLevel"), (int, float)):
        existing.fuel_level_percent = float(telemetry["fuelLevel"])

    # Location
    if location.get("latitude") and location.get("longitude"):
        existing.last_parked_latitude = float(location["latitude"])
        existing.last_parked_longitude = float(location["longitude"])

    # Electric (bZ4X)
    if electric:
        battery = electric.get("battery") or {}
        charging = electric.get("charging") or {}
        settings = charging.get("chargeSettings") or {}

        # Charging status mapping
        raw_status = str(charging.get("chargingStatus", "")).lower()
        if "charg" in raw_status:
            status_enum = ChargingStatus.CHARGING
        elif "stop" in raw_status:
            status_enum = ChargingStatus.STOPPED
        elif "comp" in raw_status:
            status_enum = ChargingStatus.COMPLETE
        elif "wait" in raw_status:
            status_enum = ChargingStatus.WAITING
        else:
            status_enum = ChargingStatus.UNKNOWN

        # Dashboard SOC % (prefers stateOfChargeDisplay)
        soc_display = (battery.get("stateOfChargeDisplay") or {}).get("value")
        if soc_display is None:
            soc_display = (battery.get("chargeRemainingAmount") or {}).get("value")

        conn = charging.get("connector") or {}
        plugged_in = bool(conn.get("plugStatus") or conn.get("plugInInfo"))

        existing.electric = ElectricVehicleStatus(
            battery_level=_safe_float(soc_display),
            charge_remaining_amount=_safe_float(
                (battery.get("chargeRemainingAmount") or {}).get("value")
            ),
            range_km=_distance_to_km(battery.get("travelableDistance")),
            range_ac_on_km=_distance_to_km(battery.get("travelableDistanceAC")),
            charging_status=status_enum,
            charging_power_kw=_safe_float((charging.get("actualChargingRate") or {}).get("value")),
            time_to_full_minutes=_safe_int(
                (charging.get("remainingChargeTime") or {}).get("value")
            ),
            time_to_80_minutes=_safe_int(
                (charging.get("remainingChargeTimeTo80Percent") or {}).get("value")
            ),
            plug_connected=plugged_in,
            target_charge_limit=_safe_int((settings.get("targetLimit") or {}).get("value")),
            max_ac_current_amps=_safe_int((settings.get("maxACCurrent") or {}).get("value")),
        )

    return existing


@asynccontextmanager
async def _resolve_session(session: aiohttp.ClientSession | None, auth: ToyotaAuth):
    """Yield explicitly provided session, active auth session, or a managed ephemeral session."""
    if session is not None and not session.closed:
        yield session
    elif auth._session is not None and not auth._session.closed:
        yield auth._session
    else:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as local_session:
            yield local_session


async def execute_graphql(
    auth: ToyotaAuth,
    query: str,
    variables: dict[str, Any],
    vin: str = "",
    region: str = "CA",
    brand_code: str = "T",
    user_agent: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, Any]:
    """Execute GraphQL query or mutation against AppSync endpoint."""
    token = await auth.get_access_token()
    guid = await auth.get_guid()

    headers = {
        "Content-Type": "application/json",
        "x-api-key": APPSYNC_API_KEY,
        "x-resolver-api-key": RESOLVER_API_KEY,
        "Authorization": f"Bearer {token}",
        "vin": vin,
        "x-guid": guid,
        "x-deviceid": auth.device_id,
        "X-BRAND": brand_code,
        "X-APPBRAND": brand_code,
        "X-Brand-Id": brand_code,
        "x-channel": "ONEAPP",
        "X-APPVERSION": "3.10.0",
        "X-OSNAME": "Android",
        "X-OSVERSION": "14",
        "x-region": region,
        "User-Agent": user_agent or USER_AGENT,
    }

    payload = json.dumps({"query": query, "variables": variables})

    async with (
        _resolve_session(session, auth) as active_session,
        active_session.post(GRAPHQL_HTTP_ENDPOINT, headers=headers, data=payload) as resp,
    ):
        body = await resp.text()
        if resp.status >= 400:
            _LOGGER.error("GraphQL HTTP error %d: %s", resp.status, body[:300])
            raise RuntimeError(f"GraphQL HTTP {resp.status}: {body[:200]}")
        result = json.loads(body)

    if result.get("errors"):
        err = result["errors"][0]
        _LOGGER.error("GraphQL error: %s: %s", err.get("errorType"), err.get("message"))
        raise RuntimeError(f"GraphQL error: {err.get('message')}")

    return result.get("data") or {}


class ToyotaAppSyncWebSocket:
    """Manages persistent AppSync WebSocket for realtime vehicle status & command callbacks."""

    def __init__(
        self,
        auth: ToyotaAuth,
        status_callback: Callable[[str, dict[str, Any]], None],
        command_callback: Callable[[str, dict[str, Any]], None] | None = None,
        brand_code: str = "T",
    ) -> None:
        self._auth = auth
        self._status_callback = status_callback
        self._command_callback = command_callback
        self._brand_code = brand_code
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._vins: list[str] = []
        self._region: str = "CA"
        self._subscriptions: dict[str, str] = {}  # sub_id -> vin
        self._running = False
        self._loop_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def start(self, vins: list[str], region: str = "CA") -> None:
        """Start background loop and register VINs."""
        self._vins = list(vins)
        self._region = region
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Gracefully disconnect WebSocket and terminate task."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        if self._loop_task:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task

    async def _run_loop(self) -> None:
        delay = 5
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                return
            except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, RuntimeError) as e:
                _LOGGER.debug("AppSync WebSocket error: %s", e)

            if not self._running:
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120)

    async def _connect_and_listen(self) -> None:
        token = await self._auth.get_access_token()
        guid = await self._auth.get_guid()

        auth_header = {
            "host": GRAPHQL_HOST,
            "x-api-key": APPSYNC_API_KEY,
            "Authorization": f"Bearer {token}",
            "x-channel": "ONEAPP",
            "x-region": self._region,
        }
        header_b64 = base64.b64encode(json.dumps(auth_header).encode()).decode()
        payload_b64 = base64.b64encode(b"{}").decode()
        url = f"{GRAPHQL_WS_ENDPOINT}?header={header_b64}&payload={payload_b64}"

        self._session = aiohttp.ClientSession(timeout=HTTP_TIMEOUT)
        try:
            self._ws = await self._session.ws_connect(url, protocols=["graphql-ws"], heartbeat=30)
            await self._ws.send_json({"type": "connection_init"})

            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    msg_type = data.get("type")

                    if msg_type == "connection_ack":
                        for vin in self._vins:
                            await self._subscribe_vin(vin, token, guid)
                            if self._command_callback:
                                await self._subscribe_command(vin, token, guid)
                    elif msg_type == "data":
                        payload = data.get("payload", {}).get("data", {})
                        if "onVehicleStatusUpdated" in payload:
                            status = payload["onVehicleStatusUpdated"]
                            vin = status.get("vin")
                            if vin:
                                self._status_callback(vin, status)
                        elif "onPostRemoteCallback" in payload and self._command_callback:
                            cmd_status = payload["onPostRemoteCallback"]
                            vin = cmd_status.get("vin")
                            if vin:
                                self._command_callback(vin, cmd_status)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            if self._ws and not self._ws.closed:
                await self._ws.close()
            if self._session and not self._session.closed:
                await self._session.close()

    async def _subscribe_vin(self, vin: str, token: str, guid: str) -> None:
        sub_id = str(uuid.uuid4())
        self._subscriptions[sub_id] = vin
        payload = {
            "id": sub_id,
            "type": "start",
            "payload": {
                "data": json.dumps(
                    {"query": RECEIVE_VEHICLE_STATUS_SUBSCRIPTION, "variables": {"vin": vin}}
                ),
                "extensions": {
                    "authorization": {
                        "host": GRAPHQL_HOST,
                        "x-api-key": APPSYNC_API_KEY,
                        "Authorization": f"Bearer {token}",
                        "x-channel": "ONEAPP",
                        "vin": vin,
                        "x-guid": guid,
                        "x-region": self._region,
                    }
                },
            },
        }
        if self._ws and not self._ws.closed:
            await self._ws.send_json(payload)

    async def _subscribe_command(self, vin: str, token: str, guid: str) -> None:
        sub_id = str(uuid.uuid4())
        self._subscriptions[sub_id] = vin
        payload = {
            "id": sub_id,
            "type": "start",
            "payload": {
                "data": json.dumps(
                    {
                        "query": RECEIVE_REMOTE_COMMAND_STATUS_SUBSCRIPTION,
                        "variables": {"vin": vin},
                    }
                ),
                "extensions": {
                    "authorization": {
                        "host": GRAPHQL_HOST,
                        "x-api-key": APPSYNC_API_KEY,
                        "Authorization": f"Bearer {token}",
                        "x-channel": "ONEAPP",
                        "vin": vin,
                        "x-guid": guid,
                        "x-region": self._region,
                    }
                },
            },
        }
        if self._ws and not self._ws.closed:
            await self._ws.send_json(payload)
