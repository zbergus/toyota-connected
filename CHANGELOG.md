# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). The GitHub release notes for each tag are
generated from the matching section below.

## [Unreleased]

## [3.0.5] - 2026-10-30

### Added
- North America: a debug log line per vehicle with the capability flags Toyota reports (for
  example `can300Capable`, `features`, `extendedCapabilities`), to make vehicle-support reports
  actionable. It logs only booleans, 0/1 flags and the fixed values `ACTIVE`, `INACTIVE`, `E` and `I`, plus
  the generation and model year, never the VIN, account identifiers, names or location.

## [3.0.4] - 2026-10-30

### Added
- "Vehicle support" issue form for cars that are missing, partially working or newer than the
  documented list (including 2026 model years), asking for the diagnostics download.

### Fixed
- Diagnostics now also redact the config entry `title` and `unique_id` (which embeds the account
  identifier).
- North America: an unrecognised vehicle generation code is now logged as a warning instead of
  being silently mapped to `UNKNOWN`, so it can be reported.

### Changed
- README and architecture docs state plainly that 2026 model years are not yet verified, explain
  what happens for an unrecognised generation code, and point users to the new issue form.
- Manifest now declares its Home Assistant category (`vehicles_transport.cars_evs`), which
  clears the hassfest "no categories" warning and files the integration correctly in the
  integration picker.

## [3.0.3] - 2026-10-30

### Added
- Integration icon, shipped in `custom_components/toyota_connected/brand/` so Home Assistant
  and HACS show it without a `home-assistant/brands` submission.
- This changelog; release notes are now taken from it instead of a bare compare link.

## [3.0.2] - 2026-10-30

### Fixed
- Config-flow text now renders in the UI: added `translations/en.json` (Home Assistant does
  not ship `strings.json` to the frontend for custom integrations).

### Changed
- README trimmed for the HACS card: install and setup first, the feature matrix, battery-safety
  rationale and repository layout moved to `docs/architecture.md`.
- README title now matches the display name in `hacs.json` and `manifest.json`.

### CI
- New `Validate` workflow: hassfest, the HACS action, a check that the bundled SDK copy matches
  `src/toyota_connected`, and a check that the release zip contains the manifest, strings and
  translations and no `__pycache__`.

## [3.0.1] - 2026-10-30

### Fixed
- North America: send correlation-id headers on OneAPI REST calls and prefer
  `v3/electric/status` over v2. Verified against production: v3 returns 200 with the header and
  500 `ONE-RES-10015` without it; v2 and v3 payloads parse identically.
- Transient upstream gateway errors are logged at a lower severity instead of as errors.

### CI
- Weekly Dependabot updates for GitHub Actions and Python dependencies.
- Bumped `actions/checkout` to v7, `actions/upload-artifact` to v7, `astral-sh/setup-uv` to v7
  and `softprops/action-gh-release` to v3.

## [3.0.0] - 2026-10-24

### Added
- Unified Toyota, Lexus and Subaru (Solterra Connect) integration for North America and Europe,
  with the same code published as a Python SDK.
- 12V battery drain protection: passive cloud reads, an hourly wake-rate limiter and a circuit
  breaker. Your own commands still go out immediately.
- Release workflow that builds and attaches the HACS zip.
- Contribution guidelines, issue forms, PR template, code of conduct and security policy.

### Changed
- The climate pre-conditioning switch is now named "Remote start".

### Fixed
- Lock entity no longer flips back to its old state before the cloud confirms (optimistic update
  followed by a delayed refresh).
- Active charging power is computed in kW for 21MM battery-electric vehicles.

[Unreleased]: https://github.com/zbergus/toyota-connected/compare/v3.0.5...HEAD
[3.0.5]: https://github.com/zbergus/toyota-connected/compare/v3.0.4...v3.0.5
[3.0.4]: https://github.com/zbergus/toyota-connected/compare/v3.0.3...v3.0.4
[3.0.3]: https://github.com/zbergus/toyota-connected/compare/v3.0.2...v3.0.3
[3.0.2]: https://github.com/zbergus/toyota-connected/compare/v3.0.1...v3.0.2
[3.0.1]: https://github.com/zbergus/toyota-connected/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/zbergus/toyota-connected/releases/tag/v3.0.0
