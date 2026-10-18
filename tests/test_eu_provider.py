"""Unit tests for the European Regional Provider (EuropeProvider)."""

from __future__ import annotations

import tests  # Prepares mock Home Assistant stubs if not present

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.toyota_na.client import create_toyota_provider
from custom_components.toyota_na.client.auth import NotLoggedIn
from custom_components.toyota_na.client.eu_provider import EuropeProvider
from custom_components.toyota_na.client.models import (
    ChargingStatus,
    ElectricVehicleStatus,
    RemoteCommand,
    VehicleGeneration,
    VehicleStatus,
)
from custom_components.toyota_na.client.na_provider import NorthAmericaProvider


class TestEuropeProvider(unittest.IsolatedAsyncioTestCase):
    """Test suite for European regional provider."""

    def setUp(self) -> None:
        self.callback_mock = MagicMock()
        self.provider = EuropeProvider(
            token_callback=self.callback_mock,
            initial_tokens={
                "access_token": "eu_access_123",
                "refresh_token": "eu_refresh_456",
                "id_token": "eu_id_789",
                "guid": "eu_sub_user_001",
                "expires_at": time.time() + 3600,
                "region": "eu",
            },
        )

    def test_provider_factory(self) -> None:
        """Verify create_toyota_provider returns EuropeProvider for 'eu' and NorthAmericaProvider for 'na'."""
        eu = create_toyota_provider("eu")
        self.assertIsInstance(eu, EuropeProvider)
        self.assertEqual(eu.region_code, "eu")

        na = create_toyota_provider("na")
        self.assertIsInstance(na, NorthAmericaProvider)
        self.assertEqual(na.region_code, "na")

        # Case-insensitivity check
        eu_caps = create_toyota_provider("EU")
        self.assertIsInstance(eu_caps, EuropeProvider)

    def test_token_get_and_set(self) -> None:
        """Verify token retrieval and updating."""
        tokens = self.provider.get_tokens()
        self.assertEqual(tokens["access_token"], "eu_access_123")
        self.assertEqual(tokens["refresh_token"], "eu_refresh_456")
        self.assertEqual(tokens["guid"], "eu_sub_user_001")
        self.assertEqual(tokens["region"], "eu")

        self.provider.set_tokens({
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_at": 1700000000.0,
        })
        updated = self.provider.get_tokens()
        self.assertEqual(updated["access_token"], "new_access")
        self.assertEqual(updated["refresh_token"], "new_refresh")
        self.assertEqual(updated["expires_at"], 1700000000.0)

    async def test_check_tokens_raises_if_not_logged_in(self) -> None:
        """Verify check_tokens raises NotLoggedIn when session has no tokens."""
        empty_provider = EuropeProvider()
        with self.assertRaises(NotLoggedIn):
            await empty_provider.check_tokens()

    def test_parse_eu_vehicle_status(self) -> None:
        """Test European ctpa-oneapi vehicle status payload parsing."""
        vehicle = VehicleStatus(
            vin="SB1EVTEST12345678",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
        )

        raw_payload = {
            "vehicleStatus": {
                "doors": {
                    "driverSide": {"position": "closed", "lock": "locked"},
                    "passengerSide": {"position": "closed", "lock": "locked"},
                    "rearDriverSide": {"position": "open", "lock": "unlocked"},
                    "rearPassengerSide": {"position": "closed", "lock": "locked"},
                },
                "windows": {
                    "driverSide": {"position": "closed"},
                    "passengerSide": {"position": "open"},
                },
                "hatch": {"position": "closed", "lock": "locked"},
            }
        }

        self.provider._parse_eu_vehicle_status(raw_payload, vehicle)

        self.assertTrue(vehicle.driver_door.closed)
        self.assertTrue(vehicle.driver_door.locked)
        self.assertFalse(vehicle.rear_driver_door.closed)
        self.assertFalse(vehicle.rear_driver_door.locked)
        self.assertTrue(vehicle.driver_window_closed)
        self.assertFalse(vehicle.passenger_window_closed)
        self.assertTrue(vehicle.hatch.closed)
        self.assertTrue(vehicle.hatch.locked)

    def test_parse_eu_electric_status(self) -> None:
        """Test European ctpa-oneapi electric status payload parsing."""
        vehicle = VehicleStatus(
            vin="SB1EVTEST12345678",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            is_electric=True,
        )

        raw_payload = {
            "batteryLevel": 77,
            "evRange": {"value": 365.5, "unit": "km"},
            "evRangeWithAc": {"value": 328.0, "unit": "km"},
            "chargingStatus": "charging",
            "remainingChargeTime": 45,
            "canSetNextChargingEvent": True,
        }

        self.provider._parse_eu_electric_status(raw_payload, vehicle)

        self.assertIsNotNone(vehicle.electric)
        ev = vehicle.electric
        self.assertEqual(ev.battery_level, 77.0)
        self.assertEqual(ev.range_km, 365.5)
        self.assertEqual(ev.range_ac_on_km, 328.0)
        self.assertEqual(ev.charging_status, ChargingStatus.CHARGING)
        self.assertEqual(ev.time_to_full_minutes, 45)
        self.assertTrue(ev.plug_connected)

    async def test_send_remote_command_doors(self) -> None:
        """Verify remote door lock/unlock calls the correct EU endpoint."""
        with patch.object(self.provider, "_api_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"status": "success"}

            res = await self.provider.send_remote_command("SB1EVTEST12345678", RemoteCommand.DOOR_LOCK)
            self.assertEqual(res, {"status": "success"})
            mock_req.assert_called_once_with(
                "POST",
                "/v1/global/remote/command",
                vin="SB1EVTEST12345678",
                json_data={"command": "door-lock"},
            )

            mock_req.reset_mock()
            await self.provider.send_remote_command("SB1EVTEST12345678", RemoteCommand.DOOR_UNLOCK)
            mock_req.assert_called_once_with(
                "POST",
                "/v1/global/remote/command",
                vin="SB1EVTEST12345678",
                json_data={"command": "door-unlock"},
            )

    async def test_send_remote_command_climate(self) -> None:
        """Verify remote climate control calls /v2/remote/climate-control in EU."""
        with patch.object(self.provider, "_api_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"status": "climate_started"}

            res = await self.provider.send_remote_command("SB1EVTEST12345678", RemoteCommand.ENGINE_START)
            self.assertEqual(res, {"status": "climate_started"})
            mock_req.assert_called_once_with(
                "POST",
                "/v2/remote/climate-control",
                vin="SB1EVTEST12345678",
                json_data={"command": "start", "targetTemperature": 21.0},
            )


if __name__ == "__main__":
    unittest.main()
