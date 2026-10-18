"""Modern, secure OAuth2 and ForgeRock OpenAM authentication client for Toyota Connected Services.

Implements:
- RFC 7636 PKCE S256 (cryptographic 64-byte high-entropy verifiers, SHA-256 challenges)
- ForgeRock OpenAM challenge-response authentication with Multi-Factor Authentication (OTP)
- Thread-safe / coroutine-safe atomic token refresh serialized by asyncio.Lock
- Unix timestamp lifetime calculation with safety buffer
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import math
import secrets
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
import jwt

_LOGGER = logging.getLogger(__name__)

AUTHENTICATE_URL = (
    "https://login.toyotadriverslogin.com/json/realms/root/realms/tmna-native/authenticate"
)
AUTHORIZE_URL = (
    "https://login.toyotadriverslogin.com/oauth2/realms/root/realms/tmna-native/authorize"
)
ACCESS_TOKEN_URL = (
    "https://login.toyotadriverslogin.com/oauth2/realms/root/realms/tmna-native/access_token"  # nosec B105
)
CLIENT_ID = "oneappsdkclient"
REDIRECT_URI = "com.toyota.oneapp:/oauth2Callback"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)


class AuthError(Exception):
    """Base exception for authentication errors."""


class LoginError(AuthError):
    """Raised when authentication credentials or challenges fail."""


class NotLoggedIn(AuthError):
    """Raised when an operation requires an active login session."""


class TokenExpired(AuthError):
    """Raised when an OAuth access token has expired and cannot be renewed."""


class ToyotaAuth:
    """Manages ForgeRock OpenAM authentication and OAuth2 PKCE tokens for Toyota, Lexus, and Subaru."""

    def __init__(
        self,
        token_callback: Callable[[dict[str, Any]], None] | None = None,
        initial_tokens: dict[str, Any] | None = None,
        refresh_buffer_secs: int = 300,
        auth_host: str = "login.toyotadriverslogin.com",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._token_callback = token_callback
        self._refresh_buffer_secs = refresh_buffer_secs
        self.auth_host = auth_host
        self._session = session
        self._set_auth_urls(auth_host)

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._id_token: str | None = None
        self._guid: str | None = None
        self._expires_at: float | None = None
        self._updated_at: float | None = None
        self._device_id: str = secrets.token_hex(16)

        self._code_verifier: str | None = None
        self.otp_callbacks: dict[str, Any] | None = None
        self._token_lock = asyncio.Lock()

        if initial_tokens:
            self.set_tokens(initial_tokens)

    def _set_auth_urls(self, host: str) -> None:
        self.auth_host = host
        self.authenticate_url = f"https://{host}/json/realms/root/realms/tmna-native/authenticate"
        self.authorize_url = f"https://{host}/oauth2/realms/root/realms/tmna-native/authorize"
        self.access_token_url = f"https://{host}/oauth2/realms/root/realms/tmna-native/access_token"

    @asynccontextmanager
    async def _request_session(self):
        """Yield shared session if provided, otherwise yield a temporary session."""
        if self._session is not None and not self._session.closed:
            yield self._session
        else:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                yield session

    @property
    def device_id(self) -> str:
        return self._device_id

    @staticmethod
    def compute_pkce_challenge(verifier: str) -> str:
        """Compute base64url-encoded SHA256 code challenge for RFC 7636 PKCE."""
        return (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )

    @property
    def is_logged_in(self) -> bool:
        return self._expires_at is not None and time.time() < self._expires_at

    def get_tokens(self) -> dict[str, Any]:
        """Return token dictionary for persistent storage."""
        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "id_token": self._id_token,
            "guid": self._guid,
            "expires_at": self._expires_at,
            "updated_at": self._updated_at,
            "device_id": self._device_id,
            "clock": "unix",
            "auth_host": self.auth_host,
        }

    def set_tokens(self, tokens: dict[str, Any]) -> None:
        """Load tokens from persistent storage."""
        self._access_token = tokens.get("access_token")
        self._refresh_token = tokens.get("refresh_token")
        self._id_token = tokens.get("id_token")
        self._guid = tokens.get("guid")
        self._device_id = tokens.get("device_id") or self._device_id
        if tokens.get("auth_host"):
            self._set_auth_urls(tokens["auth_host"])

        if tokens.get("clock") == "unix" and tokens.get("expires_at"):
            self._expires_at = float(tokens["expires_at"])
            self._updated_at = float(tokens.get("updated_at") or time.time())
        else:
            # Force refresh to compute proper unix timestamps
            self._expires_at = 0.0
            self._updated_at = 0.0

    async def get_access_token(self) -> str:
        """Get valid access token, refreshing if necessary."""
        await self.check_tokens()
        if not self._access_token:
            raise NotLoggedIn("No active access token")
        return self._access_token

    async def get_guid(self) -> str:
        """Get user GUID from tokens or token exchange."""
        if not self._guid and self._id_token:
            self._extract_guid_from_id_token(self._id_token)
        if not self._guid:
            await self.get_access_token()
        if not self._guid:
            raise NotLoggedIn("No user GUID available")
        return self._guid

    def _extract_guid_from_id_token(self, id_token: str) -> None:
        try:
            payload = jwt.decode(
                id_token,
                algorithms=["RS256"],
                options={"verify_signature": False, "verify_aud": False},
                audience=CLIENT_ID,
            )
            self._guid = payload.get("sub")
        except jwt.PyJWTError as err:
            _LOGGER.debug("Could not decode GUID from id_token: %s", err)

    def _extract_tokens(self, response: dict[str, Any]) -> None:
        """Extract tokens from OAuth response atomically."""
        access_token = response.get("access_token")
        refresh_token = response.get("refresh_token") or self._refresh_token
        id_token = response.get("id_token") or self._id_token

        try:
            lifetime = float(response["expires_in"])
        except (KeyError, TypeError, ValueError) as err:
            raise RuntimeError("Toyota auth returned invalid token lifetime") from err

        if not all(isinstance(t, str) and t for t in (access_token, refresh_token, id_token)):
            raise RuntimeError("Toyota auth returned incomplete token set")
        if not math.isfinite(lifetime) or lifetime <= 0:
            raise RuntimeError("Toyota auth returned invalid token expiration interval")

        now = time.time()
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._id_token = id_token
        self._expires_at = now + lifetime
        self._updated_at = now

        if id_token:
            self._extract_guid_from_id_token(id_token)

        if self._token_callback:
            try:
                self._token_callback(self.get_tokens())
            except Exception:
                _LOGGER.exception("Token persistence callback failed")

    async def check_tokens(self, *, rejected_token: str | None = None) -> None:
        """Serialize token refresh and ensure tokens remain valid."""
        async with self._token_lock:
            if self._expires_at is None:
                raise NotLoggedIn("Session not initialized")

            now = time.time()
            needs_refresh = now >= (self._expires_at - self._refresh_buffer_secs) or (
                rejected_token is not None and self._access_token == rejected_token
            )

            if needs_refresh:
                try:
                    await self.refresh_tokens()
                except LoginError as err:
                    raise TokenExpired("Failed to refresh expired token") from err

    async def refresh_tokens(self) -> None:
        """Request new access token using refresh_token."""
        if not self._refresh_token:
            raise NotLoggedIn("No refresh token available")

        data = {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        async with (
            self._request_session() as session,
            session.post(self.access_token_url, data=data) as resp,
        ):
            if resp.status in (400, 401):
                try:
                    err_json = await resp.json(content_type=None)
                except ValueError:
                    err_json = {}
                if isinstance(err_json, dict) and err_json.get("error") == "invalid_grant":
                    raise LoginError("Refresh token rejected by server")
            resp.raise_for_status()
            self._extract_tokens(await resp.json())

    async def authorize(
        self, username: str, password: str | None = None, otp: str | None = None
    ) -> str | dict[str, Any]:
        """ForgeRock OpenAM authentication flow with PKCE S256."""
        async with self._request_session() as session:
            headers = {
                "Accept-API-Version": "resource=2.1, protocol=1.0",
                "Accept-Language": "en-US",
                "Content-Type": "application/json",
            }

            data: dict[str, Any] = {}
            otp_brake = False
            previous_callbacks = None

            if otp is not None and self.otp_callbacks:
                data = self.otp_callbacks

            for _ in range(15):
                if "callbacks" in data:
                    for cb in data["callbacks"]:
                        cb_type = cb.get("type")
                        outputs = cb.get("output", [])
                        prompt = ""
                        for out in outputs:
                            if out.get("name") == "prompt":
                                prompt = str(out.get("value", "")).strip().casefold()

                        if cb_type == "NameCallback":
                            if prompt in ("ui_locales", "ui locale"):
                                cb["input"][0]["value"] = "en-US"
                            elif prompt not in ("deviceprint", "mail"):
                                cb["input"][0]["value"] = username

                        elif cb_type == "PasswordCallback":
                            if prompt == "one time password":
                                if otp is None:
                                    otp_brake = True
                                    break
                                cb["input"][0]["value"] = otp
                            elif password:
                                cb["input"][0]["value"] = password

                        elif cb_type == "ChoiceCallback":
                            # Choice 0 is typically local username/password auth
                            cb["input"][0]["value"] = 0

                        elif cb_type == "ConfirmationCallback":
                            # Confirm / submit OTP
                            cb["input"][0]["value"] = 0

                        elif cb_type in ("HiddenValueCallback", "TextOutputCallback"):
                            pass

                if otp_brake:
                    self.otp_callbacks = data
                    _LOGGER.debug("MFA OTP required by Toyota authentication")
                    return data

                if "callbacks" in data:
                    if data["callbacks"] == previous_callbacks:
                        raise LoginError(
                            "Toyota OpenAM repeated an authentication challenge without progression"
                        )
                    previous_callbacks = deepcopy(data["callbacks"])

                async with session.post(self.authenticate_url, json=data, headers=headers) as resp:
                    if resp.status != 200:
                        _LOGGER.info("Toyota authentication failed with HTTP %d", resp.status)
                        raise LoginError(f"HTTP {resp.status} during authentication")
                    data = await resp.json()

                    for cb in data.get("callbacks", []):
                        if cb.get("type") == "TextOutputCallback":
                            msg = ""
                            for out in cb.get("output", []):
                                if out.get("name") == "message":
                                    msg = str(out.get("value", "")).strip()
                            if msg.casefold() in ("invalid otp", "password_history_failure"):
                                self.otp_callbacks = data
                                raise LoginError(f"Authentication challenge error: {msg}")

                    if "tokenId" in data:
                        break

            if "tokenId" not in data:
                raise LoginError("OpenAM authentication did not yield a valid tokenId session")

            # Exchange tokenId for OAuth authorization code using PKCE S256
            self._code_verifier = secrets.token_urlsafe(64)
            challenge = self.compute_pkce_challenge(self._code_verifier)

            auth_params = {
                "client_id": CLIENT_ID,
                "scope": "openid profile write",
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }

            req_headers = {
                "Cookie": f"iPlanetDirectoryPro={data['tokenId']}",
                "Accept-Language": "en-US",
            }
            auth_url = f"{self.authorize_url}?{urlencode(auth_params)}"

            async with session.get(auth_url, headers=req_headers, allow_redirects=False) as resp:
                if resp.status not in (301, 302, 303, 307, 308):
                    raise LoginError(f"Toyota authorize redirect returned HTTP {resp.status}")

                location = resp.headers.get("Location", "")
                redirect = urlparse(location)
                query = parse_qs(redirect.query, keep_blank_values=True)
                codes = query.get("code", [])

                if "error" in query or not codes:
                    raise LoginError(f"Authorization redirect missing valid code: {location}")

                return codes[0]

    async def request_tokens(self, code: str) -> None:
        """Exchange authorization code and PKCE verifier for OAuth tokens."""
        if not self._code_verifier:
            raise LoginError("Missing PKCE code verifier for token exchange")

        data = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "code_verifier": self._code_verifier,
            "code": code,
        }

        async with (
            self._request_session() as session,
            session.post(self.access_token_url, data=data) as resp,
        ):
            if resp.status != 200:
                text = await resp.text()
                raise LoginError(f"Token exchange failed HTTP {resp.status}: {text}")
            self._extract_tokens(await resp.json())
            self._code_verifier = None

    async def login(
        self, username: str, password: str | None = None, otp: str | None = None
    ) -> None:
        """Full login helper: authenticates and acquires OAuth tokens."""
        result = await self.authorize(username, password, otp)
        if isinstance(result, str):
            await self.request_tokens(result)
        else:
            raise LoginError("OTP required to finish login")
