"""Unit tests for GraphQL queries, mutation execution, and push payload parsing."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

import tests  # noqa: F401 - Prepares mock Home Assistant stubs if not present
from toyota_connected.auth import ToyotaAuth
from toyota_connected.graphql import (
    CONFIRM_SUBSCRIPTION_MUTATION,
    GET_VEHICLE_STATUS_QUERY,
    POST_CHARGE_SETTINGS_MUTATION,
    PRE_WAKE_MUTATION,
    RECEIVE_REMOTE_COMMAND_STATUS_SUBSCRIPTION,
    RECEIVE_VEHICLE_STATUS_SUBSCRIPTION,
    REFRESH_STATUS_MUTATION,
    SEND_REMOTE_COMMAND_MUTATION,
    ToyotaAppSyncWebSocket,
    execute_graphql,
    parse_appsync_vehicle_status,
)
from toyota_connected.models import VehicleGeneration, VehicleStatus


class TestGraphQLContractAndExecution(unittest.IsolatedAsyncioTestCase):
    """Test GraphQL contract completeness, query execution, and realtime handling."""

    def setUp(self) -> None:
        self.schema_file = (
            Path(__file__).resolve().parent.parent / "contracts" / "schemas" / "telemetry.graphql"
        )
        self.mock_auth = MagicMock(spec=ToyotaAuth)
        self.mock_auth.get_access_token = AsyncMock(return_value="mock_access_token_123")
        self.mock_auth.get_guid = AsyncMock(return_value="mock_guid_456")
        self.mock_auth.device_id = "mock_device_789"
        self.mock_auth._session = None

    def test_schema_contract_contains_all_operations(self) -> None:
        """Verify the shared contracts/schemas/telemetry.graphql matches SDK operations."""
        self.assertTrue(self.schema_file.exists(), "telemetry.graphql schema must exist")
        schema_text = self.schema_file.read_text(encoding="utf-8")

        # All canonical operations must be present in the contract specification
        expected_operations = [
            "GetVehicleStatus",
            "ReceiveVehicleStatus",
            "ReceiveRemoteCommandStatus",
            "SendRemoteCommand",
            "PostChargeSettings",
            "SendPreWakeCommand",
            "ConfirmSubscriptionStatus",
            "RefreshVehicleStatus",
        ]
        for op in expected_operations:
            self.assertIn(op, schema_text)

    async def test_execute_graphql_success(self) -> None:
        """Verify execute_graphql sets required headers, serializes payload, and returns data."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text.return_value = json.dumps(
            {
                "data": {
                    "executeRemoteCommand": {
                        "payload": {"returnCode": "0000", "requestNo": "req_1"},
                    }
                }
            }
        )

        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_session.closed = False
        mock_session.post.return_value.__aenter__.return_value = mock_resp

        result = await execute_graphql(
            self.mock_auth,
            SEND_REMOTE_COMMAND_MUTATION,
            {"command": "door-lock", "autoFixCommands": []},
            vin="4T1TESTVIN12345",
            region="CA",
            brand_code="T",
            session=mock_session,
        )

        self.assertIn("executeRemoteCommand", result)
        self.assertEqual(result["executeRemoteCommand"]["payload"]["returnCode"], "0000")

        # Verify call arguments
        mock_session.post.assert_called_once()
        _, kwargs = mock_session.post.call_args
        headers = kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer mock_access_token_123")
        self.assertEqual(headers["vin"], "4T1TESTVIN12345")
        self.assertEqual(headers["x-guid"], "mock_guid_456")
        self.assertEqual(headers["x-region"], "CA")
        self.assertEqual(headers["X-BRAND"], "T")

        # Verify payload contains query and variables
        posted_data = json.loads(kwargs["data"])
        self.assertEqual(posted_data["variables"]["command"], "door-lock")

    async def test_execute_graphql_error_handling(self) -> None:
        """Verify execute_graphql raises RuntimeError on GraphQL-level error response."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text.return_value = json.dumps(
            {"errors": [{"errorType": "UnauthorizedException", "message": "Access Denied"}]}
        )

        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_session.closed = False
        mock_session.post.return_value.__aenter__.return_value = mock_resp

        with self.assertRaises(RuntimeError) as ctx:
            await execute_graphql(
                self.mock_auth,
                POST_CHARGE_SETTINGS_MUTATION,
                {"chargingTargetLimit": 80},
                session=mock_session,
            )
        self.assertIn("Access Denied", str(ctx.exception))

    def test_realtime_subscription_payload_parsing(self) -> None:
        """Verify onVehicleStatusUpdated realtime push event parsing."""
        vehicle = VehicleStatus(
            vin="4T1BZ4X2024TEST01",
            model_name="bZ4X",
            model_year="2024",
            generation=VehicleGeneration.MM24,
            is_electric=True,
        )
        push_payload = {
            "onVehicleStatusUpdated": {
                "vehicleState": {
                    "doors": {
                        "driverSide": {
                            "position": {"status": "closed"},
                            "lock": {"status": "locked"},
                        },
                    },
                    "hood": {"position": {"status": "open"}},
                    "moonroof": {"position": {"status": "open"}},
                    "engine": {"running": True, "status": "started"},
                },
            }
        }
        updated = parse_appsync_vehicle_status(push_payload, vehicle)
        self.assertTrue(updated.driver_door.closed)
        self.assertTrue(updated.driver_door.locked)
        self.assertFalse(updated.hood.closed)
        self.assertFalse(updated.moonroof.closed)
        self.assertTrue(updated.climate_active)

    def test_graphql_contract_constants(self) -> None:
        """Verify all exported GraphQL mutation, query, and subscription constants."""
        self.assertIn("ConfirmSubscriptionStatus", CONFIRM_SUBSCRIPTION_MUTATION)
        self.assertIn("GetVehicleStatus", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("PostChargeSettings", POST_CHARGE_SETTINGS_MUTATION)
        self.assertIn("SendPreWakeCommand", PRE_WAKE_MUTATION)
        self.assertIn("ReceiveRemoteCommandStatus", RECEIVE_REMOTE_COMMAND_STATUS_SUBSCRIPTION)
        self.assertIn("ReceiveVehicleStatus", RECEIVE_VEHICLE_STATUS_SUBSCRIPTION)
        self.assertIn("RefreshVehicleStatus", REFRESH_STATUS_MUTATION)
        self.assertIn("SendRemoteCommand", SEND_REMOTE_COMMAND_MUTATION)

    async def test_appsync_websocket_lifecycle(self) -> None:
        """Verify ToyotaAppSyncWebSocket initialization, callbacks, and lifecycle."""
        status_cb = MagicMock()
        cmd_cb = MagicMock()
        ws = ToyotaAppSyncWebSocket(
            self.mock_auth,
            status_callback=status_cb,
            command_callback=cmd_cb,
            brand_code="T",
        )

        self.assertFalse(ws._running)
        self.assertIs(ws._status_callback, status_cb)
        self.assertIs(ws._command_callback, cmd_cb)

        with patch.object(ws, "_run_loop", new_callable=AsyncMock):
            await ws.start(vins=["4T1TESTVIN12345"], region="US")
            self.assertTrue(ws._running)
            self.assertEqual(ws._region, "US")
            self.assertEqual(ws._vins, ["4T1TESTVIN12345"])

            await ws.stop()
            self.assertFalse(ws._running)


if __name__ == "__main__":
    unittest.main()
