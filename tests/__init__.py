"""Test environment setup: mocks Home Assistant modules if running standalone."""

import sys
import types
from dataclasses import dataclass
from enum import Enum
from typing import Any


def _ensure_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = mod
    return sys.modules[name]


try:
    import homeassistant
except ImportError:
    # Set up lightweight mock stubs so standalone python3 -m unittest works
    ha = _ensure_module("homeassistant")
    ha_components = _ensure_module("homeassistant.components")
    ha_helpers = _ensure_module("homeassistant.helpers")
    ha_const = _ensure_module("homeassistant.const")
    ha_config = _ensure_module("homeassistant.config_entries")
    ha_core = _ensure_module("homeassistant.core")
    ha_exceptions = _ensure_module("homeassistant.exceptions")
    ha_diag = _ensure_module("homeassistant.components.diagnostics")
    ha_update = _ensure_module("homeassistant.helpers.update_coordinator")
    ha_device = _ensure_module("homeassistant.helpers.device_registry")
    ha_sensor = _ensure_module("homeassistant.components.sensor")
    ha_bin_sensor = _ensure_module("homeassistant.components.binary_sensor")
    ha_switch = _ensure_module("homeassistant.components.switch")
    ha_select = _ensure_module("homeassistant.components.select")
    ha_lock = _ensure_module("homeassistant.components.lock")
    ha_climate = _ensure_module("homeassistant.components.climate")
    ha_entity_plat = _ensure_module("homeassistant.helpers.entity_platform")
    ha_data_flow = _ensure_module("homeassistant.data_entry_flow")

    # AddEntitiesCallback
    class AddEntitiesCallback:
        def __call__(self, new_entities, update_before_add=False):
            pass

    ha_entity_plat.AddEntitiesCallback = AddEntitiesCallback

    # Core classes
    class HomeAssistant:
        def __init__(self):
            self.data = {}
            self.services = types.SimpleNamespace(async_register=lambda *args, **kwargs: None)
            self.config_entries = types.SimpleNamespace(
                async_update_entry=lambda *args, **kwargs: None,
                async_forward_entry_setups=lambda *args, **kwargs: None,
                async_unload_platforms=lambda *args, **kwargs: True,
            )

    class ServiceCall:
        def __init__(self, domain, service, data=None):
            self.domain = domain
            self.service = service
            self.data = data or {}

    ha_core.HomeAssistant = HomeAssistant
    ha_core.ServiceCall = ServiceCall

    class FlowResult(dict):
        pass

    ha_data_flow.FlowResult = FlowResult

    # Constants & Units
    class Platform(str, Enum):
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        SWITCH = "switch"
        SELECT = "select"
        LOCK = "lock"
        CLIMATE = "climate"

    ha_const.Platform = Platform
    ha_const.PERCENTAGE = "%"

    class UnitOfLength(str, Enum):
        KILOMETERS = "km"
        MILES = "mi"

    class UnitOfPower(str, Enum):
        KILO_WATT = "kW"

    class UnitOfPressure(str, Enum):
        KPA = "kPa"
        PSI = "psi"

    class UnitOfTime(str, Enum):
        MINUTES = "min"

    class UnitOfTemperature(str, Enum):
        CELSIUS = "°C"

    ha_const.UnitOfLength = UnitOfLength
    ha_const.UnitOfPower = UnitOfPower
    ha_const.UnitOfPressure = UnitOfPressure
    ha_const.UnitOfTime = UnitOfTime
    ha_const.UnitOfTemperature = UnitOfTemperature

    # Config entry
    class ConfigEntry:
        def __init__(self, entry_id="mock_id", data=None):
            self.entry_id = entry_id
            self.data = data or {}

        def as_dict(self):
            return {"entry_id": self.entry_id, "data": self.data}

    class ConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            cls.DOMAIN = domain

        async def async_set_unique_id(self, unique_id):
            return None

        def _abort_if_unique_id_configured(self):
            pass

        def async_show_form(self, step_id, data_schema, errors=None):
            return {"type": "form", "step_id": step_id, "errors": errors}

        def async_create_entry(self, title, data):
            return {"type": "create_entry", "title": title, "data": data}

    ha_config.ConfigEntry = ConfigEntry
    ha_config.ConfigFlow = ConfigFlow

    class ConfigEntryAuthFailed(Exception):
        pass

    ha_exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed

    # Coordinator
    class DataUpdateCoordinator:
        def __init__(self, hass, logger, name, update_method=None, update_interval=None):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_method = update_method
            self.update_interval = update_interval
            self.data = {}

        async def async_config_entry_first_refresh(self):
            if self.update_method:
                self.data = await self.update_method()

        async def async_request_refresh(self):
            if self.update_method:
                self.data = await self.update_method()

        def async_set_updated_data(self, data):
            self.data = data

    class UpdateFailed(Exception):
        pass

    ha_update.DataUpdateCoordinator = DataUpdateCoordinator
    ha_update.UpdateFailed = UpdateFailed

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        def async_write_ha_state(self):
            pass

    ha_update.CoordinatorEntity = CoordinatorEntity

    # Device registry
    class DeviceInfo(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    ha_device.DeviceInfo = DeviceInfo

    # Sensor entity classes
    class SensorDeviceClass(str, Enum):
        BATTERY = "battery"
        DISTANCE = "distance"
        POWER = "power"
        DURATION = "duration"
        PRESSURE = "pressure"

    class SensorStateClass(str, Enum):
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    @dataclass(frozen=True, kw_only=True)
    class SensorEntityDescription:
        key: str
        device_class: Any = None
        state_class: Any = None
        native_unit_of_measurement: str | None = None
        name: str | None = None

    class SensorEntity:
        pass

    ha_sensor.SensorDeviceClass = SensorDeviceClass
    ha_sensor.SensorStateClass = SensorStateClass
    ha_sensor.SensorEntityDescription = SensorEntityDescription
    ha_sensor.SensorEntity = SensorEntity

    # Binary sensor entity classes
    class BinarySensorDeviceClass(str, Enum):
        BATTERY_CHARGING = "battery_charging"
        PLUG = "plug"
        DOOR = "door"
        WINDOW = "window"

    @dataclass(frozen=True, kw_only=True)
    class BinarySensorEntityDescription:
        key: str
        device_class: Any = None
        name: str | None = None

    class BinarySensorEntity:
        pass

    ha_bin_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass
    ha_bin_sensor.BinarySensorEntityDescription = BinarySensorEntityDescription
    ha_bin_sensor.BinarySensorEntity = BinarySensorEntity

    # Switch entity classes
    class SwitchDeviceClass(str, Enum):
        SWITCH = "switch"

    class SwitchEntity:
        pass

    ha_switch.SwitchDeviceClass = SwitchDeviceClass
    ha_switch.SwitchEntity = SwitchEntity

    # Select entity classes
    class SelectEntity:
        pass

    ha_select.SelectEntity = SelectEntity

    # Lock entity classes
    class LockEntity:
        pass

    ha_lock.LockEntity = LockEntity

    # Climate entity classes
    class HVACMode(str, Enum):
        OFF = "off"
        HEAT_COOL = "heat_cool"

    class ClimateEntityFeature:
        TARGET_TEMPERATURE = 1
        PRESET_MODE = 2

    class ClimateEntity:
        pass

    ha_climate.HVACMode = HVACMode
    ha_climate.ClimateEntityFeature = ClimateEntityFeature
    ha_climate.ClimateEntity = ClimateEntity

    # Diagnostics
    def async_redact_data(data, to_redact):
        if isinstance(data, dict):
            return {k: ("**REDACTED**" if k in to_redact else async_redact_data(v, to_redact)) for k, v in data.items()}
        elif isinstance(data, list):
            return [async_redact_data(item, to_redact) for item in data]
        return data

    ha_diag.async_redact_data = async_redact_data
