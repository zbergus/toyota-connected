"""Unit tests for smart wake policy and 12V auxiliary battery protection."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

import tests  # noqa: F401 - Prepares mock Home Assistant stubs if not present
from toyota_connected.models import VehicleGeneration, VehicleStatus
from toyota_connected.smart_refresh import (
    SmartWakeDecisionTree,
    WakeBlockReason,
)


class TestSmartWakePolicy(unittest.TestCase):
    """Test 12V battery protection wake rules."""

    def setUp(self) -> None:
        self.tree = SmartWakeDecisionTree(
            min_cooldown_seconds=120,
            max_wakes_per_hour=4,
            failed_wake_threshold=3,
        )
        self.vehicle = VehicleStatus(
            vin="4T1BZ4X2024MOCK01",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            odometer_km=1000.0,
        )

    def test_parked_vehicle_sleeps_without_wake(self) -> None:
        """Vehicle parked with constant odometer should NOT trigger active wake."""
        now = datetime.now(UTC)
        # Initial poll
        self.assertFalse(self.tree.should_wake_vehicle(self.vehicle, now))
        # 1 hour later, vehicle still parked
        self.assertFalse(self.tree.should_wake_vehicle(self.vehicle, now + timedelta(hours=1)))
        # 5 hours later, vehicle still parked
        self.assertFalse(self.tree.should_wake_vehicle(self.vehicle, now + timedelta(hours=5)))

    def test_trip_arrival_wakes_vehicle(self) -> None:
        """When odometer increases (trip occurred), wake once to refresh final state."""
        now = datetime.now(UTC)
        self.tree.should_wake_vehicle(self.vehicle, now)

        # Car drove 15 km
        self.vehicle.odometer_km = 1015.0
        self.assertTrue(self.tree.should_wake_vehicle(self.vehicle, now + timedelta(minutes=30)))

        # Next poll, parked at destination -> stays asleep
        self.assertFalse(self.tree.should_wake_vehicle(self.vehicle, now + timedelta(minutes=35)))

    def test_user_command_wakes_immediately(self) -> None:
        """User remote command triggers immediate wake."""
        now = datetime.now(UTC)
        self.assertTrue(self.tree.should_wake_vehicle(self.vehicle, now, is_user_command=True))

    def test_user_command_cooldown_throttles_rapid_wakes(self) -> None:
        """Rapid successive user commands must be throttled by minimum cooldown."""
        now = datetime.now(UTC)
        # First wake succeeds
        can_wake_1, reason_1 = self.tree.can_wake_vehicle(
            self.vehicle.vin, self.vehicle, now, is_user_command=True
        )
        self.assertTrue(can_wake_1)
        self.assertEqual(reason_1, WakeBlockReason.ALLOWED_USER_COMMAND)
        self.tree.record_wake(self.vehicle.vin, now)

        # Second wake 30 seconds later (under 120s cooldown) is blocked
        thirty_secs_later = now + timedelta(seconds=30)
        can_wake_2, reason_2 = self.tree.can_wake_vehicle(
            self.vehicle.vin, self.vehicle, thirty_secs_later, is_user_command=True
        )
        self.assertFalse(can_wake_2)
        self.assertEqual(reason_2, WakeBlockReason.BLOCKED_COOLDOWN)

        # Third wake after cooldown (130s later) succeeds
        after_cooldown = now + timedelta(seconds=130)
        can_wake_3, reason_3 = self.tree.can_wake_vehicle(
            self.vehicle.vin, self.vehicle, after_cooldown, is_user_command=True
        )
        self.assertTrue(can_wake_3)
        self.assertEqual(reason_3, WakeBlockReason.ALLOWED_USER_COMMAND)

    def test_hourly_rate_limit_blocks_excessive_wakes(self) -> None:
        """Hard ceiling of 4 wakes per hour prevents 12V battery drain."""
        base_time = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)

        # Dispatch 4 spaced wakes within an hour (every 10 minutes)
        for i in range(4):
            wake_time = base_time + timedelta(minutes=10 * i)
            can_wake, _ = self.tree.can_wake_vehicle(
                self.vehicle.vin, self.vehicle, wake_time, is_user_command=True
            )
            self.assertTrue(can_wake, f"Wake {i + 1} should be permitted")
            self.tree.record_wake(self.vehicle.vin, wake_time)

        # 5th wake within the same hour (at minute 40) is blocked by hourly limit
        fifth_wake_time = base_time + timedelta(minutes=40)
        can_wake_5, reason_5 = self.tree.can_wake_vehicle(
            self.vehicle.vin, self.vehicle, fifth_wake_time, is_user_command=True
        )
        self.assertFalse(can_wake_5)
        self.assertEqual(reason_5, WakeBlockReason.BLOCKED_HOURLY_LIMIT)

        # After 1 hour rolls over, wakes become permitted again
        one_hour_later = base_time + timedelta(minutes=75)
        can_wake_6, _ = self.tree.can_wake_vehicle(
            self.vehicle.vin, self.vehicle, one_hour_later, is_user_command=True
        )
        self.assertTrue(can_wake_6)

    def test_circuit_breaker_after_consecutive_failures(self) -> None:
        """Vehicle failing to respond 3 times trips circuit breaker to stop draining 12V."""
        now = datetime.now(UTC)
        vin = self.vehicle.vin

        # Record 2 failures -> not yet tripped
        self.tree.record_wake_failure(vin)
        self.tree.record_wake_failure(vin)
        can_wake, _ = self.tree.can_wake_vehicle(vin, self.vehicle, now)
        self.assertFalse(self.tree._get_state(vin).circuit_breaker_active)

        # 3rd failure trips the circuit breaker
        self.tree.record_wake_failure(vin)
        self.assertTrue(self.tree._get_state(vin).circuit_breaker_active)

        # Next automatic check is blocked by circuit breaker
        can_wake, reason = self.tree.can_wake_vehicle(vin, self.vehicle, now)
        self.assertFalse(can_wake)
        self.assertEqual(reason, WakeBlockReason.BLOCKED_CIRCUIT_BREAKER)

    def test_circuit_breaker_resets_on_driving(self) -> None:
        """Driving (odometer advance) proves vehicle is awake and clears circuit breaker."""
        now = datetime.now(UTC)
        vin = self.vehicle.vin

        # Trip circuit breaker
        for _ in range(3):
            self.tree.record_wake_failure(vin)
        self.assertTrue(self.tree._get_state(vin).circuit_breaker_active)

        # Car drives 20 km
        self.tree.update_telemetry(vin, 1000.0, now)
        self.tree.update_telemetry(vin, 1020.0, now + timedelta(minutes=15))

        # Circuit breaker is cleared
        self.assertFalse(self.tree._get_state(vin).circuit_breaker_active)

    def test_multi_vehicle_isolation(self) -> None:
        """Two vehicles on same account maintain completely isolated 12V states."""
        now = datetime.now(UTC)
        vin_1 = "VIN_BZ4X_01"
        vin_2 = "VIN_RAV4_02"

        v1 = VehicleStatus(
            vin=vin_1,
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            odometer_km=5000.0,
        )
        v2 = VehicleStatus(
            vin=vin_2,
            model_name="RAV4",
            model_year="2023",
            generation=VehicleGeneration.MM21,
            odometer_km=42000.0,
        )

        # Wake VIN 1
        self.tree.record_wake(vin_1, now)

        # VIN 1 is under cooldown
        can_wake_1, reason_1 = self.tree.can_wake_vehicle(
            vin_1, v1, now + timedelta(seconds=30), is_user_command=True
        )
        self.assertFalse(can_wake_1)
        self.assertEqual(reason_1, WakeBlockReason.BLOCKED_COOLDOWN)

        # VIN 2 is NOT under cooldown
        can_wake_2, reason_2 = self.tree.can_wake_vehicle(
            vin_2, v2, now + timedelta(seconds=30), is_user_command=True
        )
        self.assertTrue(can_wake_2)
        self.assertEqual(reason_2, WakeBlockReason.ALLOWED_USER_COMMAND)


if __name__ == "__main__":
    unittest.main()
