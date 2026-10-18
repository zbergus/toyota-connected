"""Region-agnostic Config Flow for Toyota Connected Services."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .client import ToyotaRegionProvider, create_toyota_provider, get_brand
from .client.auth import AuthError, LoginError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

REGION_CHOICES = {
    "na": "North America (Canada, USA, Mexico)",
    "eu": "Europe (EU, UK)",
}

BRAND_CHOICES = {
    "toyota": "Toyota",
    "lexus": "Lexus",
    "subaru": "Subaru (Solterra Connect)",
}


class ToyotaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Toyota, Lexus, and Subaru Connected Services."""

    VERSION = 1

    def __init__(self) -> None:
        self._region: str = "na"
        self._brand: str = "toyota"
        self._provider: ToyotaRegionProvider | None = None
        self._username: str | None = None
        self._password: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1: Choose geographic region and vehicle brand."""
        if user_input is not None:
            self._region = user_input["region"]
            self._brand = user_input.get("brand", "toyota")
            self._provider = create_toyota_provider(region=self._region, brand=self._brand)
            return await self.async_step_credentials()

        schema = vol.Schema(
            {
                vol.Required("region", default="na"): vol.In(REGION_CHOICES),
                vol.Required("brand", default="toyota"): vol.In(BRAND_CHOICES),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_credentials(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2: Enter email and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input["username"].strip()
            self._password = user_input["password"]

            if not self._provider:
                self._provider = create_toyota_provider(self._region)

            try:
                result = await self._provider.login(self._username, self._password)
                if isinstance(result, str):
                    await self._provider.request_tokens(result)
                    return await self._create_entry_from_provider()
                else:
                    return await self.async_step_otp()
            except LoginError as err:
                _LOGGER.warning("Toyota login rejected: %s", err)
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
        return self.async_show_form(step_id="credentials", data_schema=schema, errors=errors)

    async def async_step_otp(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 3: Enter One-Time Password (OTP) verification code (if prompted by NA OpenAM)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            otp_code = user_input["code"].strip()
            if not self._provider:
                self._provider = create_toyota_provider(self._region)

            try:
                result = await self._provider.login(self._username or "", self._password, otp=otp_code)
                if isinstance(result, str):
                    await self._provider.request_tokens(result)
                    return await self._create_entry_from_provider()
                errors["base"] = "invalid_otp"
            except LoginError as err:
                _LOGGER.warning("Toyota OTP verification failed: %s", err)
                errors["base"] = "invalid_otp"
            except Exception as err:
                _LOGGER.exception("Unexpected error during OTP: %s", err)
                errors["base"] = "unknown"

        schema = vol.Schema({vol.Required("code"): str})
        return self.async_show_form(step_id="otp", data_schema=schema, errors=errors)

    async def _create_entry_from_provider(self) -> FlowResult:
        tokens = self._provider.get_tokens() if self._provider else {}
        guid = tokens.get("guid") or self._username

        await self.async_set_unique_id(f"{DOMAIN}:{self._region}:{self._brand}:{guid}")
        self._abort_if_unique_id_configured()

        entry_data = {
            "region": self._region,
            "brand": self._brand,
            "tokens": tokens,
            "username": self._username,
            "guid": guid,
        }

        # Clear plaintext password from memory
        self._password = None

        if self._region == "na":
            brand_label = get_brand(self._brand).name
            title = f"{brand_label} ({self._username})"
        else:
            title = f"Toyota Europe ({self._username})"

        return self.async_create_entry(
            title=title,
            data=entry_data,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauthorization if refresh tokens expire."""
        self._region = entry_data.get("region", "na")
        self._brand = entry_data.get("brand", "toyota")
        self._username = entry_data.get("username")
        self._provider = create_toyota_provider(self._region, brand=self._brand)
        return await self.async_step_credentials()
