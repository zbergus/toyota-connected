"""Unit tests for bZ4X AppSync GraphQL payload parsing."""

from __future__ import annotations

import tests  # Prepares mock Home Assistant stubs if not present

import unittest

from custom_components.toyota_na.client.graphql import parse_appsync_vehicle_status
from custom_components.toyota_na.client.models import (
    ChargingStatus,
    VehicleGeneration,
    VehicleStatus,
)


class TestBz4xModelParsing(unittest.TestCase):
    """Test 2024 bZ4X BEV AppSync GraphQL parsing."""

    def setUp(self) -> None:
        self.vehicle = VehicleStatus(
            vin="4T1BZ4X2024MOCK01",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            region="CA",
            is_electric=True,
        )

    def test_parse_bz4x_payload(self) -> None:
        """Verify parsing of full bZ4X GraphQL payload."""
        sample_payload = {
            "vin": "4T1BZ4X2024MOCK01",
            "lastUpdateDateTime": "2026-10-18T12:00:00Z",
            "vehicleState": {
                "doors": {
                    "driverSide": {"position": {"status": "closed"}, "lock": {"status": "locked"}},
                    "passengerSide": {"position": {"status": "closed"}, "lock": {"status": "locked"}},
                    "rearDriverSide": {"position": {"status": "closed"}, "lock": {"status": "locked"}},
                    "rearPassengerSide": {"position": {"status": "open"}, "lock": {"status": "unlocked"}},
                },
                "windows": {
                    "driverSide": {"position": {"status": "closed"}},
                    "passengerSide": {"position": {"status": "open"}},
                },
                "hatch": {"position": {"status": "closed"}, "lock": {"status": "locked"}},
                "hood": {"position": {"status": "closed"}},
                "moonroof": {"position": {"status": "closed"}},
                "tires": {
                    "frontLeft": {"kpa": 240.0, "psi": 34.8, "displayLowTirePressureWarning": False},
                    "frontRight": {"kpa": 242.0, "psi": 35.1, "displayLowTirePressureWarning": False},
                    "rearLeft": {"kpa": 238.0, "psi": 34.5, "displayLowTirePressureWarning": False},
                    "rearRight": {"kpa": 210.0, "psi": 30.5, "displayLowTirePressureWarning": True},
                },
                "engine": {"running": False, "status": "stopped"},
            },
            "location": {"latitude": 45.4215, "longitude": -75.6972},
            "telemetry": {
                "odo": {"value": 15420.5, "unit": "km"},
                "range": {"value": 380, "unit": "km"},
            },
            "electric": {
                "battery": {
                    "stateOfChargeDisplay": {"value": 85},
                    "chargeRemainingAmount": {"value": 82.5},
                    "travelableDistance": {"value": 410.0, "unit": "km"},
                    "travelableDistanceAC": {"value": 365.0, "unit": "km"},
                },
                "charging": {
                    "chargingStatus": "charging",
                    "actualChargingRate": {"value": 11.2, "unit": "kW"},
                    "remainingChargeTime": {"value": 45, "unit": "min"},
                    "remainingChargeTimeTo80Percent": {"value": 0, "unit": "min"},
                    "connector": {"plugStatus": 1, "status": "connected"},
                    "chargeSettings": {
                        "targetLimit": {"value": 90, "unit": "%"},
                        "maxACCurrent": {"value": 32, "setting": "32A"},
                    },
                },
            },
        }

        updated = parse_appsync_vehicle_status(sample_payload, self.vehicle)

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

        # bZ4X BEV Metrics
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


if __name__ == "__main__":
    unittest.main()
