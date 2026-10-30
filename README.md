# Toyota, Lexus & Solterra Connected Services

Your Toyota, Lexus or Subaru (Solterra Connect) in Home Assistant: battery and charging,
range, doors and windows, locks, climate and remote start — Canada/US and Europe.

[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/github/v/release/zbergus/toyota-connected)](https://github.com/zbergus/toyota-connected/releases)
[![license](https://img.shields.io/github/license/zbergus/toyota-connected)](LICENSE)

Needs Home Assistant 2024.1+ and an active connected-services subscription
(Toyota Remote Connect, Lexus Enform Remote or Subaru Solterra Connect).

---

## What you get

- **Battery & charging** — state of charge, usable capacity, EV range with A/C off and on,
  charging power, time to full, and time to 80% on 2024+ vehicles.
- **Controls** — start/stop charging, lock and unlock, hazard lights, climate pre-conditioning
  and remote start. Target charge limit and AC current limit on 2024+ vehicles.
- **Vehicle state** — doors, windows, hatch, hood, tire pressures, odometer, fuel level.
- **Battery-safe polling** — passive cloud reads, an hourly wake-rate limiter and a circuit
  breaker protect the 12V battery; your own commands still go out immediately.
- **The same code as a Python SDK** — `pip install toyota-connected` for scripts and tooling.

## Supported vehicles

- **2024+ (MM24 / MM25)** — bZ4X, Grand Highlander, Land Cruiser, Tacoma, Lexus TX.
  Everything above, including charge limit and AC current limit.
- **2022–2024 (21MM)** — bZ4X, Solterra, Lexus RZ, Tundra, Sequoia, RAV4 Prime, Lexus NX.
  Telemetry and remote commands; charge limit and AC current are set in the car, not via cloud.
- **Europe (TME)** — bZ4X, Yaris Cross, RAV4 PHEV, Corolla. SoC, range, charge time, locks,
  climate.
- **2018–2022 (17CY / 17CYPLUS)** — Camry, RAV4, Corolla, Highlander, Avalon. Odometer, fuel,
  tire pressures, locks, remote start.

**2026 model years** aren't individually verified yet. In North America a new car reports a
generation code, and if it isn't one of the above the integration treats it as a basic vehicle
until support is added, so you may see fewer entities than the car offers. Tell us — see below.

Full feature matrix and platform details: [docs/architecture.md](docs/architecture.md).

### Car missing, or something looks off?

Please [open a vehicle support issue](https://github.com/zbergus/toyota-connected/issues/new?template=vehicle_support.yml)
with your model, year, region, the diagnostics download (Settings → Devices & services → this
integration → ⋮ → Download diagnostics) and any "Unrecognised vehicle generation" line from your
Home Assistant log. It's usually a quick fix once we can see the generation code your car reports,
and it helps everyone with the same model. Other problems:
[bug report](https://github.com/zbergus/toyota-connected/issues/new?template=bug_report.yml).

## Install

### HACS (recommended)

1. **HACS → Integrations → ⋮ → Custom repositories**
2. URL `https://github.com/zbergus/toyota-connected`, category **Integration**
3. Search for **Toyota, Lexus & Solterra Connected Services** and click **Download**
4. Restart Home Assistant

### Manual

Copy `custom_components/toyota_connected` into `/config/custom_components/` and restart.

## Setup

1. **Settings → Devices & Services → Add integration**
2. Search for **Toyota, Lexus & Solterra Connected Services**
3. Choose region (**North America** or **Europe**) and brand (**Toyota**, **Lexus**, **Subaru**)
4. Sign in, and enter the 6-digit one-time code if Toyota asks for it

Every vehicle on the account is added automatically, with entities chosen from the vehicle's
detected generation and powertrain.

## Actions

- `toyota_connected.door_lock` / `door_unlock` — lock or unlock the doors.
- `toyota_connected.start_charge` / `stop_charge` — control charging while plugged in.
- `toyota_connected.climate_start` / `climate_stop` — pre-conditioning, or remote engine start
  on ICE/HEV.
- `toyota_connected.set_charge_limit` — target charge percentage (MM24/MM25 only).
- `toyota_connected.refresh` — request a fresh sync (subject to the 12V wake limiter).

## Good to know

- **Don't shorten the poll interval.** Parked cars sleep; polling wakes the cellular module and
  drains the 12V battery. The defaults are deliberate.
- **Remote start needs a subscription**, and the car must be locked with doors, windows and hood
  closed. Toyota stops the engine after 10 minutes.
- **Europe and 21MM** vehicles cannot set charge limits through the API — use the car's own
  schedule or in-dash settings.

## Troubleshooting

- `403` / `504` bursts during Toyota cloud maintenance are transient; the next cycle recovers.
- A reauth prompt means the refresh token was revoked — sign in again from the integration page.
- Car not listed, 2026 model year, or missing entities: use the
  [vehicle support issue form](https://github.com/zbergus/toyota-connected/issues/new?template=vehicle_support.yml).
- For any issue, enable debug logging for `toyota_connected` and `toyota_connected.rest` and
  attach diagnostics (VIN, tokens and location are redacted).

## Documentation

- [Architecture, supported vehicles, development](docs/architecture.md)
- [API contracts and fixtures](contracts/README.md)
- [Contributing](CONTRIBUTING.md)

## Credits

Built on the reverse-engineering work of **ha-toyota-na** (Orien Wagner, from widewing and
vanstinator) and **ha_toyota / mytoyota** (the pytoyoda team). Full attribution in
[docs/architecture.md](docs/architecture.md#acknowledgments).

## License

MIT — see [LICENSE](LICENSE).
