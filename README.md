# Toyota, Lexus & Subaru Connected Services (`toyota-connected`)

A modern, high-performance, and secure ecosystem for **Toyota**, **Lexus**, and **Subaru (Solterra Connect)** Connected Services. 

Provides both a standalone, asynchronous Python SDK (`toyota-connected`) and a native Home Assistant integration (`toyota_connected`) with first-class support for **Canada**, **Europe**, and modern electrified vehicles (**Toyota bZ4X**, **Subaru Solterra**, and **Lexus RZ**).

---

## Key Highlights & Modern Upgrades

### Multi-Brand & Multi-Region Support
- **Multi-Brand Registry**: Unified client handling brand scoping, endpoints, and authentication for **Toyota**, **Lexus**, and **Subaru (Solterra Connect)**.
- **Global Architecture**:
  - **North America**: Dynamic regional routing (`CA` / `US`) with native metric (`km`, `°C`, `kPa`, `kW`) and imperial conversion.
  - **Europe**: Native support for European CTPA OneAPI telematics and remote commands.

### Electrified Vehicle (EV/PHEV) Control
- **bZ4X, Solterra & RZ Generation (MM24)**:
  - **Sensors**: Battery State of Charge (SoC %), Usable Battery Capacity %, Driving Range (AC Off vs. AC On), Charging Power (kW), Remaining Charge Time (to 100% and to 80%), Odometer, and Individual Tire Pressures (kPa / PSI).
  - **Binary Sensors**: Active Charging, Plug Connection, Doors, Windows, Hatch, and Hood.
  - **Controls**:
    - `switch.*_immediate_charge`: Start or stop charging immediately.
    - `switch.*_climate_preconditioning`: Quick toggle for cabin pre-conditioning.
    - `select.*_target_charge_limit`: Set target battery charging limit (50%, 60%, 70%, 80%, 90%, 100%).
    - `select.*_ac_current_limit`: Set max AC charging current (8 A, 16 A, 32 A, Max).
    - `lock.*_door_lock`: Remote lock and unlock.
    - `climate.*_climate`: Cabin pre-conditioning thermostat.

### 12V Auxiliary Battery Drain Protection
Quiescent sleep preservation for vulnerable 12V auxiliary batteries in EVs and hybrids:
- **Passive Cloud Polling**: Regular coordinator updates query cloud caches without triggering cellular Data Communication Module (DCM) wake-ups.
- **Trip Arrival Wake**: Automatically triggers fresh status synchronization only upon trip completion (odometer advancement detected).
- **Hourly Rate Limiter**: Hard ceiling on active cellular wake attempts per hour.
- **Circuit Breaker**: Automatically suspends wake requests if a vehicle is unreachable (e.g., underground parking garage) until the next drive cycle.

### Strict Security & Contract Testing
- **RFC 7636 PKCE S256**: OAuth 2.0 PKCE authentication eliminating plaintext challenges.
- **Serialized Token Refresh**: Guarded by `asyncio.Lock()` to prevent race conditions and invalid grant lockouts.
- **Golden Contract Fixtures**: Deterministic schema validation against real JSON payloads in `contracts/fixtures/`.
- **Zero Plaintext Password Persistence**: Tokens stored securely; strict diagnostics redaction.

---

## Repository Structure

```text
.
├── contracts/
│   ├── schemas/                      # GraphQL schema definitions shared with Kaizen (iOS)
│   │   └── telemetry.graphql
│   └── fixtures/                     # Golden JSON payloads for contract verification
│       ├── telemetry_bev_metric.json
│       ├── telemetry_bev_imperial.json
│       ├── telemetry_hybrid_ice.json
│       ├── eu_electric_status.json
│       └── eu_vehicle_status.json
│
├── src/
│   └── toyota_connected/             # Standalone Python SDK (pip installable)
│       ├── auth.py                   # PKCE S256 & token management
│       ├── brands.py                 # Toyota, Lexus, Subaru registry
│       ├── smart_refresh.py          # 12V battery drain protection
│       ├── graphql.py                # AppSync queries & mutations
│       ├── na_provider.py            # North America regional provider
│       └── eu_provider.py            # Europe regional provider
│
├── custom_components/
│   └── toyota_connected/             # Home Assistant Integration (HACS)
│       ├── manifest.json
│       ├── config_flow.py
│       └── sensor.py, climate.py, etc.
│
└── tests/                            # 42 automated unit & contract tests
```

---

## Home Assistant Installation

### Method 1: HACS (Recommended)
1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the three dots in the top right > **Custom repositories**.
3. Add your repository URL: `https://github.com/zbergus/toyota-connected` with Category: **Integration**.
4. Search for `Toyota, Lexus & Solterra Connected Services` and click **Download**.
5. Restart Home Assistant.

### Method 2: Manual Installation
1. Copy or symlink `custom_components/toyota_connected` into your Home Assistant directory:
   ```bash
   ln -s /path/to/toyota/custom_components/toyota_connected ~/.homeassistant/custom_components/toyota_connected
   ```
2. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Toyota, Lexus & Solterra Connected Services**.
3. Select your region (**North America** or **Europe**) and brand (**Toyota**, **Lexus**, or **Subaru**).
4. Enter your account credentials and complete OTP verification if prompted.
5. All vehicles associated with your account are automatically discovered with sensors and controls.

---

## Testing

Run the automated test suite:
```bash
python3 -m unittest discover -s tests -v
```
