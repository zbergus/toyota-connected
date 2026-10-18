"""Contract verification test suite.

Verifies that the Python SDK (toyota-connected) strictly conforms to the shared
golden JSON fixtures in contracts/fixtures/ that also validate the Swift SDK (ConnectedKit).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


if __name__ == "__main__":
    unittest.main()
