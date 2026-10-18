"""Modern, region-agnostic Toyota Connected Services API client."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .base_provider import ToyotaRegionProvider
from .brands import BRANDS, DEFAULT_BRAND, BrandConfig, get_brand
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
    brand: str | BrandConfig = DEFAULT_BRAND,
    token_callback: Callable[[dict[str, Any]], None] | None = None,
    initial_tokens: dict[str, Any] | None = None,
) -> ToyotaRegionProvider:
    """Factory creating the appropriate regional provider (North America or Europe) and brand."""
    clean_region = str(region).lower().strip()
    if clean_region == "eu":
        _LOGGER.debug("Instantiating EuropeProvider (TME ctpa-oneapi)")
        return EuropeProvider(token_callback=token_callback, initial_tokens=initial_tokens)

    # If brand not explicitly supplied, check initial_tokens
    resolved_brand = brand
    if resolved_brand == DEFAULT_BRAND and initial_tokens and initial_tokens.get("brand"):
        resolved_brand = initial_tokens["brand"]

    _LOGGER.debug("Instantiating NorthAmericaProvider for brand: %s", resolved_brand)
    return NorthAmericaProvider(
        token_callback=token_callback,
        initial_tokens=initial_tokens,
        brand=resolved_brand,
    )
