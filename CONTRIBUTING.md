# Contributing to Toyota Connected Services

Thank you for your interest in contributing to `toyota-connected`! This project provides a unified Python SDK and Home Assistant custom integration for Toyota, Lexus, and Subaru Connected Services in North America (Canada/US) and Europe.

---

## Core Architecture Principles

Before proposing changes, please review our foundational principles:

### 1. 12V Auxiliary Battery & Telematics Drain Protection
- Toyota and Lexus connected vehicles (especially EVs like the bZ4X and Solterra) rely on a separate 12V auxiliary battery to power the onboard telematics control unit (DCM).
- **Never implement aggressive active polling loops.** Sending wake commands or querying active status while a vehicle is asleep can deplete the 12V battery and leave the owner stranded.
- All polling must remain passive (WebSocket listeners or cache reads) when the vehicle is parked. Active refreshes are only triggered by explicit user interaction or detected trip completions (odometer advancement).

### 2. Strict Security & Privacy
- **Zero Plaintext Persistence**: Tokens are refreshed through RFC 7636 PKCE S256 OAuth flows and serialized via an `asyncio.Lock()`.
- **Diagnostics Redaction**: Any payload logged or returned through Home Assistant diagnostics must strip OAuth tokens, GUIDs, VINs, and physical GPS coordinates.
- **No Real PII in Git**: Test fixtures and PRs must use mock VINs (e.g., `4T1BZ4X2024MOCK01`) and landmark civic coordinates.

### 3. Decoupled Architecture
- The core API client lives as a standalone Python SDK in [`src/toyota_connected`](src/toyota_connected).
- The Home Assistant integration in [`custom_components/toyota_connected`](custom_components/toyota_connected) imports the SDK.
- Non-HA-specific features (auth, REST/GraphQL parsing, brand abstractions) belong in the SDK.

---

## Development Environment Setup

We use [`uv`](https://docs.astral.sh/uv/) for fast, deterministic dependency management. Python 3.12 or higher is required.

### 1. Clone the repository
```bash
git clone https://github.com/zbergus/toyota-connected.git
cd toyota-connected
```

### 2. Install dependencies
```bash
uv sync --extra dev
```

### 3. Run the test suite
```bash
uv run pytest -v
```

### 4. Code Quality & Formatting
We enforce formatting and linting via `ruff`, static typing with `mypy`, and security scanning with `bandit`:

```bash
# Check formatting and style
uv run ruff check .
uv run ruff format --check .

# Auto-format code
uv run ruff format .

# Type checking
uv run mypy src custom_components

# Security scanner
uv run bandit -r src
```

---

## Git & Commit Conventions

This project enforces [Conventional Commits](https://www.conventionalcommits.org/). Each commit message should follow this format:

```text
<type>(<optional scope>): <description>

[optional body]
```

### Allowed Types
- `feat`: A new feature or platform entity
- `fix`: A bug fix
- `docs`: Documentation updates
- `test`: Adding or correcting tests
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `ci`: Changes to CI/CD workflows and configuration
- `chore`: Tooling, dependencies, or formatting updates

### Examples
- `feat(sensor): add active charging power sensor for 21MM BEVs`
- `fix(lock): prevent premature state reversion with optimistic update`
- `docs(readme): add installation guide for Subaru Solterra`

---

## Pull Request Guidelines

1. **Create a topic branch**: `git checkout -b feat/your-feature-name`
2. **Write tests**: Any new feature or bugfix should include corresponding unit tests under `tests/`.
3. **Verify contracts**: If modifying API schemas, ensure golden contract fixtures in `contracts/fixtures/` are respected.
4. **Run all checks locally** before opening the PR.
5. **Open a PR**: Fill out the pull request template completely, ensuring the 12V battery impact is explicitly addressed.
