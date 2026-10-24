# Toyota, Lexus & Subaru Connected Services (`toyota-connected`)

A modern, high-performance, and secure ecosystem for **Toyota**, **Lexus**, and **Subaru (Solterra Connect)** Connected Services.

Provides both a standalone, asynchronous Python SDK (`toyota-connected`) and a native Home Assistant integration (`toyota_connected`) with first-class support for **North America** (United States, Canada, Mexico) and **Europe**, tailored for modern electrified vehicles (**Toyota bZ4X**, **Subaru Solterra**, and **Lexus RZ**) as well as internal combustion (ICE) and hybrid (HEV/PHEV) powertrains.

---

## Architecture & Vehicle Generation Matrix

Toyota Connected Services uses different telematics platforms depending on vehicle generation, model year, and region. Features dynamically adapt based on the vehicle's reported capabilities:

| Generation | Model Years (Approx.) | Representative Models | Telematics Gateway & Protocol | Key Features & API Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **MM24 / MM25** | **2024+ / 2025+** | 2025+ bZ4X, 2024+ Grand Highlander, Land Cruiser, Tacoma, Lexus TX | AWS AppSync GraphQL (`/graphql`) with real-time Stencil WebSocket subscriptions | **Full feature set**: Dynamic target charge limit via API (50%–100%), AC current limit via API (8A, 16A, 32A, Max), remaining charge time to 80% and 100%, climate pre-conditioning with thermostat setpoint control, and real-time push telemetry. |
| **21MM** | **2022 – 2024** | 2023–2024 bZ4X, 2023–2024 Solterra, 2023–2024 Lexus RZ, 2022–2024 Tundra, Sequoia, RAV4 Prime, Lexus NX | Toyota OneAPI REST (`api.toyota.com`) over HTTPS | **Standard telemetry & remote commands**: State of charge (SoC %), usable battery %, EV range (AC On/Off), total charge time to 100%, immediate charge start/stop, remote start / cabin pre-conditioning, door lock/unlock, hazard lights.<br>⚠️ **Model Year / API Limitations**: Setting target charge limits (e.g. 80%) or AC current limits **cannot be done via API** on 21MM (must be configured in-vehicle via multimedia/cluster settings); remaining charge time to 80% is not exposed by Toyota's REST API. |
| **Europe (TME)** | **All Supported Years** | bZ4X, Yaris Cross, RAV4 PHEV, Corolla (EU spec) | European CTPA OneAPI (`ctpa-oneapi.tceu-ctp-prd.toyotaconnectedeurope.io`) | Battery SoC %, EV range, remaining charge time to full, lock/unlock, cabin climate pre-conditioning (`/v2/remote/climate-control`).<br>⚠️ **Note**: Target charge limits in Europe are configured in-dash or via scheduled charging rather than direct cloud mutations. |
| **17CY / 17CYPLUS** | **2018 – 2022** | Camry, RAV4, Corolla, Highlander, Avalon | Toyota Legacy REST Gateway | Odometer, fuel level, tire pressures, door lock/unlock, and remote engine start (where subscribed). No EV battery management. |

---

## Key Highlights & Features

### Multi-Brand & Multi-Region Support
- **Multi-Brand Registry**: Unified client handling brand scoping, endpoints, and authentication for **Toyota**, **Lexus**, and **Subaru (Solterra Connect)**.
- **Global Architecture**:
  - **North America**: Dynamic regional routing (`CA` / `US`) with native metric (`km`, `°C`, `kPa`, `kW`) and imperial (`mi`, `°F`, `PSI`) conversion.
  - **Europe**: Native support for European CTPA OneAPI telematics and remote commands.

### Electrified Vehicle (EV/PHEV) Control
- **Telemetry Sensors**:
  - Battery State of Charge (SoC %) and Usable Battery Capacity %.
  - Driving Range with AC Off vs. AC On.
  - Charging Power (kW) and Total Remaining Charge Time (to 100%).
  - **Remaining Charge Time to 80%** (supported on MM24/MM25 vehicles).
- **Binary Sensors**:
  - Active Charging and Charge Plug Connected status.
  - Doors (Driver, Passenger, Rear Driver, Rear Passenger), Windows, Hatch/Tailgate, and Hood.
- **Remote Controls**:
  - `switch.*_immediate_charge`: Start or stop charging immediately while plugged in.
  - `select.*_target_charge_limit`: Set target battery charging limit (50%, 60%, 70%, 80%, 90%, 100%) — *MM24/MM25 generation only*.
  - `select.*_ac_current_limit`: Set maximum AC charging current (8 A, 16 A, 32 A, Max) — *MM24/MM25 generation only*.
  - `lock.*_door_lock`: Remote door lock and unlock.
  - `switch.*_hazard_lights`: Toggle hazard flasher lights.

### Cabin Pre-Conditioning & Remote Start
Cabin climate and pre-conditioning behavior is powertrain- and model-year-dependent:
- **Electric Vehicles (BEV / PHEV)**:
  - `climate.*_climate` and `switch.*_remote_start` operate the high-voltage electric heat pump / A/C compressor without starting an engine.
  - On MM24/MM25 vehicles, target cabin temperature can be adjusted directly from Home Assistant.
  - On 21MM and European vehicles, pre-conditioning turns on heating/cooling using the vehicle's last-set in-cabin HVAC settings or standard preset.
- **Combustion & Hybrid Vehicles (ICE / HEV)**:
  - `switch.*_remote_start` or turning on `climate.*_climate` activates Remote Engine Start (`engine-start`) to precondition the interior.
  - Subject to vehicle safety interlocks: all doors, windows, and hood must be closed and locked, transmission in Park, hazard lights off, key fob not inside, and sufficient fuel.
  - Standard Toyota factory safety limit automatically shuts off the engine after **10 minutes**.
- **Subscription Requirement**: Remote start and cabin pre-conditioning require an active **Toyota Remote Connect**, **Lexus Enform Remote**, or **Subaru Solterra Connect** subscription.

### 12V Auxiliary Battery Drain Protection
Frequent cellular Data Communication Module (DCM) polling can rapidly discharge the 12V auxiliary battery in parked EVs and hybrids. `toyota-connected` incorporates a robust safety coordinator:
- **Passive Cloud Polling**: Regular coordinator intervals read cloud-cached telemetry without sending cellular wake-up packets to the car.
- **Trip Arrival Wake**: Detects drive completion (odometer advancement) and triggers an active sync only after a trip has ended.
- **Hourly Cellular Rate Limiter**: Imposes a strict ceiling on active DCM wake attempts per hour.
- **Circuit Breaker**: Automatically suspends wake requests if a vehicle is unreachable (such as in an underground parkade) until the next drive cycle.
- **Immediate Command Bypass**: User-initiated actions (door lock/unlock, immediate charging, pre-conditioning) bypass rate limits and dispatch immediately.

### Strict Security & Contract Testing
- **RFC 7636 PKCE S256**: Modern OAuth 2.0 PKCE authentication flow without plaintext credential storage.
- **Serialized Token Refresh**: Protected by `asyncio.Lock()` to prevent race conditions and invalid refresh token lockouts.
- **Golden Contract Fixtures**: Deterministic schema validation against recorded JSON payloads in `contracts/fixtures/`.
- **Diagnostics Redaction**: Automatic masking of VINs, user IDs, tokens, and location coordinates in Home Assistant diagnostics and logs.

---

## Repository Structure

```text
.
├── contracts/
│   ├── README.md                     # Direct API contract documentation and endpoint reference
│   ├── schemas/                      # Telemetry AppSync GraphQL schema definitions
│   │   └── telemetry.graphql
│   └── fixtures/                     # Golden JSON payloads for contract verification
│       ├── na_electric_status_bev.json
│       ├── na_telemetry_bev.json
│       ├── na_remote_status.json
│       ├── telemetry_bev_metric.json
│       ├── telemetry_bev_imperial.json
│       ├── telemetry_hybrid_ice.json
│       ├── eu_electric_status.json
│       └── eu_vehicle_status.json
│
├── src/
│   └── toyota_connected/             # Standalone Python SDK (pip installable)
│       ├── auth.py                   # PKCE S256 & token management
│       ├── base_provider.py          # Abstract regional provider interface
│       ├── brands.py                 # Toyota, Lexus, Subaru brand registry
│       ├── smart_refresh.py          # 12V battery drain protection & rate limiter
│       ├── models.py                 # Dataclasses & enums
│       ├── graphql.py                # AppSync queries, mutations & Stencil subscriptions
│       ├── rest.py                   # OneAPI REST client & telematics parser
│       ├── na_provider.py            # North America regional provider (US, CA, MX)
│       └── eu_provider.py            # Europe regional provider (EU, UK)
│
├── custom_components/
│   └── toyota_connected/             # Home Assistant Integration (HACS)
│       ├── manifest.json
│       ├── config_flow.py            # Config flow with region/brand selection & 2FA/OTP
│       ├── base_entity.py
│       ├── sensor.py                 # Battery, range, odometer, tire pressure
│       ├── binary_sensor.py          # Charging, plug, doors, windows, hood
│       ├── switch.py                 # Immediate charge, remote start, hazard lights
│       ├── select.py                 # Target charge limit & AC current (MM24+)
│       ├── lock.py                   # Door lock / unlock
│       ├── climate.py                # Cabin pre-conditioning entity
│       ├── diagnostics.py           # Redacted diagnostics export
│       └── services.yaml             # Action/service definitions
│
└── tests/                            # Automated unit & contract tests
```

---

## Home Assistant Installation

### Method 1: HACS (Recommended)
1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the three dots in the top right > **Custom repositories**.
3. Add the repository URL: `https://github.com/zbergus/toyota-connected` with Category: **Integration**.
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

1. In Home Assistant, navigate to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Toyota, Lexus & Solterra Connected Services**.
3. Select your geographic region:
   - **North America (Canada, USA, Mexico)**
   - **Europe (EU, UK)**
4. Select your vehicle brand:
   - **Toyota**
   - **Lexus**
   - **Subaru (Solterra Connect)**
5. Enter your account credentials and complete the 6-digit OTP / SMS verification code if prompted.
6. All vehicles associated with your account are automatically discovered with appropriate sensors and controls based on their detected generation and powertrain.

---

## Available Home Assistant Services

The integration provides the following services under the `toyota_connected` domain:

| Service | Description | Applicability |
| :--- | :--- | :--- |
| `toyota_connected.door_lock` | Remotely locks vehicle doors | Subscribed vehicles |
| `toyota_connected.door_unlock` | Remotely unlocks vehicle doors | Subscribed vehicles |
| `toyota_connected.start_charge` | Starts immediate EV/PHEV traction battery charging | Plugged-in EVs/PHEVs |
| `toyota_connected.stop_charge` | Stops ongoing battery charging | Plugged-in EVs/PHEVs |
| `toyota_connected.climate_start` | Starts cabin pre-conditioning or remote engine start | Subscribed vehicles |
| `toyota_connected.climate_stop` | Stops cabin pre-conditioning or remote engine start | Subscribed vehicles |
| `toyota_connected.set_charge_limit` | Sets target battery charge limit percentage (50%–100%) | MM24 / MM25 EVs only |
| `toyota_connected.refresh` | Requests a fresh vehicle telemetry synchronization | Subject to 12V drain limiter |

---

## Acknowledgments & Upstream Credits

This project builds upon the reverse engineering and integration work of two foundational open-source projects:

- **[`ha-toyota-na`](https://github.com/orienw/ha-toyota-na)** maintained by **Orien Wagner** (forked from original work by **widewing** and **vanstinator**):
  - Provided the foundation for North American Toyota Connected Services, ForgeRock OpenAM authentication, OneAPI REST endpoints, and AppSync GraphQL telemetry for modern 21MM and 24MM vehicles.
- **[`ha_toyota`](https://github.com/pytoyoda/ha_toyota)** / **`mytoyota`** by the **pytoyoda** team (authored by **Simon Hansen**, **deejay1**, and **CM000n**):
  - Provided the European CTPA architecture, standard Home Assistant async data coordinator modeling, and inspired safe telemetry polling and quiescent battery care.

---

## Development & Testing

Run the automated test suite, linter, type checker, and security audit:
```bash
uv run --python 3.12 --extra dev pytest -q
uv run --python 3.12 --extra dev ruff check .
uv run --python 3.12 --extra dev mypy src custom_components
uv run --python 3.12 --extra dev bandit -r src
```
