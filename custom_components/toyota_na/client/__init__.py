"""Modern, region-agnostic Toyota Connected Services API client."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .base_provider import ToyotaRegionProvider
from .eu_provider import EuropeProvider
from .models import (
    ChargingStatus,
    ElectricVehicleStatus,
    OpeningState,
    RemoteCommand,
    TirePressure,
    VehicleGeneration,
    VehicleStatus,
)
from .na_provider import NorthAmericaProvider

_LOGGER = logging.getLogger(__name__)


def create_toyota_provider(
    region: str = "na",
    token_callback: Callable[[dict[str, Any]], None] | None = None,
    initial_tokens: dict[str, Any] | None = None,
) -> ToyotaRegionProvider:
    """Factory creating the appropriate regional provider (North America or Europe)."""
    clean_region = str(region).lower().strip()
    if clean_region == "eu":
        _LOGGER.debug("Instantiating EuropeProvider (TME ctpa-oneapi)")
        return EuropeProvider(token_callback=token_callback, initial_tokens=initial_tokens)

    _LOGGER.debug("Instantiating NorthAmericaProvider (TMNA/TCI AppSync GraphQL & WebSockets)")
    return NorthAmericaProvider(token_callback=token_callback, initial_tokens=initial_tokens)
