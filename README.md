# promptgate

![PyPI version](https://img.shields.io/pypi/v/promptgate.svg)
![CI](https://github.com/core-labs-io/promptgate/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python versions](https://img.shields.io/pypi/pyversions/promptgate.svg)

*Every prompt you send is too expensive and too revealing. Fix both with one line.*

promptgate is a **prompt firewall**: a lightweight, provider-agnostic layer that
every message list passes through before it leaves your machine and reaches an
LLM API. It does two jobs in one pipeline:

1. **Save** — reduce token usage of conversation history (sliding window,
   stale tool-output truncation), targeting large reductions on long
   conversations and agent workloads.
2. **Protect** — detect and mask secrets (API keys, tokens, private keys,
   credentials) and PII (emails, phones, etc.) so they never reach a
   third-party API.

```
messages → scrub secrets → mask PII → truncate stale tool outputs → fit window to budget → validated output
                      ↑ PII mapping stays in the caller's process ↑
```

The unified `explain()` report showing both pillars in one output IS the
product:

```
promptgate report
─────────────────
Tokens:  11,840 → 5,210  (56% saved)
Secrets: 1 AWS key BLOCKED (one-way)
PII:     3 emails, 1 phone masked (reversible)
Structure: valid ✓
```

## Benchmarks

Measured with `benchmarks/generate.py` + `benchmarks/run.py` against
synthetic 50-turn agent transcripts (verbose tool output, 5 planted
recall-facts, a planted fake secret, and a planted fake email per
transcript). These numbers are for **this specific agent-style workload**,
not a universal claim — see `benchmarks/results.md` to regenerate.

| Strategy | Tokens before → after | % saved | Recall-facts surviving | Secrets/PII caught |
|---|---|---|---|---|
| window | 27,322 → 3,330 | 88% | 0% | 100% |
| truncate_tools | 27,322 → 2,596 | 90% | 100% | 100% |
| hybrid | 27,322 → 2,596 | 90% | 100% | 100% |

Plain sliding-window compression evicts the early turns where facts were
planted entirely — losing them. `truncate_tools` (and `hybrid`, which tries
it first) instead stubs out the stale, verbose tool output that was
crowding the budget, keeping every real message — and every fact — intact.
That's the differentiator this library exists for.

## Quickstart

```python
from promptgate import Gate

gate = Gate(budget=8000)
safe_messages, pii_map = gate.prepare(messages)
print(gate.explain(messages))
restored = gate.rehydrate(llm_reply_text, pii_map)
```

Install: `pip install promptgate` (zero required dependencies). Add
`pip install promptgate[openai]` for exact `tiktoken`-based token counts —
without it, promptgate uses a pessimistic stdlib heuristic that never
undercounts your budget.

## Save

`Gate(budget=..., compress=..., keep_last=..., pin=..., counter=...)`
fits your conversation to a token budget using one of three strategies:

- **`window`** — keeps pinned messages (`pin`, default `["system"]`) and the
  last `keep_last` messages verbatim, then walks backward adding older
  messages until the budget runs out. Never evicts the most recent user
  message.
- **`truncate_tools`** — the differentiator. In agent workloads, stale tool
  output is often 60-70% of context. Tool results older than the most
  recent turn and larger than a size threshold get replaced with a
  shape-preserving stub: `[tool result truncated: search returned ~1,200 tokens]`.
- **`hybrid`** (default) — `truncate_tools` first, then `window` only if
  still over budget.

Compression never orphans a tool result from its tool call, drops the most
recent user message, strips the system prompt, or emits an invalid role
sequence — every strategy runs through structural repair and validation
before returning. If your input already fits the budget and there's
nothing to scrub, `prepare()` returns it unchanged.

## Protect

`scrub=["secrets", "email", "phone"]` (configurable categories) and
`on_secret="warn"` (`"mask"` | `"warn"` | `"raise"`) control detection.
Secrets are found in three layers — PEM key blocks first (masked as one
atomic unit), then known-credential prefixes (`sk-ant-`, `sk-`, AWS,
GitHub, Slack, Google, Stripe, JWTs, Bearer tokens), then context-keyword
assignments (`password=`, `api_key:`, connection-string credentials).
Entropy-based detection is available but opt-in (`entropy_threshold=...`),
since it's a false-positive factory on git SHAs and UUIDs.

**Secrets are one-way; PII is reversible.** This asymmetry is deliberate:
a real API key must never flow back through this library — once masked,
it's gone, and `on_secret="warn"` treats every detection as a security
event worth rotating, because it's probably already in your shell history
or logs. PII placeholders (`[[EMAIL_1]]`, `[[PHONE_2]]`) are rehydrated via
`gate.rehydrate(text, pii_map)`, where `pii_map` is a plain dict that stays
in your process — promptgate's core has no server, no database, and no
memory between calls. Pass the same `pii_map` back into `prepare()` on
the next turn to keep placeholders consistent across a conversation.

`explain()` is a dry run: it shows exactly what *would* be cut or masked,
and never mutates your input or raises, even if `on_secret="raise"`.
Secret values never appear in a report, warning, or exception — only
their category and label.

## Known limitations (v0.1.0)

- **Multimodal content** (image parts) is detected and passed through
  untouched and uncounted beyond its text parts — it is never scrubbed or
  compressed.
- **PII detection is regex-only** (Phase 1) — no NER. It can miss PII that
  doesn't match a pattern and can false-positive on things that look like
  one.
- **Phone number detection is NA-formats only.**
- The stdlib token-counting heuristic (used without `tiktoken`) is a
  conservative estimate, not an exact count for any specific model.

## Roadmap

- **v0.1.0 (current)** — everything above.
- **v0.2** — rolling incremental summarization (bring-your-own cheap model
  callable), Anthropic + Gemini message-format adapters, an LLM-judge
  quality metric in benchmarks.
- **v0.3** — an optional `[privacy]` extra with Presidio NER for names and
  addresses, plus a key-facts extraction block alongside summaries.
- **Out of scope**: proxy server mode, team policies, audit logs, and
  framework adapters — those belong in a future `promptgate-integrations`
  repo, not core.

## Credits

Secret-detection patterns are informed by [gitleaks](https://github.com/gitleaks/gitleaks)
(MIT) and [detect-secrets](https://github.com/Yelp/detect-secrets)
(Apache 2.0).

See [SECURITY.md](SECURITY.md) for the threat model and
[DECISIONS.md](DECISIONS.md) for the non-obvious calls made while building
this.
