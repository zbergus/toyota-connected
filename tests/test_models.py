"""Unit tests for vehicle AppSync GraphQL telematics payload parsing (BEV, PHEV, Hybrid, and ICE)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import tests  # noqa: F401 - Prepares mock Home Assistant stubs if not present
from toyota_connected.graphql import parse_appsync_vehicle_status
from toyota_connected.models import (
    ChargingStatus,
    VehicleGeneration,
    VehicleStatus,
)


class TestVehicleTelemetryParsing(unittest.TestCase):
    """Test AppSync GraphQL telemetry parsing across BEV, PHEV, Hybrid, and ICE vehicles."""

    def setUp(self) -> None:
        self.fixtures_dir = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"
        self.ev_vehicle = VehicleStatus(
            vin="4T1EVTEST2024MOCK01",
            model_name="bZ4X / Solterra / RZ",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            region="CA",
            is_electric=True,
        )
        self.ice_vehicle = VehicleStatus(
            vin="4T1HYBRID2024MOCK02",
            model_name="RAV4 Hybrid / Camry / RX",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            region="CA",
            is_electric=False,
        )

    def test_parse_bev_phev_metric_payload(self) -> None:
        """Verify parsing of full electrified vehicle GraphQL payload from golden fixture."""
        sample_payload = json.loads(
            (self.fixtures_dir / "telemetry_bev_metric.json").read_text(encoding="utf-8")
        )
        updated = parse_appsync_vehicle_status(sample_payload, self.ev_vehicle)

        # Doors & Openings
        self.assertTrue(updated.driver_door.closed)
        self.assertTrue(updated.driver_door.locked)
        self.assertFalse(updated.rear_passenger_door.closed)
        self.assertFalse(updated.rear_passenger_door.locked)
        self.assertTrue(updated.hatch.closed)
        self.assertFalse(updated.passenger_window_closed)

        # Tires (Metric kPa)
        self.assertEqual(updated.tire_front_left.kpa, 240.0)
        self.assertTrue(updated.tire_rear_right.low_pressure_warning)

        # Telemetry & Location
        self.assertEqual(updated.odometer_km, 15420.5)
        self.assertEqual(updated.last_parked_latitude, 45.4215)
        self.assertEqual(updated.last_parked_longitude, -75.6972)

        # Electrified Vehicle Metrics (bZ4X, Solterra, RZ, RAV4 Prime, etc.)
        self.assertIsNotNone(updated.electric)
        ev = updated.electric
        self.assertEqual(ev.battery_level, 85.0)
        self.assertEqual(ev.charge_remaining_amount, 82.5)
        self.assertEqual(ev.range_km, 410.0)
        self.assertEqual(ev.range_ac_on_km, 365.0)
        self.assertEqual(ev.charging_status, ChargingStatus.CHARGING)
        self.assertEqual(ev.charging_power_kw, 11.2)
        self.assertEqual(ev.time_to_full_minutes, 45)
        self.assertTrue(ev.plug_connected)
        self.assertEqual(ev.target_charge_limit, 90)
        self.assertEqual(ev.max_ac_current_amps, 32)

    def test_parse_bev_phev_imperial_payload(self) -> None:
        """Verify parsing and unit conversion of imperial (miles) telemetry from golden fixture."""
        imperial_payload = json.loads(
            (self.fixtures_dir / "telemetry_bev_imperial.json").read_text(encoding="utf-8")
        )
        updated = parse_appsync_vehicle_status(imperial_payload, self.ev_vehicle)
        self.assertAlmostEqual(updated.odometer_km, 16093.4, places=1)
        self.assertAlmostEqual(updated.fuel_range_km, 321.868, places=1)
        self.assertIsNotNone(updated.electric)
        self.assertAlmostEqual(updated.electric.range_km, 321.868, places=1)
        self.assertAlmostEqual(updated.electric.range_ac_on_km, 289.6812, places=1)
        self.assertEqual(updated.electric.charging_status, ChargingStatus.STOPPED)

    def test_parse_hybrid_ice_payload(self) -> None:
        """Verify standard hybrid / ICE vehicles parse without error when electric block is null."""
        hybrid_payload = json.loads(
            (self.fixtures_dir / "telemetry_hybrid_ice.json").read_text(encoding="utf-8")
        )
        updated = parse_appsync_vehicle_status(hybrid_payload, self.ice_vehicle)

        self.assertEqual(updated.odometer_km, 28500.0)
        self.assertEqual(updated.fuel_range_km, 650.0)
        self.assertTrue(updated.driver_door.closed)
        self.assertTrue(updated.driver_door.locked)
        self.assertEqual(updated.tire_front_left.kpa, 235.0)
        # Verify electric telemetry is cleanly None for ICE/Hybrid
        self.assertIsNone(updated.electric)


if __name__ == "__main__":
    unittest.main()
