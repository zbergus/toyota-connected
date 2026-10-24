## Summary

<!-- Provide a concise description of what this PR accomplishes. -->

## Type of Change

- [ ] `feat`: New feature or capability
- [ ] `fix`: Bug fix
- [ ] `docs`: Documentation updates
- [ ] `refactor`: Code refactoring without changing functionality
- [ ] `test`: New or updated tests
- [ ] `ci`: CI/CD workflow updates
- [ ] `chore`: Maintenance, dependencies, or tooling

## 12V Auxiliary Battery & Telematics Impact

- [ ] **No polling impact**: This PR does not alter polling intervals, wake mechanisms, or telematics refresh frequencies.
- [ ] **Changes polling/wake**: Explain how 12V battery drain is prevented and why active telematics wake is required:

## Testing Performed

- [ ] All unit tests pass: `uv run pytest -v`
- [ ] Ruff lint & format pass: `uv run ruff check .` and `uv run ruff format --check .`
- [ ] Mypy type-checking passes: `uv run mypy src custom_components`
- [ ] Home Assistant hassfest validation passes

## Checklist

- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g., `feat(sensor): ...`, `fix(auth): ...`).
- [ ] No real VINs, GPS coordinates, session tokens, or credentials are included in code, fixtures, or PR discussions.
- [ ] Golden fixtures and contract tests updated (if changing API payloads).
- [ ] Documentation updated (if applicable).
