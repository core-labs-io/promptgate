# Decisions

Non-obvious choices made while building promptgate, and why. Newest entries at the bottom.

- 2026-07-02: Scaffolded with `hatchling` + `src/` layout, zero required runtime dependencies. `tiktoken` is an extra (`[openai]`); `pytest`/`pytest-cov`/`ruff` live under `[dev]`. Per Design Principle 2.
