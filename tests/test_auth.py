"""Unit tests for Toyota OAuth2 PKCE S256 and token management."""

from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

import tests  # noqa: F401 - Prepares mock Home Assistant stubs if not present
from toyota_connected.auth import ToyotaAuth


class TestToyotaAuth(unittest.IsolatedAsyncioTestCase):
    """Test PKCE S256, token management, and locking."""

    def test_pkce_challenge_math(self) -> None:
        """Verify RFC 7636 PKCE S256 base64url challenge calculation."""
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        self.assertEqual(ToyotaAuth.compute_pkce_challenge(verifier), expected_challenge)

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

    async def test_session_reuse_context_manager(self) -> None:
        """Verify provided session is yielded without being closed."""
        mock_session = AsyncMock()
        mock_session.closed = False
        auth = ToyotaAuth(session=mock_session)

        async with auth._request_session() as session:
            self.assertIs(session, mock_session)

        mock_session.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
