"""Unit tests for multi-brand architecture (Toyota, Lexus, Subaru Solterra)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import tests  # noqa: F401 - Prepares mock Home Assistant stubs if not present
from toyota_connected import create_toyota_provider
from toyota_connected.auth import ToyotaAuth
from toyota_connected.brands import (
    DEFAULT_BRAND,
    LEXUS,
    SUBARU,
    TOYOTA,
    get_brand,
)
from toyota_connected.models import VehicleGeneration
from toyota_connected.na_provider import NorthAmericaProvider


class TestMultiBrandRegistry(unittest.IsolatedAsyncioTestCase):
    """Test suite for BrandConfig registry and provider parameterization."""

    def test_brand_resolution(self) -> None:
        """Verify get_brand correctly resolves slugs, codes, and fallbacks."""
        self.assertEqual(get_brand("toyota"), TOYOTA)
        self.assertEqual(get_brand("T"), TOYOTA)
        self.assertEqual(get_brand("t"), TOYOTA)

        self.assertEqual(get_brand("lexus"), LEXUS)
        self.assertEqual(get_brand("L"), LEXUS)

        self.assertEqual(get_brand("subaru"), SUBARU)
        self.assertEqual(get_brand("S"), SUBARU)

        # Fallback for unknown brand
        self.assertEqual(get_brand("unknown_car"), DEFAULT_BRAND)
        self.assertEqual(get_brand(None), DEFAULT_BRAND)

    def test_brand_endpoints_and_headers(self) -> None:
        """Verify brand-specific OpenAM URLs and scoping headers."""
        # Toyota
        self.assertEqual(TOYOTA.auth_host, "login.toyotadriverslogin.com")
        self.assertEqual(
            TOYOTA.authenticate_url,
            "https://login.toyotadriverslogin.com/json/realms/root/realms/tmna-native/authenticate",
        )
        self.assertEqual(
            TOYOTA.headers(),
            {"X-BRAND": "T", "X-APPBRAND": "T", "X-Brand-Id": "T"},
        )

        # Subaru
        self.assertEqual(SUBARU.auth_host, "login.subarudriverslogin.com")
        self.assertEqual(
            SUBARU.authenticate_url,
            "https://login.subarudriverslogin.com/json/realms/root/realms/tmna-native/authenticate",
        )
        self.assertEqual(
            SUBARU.headers(),
            {"X-BRAND": "S", "X-APPBRAND": "S", "X-Brand-Id": "S"},
        )
        self.assertTrue(SUBARU.bootstrap_on_empty)

        # Lexus
        self.assertEqual(LEXUS.auth_host, "login.lexusdriverslogin.com")
        self.assertEqual(
            LEXUS.headers(),
            {"X-BRAND": "L", "X-APPBRAND": "L", "X-Brand-Id": "L"},
        )

    def test_toyota_auth_subaru_host(self) -> None:
        """Verify ToyotaAuth uses the Subaru OpenAM host when configured."""
        auth = ToyotaAuth(auth_host="login.subarudriverslogin.com")
        self.assertEqual(auth.auth_host, "login.subarudriverslogin.com")
        self.assertEqual(
            auth.authenticate_url,
            "https://login.subarudriverslogin.com/json/realms/root/realms/tmna-native/authenticate",
        )
        self.assertEqual(
            auth.authorize_url,
            "https://login.subarudriverslogin.com/oauth2/realms/root/realms/tmna-native/authorize",
        )
        self.assertEqual(
            auth.access_token_url,
            "https://login.subarudriverslogin.com/oauth2/realms/root/realms/tmna-native/access_token",
        )

    async def test_subaru_provider_vehicle_manufacturer(self) -> None:
        """Verify NorthAmericaProvider with Subaru sets vehicle manufacturer to Subaru."""
        provider = create_toyota_provider("na", brand="subaru")
        self.assertIsInstance(provider, NorthAmericaProvider)
        self.assertEqual(provider.brand, SUBARU)

        mock_vehicles = [
            {
                "vin": "JF2EAAA12P8123456",
                "modelName": "Solterra",
                "modelYear": "2024",
                "generation": "24MM",
                "evVehicle": True,
                "subscriptionStatus": "ACTIVE",
            }
        ]

        with patch.object(provider.rest, "get_vehicle_list", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_vehicles
            vehicles = await provider.get_user_vehicles()

            self.assertEqual(len(vehicles), 1)
            v = vehicles[0]
            self.assertEqual(v.vin, "JF2EAAA12P8123456")
            self.assertEqual(v.model_name, "Solterra")
            self.assertEqual(v.manufacturer, "Subaru")
            self.assertTrue(v.is_electric)
            self.assertEqual(v.generation, VehicleGeneration.MM24)

    async def test_subaru_empty_discovery_bootstrap(self) -> None:
        """Verify that when vehicle list is empty for Subaru, v4/account bootstrap is called."""
        provider = NorthAmericaProvider(brand="subaru")

        with (
            patch.object(provider.rest, "get_vehicle_list", new_callable=AsyncMock) as mock_list,
            patch.object(provider.rest, "bootstrap_account", new_callable=AsyncMock) as mock_boot,
        ):
            # First returns empty list, second call after bootstrap returns Solterra
            mock_list.side_effect = [
                [],
                [
                    {
                        "vin": "JF2EAAA12P8123456",
                        "modelName": "Solterra EV",
                        "modelYear": "2024",
                        "generation": "24MM",
                        "evVehicle": True,
                    }
                ],
            ]
            mock_boot.return_value = {"status": "ok"}

            vehicles = await provider.get_user_vehicles()

            mock_boot.assert_called_once()
            self.assertEqual(len(vehicles), 1)
            self.assertEqual(vehicles[0].model_name, "Solterra EV")

    async def test_config_flow_brand_retention(self) -> None:
        """Verify ToyotaConfigFlow retains the selected brand across step_credentials."""
        from custom_components.toyota_connected.config_flow import ToyotaConfigFlow

        flow = ToyotaConfigFlow()
        flow.hass = None
        await flow.async_step_user({"region": "na", "brand": "subaru"})
        self.assertEqual(flow._brand, "subaru")

        # Simulate provider being None before step_credentials
        flow._provider = None
        with patch(
            "custom_components.toyota_connected.config_flow.create_toyota_provider"
        ) as mock_create:
            mock_provider = AsyncMock()
            mock_create.return_value = mock_provider
            await flow.async_step_credentials(
                {"username": "solterra_owner@example.com", "password": "pass"}
            )
            mock_create.assert_called_once_with(region="na", brand="subaru", session=None)


if __name__ == "__main__":
    unittest.main()
