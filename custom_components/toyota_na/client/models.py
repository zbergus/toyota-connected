"""Data models for Toyota Connected Services API entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


class VehicleGeneration(str, Enum):
    CY17 = "17CY"
    CY17PLUS = "17CYPLUS"
    MM21 = "21MM"
    MM24 = "24MM"
    MM25 = "25MM"
    GR86 = "GR86"
    PRE17CY = "PRE17CY"
    UNKNOWN = "UNKNOWN"


class ChargingStatus(str, Enum):
    CHARGING = "charging"
    STOPPED = "stopped"
    COMPLETE = "complete"
    WAITING = "waiting"
    ERROR = "error"
    UNKNOWN = "unknown"


class RemoteCommand(str, Enum):
    DOOR_LOCK = "door-lock"
    DOOR_UNLOCK = "door-unlock"
    ENGINE_START = "engine-start"
    ENGINE_STOP = "engine-stop"
    HAZARD_ON = "hazard-on"
    HAZARD_OFF = "hazard-off"
    SOUND_HORN = "sound-horn"
    BUZZER_WARNING = "buzzer-warning"
    WINDOW_OPEN = "power-window-open"
    WINDOW_CLOSE = "power-window-close"
    IMMEDIATE_CHARGE = "immediate-charge"
    CHARGE_STOP = "charge-stop"


@dataclass
class TirePressure:
    psi: float | None = None
    kpa: float | None = None
    bar: float | None = None
    low_pressure_warning: bool = False


@dataclass
class OpeningState:
    closed: bool = True
    locked: bool | None = None


@dataclass
class ElectricVehicleStatus:
    """Full electric vehicle status model, specialized for bZ4X BEV."""
    battery_level: float | None = None             # Dashboard state of charge (0-100%)
    charge_remaining_amount: float | None = None   # Usable capacity %
    range_km: float | None = None                  # Driving range with AC OFF (km)
    range_ac_on_km: float | None = None            # Driving range with AC ON (km)
    charging_status: ChargingStatus = ChargingStatus.UNKNOWN
    charging_power_kw: float | None = None         # Active charging rate (kW)
    time_to_full_minutes: int | None = None        # Remaining minutes to 100%
    time_to_80_minutes: int | None = None          # Remaining minutes to 80%
    plug_connected: bool = False                   # Connector plugged in
    target_charge_limit: int | None = None         # Selected charge limit % (e.g. 80%)
    max_ac_current_amps: int | None = None         # Max AC current in Amps
    v2l_power_supply_hours: float | None = None    # V2L power supply time
    last_updated: datetime | None = None


@dataclass
class VehicleStatus:
    """Comprehensive vehicle state combining AppSync GraphQL and REST telemetry."""
    vin: str
    model_name: str
    model_year: str
    generation: VehicleGeneration
    region: str = "CA"                             # Default "CA" for Canada, "US" for USA
    manufacturer: str = "Toyota"                   # "Toyota", "Lexus", or "Subaru"
    subscribed: bool = True
    is_electric: bool = False                      # True for bZ4X
    backdoor_type: str = "hatch"

    # Openings & Locks
    driver_door: OpeningState = field(default_factory=OpeningState)
    passenger_door: OpeningState = field(default_factory=OpeningState)
    rear_driver_door: OpeningState = field(default_factory=OpeningState)
    rear_passenger_door: OpeningState = field(default_factory=OpeningState)
    hatch: OpeningState = field(default_factory=OpeningState)
    hood: OpeningState = field(default_factory=OpeningState)
    moonroof: OpeningState = field(default_factory=OpeningState)

    # Windows
    driver_window_closed: bool = True
    passenger_window_closed: bool = True
    rear_driver_window_closed: bool = True
    rear_passenger_window_closed: bool = True

    # Tires
    tire_front_left: TirePressure = field(default_factory=TirePressure)
    tire_front_right: TirePressure = field(default_factory=TirePressure)
    tire_rear_left: TirePressure = field(default_factory=TirePressure)
    tire_rear_right: TirePressure = field(default_factory=TirePressure)

    # Telemetry
    odometer_km: float | None = None
    fuel_level_percent: float | None = None
    fuel_range_km: float | None = None
    last_parked_latitude: float | None = None
    last_parked_longitude: float | None = None

    # Climate / Remote Start
    climate_active: bool = False
    climate_target_temp_c: float | None = None

    # Electric (bZ4X)
    electric: ElectricVehicleStatus | None = None
    last_update_timestamp: datetime | None = None
