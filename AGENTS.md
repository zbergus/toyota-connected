# AGENTS.md: toyota-connected

Context for AI coding agents. Shared by agy, OpenCode (`oc`) and aider (`ai`). Read this first, then `README.md`.

## What this is
`toyota-connected`: async Python SDK plus a Home Assistant custom integration (`custom_components/toyota_connected`) for Toyota, Lexus and Subaru (bZ4X, Solterra, RZ) connected services, Canada/US and Europe. Includes 12V battery drain protection (do not make polling more aggressive without reading the README section on it). Remote: `zbergus/toyota-connected`.

## Layout
`src/toyota_connected` (SDK), `custom_components/` (HA integration), `tests/`, `contracts/` (API contract fixtures), `vendor/` (vendored wheels, do not edit), `ha_toyota`, `ha-toyota-na`, `orienw-ha-toyota-na` (reference copies of upstream projects, read-only), `dist/` (build output).

## Commands (verified 2026-10-23 on the VM; `uv` is in `~/.local/bin`)
- Tests: `uv run --python 3.12 --extra dev pytest -q` (44 pass, under a second). System Python is 3.11, so always go through `uv`.
- Lint: `uv run --python 3.12 --extra dev ruff check .`; types: `... mypy`; security: `... bandit -r src`. Config lives in `pyproject.toml` (ruff line length 100, py312).

## Rules
- No real credentials, VINs or tokens in code, fixtures or commits. Tests must not hit the network.
- Small, reversible changes; run the tests before and after; one logical change per commit.
- Do not edit `vendor/` or the three reference upstream folders.
