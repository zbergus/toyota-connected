"""Toyota Connected Services Home Assistant Integration (Region Agnostic)."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

# Ensure src/ or bundled directory is accessible if running without pip install
_SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
_LOCAL_DIR = Path(__file__).resolve().parent
if _LOCAL_DIR.exists() and str(_LOCAL_DIR) not in sys.path:
    sys.path.insert(0, str(_LOCAL_DIR))

from toyota_connected import (  # noqa: E402
    RemoteCommand,
    SmartWakeDecisionTree,
    ToyotaRegionProvider,
    VehicleStatus,
    create_toyota_provider,
)
from toyota_connected.auth import AuthError  # noqa: E402
from toyota_connected.graphql import parse_appsync_vehicle_status  # noqa: E402

from .const import (  # noqa: E402
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

    region = entry.data.get("region", "na")
    brand = entry.data.get("brand", "toyota")
    session = async_get_clientsession(hass)
    provider: ToyotaRegionProvider = create_toyota_provider(
        region=region,
        brand=brand,
        token_callback=token_callback,
        initial_tokens=entry.data.get("tokens"),
        session=session,
    )

    try:
        await provider.check_tokens()
    except AuthError as err:
        _LOGGER.warning("Token validation failed, reauth required: %s", err)
        raise ConfigEntryAuthFailed(err) from err

    smart_wake = SmartWakeDecisionTree()

    async def async_update_data() -> dict[str, VehicleStatus]:
        try:
            vehicles = await provider.get_user_vehicles()
            vehicle_map: dict[str, VehicleStatus] = {}
            now = datetime.now(UTC)
            for v in vehicles:
                await provider.update_vehicle_status(v)
                vehicle_map[v.vin] = v
                smart_wake.update_telemetry(v.vin, v.odometer_km, now)
            return vehicle_map
        except AuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except Exception as err:
            _LOGGER.exception("Failed to update Toyota vehicle data")
            raise UpdateFailed(err) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
    )

    await coordinator.async_config_entry_first_refresh()

    # Realtime push events listener (AppSync WebSockets for NA)
    def realtime_status_callback(vin: str, raw_payload: dict[str, Any]) -> None:
        current_data = coordinator.data or {}
        if vin in current_data:
            vehicle = current_data[vin]
            parse_appsync_vehicle_status(raw_payload, vehicle)
            coordinator.async_set_updated_data(dict(current_data))
            _LOGGER.debug("Realtime push updated state for VIN ...%s", vin[-4:])

    subscribed_vins = [v.vin for v in (coordinator.data or {}).values() if v.subscribed]
    if subscribed_vins:
        await provider.start_realtime_listener(subscribed_vins, realtime_status_callback)

    hass.data[DOMAIN][entry.entry_id] = {
        "provider": provider,
        "coordinator": coordinator,
        "smart_wake": smart_wake,
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

        now = datetime.now(UTC)
        if service_name == SERVICE_DOOR_LOCK:
            smart_wake.record_wake(vin, now)
            await provider.send_remote_command(vin, RemoteCommand.DOOR_LOCK)
        elif service_name == SERVICE_DOOR_UNLOCK:
            smart_wake.record_wake(vin, now)
            await provider.send_remote_command(vin, RemoteCommand.DOOR_UNLOCK)
        elif service_name == SERVICE_START_CHARGE:
            smart_wake.record_wake(vin, now)
            await provider.send_remote_command(vin, RemoteCommand.IMMEDIATE_CHARGE)
        elif service_name == SERVICE_STOP_CHARGE:
            smart_wake.record_wake(vin, now)
            await provider.send_remote_command(vin, RemoteCommand.CHARGE_STOP)
        elif service_name == SERVICE_CLIMATE_START:
            smart_wake.record_wake(vin, now)
            await provider.send_remote_command(vin, RemoteCommand.ENGINE_START)
        elif service_name == SERVICE_CLIMATE_STOP:
            smart_wake.record_wake(vin, now)
            await provider.send_remote_command(vin, RemoteCommand.ENGINE_STOP)
        elif service_name == SERVICE_SET_CHARGE_LIMIT:
            limit = int(call.data.get("limit", 80))
            await provider.set_charge_limit(vin, limit)
        elif service_name == SERVICE_REFRESH:
            vehicle = coordinator.data.get(vin)
            can_wake, reason = smart_wake.can_wake_vehicle(vin, vehicle, now, is_user_command=True)
            if not can_wake:
                _LOGGER.warning(
                    "12V battery protection: refresh request throttled for %s (reason: %s)",
                    vin,
                    reason,
                )
                return
            smart_wake.record_wake(vin, now)
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
    provider: ToyotaRegionProvider | None = entry_data.get("provider")
    if provider:
        await provider.stop_realtime_listener()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Unregister services if no active entries remain
    if not hass.data[DOMAIN]:
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
            hass.services.async_remove(DOMAIN, srv)

    return unload_ok
