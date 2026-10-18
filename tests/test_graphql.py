"""Unit tests for GraphQL queries and mutation document structure."""

from __future__ import annotations

import tests  # Prepares mock Home Assistant stubs if not present

import unittest

from custom_components.toyota_na.client.graphql import (
    GET_VEHICLE_STATUS_QUERY,
    POST_CHARGE_SETTINGS_MUTATION,
    RECEIVE_VEHICLE_STATUS_SUBSCRIPTION,
    SEND_REMOTE_COMMAND_MUTATION,
)


class TestGraphQLDocuments(unittest.TestCase):
    """Test GraphQL queries and mutations contain all required fields for bZ4X."""

    def test_get_vehicle_status_query(self) -> None:
        self.assertIn("query GetVehicleStatus", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("doors", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("windows", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("tires", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("electric", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("stateOfChargeDisplay", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("travelableDistanceAC", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("chargingStatus", GET_VEHICLE_STATUS_QUERY)
        self.assertIn("chargeSettings", GET_VEHICLE_STATUS_QUERY)

    def test_send_remote_command_mutation(self) -> None:
        self.assertIn("mutation SendRemoteCommand", SEND_REMOTE_COMMAND_MUTATION)
        self.assertIn("executeRemoteCommand", SEND_REMOTE_COMMAND_MUTATION)
        self.assertIn("commandInputBody", SEND_REMOTE_COMMAND_MUTATION)

    def test_post_charge_settings_mutation(self) -> None:
        self.assertIn("mutation PostChargeSettings", POST_CHARGE_SETTINGS_MUTATION)
        self.assertIn("postChargeSettingsInputBody", POST_CHARGE_SETTINGS_MUTATION)
        self.assertIn("chargingTargetLimit", POST_CHARGE_SETTINGS_MUTATION)

    def test_subscription_document(self) -> None:
        self.assertIn("subscription ReceiveVehicleStatus", RECEIVE_VEHICLE_STATUS_SUBSCRIPTION)
        self.assertIn("onVehicleStatusUpdated", RECEIVE_VEHICLE_STATUS_SUBSCRIPTION)


if __name__ == "__main__":
    unittest.main()
