"""Modern Config Flow for Toyota Connected Services."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .client.auth import AuthError, LoginError, ToyotaAuth
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ToyotaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Toyota Connected Services."""

    VERSION = 1

    def __init__(self) -> None:
        self._auth = ToyotaAuth()
        self._username: str | None = None
        self._password: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1: Enter email and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input["username"].strip()
            self._password = user_input["password"]

            try:
                result = await self._auth.authorize(self._username, self._password)
                if isinstance(result, str):
                    # Direct login succeeded without OTP
                    await self._auth.request_tokens(result)
                    return await self._create_entry_from_auth()
                else:
                    # OTP required
                    return await self.async_step_otp()
            except LoginError as err:
                _LOGGER.warning("Toyota login error: %s", err)
                errors["base"] = "invalid_auth"
            except AuthError as err:
                _LOGGER.error("Toyota authentication error: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error during login: %s", err)
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required("username"): str,
                vol.Required("password"): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_otp(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2: Enter One-Time Password (OTP) verification code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            otp_code = user_input["code"].strip()
            try:
                result = await self._auth.authorize(self._username or "", self._password, otp=otp_code)
                if isinstance(result, str):
                    await self._auth.request_tokens(result)
                    return await self._create_entry_from_auth()
                errors["base"] = "invalid_otp"
            except LoginError as err:
                _LOGGER.warning("Toyota OTP verification failed: %s", err)
                errors["base"] = "invalid_otp"
            except Exception as err:
                _LOGGER.exception("Unexpected error during OTP: %s", err)
                errors["base"] = "unknown"

        schema = vol.Schema({vol.Required("code"): str})
        return self.async_show_form(step_id="otp", data_schema=schema, errors=errors)

    async def _create_entry_from_auth(self) -> FlowResult:
        guid = await self._auth.get_guid()
        await self.async_set_unique_id(f"{DOMAIN}:{guid}")
        self._abort_if_unique_id_configured()

        entry_data = {
            "tokens": self._auth.get_tokens(),
            "username": self._username,
            "guid": guid,
        }

        # Clear plaintext password from memory
        self._password = None

        return self.async_create_entry(
            title=f"Toyota ({self._username})",
            data=entry_data,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauthorization if refresh tokens expire."""
        self._username = entry_data.get("username")
        return await self.async_step_user()
