"""Contract verification test suite.

Verifies that the Python SDK (toyota-connected) strictly conforms to the canonical
golden JSON fixtures in contracts/fixtures/.
"""

from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import tests  # noqa: F401 - Prepares mock Home Assistant stubs if not present
from toyota_connected.graphql import (
    CONFIRM_SUBSCRIPTION_MUTATION,
    PRE_WAKE_MUTATION,
    REFRESH_STATUS_MUTATION,
    parse_appsync_vehicle_status,
)
from toyota_connected.models import (
    ChargingStatus,
    VehicleGeneration,
    VehicleStatus,
)
from toyota_connected.na_provider import NorthAmericaProvider
from toyota_connected.rest import (
    ToyotaRestClient,
    parse_rest_electric_status,
    parse_rest_telemetry,
    parse_rest_vehicle_status,
)


class TestContractFixtures(unittest.IsolatedAsyncioTestCase):
    """Verify golden contract fixtures parse accurately into typed domain models."""

    def setUp(self) -> None:
        self.fixtures_dir = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"

    def test_bev_metric_telemetry_contract(self) -> None:
        """Verify contracts/fixtures/telemetry_bev_metric.json contract."""
        data = json.loads(
            (self.fixtures_dir / "telemetry_bev_metric.json").read_text(encoding="utf-8")
        )
        vehicle = VehicleStatus(
            vin="4T1BZ4XCONTRACT01",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            is_electric=True,
        )
        updated = parse_appsync_vehicle_status(data, vehicle)

        self.assertEqual(updated.odometer_km, 15420.5)
        self.assertIsNotNone(updated.electric)
        assert updated.electric is not None
        self.assertEqual(updated.electric.battery_level, 85.0)
        self.assertEqual(updated.electric.charging_power_kw, 11.2)
        self.assertEqual(updated.electric.charging_status, ChargingStatus.CHARGING)
        self.assertTrue(updated.electric.plug_connected)
        self.assertEqual(updated.electric.target_charge_limit, 90)
        self.assertEqual(updated.electric.max_ac_current_amps, 32)

    def test_hybrid_ice_telemetry_contract(self) -> None:
        """Verify contracts/fixtures/telemetry_hybrid_ice.json contract."""
        data = json.loads(
            (self.fixtures_dir / "telemetry_hybrid_ice.json").read_text(encoding="utf-8")
        )
        vehicle = VehicleStatus(
            vin="4T1HYBRIDCONTRACT02",
            model_name="RAV4 Hybrid",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            is_electric=False,
        )
        updated = parse_appsync_vehicle_status(data, vehicle)

        self.assertEqual(updated.odometer_km, 28500.0)
        self.assertEqual(updated.fuel_range_km, 650.0)
        self.assertIsNone(updated.electric)

    def test_na_rest_fixtures_contract(self) -> None:
        """Verify contracts/fixtures/na_*.json fixtures match 21MM BEV domain model."""
        vehicle = VehicleStatus(
            vin="4T1BZ4X2024MOCK01",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM21,
            region="CA",
            is_electric=True,
        )

        # 1. Electric status fixture
        elec_data = json.loads(
            (self.fixtures_dir / "na_electric_status_bev.json").read_text(encoding="utf-8")
        )
        parse_rest_electric_status(elec_data, vehicle)
        self.assertIsNotNone(vehicle.electric)
        assert vehicle.electric is not None
        self.assertEqual(vehicle.electric.battery_level, 71.0)
        self.assertEqual(vehicle.electric.range_km, 259.9)
        self.assertEqual(vehicle.electric.range_ac_on_km, 231.3)
        self.assertEqual(vehicle.electric.charging_status, ChargingStatus.STOPPED)
        self.assertFalse(vehicle.electric.plug_connected)
        self.assertEqual(vehicle.climate_target_temp_c, 21.0)

        # 2. Telemetry fixture
        telem_data = json.loads(
            (self.fixtures_dir / "na_telemetry_bev.json").read_text(encoding="utf-8")
        )
        parse_rest_telemetry(telem_data, vehicle)
        self.assertEqual(vehicle.odometer_km, 37758.0)
        self.assertEqual(vehicle.tire_front_left.psi, 38.0)
        self.assertEqual(vehicle.tire_rear_right.psi, 38.0)

        # 3. Remote status fixture
        remote_data = json.loads(
            (self.fixtures_dir / "na_remote_status.json").read_text(encoding="utf-8")
        )
        parse_rest_vehicle_status(remote_data, vehicle)
        self.assertTrue(vehicle.driver_door.closed)
        self.assertTrue(vehicle.driver_door.locked)
        self.assertTrue(vehicle.hatch.closed)
        self.assertTrue(vehicle.driver_window_closed)
        self.assertEqual(vehicle.last_parked_latitude, 45.4215)
        self.assertEqual(vehicle.last_parked_longitude, -75.6972)

    async def test_na_provider_sdk_graphql_methods(self) -> None:
        """Verify new typed SDK methods (confirm_subscription, send_pre_wake, refresh_status) dispatch properly."""
        provider = NorthAmericaProvider(brand="toyota")

        with patch(
            "toyota_connected.na_provider.execute_graphql", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = {"status": "ok"}

            # confirm_subscription
            await provider.confirm_subscription("4T1TESTVIN001", region="CA")
            mock_exec.assert_called_with(
                provider.auth,
                CONFIRM_SUBSCRIPTION_MUTATION,
                {"vin": "4T1TESTVIN001"},
                vin="4T1TESTVIN001",
                region="CA",
                brand_code=provider.brand.code,
                user_agent=provider.brand.user_agent,
                session=provider._session,
            )

            # send_pre_wake
            mock_exec.reset_mock()
            await provider.send_pre_wake("guid_user_123", region="CA")
            mock_exec.assert_called_with(
                provider.auth,
                PRE_WAKE_MUTATION,
                {"guid": "guid_user_123"},
                region="CA",
                brand_code=provider.brand.code,
                user_agent=provider.brand.user_agent,
                session=provider._session,
            )

            # refresh_status
            mock_exec.reset_mock()
            await provider.refresh_status("4T1TESTVIN001", region="US")
            mock_exec.assert_called_with(
                provider.auth,
                REFRESH_STATUS_MUTATION,
                {"vin": "4T1TESTVIN001"},
                vin="4T1TESTVIN001",
                region="US",
                brand_code=provider.brand.code,
                user_agent=provider.brand.user_agent,
                session=provider._session,
            )

    async def test_rest_headers_contain_correlation_id(self) -> None:
        """Verify REST client generates valid UUIDv4 correlation IDs with correct casing."""
        mock_auth = MagicMock()
        mock_auth.get_access_token = AsyncMock(return_value="mock_token")
        mock_auth.get_guid = AsyncMock(return_value="mock_guid")

        client = ToyotaRestClient(mock_auth, brand="toyota")
        headers = await client._headers(vin="4T1TESTVIN001", region="CA")

        self.assertIn("x-correlationId", headers)
        self.assertIn("X-CorrelationId", headers)
        self.assertIn("X-CORRELATIONID", headers)

        # Ensure value is a valid UUIDv4
        parsed = uuid.UUID(headers["x-correlationId"])
        self.assertEqual(parsed.version, 4)
        self.assertEqual(headers["X-CorrelationId"], headers["x-correlationId"])
        self.assertEqual(headers["X-CORRELATIONID"], headers["x-correlationId"])

    async def test_electric_status_prefers_v3_with_v2_fallback(self) -> None:
        """Verify electric status requests v3 first, and falls back to v2 if v3 fails."""
        mock_auth = MagicMock()
        mock_auth.get_access_token = AsyncMock(return_value="mock_token")
        mock_auth.get_guid = AsyncMock(return_value="mock_guid")

        client = ToyotaRestClient(mock_auth, brand="toyota")

        # Scenario 1: v3 succeeds
        v3_payload = {"vehicleInfo": {"chargeInfo": {"chargeRemainingAmount": 75}}}
        with patch.object(client, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = v3_payload
            res = await client.get_electric_status("4T1TESTVIN001", region="CA")
            self.assertEqual(res, v3_payload)
            mock_req.assert_called_once_with(
                "GET",
                "v3/electric/status",
                vin="4T1TESTVIN001",
                region="CA",
                extra_headers={"X-GENERATION": "21MM"},
            )

        # Scenario 2: v3 fails, falls back to v2
        v2_payload = {"vehicleInfo": {"chargeInfo": {"chargeRemainingAmount": 70}}}
        with patch.object(client, "request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                ValueError("500 Internal Server Error"),
                v2_payload,
            ]
            res = await client.get_electric_status("4T1TESTVIN001", region="CA")
            self.assertEqual(res, v2_payload)
            self.assertEqual(mock_req.call_count, 2)
            self.assertEqual(mock_req.call_args_list[0][0][1], "v3/electric/status")
            self.assertEqual(mock_req.call_args_list[1][0][1], "v2/electric/status")


if __name__ == "__main__":
    unittest.main()
