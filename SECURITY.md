# Security Policy

## Supported Versions

Only the latest release of `toyota-connected` receives security patches and bug fixes.

| Version | Supported          |
| ------- | ------------------ |
| 3.0.x   | :white_check_mark: |
| < 3.0   | :x:                |

## Reporting a Vulnerability

We take the security and privacy of vehicle telematics, credentials, and telemetry very seriously.

If you believe you have discovered a security vulnerability in `toyota-connected`, **please do not report it in a public issue or pull request**.

Instead, please submit a report through **GitHub Private Vulnerability Reporting**:
1. Navigate to the repository's [Security Tab](https://github.com/zbergus/toyota-connected/security).
2. Click **Report a vulnerability**.
3. Provide details regarding the potential impact, reproduction steps, and any proof-of-concept.

You will receive an acknowledgment within 48 hours. If the vulnerability is accepted, we will work with you to coordinate a patched release and appropriate credit in the release notes.

## Sensitive Information Guidelines

- **Never** include your vehicle's VIN, full GUID, OAuth bearer/access tokens, refresh tokens, passwords, or exact parked GPS coordinates in issues, PRs, or public discussions.
- Use Home Assistant's built-in diagnostics download whenever possible, as this integration automatically redacts credentials, device identifiers, and location coordinates.
