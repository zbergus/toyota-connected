"""Multi-brand configuration registry for Toyota, Lexus, and Subaru Connected Services."""

from __future__ import annotations

from dataclasses import dataclass

# Shared ForgeRock/OpenAM & OAuth parameters across all brands on the shared telematics cloud
SHARED_REALM_PATH = "realms/root/realms/tmna-native"
SHARED_CLIENT_ID = "oneappsdkclient"
SHARED_REDIRECT_URI = "com.toyota.oneapp:/oauth2Callback"
SHARED_SCOPE = "openid profile write"


@dataclass(frozen=True, slots=True)
class BrandConfig:
    """Immutable configuration defining endpoints and headers for a supported brand."""

    code: str
    """Short brand identifier sent in API headers (e.g. 'T', 'L', 'S')."""

    brand_id: str
    """Normalized slug identifier (e.g. 'toyota', 'lexus', 'subaru')."""

    name: str
    """Human-readable display name for UI and configuration flows."""

    manufacturer: str
    """Device registry manufacturer string."""

    auth_host: str
    """ForgeRock OpenAM tenant hostname for user authentication."""

    user_agent: str
    """User-Agent header simulating the native mobile application."""

    bootstrap_on_empty: bool = False
    """Whether to call GET v4/account if initial vehicle discovery returns empty."""

    @property
    def authenticate_url(self) -> str:
        """URL for OpenAM username/password and MFA authentication callbacks."""
        return f"https://{self.auth_host}/json/{SHARED_REALM_PATH}/authenticate"

    @property
    def authorize_url(self) -> str:
        """URL for OpenID Connect authorization code redirect."""
        return f"https://{self.auth_host}/oauth2/{SHARED_REALM_PATH}/authorize"

    @property
    def access_token_url(self) -> str:
        """URL for OAuth 2.0 authorization_code and refresh_token exchanges."""
        return f"https://{self.auth_host}/oauth2/{SHARED_REALM_PATH}/access_token"

    def headers(self) -> dict[str, str]:
        """Brand-scoping headers sent on REST gateway and GraphQL AppSync requests.

        Note: X-APPBRAND is the critical header that gates Subaru vehicle discovery;
        without it, authentication succeeds but /v2/vehicle/guid returns an empty list.
        """
        return {
            "X-BRAND": self.code,
            "X-APPBRAND": self.code,
            "X-Brand-Id": self.code,
        }


TOYOTA = BrandConfig(
    code="T",
    brand_id="toyota",
    name="Toyota",
    manufacturer="Toyota",
    auth_host="login.toyotadriverslogin.com",
    user_agent="ToyotaOneApp/3.10.0 (com.toyota.oneapp; build:3100; Android 14) okhttp/4.12.0",
    bootstrap_on_empty=False,
)

LEXUS = BrandConfig(
    code="L",
    brand_id="lexus",
    name="Lexus",
    manufacturer="Lexus",
    auth_host="login.lexusdriverslogin.com",
    user_agent="LexusOneApp/3.10.0 (com.lexus.oneapp; build:3100; Android 14) okhttp/4.12.0",
    bootstrap_on_empty=False,
)

SUBARU = BrandConfig(
    code="S",
    brand_id="subaru",
    name="Subaru (Solterra Connect)",
    manufacturer="Subaru",
    auth_host="login.subarudriverslogin.com",
    user_agent="SubaruConnect/3.10.0 (com.subaru.oneapp; build:3100; Android 14) okhttp/4.12.0",
    bootstrap_on_empty=True,
)

BRANDS: dict[str, BrandConfig] = {
    "toyota": TOYOTA,
    "lexus": LEXUS,
    "subaru": SUBARU,
    "t": TOYOTA,
    "l": LEXUS,
    "s": SUBARU,
}

DEFAULT_BRAND = TOYOTA


def get_brand(identifier: str | BrandConfig | None) -> BrandConfig:
    """Resolve a brand slug or code, falling back cleanly to Toyota if unspecified."""
    if isinstance(identifier, BrandConfig):
        return identifier
    if not identifier:
        return DEFAULT_BRAND
    return BRANDS.get(str(identifier).lower().strip(), DEFAULT_BRAND)
