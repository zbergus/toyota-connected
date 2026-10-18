"""Unit tests for Toyota OAuth2 PKCE S256 and token management."""

from __future__ import annotations

import tests  # Prepares mock Home Assistant stubs if not present

import asyncio
import base64
import hashlib
import time
import unittest
from unittest.mock import AsyncMock, patch

from custom_components.toyota_na.client.auth import ToyotaAuth


class TestToyotaAuth(unittest.IsolatedAsyncioTestCase):
    """Test PKCE S256, token management, and locking."""

    def test_pkce_challenge_math(self) -> None:
        """Verify RFC 7636 PKCE S256 base64url challenge calculation."""
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        
        computed = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        self.assertEqual(computed, expected_challenge)

    def test_token_loading_and_retrieval(self) -> None:
        """Verify token storage and unix clock parsing."""
        auth = ToyotaAuth()
        now = time.time()
        initial = {
            "access_token": "mock_access",
            "refresh_token": "mock_refresh",
            "id_token": "mock_id",
            "guid": "guid_12345",
            "expires_at": now + 3600,
            "updated_at": now,
            "device_id": "dev_abc",
            "clock": "unix",
        }
        auth.set_tokens(initial)
        self.assertTrue(auth.is_logged_in)
        tokens = auth.get_tokens()
        self.assertEqual(tokens["access_token"], "mock_access")
        self.assertEqual(tokens["guid"], "guid_12345")

    async def test_token_refresh_locking(self) -> None:
        """Verify concurrent check_tokens calls are serialized by asyncio.Lock."""
        auth = ToyotaAuth(refresh_buffer_secs=5000)
        auth._expires_at = time.time() + 100  # Will trigger refresh
        auth._refresh_token = "valid_refresh"

        call_count = 0

        async def mock_refresh():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            auth._expires_at = time.time() + 7200
            auth._access_token = "new_access"

        with patch.object(auth, "refresh_tokens", side_effect=mock_refresh):
            await asyncio.gather(
                auth.check_tokens(),
                auth.check_tokens(),
                auth.check_tokens(),
                auth.check_tokens(),
                auth.check_tokens(),
            )

        self.assertEqual(call_count, 1)
        self.assertEqual(auth._access_token, "new_access")


if __name__ == "__main__":
    unittest.main()
