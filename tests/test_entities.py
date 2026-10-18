"""Unit tests for entity state derivation and diagnostics redaction."""

from __future__ import annotations

import tests  # Prepares mock Home Assistant stubs if not present

import unittest

from custom_components.toyota_na.client.models import (
    ChargingStatus,
    ElectricVehicleStatus,
    OpeningState,
    TirePressure,
    VehicleGeneration,
    VehicleStatus,
)
from custom_components.toyota_na.diagnostics import TO_REDACT, async_redact_data
from custom_components.toyota_na.sensor import SENSOR_DESCRIPTIONS


class TestEntitiesAndDiagnostics(unittest.TestCase):
    """Test entity value extraction and sensitive data redaction."""

    def setUp(self) -> None:
        self.vehicle = VehicleStatus(
            vin="2T3BZ4XCANADA2024",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            region="CA",
            is_electric=True,
            odometer_km=12345.6,
            electric=ElectricVehicleStatus(
                battery_level=88.0,
                range_km=420.0,
                range_ac_on_km=380.0,
                charging_power_kw=7.2,
                time_to_full_minutes=60,
                charging_status=ChargingStatus.CHARGING,
                plug_connected=True,
                target_charge_limit=80,
                max_ac_current_amps=32,
            ),
            tire_front_left=TirePressure(kpa=240.0),
        )

    def test_sensor_values(self) -> None:
        """Verify all sensor description extractors work as expected."""
        desc_map = {d.key: d for d in SENSOR_DESCRIPTIONS}

        self.assertEqual(desc_map["battery_level"].value_fn(self.vehicle), 88.0)
        self.assertEqual(desc_map["ev_range"].value_fn(self.vehicle), 420.0)
        self.assertEqual(desc_map["ev_range_ac_on"].value_fn(self.vehicle), 380.0)
        self.assertEqual(desc_map["charging_power"].value_fn(self.vehicle), 7.2)
        self.assertEqual(desc_map["time_to_full"].value_fn(self.vehicle), 60)
        self.assertEqual(desc_map["odometer"].value_fn(self.vehicle), 12345.6)
        self.assertEqual(desc_map["tire_front_left"].value_fn(self.vehicle), 240.0)

    def test_diagnostics_redaction(self) -> None:
        """Verify tokens, passwords, GUIDs, and coordinates are redacted."""
        raw_dump = {
            "entry": {
                "username": "user@example.ca",
                "tokens": {"access_token": "secret_token_123", "refresh_token": "secret_refresh_456"},
                "guid": "private_guid_789",
            },
            "vehicle": {
                "latitude": 45.4215,
                "longitude": -75.6972,
                "battery": 88.0,
            },
        }

        redacted = async_redact_data(raw_dump, TO_REDACT)

        self.assertEqual(redacted["entry"]["username"], "**REDACTED**")
        self.assertEqual(redacted["entry"]["tokens"], "**REDACTED**")
        self.assertEqual(redacted["entry"]["guid"], "**REDACTED**")
        self.assertEqual(redacted["vehicle"]["latitude"], "**REDACTED**")
        self.assertEqual(redacted["vehicle"]["longitude"], "**REDACTED**")
        self.assertEqual(redacted["vehicle"]["battery"], 88.0)


if __name__ == "__main__":
    unittest.main()
