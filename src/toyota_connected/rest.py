"""REST client for Toyota Connected Services API Gateway."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .auth import ToyotaAuth
from .brands import DEFAULT_BRAND, BrandConfig, get_brand
from .graphql import RESOLVER_API_KEY

_LOGGER = logging.getLogger(__name__)

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)


class ToyotaRestClient:
    """Communicates with Toyota OneApp REST API gateway for Toyota, Lexus, and Subaru."""

    def __init__(
        self,
        auth: ToyotaAuth,
        brand: BrandConfig | str = DEFAULT_BRAND,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._auth = auth
        self._brand = get_brand(brand)
        self._session = session

    @asynccontextmanager
    async def _request_session(self):
        """Yield shared session if provided, otherwise yield an ephemeral session."""
        if self._session is not None and not self._session.closed:
            yield self._session
        else:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                yield session

    @property
    def brand(self) -> BrandConfig:
        return self._brand

    async def _headers(self, vin: str = "", region: str = "CA") -> dict[str, str]:
        token = await self._auth.get_access_token()
        guid = await self._auth.get_guid()
        headers = {
            "AUTHORIZATION": f"Bearer {token}",
            "X-API-KEY": RESOLVER_API_KEY,
            "X-GUID": guid,
            "X-CHANNEL": "ONEAPP",
            "x-region": region,
            "X-APPVERSION": "3.10.0",
            "X-LOCALE": "en-US",
            "User-Agent": self._brand.user_agent,
            "Accept": "application/json",
        }
        headers.update(self._brand.headers())
        if vin:
            headers["VIN"] = vin
        return headers

    async def request(
        self,
        method: str,
        endpoint: str,
        vin: str = "",
        region: str = "CA",
        json_data: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """Issue HTTP request against API Gateway with automatic authentication."""
        headers = await self._headers(vin=vin, region=region)
        if extra_headers:
            headers.update(extra_headers)

        url = urljoin(API_GATEWAY, endpoint.lstrip("/"))

        async with (
            self._request_session() as session,
            session.request(method, url, headers=headers, json=json_data) as resp,
        ):
            if resp.status >= 400:
                text = await resp.text()
                _LOGGER.error(
                    "Toyota REST API error %d for %s: %s", resp.status, endpoint, text[:300]
                )
                resp.raise_for_status()

            data = await resp.json()
            if isinstance(data, dict) and "payload" in data:
                return data["payload"]
            return data

    async def get_vehicle_list(self) -> list[dict[str, Any]]:
        """Fetch list of user's registered vehicles."""
        result = await self.request("GET", "v2/vehicle/guid")
        if isinstance(result, list):
            return result
        return []

    async def bootstrap_account(self) -> dict[str, Any] | None:
        """Bootstrap account profile for Subaru accounts if initial vehicle list returns empty."""
        try:
            _LOGGER.debug("Bootstrapping account profile via v4/account")
            return await self.request("GET", "v4/account")
        except (aiohttp.ClientError, KeyError, ValueError) as e:
            _LOGGER.warning("Account bootstrap call failed: %s", e)
            return None

    async def get_telemetry(
        self, vin: str, generation: str = "24MM", region: str = "CA"
    ) -> dict[str, Any] | None:
        """Fetch vehicle telemetry data."""
        try:
            extra = {"GENERATION": generation, "X-BRAND": self._brand.code}
            return await self.request(
                "GET", "v2/telemetry", vin=vin, region=region, extra_headers=extra
            )
        except (aiohttp.ClientError, KeyError, ValueError) as e:
            _LOGGER.warning("Failed to fetch telemetry for %s: %s", vin, e)
            return None
