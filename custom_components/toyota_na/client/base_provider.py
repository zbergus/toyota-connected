"""Abstract base provider for regional Toyota Connected Services backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from .models import RemoteCommand, VehicleStatus


class ToyotaRegionProvider(ABC):
    """Abstract interface that every regional backend (North America, Europe, etc.) must implement."""

    @property
    @abstractmethod
    def region_code(self) -> str:
        """Return the region identifier (e.g. 'na' or 'eu')."""

    @abstractmethod
    async def login(
        self,
        username: str,
        password: str | None = None,
        otp: str | None = None,
    ) -> str | dict[str, Any] | None:
        """Authenticate with regional identity provider. Returns token/callback or None."""

    @abstractmethod
    async def request_tokens(self, code: str) -> None:
        """Exchange authorization code for OAuth tokens."""

    @abstractmethod
    async def check_tokens(self) -> None:
        """Validate and proactively renew access tokens."""

    @abstractmethod
    def get_tokens(self) -> dict[str, Any]:
        """Return persistent token dictionary."""

    @abstractmethod
    def set_tokens(self, tokens: dict[str, Any]) -> None:
        """Load persistent tokens."""

    @abstractmethod
    async def get_user_vehicles(self) -> list[VehicleStatus]:
        """Fetch vehicles registered to account and initialize their models."""

    @abstractmethod
    async def update_vehicle_status(self, vehicle: VehicleStatus) -> VehicleStatus:
        """Update vehicle status (doors, locks, battery, charging, range, tires)."""

    @abstractmethod
    async def send_remote_command(self, vin: str, command: RemoteCommand) -> dict[str, Any]:
        """Dispatch a remote command (lock, unlock, immediate charge, climate pre-condition)."""

    @abstractmethod
    async def set_charge_limit(self, vin: str, target_percent: int) -> dict[str, Any]:
        """Update EV target charge limit percentage (e.g. 80%)."""

    @abstractmethod
    async def set_ac_current_limit(self, vin: str, max_amps: int) -> dict[str, Any]:
        """Update EV max AC charging amperage limit."""

    @abstractmethod
    async def start_realtime_listener(
        self,
        vins: list[str],
        callback: Callable[[str, dict[str, Any]], None],
    ) -> None:
        """Start realtime push event listener if supported by regional transport."""

    @abstractmethod
    async def stop_realtime_listener(self) -> None:
        """Stop realtime push listener."""
