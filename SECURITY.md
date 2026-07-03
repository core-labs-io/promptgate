# Security

## Threat model

promptgate protects against **accidental transmission of secrets and PII to
a third-party LLM API** as part of normal conversation history. It runs
entirely in your process, on your machine, before your messages leave for
an API call.

### In scope

- Common credential formats (API keys, tokens, private keys, connection
  strings) accidentally left in message history — pasted logs, config
  dumps, copy-pasted shell output, etc.
- Common PII formats (email, NA phone numbers, credit card numbers, SSNs,
  IP addresses) in the same situations.
- Never leaking a detected secret's *value* back out through promptgate
  itself — not in the compressed output, not in a warning, not in an
  exception, not in a log line.
- Never corrupting message structure in a way that could cause a client
  library or API to misbehave (orphaned tool results, dropped system
  prompts, invalid role sequences).

### Explicitly out of scope

- **PII the regexes miss.** Phase 1 detection is regex-only — no NER, no
  fuzzy matching. Names, physical addresses, and PII in languages or
  formats the patterns don't cover will not be caught. Don't treat a clean
  `explain()` report as a compliance guarantee.
- **Secrets or PII embedded in images or other non-text content.**
  Multimodal parts are passed through untouched and unscanned.
- **A malicious model or malicious tool output trying to exfiltrate data
  *out* of the conversation** (e.g. a compromised tool response trying to
  trick a downstream system). promptgate scrubs what goes *into* the
  request; it is not a general data-loss-prevention or sandboxing system.
- **An attacker with access to your machine or process.** promptgate holds
  the `pii_map` (and, transiently, any secret it detects) in your process
  memory. If your process or machine is already compromised, promptgate
  provides no additional protection.
- **Guaranteeing zero false negatives.** Entropy-based detection is
  opt-in specifically because heuristic secret detection always trades off
  false positives against false negatives; defaults favor a low
  false-positive rate over perfect recall.

Honest scoping builds more trust than overclaiming — if you find a gap
between this document and actual behavior, that's a bug; please report it.

## Reporting a vulnerability

Please do not open a public GitHub issue for a security report. Instead,
email the maintainers with details and, if possible, a minimal
reproduction. We'll acknowledge within a reasonable timeframe and work
with you on disclosure.
