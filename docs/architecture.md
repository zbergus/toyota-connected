# Architecture, Supported Vehicles & Development

Deep-dive material that would otherwise bloat the README on the HACS page.
For install and setup, see the [README](../README.md).

## Architecture & vehicle generation matrix

Toyota Connected Services uses different telematics platforms depending on vehicle
generation, model year and region. Features adapt dynamically to the vehicle's reported
capabilities.

| Generation | Model Years (approx.) | Representative models | Telematics gateway & protocol | Key features & API capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **MM24 / MM25** | **2024+ / 2025+** | 2025+ bZ4X, 2024+ Grand Highlander, Land Cruiser, Tacoma, Lexus TX | AWS AppSync GraphQL (`/graphql`) with real-time Stencil WebSocket subscriptions | **Full feature set**: dynamic target charge limit via API (50%–100%), AC current limit via API (8A, 16A, 32A, Max), remaining charge time to 80% and 100%, climate pre-conditioning with thermostat setpoint control, real-time push telemetry. |
| **21MM** | **2022 – 2024** | 2023–2024 bZ4X, 2023–2024 Solterra, 2023–2024 Lexus RZ, 2022–2024 Tundra, Sequoia, RAV4 Prime, Lexus NX | Toyota OneAPI REST (`api.toyota.com`) over HTTPS | **Standard telemetry & remote commands**: SoC %, usable battery %, EV range (AC off/on), total charge time to 100%, immediate charge start/stop, remote start / cabin pre-conditioning, door lock/unlock, hazard lights.<br>⚠️ Target charge limits and AC current limits **cannot be set via API** on 21MM (configure in-vehicle); time to 80% is not exposed by the REST API. |
| **Europe (TME)** | **All supported years** | bZ4X, Yaris Cross, RAV4 PHEV, Corolla (EU spec) | European CTPA OneAPI (`ctpa-oneapi.tceu-ctp-prd.toyotaconnectedeurope.io`) | Battery SoC %, EV range, remaining charge time to full, lock/unlock, cabin climate pre-conditioning (`/v2/remote/climate-control`).<br>⚠️ Charge limits are configured in-dash or via scheduled charging, not via cloud mutations. |
| **17CY / 17CYPLUS** | **2018 – 2022** | Camry, RAV4, Corolla, Highlander, Avalon | Toyota legacy REST gateway | Odometer, fuel level, tire pressures, door lock/unlock, remote engine start (where subscribed). No EV battery management. |

### 2026 model years and newer platforms

The table is based on vehicles reported by users and on the generation codes the code recognises
(`17CY`, `17CYPLUS`, `21MM`, `24MM`, `25MM`, `GR86`, `PRE17CY`). 2026 model-year vehicles are not
yet individually verified. If Toyota's cloud reports a code the integration doesn't recognise, the
vehicle is loaded as `UNKNOWN` and is not sent down the AppSync GraphQL path, so expect reduced
entities until support is added. Diagnostics show the reported `generation` and `model_year`, which
is exactly what's needed to add a new platform. See the
[vehicle support issue form](https://github.com/zbergus/toyota-connected/issues/new?template=vehicle_support.yml).

## Multi-brand & multi-region support

- **Multi-brand registry**: unified client for brand scoping, endpoints and authentication
  across **Toyota**, **Lexus** and **Subaru (Solterra Connect)**.
- **North America**: dynamic regional routing (`CA` / `US`) with native metric (`km`, `°C`,
  `kPa`, `kW`) and imperial (`mi`, `°F`, `PSI`) conversion.
- **Europe**: native support for European CTPA OneAPI telematics and remote commands.

## Cabin pre-conditioning & remote start

Cabin climate behaviour is powertrain- and model-year-dependent:

- **BEV / PHEV** — `climate.*_climate` and `switch.*_remote_start` drive the high-voltage heat
  pump / A/C compressor without starting an engine. On MM24/MM25 the target cabin temperature
  is adjustable from Home Assistant; on 21MM and European vehicles pre-conditioning uses the
  vehicle's last-set HVAC settings.
- **ICE / HEV** — `switch.*_remote_start` (or turning on `climate.*_climate`) performs Remote
  Engine Start. Subject to vehicle safety interlocks: doors, windows and hood closed and locked,
  transmission in Park, hazards off, fob not inside, sufficient fuel. Toyota's factory limit
  shuts the engine off after **10 minutes**.
- **Subscription required** — remote start and cabin pre-conditioning need an active
  **Toyota Remote Connect**, **Lexus Enform Remote** or **Subaru Solterra Connect** subscription.

## 12V auxiliary battery drain protection

Frequent cellular Data Communication Module (DCM) polling can rapidly discharge the 12V
auxiliary battery of a parked EV or hybrid. `toyota-connected` therefore:

- **Polls passively** — regular coordinator intervals read cloud-cached telemetry without
  sending cellular wake-up packets to the car.
- **Wakes once, after a trip** — detects drive completion (odometer advancement) and triggers an
  active sync only after the trip has ended.
- **Rate-limits cellular wakes** — a strict hourly ceiling on active DCM wake attempts.
- **Trips a circuit breaker** — suspends wake requests if a vehicle is unreachable (e.g. an
  underground parkade) until the next drive cycle.
- **Bypasses limits for commands** — user-initiated actions (lock/unlock, immediate charge,
  pre-conditioning) dispatch immediately.

Do not lower the poll interval or remove these guards: the failure mode is a flat 12V battery
and a car that cannot close its contactors.

## Security & contract testing

- **RFC 7636 PKCE S256** — modern OAuth 2.0 flow, no plaintext credential storage.
- **Serialized token refresh** — guarded by `asyncio.Lock()` to avoid race conditions and
  invalid-refresh-token lockouts.
- **Golden contract fixtures** — deterministic schema validation against recorded JSON payloads
  in [`contracts/fixtures/`](../contracts/fixtures/).
- **Diagnostics redaction** — VINs, user IDs, tokens and location coordinates are masked in
  Home Assistant diagnostics and logs.

## Repository structure

```
.
├── contracts/                        # API contract docs, GraphQL schema, golden fixtures
├── src/toyota_connected/             # Standalone Python SDK (pip installable)
│   ├── auth.py                       # PKCE S256 & token management
│   ├── base_provider.py              # Abstract regional provider interface
│   ├── brands.py                     # Toyota, Lexus, Subaru brand registry
│   ├── smart_refresh.py              # 12V drain protection & wake rate limiter
│   ├── models.py                     # Dataclasses & enums
│   ├── graphql.py                    # AppSync queries, mutations, Stencil subscriptions
│   ├── rest.py                       # OneAPI REST client & telematics parser
│   ├── na_provider.py                # North America (US, CA, MX)
│   └── eu_provider.py                # Europe (EU, UK)
├── custom_components/toyota_connected/   # Home Assistant integration (HACS)
│   ├── manifest.json
│   ├── config_flow.py                # Region/brand selection & 2FA/OTP
│   ├── sensor.py                     # Battery, range, odometer, tire pressure
│   ├── binary_sensor.py              # Charging, plug, doors, windows, hood
│   ├── switch.py                     # Immediate charge, remote start, hazards
│   ├── select.py                     # Target charge limit & AC current (MM24+)
│   ├── lock.py                       # Door lock / unlock
│   ├── climate.py                    # Cabin pre-conditioning
│   └── diagnostics.py                # Redacted diagnostics export
└── tests/                            # Unit & contract tests
```

## Development & testing

```bash
uv run --python 3.12 --extra dev pytest -q
uv run --python 3.12 --extra dev ruff check .
uv run --python 3.12 --extra dev mypy src custom_components
uv run --python 3.12 --extra dev bandit -r src
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for environment setup, commit conventions and PR
guidelines.

## Acknowledgments

This project builds on the reverse-engineering work of two foundational open-source projects:

- **ha-toyota-na** maintained by Orien Wagner (forked from original work by widewing and
  vanstinator): North American Toyota Connected Services, ForgeRock OpenAM authentication,
  OneAPI REST endpoints and AppSync GraphQL telemetry for modern 21MM and 24MM vehicles.
- **ha_toyota / mytoyota** by the pytoyoda team (Simon Hansen, deejay1, CM000n): the European
  CTPA architecture and the Home Assistant async coordinator model that inspired the polling
  and battery-care design.
