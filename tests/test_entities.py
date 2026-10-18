"""Unit tests for entity state derivation and diagnostics redaction."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

import tests  # noqa: F401 - Prepares mock Home Assistant stubs if not present
from custom_components.toyota_connected import async_unload_entry
from custom_components.toyota_connected.const import DOMAIN, SERVICE_DOOR_LOCK
from custom_components.toyota_connected.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
    async_redact_data,
)
from custom_components.toyota_connected.sensor import SENSOR_DESCRIPTIONS
from toyota_connected.models import (
    ChargingStatus,
    ElectricVehicleStatus,
    TirePressure,
    VehicleGeneration,
    VehicleStatus,
)


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

        # Gas / Hybrid vehicle test
        gas_vehicle = VehicleStatus(
            vin="4T1B11HK5JU123456",
            model_name="RAV4 Hybrid",
            model_year="2023",
            generation=VehicleGeneration.MM21,
            is_electric=False,
            fuel_level_percent=65.0,
            fuel_range_km=520.0,
        )
        self.assertEqual(desc_map["fuel_level"].value_fn(gas_vehicle), 65.0)
        self.assertEqual(desc_map["fuel_range"].value_fn(gas_vehicle), 520.0)

    def test_diagnostics_redaction(self) -> None:
        """Verify tokens, passwords, GUIDs, and coordinates are redacted."""
        raw_dump = {
            "entry": {
                "username": "user@example.ca",
                "tokens": {
                    "access_token": "secret_token_123",
                    "refresh_token": "secret_refresh_456",
                },
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


class TestIntegrationLifecycle(unittest.IsolatedAsyncioTestCase):
    """Test service registration and cleanup on integration entry unload."""

    async def test_service_cleanup_on_unload(self) -> None:
        hass = HomeAssistant()
        entry_mock = MagicMock()
        entry_mock.entry_id = "test_entry_001"

        provider_mock = AsyncMock()
        hass.data[DOMAIN] = {
            entry_mock.entry_id: {
                "provider": provider_mock,
                "coordinator": MagicMock(),
            }
        }

        removed_services: list[tuple[str, str]] = []
        hass.services.async_remove = lambda domain, srv: removed_services.append((domain, srv))

        unload_ok = await async_unload_entry(hass, entry_mock)
        self.assertTrue(unload_ok)
        provider_mock.stop_realtime_listener.assert_called_once()
        self.assertIn((DOMAIN, SERVICE_DOOR_LOCK), removed_services)
        self.assertEqual(len(removed_services), 8)

    async def test_async_get_config_entry_diagnostics_with_bev(self) -> None:
        """Verify diagnostics generation successfully serializes slotted ElectricVehicleStatus."""
        hass = HomeAssistant()
        entry_mock = MagicMock()
        entry_mock.entry_id = "test_entry_bev"
        entry_mock.as_dict.return_value = {
            "entry_id": "test_entry_bev",
            "domain": DOMAIN,
            "data": {
                "username": "driver@example.ca",
                "tokens": {"access_token": "secret_token"},
            },
        }

        bev_vehicle = VehicleStatus(
            vin="4T1BZ4XTEST0000001",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            is_electric=True,
            electric=ElectricVehicleStatus(
                battery_level=82.0,
                range_km=405.0,
                charging_status=ChargingStatus.CHARGING,
                plug_connected=True,
            ),
        )

        coordinator_mock = MagicMock()
        coordinator_mock.data = {bev_vehicle.vin: bev_vehicle}

        hass.data[DOMAIN] = {
            entry_mock.entry_id: {
                "coordinator": coordinator_mock,
            }
        }

        diag = await async_get_config_entry_diagnostics(hass, entry_mock)
        self.assertIn("vehicles", diag)
        self.assertIn("entry", diag)

        redacted_vin = bev_vehicle.vin[:8] + "..." + bev_vehicle.vin[-4:]
        self.assertIn(redacted_vin, diag["vehicles"])
        veh_diag = diag["vehicles"][redacted_vin]
        self.assertEqual(veh_diag["is_electric"], True)
        self.assertIsNotNone(veh_diag["electric"])
        self.assertEqual(veh_diag["electric"]["battery_level"], 82.0)
        self.assertEqual(veh_diag["electric"]["charging_status"], "charging")


if __name__ == "__main__":
    unittest.main()
