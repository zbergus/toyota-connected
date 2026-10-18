"""Smart wake policy and 12V auxiliary battery protection for Toyota vehicles.

ELECTRICAL & TELEMATICS BACKGROUND:
-----------------------------------
1. 12V Auxiliary Battery Vulnerability:
   Electrified vehicles (bZ4X BEV, RAV4 Prime PHEV, Prius Prime, Solterra, Lexus RZ)
   and standard hybrid/ICE vehicles maintain a small (35Ah-45Ah) 12V lead-acid/AGM
   auxiliary battery. In electrified vehicles, this battery powers the vehicle computers,
   DCM (Data Communication Module), and High-Voltage (HV) contactor relays.

2. Quiescent Sleep vs. Active DCM Wake:
   - When parked and asleep, the vehicle's high-voltage traction battery is disconnected
     via open contactors. The DC-DC converter does NOT continuously charge the 12V battery.
   - Quiescent sleep current is minimal (~15mA).
   - Sending an active cellular wake command (postRefreshStatus, postPreWake, or remote
     commands) forces the DCM to wake the High-Speed CAN and LIN buses and wake body ECUs.
   - Current draw jumps from 15mA to 5A-15A for 60-180 seconds per wake event.
   - Repeated wakes (e.g. while parked at an airport or home for days) will deplete
     the 12V battery, dropping terminal voltage below 11.8V, preventing the car from
     starting or closing HV contactors.

3. Multi-Layer Guard Protection Architecture:
   - Passive Cloud Polling: Normal background coordinator updates (every 5 minutes)
     ONLY query Toyota's cloud DynamoDB/cache. The DCM is NEVER pinged over cellular.
   - Trip Arrival Wake (JUST_STOPPED): Only trigger a fresh telematics sync when a
     vehicle has completed a trip (odometer advanced and has now stopped).
   - Hard Cooldown & Debounce: Rate-limits manual user service calls and remote commands
     to prevent rapid re-wake cycles (minimum cooldown interval).
   - Hourly Cap: Enforces a strict ceiling on active wakes per hour per vehicle.
   - Circuit Breaker: Automatically suspends wakes (SOFT_DISABLED) after consecutive
     failures (e.g. underground parking garage or dead zones) until the vehicle drives again.
   - Per-VIN Isolation: Independent state tracking prevents multi-vehicle fleet crosstalk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from .models import VehicleStatus

_LOGGER = logging.getLogger(__name__)


class WakeBlockReason(StrEnum):
    """Reason explaining wake eligibility or refusal."""

    ALLOWED_USER_COMMAND = "allowed_user_command"
    ALLOWED_TRIP_ARRIVAL = "allowed_trip_arrival"
    BLOCKED_COOLDOWN = "blocked_cooldown_active"
    BLOCKED_HOURLY_LIMIT = "blocked_hourly_rate_limit"
    BLOCKED_CIRCUIT_BREAKER = "blocked_consecutive_failures"
    BLOCKED_PARKED_ASLEEP = "blocked_vehicle_parked_and_asleep"


@dataclass(slots=True)
class VinWakeState:
    """Internal runtime state for one vehicle VIN."""

    last_odometer_km: float | None = None
    was_moving: bool = False
    last_wake_time: datetime | None = None
    recent_wake_timestamps: list[datetime] = field(default_factory=list)
    consecutive_failed_wakes: int = 0
    circuit_breaker_active: bool = False


class SmartWakeDecisionTree:
    """Deterministic wake logic and 12V battery protection guards."""

    def __init__(
        self,
        min_cooldown_seconds: int = 120,
        max_wakes_per_hour: int = 4,
        failed_wake_threshold: int = 3,
    ) -> None:
        self.min_cooldown = timedelta(seconds=min_cooldown_seconds)
        self.max_wakes_per_hour = max_wakes_per_hour
        self.failed_wake_threshold = failed_wake_threshold
        self._vin_states: dict[str, VinWakeState] = {}

    def _get_state(self, vin: str) -> VinWakeState:
        if vin not in self._vin_states:
            self._vin_states[vin] = VinWakeState()
        return self._vin_states[vin]

    def _prune_hourly_wakes(self, state: VinWakeState, current_time: datetime) -> None:
        cutoff = current_time - timedelta(hours=1)
        state.recent_wake_timestamps = [ts for ts in state.recent_wake_timestamps if ts > cutoff]

    def can_wake_vehicle(
        self,
        vin: str,
        vehicle: VehicleStatus | None,
        current_time: datetime,
        is_user_command: bool = False,
    ) -> tuple[bool, WakeBlockReason]:
        """Evaluate if an active cellular wake should be permitted for this VIN."""
        state = self._get_state(vin)
        self._prune_hourly_wakes(state, current_time)

        # 1. Circuit breaker check (e.g. underground parking dead-zone)
        if state.circuit_breaker_active and not is_user_command:
            return False, WakeBlockReason.BLOCKED_CIRCUIT_BREAKER

        # 2. Hard cooldown guard between wakes
        if state.last_wake_time is not None:
            time_since_last_wake = current_time - state.last_wake_time
            if time_since_last_wake < self.min_cooldown:
                return False, WakeBlockReason.BLOCKED_COOLDOWN

        # 3. Hourly rate limit ceiling guard
        if len(state.recent_wake_timestamps) >= self.max_wakes_per_hour:
            return False, WakeBlockReason.BLOCKED_HOURLY_LIMIT

        # 4. User commands bypass parked checks once cooldown & hourly limits pass
        if is_user_command:
            return True, WakeBlockReason.ALLOWED_USER_COMMAND

        # 5. Trip detection: car moving or just stopped
        if (
            vehicle
            and vehicle.odometer_km is not None
            and state.last_odometer_km is not None
            and vehicle.odometer_km > state.last_odometer_km
        ):
            state.was_moving = True
            state.last_odometer_km = vehicle.odometer_km
            # Car drove and is arriving
            return True, WakeBlockReason.ALLOWED_TRIP_ARRIVAL

        # Vehicle parked and asleep
        return False, WakeBlockReason.BLOCKED_PARKED_ASLEEP

    def record_wake(self, vin: str, current_time: datetime) -> None:
        """Record an active wake dispatch."""
        state = self._get_state(vin)
        state.last_wake_time = current_time
        state.recent_wake_timestamps.append(current_time)
        self._prune_hourly_wakes(state, current_time)

    def record_wake_failure(self, vin: str) -> None:
        """Record an active wake timeout or network failure."""
        state = self._get_state(vin)
        state.consecutive_failed_wakes += 1
        if state.consecutive_failed_wakes >= self.failed_wake_threshold:
            state.circuit_breaker_active = True
            _LOGGER.warning(
                "12V Protection: Vehicle %s unreachable after %d failed wake attempts. Circuit breaker activated.",
                vin,
                state.consecutive_failed_wakes,
            )

    def record_wake_success(self, vin: str) -> None:
        """Record successful wake confirmation."""
        state = self._get_state(vin)
        state.consecutive_failed_wakes = 0
        state.circuit_breaker_active = False

    def update_telemetry(self, vin: str, odometer_km: float | None, current_time: datetime) -> None:
        """Update passive telemetry without waking."""
        state = self._get_state(vin)
        if (
            odometer_km is not None
            and state.last_odometer_km is not None
            and odometer_km > state.last_odometer_km
        ):
            state.was_moving = True
            # Driving detected; clear circuit breaker
            state.circuit_breaker_active = False
            state.consecutive_failed_wakes = 0
        state.last_odometer_km = odometer_km

    def should_wake_vehicle(
        self,
        vehicle: VehicleStatus,
        current_time: datetime,
        is_user_command: bool = False,
    ) -> bool:
        """Convenience method matching legacy signature."""
        vin = vehicle.vin
        can_wake, _ = self.can_wake_vehicle(
            vin, vehicle, current_time, is_user_command=is_user_command
        )
        if can_wake:
            self.record_wake(vin, current_time)
            state = self._get_state(vin)
            state.last_odometer_km = vehicle.odometer_km
            return True

        state = self._get_state(vin)
        state.last_odometer_km = vehicle.odometer_km
        return False
