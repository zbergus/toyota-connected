"""Unit tests for smart wake policy (12V auxiliary battery protection)."""

from __future__ import annotations

import tests  # Prepares mock Home Assistant stubs if not present

from datetime import datetime, timedelta, timezone
import unittest

from custom_components.toyota_na.client.models import VehicleGeneration, VehicleStatus


class SmartWakeDecisionTree:
    """Deterministic wake logic preventing 12V battery drain."""

    def __init__(self) -> None:
        self.last_odometer_km: float | None = None
        self.last_wake_time: datetime | None = None

    def should_wake_vehicle(
        self,
        vehicle: VehicleStatus,
        current_time: datetime,
        is_user_command: bool = False,
    ) -> bool:
        """Decide whether to trigger an active telematics wake."""
        if is_user_command:
            self.last_wake_time = current_time
            return True

        # If vehicle was moving and has now stopped, sync final parked state
        if self.last_odometer_km is not None and vehicle.odometer_km is not None:
            if vehicle.odometer_km > self.last_odometer_km:
                self.last_odometer_km = vehicle.odometer_km
                # Car is moving or just arrived
                self.last_wake_time = current_time
                return True

        self.last_odometer_km = vehicle.odometer_km

        # If car is parked and asleep, DO NOT wake unless explicitly requested
        return False


class TestSmartWakePolicy(unittest.TestCase):
    """Test 12V battery protection wake rules."""

    def setUp(self) -> None:
        self.tree = SmartWakeDecisionTree()
        self.vehicle = VehicleStatus(
            vin="4T1BZ4X2024MOCK01",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            odometer_km=1000.0,
        )

    def test_parked_vehicle_sleeps_without_wake(self) -> None:
        """Vehicle parked with constant odometer should NOT trigger active wake."""
        now = datetime.now(timezone.utc)
        # Initial poll
        self.assertFalse(self.tree.should_wake_vehicle(self.vehicle, now))
        # 1 hour later, vehicle still parked
        self.assertFalse(self.tree.should_wake_vehicle(self.vehicle, now + timedelta(hours=1)))
        # 5 hours later, vehicle still parked
        self.assertFalse(self.tree.should_wake_vehicle(self.vehicle, now + timedelta(hours=5)))

    def test_trip_arrival_wakes_vehicle(self) -> None:
        """When odometer increases (trip occurred), wake once to refresh final state."""
        now = datetime.now(timezone.utc)
        self.tree.should_wake_vehicle(self.vehicle, now)

        # Car drove 15 km
        self.vehicle.odometer_km = 1015.0
        self.assertTrue(self.tree.should_wake_vehicle(self.vehicle, now + timedelta(minutes=30)))

        # Next poll, parked at destination -> stays asleep
        self.assertFalse(self.tree.should_wake_vehicle(self.vehicle, now + timedelta(minutes=35)))

    def test_user_command_wakes_immediately(self) -> None:
        """User remote command triggers immediate wake."""
        now = datetime.now(timezone.utc)
        self.assertTrue(self.tree.should_wake_vehicle(self.vehicle, now, is_user_command=True))


if __name__ == "__main__":
    unittest.main()
