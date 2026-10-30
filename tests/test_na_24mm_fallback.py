"""24MM vehicles whose cloud status is empty must still get telemetry-backed entities.

Shape taken from upstream reports of a 2026 RAV4 Hybrid (generation 24MM, can300Capable=false):
status and electric status come back null while telemetry carries odometer, fuel level and
location (widewing/ha-toyota-na#196). The fixture is redacted and contains no real identifiers.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import tests  # noqa: F401 - Prepares mock Home Assistant stubs if not present
from toyota_connected.graphql import VehicleNotFoundOnAppSync
from toyota_connected.models import VehicleGeneration, VehicleStatus
from toyota_connected.na_provider import NorthAmericaProvider

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "contracts"
    / "fixtures"
    / "na_telemetry_24mm_sparse.json"
)


def _hybrid_24mm() -> VehicleStatus:
    return VehicleStatus(
        vin="4T3TESTVIN24MM001",
        model_name="RAV4 Hybrid",
        model_year="2026",
        generation=VehicleGeneration.MM24,
        region="US",
        manufacturer="Toyota",
        subscribed=True,
        is_electric=False,
        backdoor_type="hatch",
    )


class Na24mmTelemetryFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.telemetry = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.provider = NorthAmericaProvider(brand="toyota")
        self.provider.rest.get_vehicle_status = AsyncMock(return_value=None)
        self.provider.rest.get_electric_status = AsyncMock(return_value=None)
        self.provider.rest.get_telemetry = AsyncMock(return_value=self.telemetry)

    def _assert_telemetry_applied(self, vehicle: VehicleStatus) -> None:
        self.assertEqual(vehicle.fuel_level_percent, 79.0)
        self.assertAlmostEqual(vehicle.odometer_km or 0.0, 166 * 1.60934, delta=0.1)
        self.assertEqual(vehicle.last_parked_latitude, 45.4215)
        self.assertEqual(vehicle.last_parked_longitude, -75.6972)

    async def test_vehicle_not_on_appsync_falls_back_to_rest_and_telemetry(self) -> None:
        with patch(
            "toyota_connected.na_provider.execute_graphql",
            new_callable=AsyncMock,
            side_effect=VehicleNotFoundOnAppSync("not on stencil"),
        ):
            vehicle = await self.provider.update_vehicle_status(_hybrid_24mm())

        self.provider.rest.get_vehicle_status.assert_awaited_once()
        self._assert_telemetry_applied(vehicle)

    async def test_empty_appsync_result_still_gets_telemetry(self) -> None:
        with patch(
            "toyota_connected.na_provider.execute_graphql",
            new_callable=AsyncMock,
            return_value={},
        ):
            vehicle = await self.provider.update_vehicle_status(_hybrid_24mm())

        self._assert_telemetry_applied(vehicle)

    async def test_appsync_error_falls_back_and_null_telemetry_fields_do_not_raise(self) -> None:
        with patch(
            "toyota_connected.na_provider.execute_graphql",
            new_callable=AsyncMock,
            side_effect=RuntimeError("appsync down"),
        ):
            vehicle = await self.provider.update_vehicle_status(_hybrid_24mm())

        self._assert_telemetry_applied(vehicle)
        # Null tire pressures and distance-to-empty stay unset rather than raising.
        self.assertIsNone(vehicle.tire_front_left.psi)
        self.assertIsNone(vehicle.fuel_range_km)


if __name__ == "__main__":
    unittest.main()
