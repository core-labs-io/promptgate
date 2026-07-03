# Changelog

All notable changes to this project are documented in this file.

## [0.1.0] - Unreleased

### Added
- `Gate` class: `prepare()`, `explain()`, `rehydrate()` — the full public API.
- Secret detection (PEM blocks, known-prefix patterns, context-keyword
  assignments, opt-in entropy detection) and PII detection (email, phone,
  credit card, SSN, IP), with reversible PII placeholders and one-way
  secret masking.
- Compression strategies: `window` (pinned + sliding tail), `truncate_tools`
  (stale tool-output stubbing), and `hybrid` (the default).
- Structural safety net (`safety.validate()` / `safety.repair()`) run on
  every compression path.
- `ExplainReport` with the unified Save+Protect hero-block output.
- Benchmark harness (`benchmarks/generate.py`, `benchmarks/run.py`) against
  synthetic 50-turn agent transcripts.
- CI: pytest matrix (3.9-3.12), ruff lint/format, gitleaks scan.
- Zero required runtime dependencies; `tiktoken` available as the
  `[openai]` extra.
