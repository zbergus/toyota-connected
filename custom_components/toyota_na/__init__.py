"""Toyota Connected Services Home Assistant Integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ToyotaClient
from .client.auth import AuthError, ToyotaAuth
from .client.graphql import ToyotaAppSyncWebSocket, parse_appsync_vehicle_status
from .client.models import RemoteCommand, VehicleStatus
from .const import (
    DOMAIN,
    SERVICE_CLIMATE_START,
    SERVICE_CLIMATE_STOP,
    SERVICE_DOOR_LOCK,
    SERVICE_DOOR_UNLOCK,
    SERVICE_REFRESH,
    SERVICE_SET_CHARGE_LIMIT,
    SERVICE_START_CHARGE,
    SERVICE_STOP_CHARGE,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.LOCK,
    Platform.CLIMATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Toyota Connected Services from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    def token_callback(tokens: dict[str, Any]) -> None:
        _LOGGER.debug("OAuth tokens renewed; persisting to ConfigEntry")
        data = dict(entry.data)
        data["tokens"] = tokens
        hass.config_entries.async_update_entry(entry, data=data)

    auth = ToyotaAuth(
        token_callback=token_callback,
        initial_tokens=entry.data.get("tokens"),
    )

    try:
        await auth.check_tokens()
    except AuthError as err:
        _LOGGER.warning("Token check failed, reauth required: %s", err)
        raise ConfigEntryAuthFailed(err) from err

    client = ToyotaClient(auth)

    async def async_update_data() -> dict[str, VehicleStatus]:
        try:
            vehicles = await client.get_user_vehicles()
            vehicle_map: dict[str, VehicleStatus] = {}
            for v in vehicles:
                await client.update_vehicle_status(v)
                vehicle_map[v.vin] = v
            return vehicle_map
        except AuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except Exception as err:
            _LOGGER.exception("Failed to update Toyota vehicle data: %s", err)
            raise UpdateFailed(err) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
    )

    await coordinator.async_config_entry_first_refresh()

    # WebSocket Realtime Event Handler for push updates (doors, charging, battery)
    def ws_status_callback(vin: str, raw_payload: dict[str, Any]) -> None:
        current_data = coordinator.data or {}
        if vin in current_data:
            vehicle = current_data[vin]
            parse_appsync_vehicle_status(raw_payload, vehicle)
            coordinator.async_set_updated_data(dict(current_data))
            _LOGGER.debug("Realtime WebSocket push updated state for VIN ...%s", vin[-4:])

    ws = ToyotaAppSyncWebSocket(auth, ws_status_callback)
    subscribed_vins = [v.vin for v in (coordinator.data or {}).values() if v.subscribed]
    region = next((v.region for v in (coordinator.data or {}).values()), "CA")

    if subscribed_vins:
        await ws.start(subscribed_vins, region=region)
        client.ws = ws

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "ws": ws,
    }

    # Register platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register integration service calls
    async def handle_service(call: ServiceCall) -> None:
        service_name = call.service
        vin = call.data.get("vin")
        if not vin and coordinator.data:
            vin = next(iter(coordinator.data.keys()))

        if not vin or vin not in (coordinator.data or {}):
            _LOGGER.error("Invalid or missing VIN for service %s", service_name)
            return

        vehicle = coordinator.data[vin]

        if service_name == SERVICE_DOOR_LOCK:
            await client.send_remote_command(vin, RemoteCommand.DOOR_LOCK, region=vehicle.region)
        elif service_name == SERVICE_DOOR_UNLOCK:
            await client.send_remote_command(vin, RemoteCommand.DOOR_UNLOCK, region=vehicle.region)
        elif service_name == SERVICE_START_CHARGE:
            await client.send_remote_command(vin, RemoteCommand.IMMEDIATE_CHARGE, region=vehicle.region)
        elif service_name == SERVICE_STOP_CHARGE:
            await client.send_remote_command(vin, RemoteCommand.CHARGE_STOP, region=vehicle.region)
        elif service_name == SERVICE_CLIMATE_START:
            await client.send_remote_command(vin, RemoteCommand.ENGINE_START, region=vehicle.region)
        elif service_name == SERVICE_CLIMATE_STOP:
            await client.send_remote_command(vin, RemoteCommand.ENGINE_STOP, region=vehicle.region)
        elif service_name == SERVICE_SET_CHARGE_LIMIT:
            limit = int(call.data.get("limit", 80))
            await client.set_charge_limit(vin, limit, region=vehicle.region)
        elif service_name == SERVICE_REFRESH:
            await coordinator.async_request_refresh()

    for srv in (
        SERVICE_DOOR_LOCK,
        SERVICE_DOOR_UNLOCK,
        SERVICE_START_CHARGE,
        SERVICE_STOP_CHARGE,
        SERVICE_CLIMATE_START,
        SERVICE_CLIMATE_STOP,
        SERVICE_SET_CHARGE_LIMIT,
        SERVICE_REFRESH,
    ):
        hass.services.async_register(DOMAIN, srv, handle_service)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Toyota Connected Services config entry."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    ws: ToyotaAppSyncWebSocket | None = entry_data.get("ws")
    if ws:
        await ws.stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
