"""REST client for Toyota Connected Services API Gateway."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .auth import ToyotaAuth
from .models import VehicleGeneration, VehicleStatus

_LOGGER = logging.getLogger(__name__)

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"
RESOLVER_API_KEY = "pypIHG015k4ABHWbcI4G0a94F7cC0JDo1OynpAsG"
USER_AGENT = "ToyotaOneApp/3.10.0 (com.toyota.oneapp; build:3100; Android 14) okhttp/4.12.0"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)


class ToyotaRestClient:
    """Communicates with Toyota OneApp REST API gateway."""

    def __init__(self, auth: ToyotaAuth) -> None:
        self._auth = auth

    async def _headers(self, vin: str = "", region: str = "CA") -> dict[str, str]:
        token = await self._auth.get_access_token()
        guid = await self._auth.get_guid()
        headers = {
            "AUTHORIZATION": f"Bearer {token}",
            "X-API-KEY": RESOLVER_API_KEY,
            "X-GUID": guid,
            "X-CHANNEL": "ONEAPP",
            "X-BRAND": "T",
            "x-region": region,
            "X-APPVERSION": "3.10.0",
            "X-LOCALE": "en-US",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
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

        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.request(method, url, headers=headers, json=json_data) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    _LOGGER.error("Toyota REST API error %d for %s: %s", resp.status, endpoint, text[:300])
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

    async def get_telemetry(self, vin: str, generation: str = "24MM", region: str = "CA") -> dict[str, Any] | None:
        """Fetch vehicle telemetry data."""
        try:
            extra = {"GENERATION": generation, "X-BRAND": "T"}
            return await self.request("GET", "v2/telemetry", vin=vin, region=region, extra_headers=extra)
        except Exception as e:
            _LOGGER.debug("Failed to fetch telemetry for %s: %s", vin, e)
            return None
