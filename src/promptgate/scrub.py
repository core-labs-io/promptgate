"""Secret and PII detection/masking.

Three secret-detection layers, applied in a fixed order (Design Principle
per §5 of the spec): PEM blocks first (atomic, never half-masked), then
known-prefix patterns (near-zero false positives), then context-keyword
assignments. Entropy detection is a fourth, opt-in layer.

Secrets are one-way: a found secret's real value is never placed in the
returned ``pii_map`` and never appears in a warning or exception message
(Design Principle 5). PII (email, phone, etc.) is reversible via the
``pii_map`` returned to the caller.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from math import log2
from typing import Callable

from promptgate import formats
from promptgate._console import supports_unicode

_PLACEHOLDER_RE = re.compile(r"^\[\[([A-Z][A-Z0-9_]*)_(\d+)\]\]$")

DEFAULT_CATEGORIES = ("secrets", "email", "phone")


class SecretFound(Exception):
    """A secret was detected. Raised when ``on_secret="raise"``.

    Also used as the record type in :attr:`ScrubReport.secrets` — its
    message never contains the secret's value, only its category/label
    (Design Principle 7: report labels only, never values).

    Example:
        >>> "rotate" in str(SecretFound("AWS", "AWS Access Key"))
        True
    """

    def __init__(self, category: str, label: str):
        self.category = category
        self.label = label
        super().__init__(str(self))

    def __str__(self) -> str:
        sep = "—" if supports_unicode() else "-"
        return (
            f"Secret detected: {self.label} ({self.category}) {sep} "
            "rotate this credential, it may already be compromised."
        )


@dataclass
class ScrubReport:
    """Result of a scrub pass: what was found, never the values themselves."""

    secrets: list = field(default_factory=list)
    pii_counts: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------

PEM_PATTERN = re.compile(r"-----BEGIN ([A-Z0-9 ]+?)-----[\s\S]+?-----END \1-----")

# (label, category token, pattern). Order matters: sk-ant- before sk-.
SECRET_PREFIX_PATTERNS = [
    ("Anthropic API Key", "ANTHROPIC", re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}")),
    ("OpenAI API Key", "OPENAI", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("AWS Access Key", "AWS", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub Token", "GITHUB", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("Slack Token", "SLACK", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API Key", "GOOGLE", re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b")),
    ("Stripe API Key", "STRIPE", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
    ("JWT", "JWT", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
]

BEARER_PATTERN = re.compile(r"\bBearer\s+([A-Za-z0-9._~+/=-]{10,})\b")

CONTEXT_KEYWORD_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token)\s*([:=])\s*"
    r"(['\"]?)([^\s'\",;]+)\3"
)

CONNECTION_STRING_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^:/\s@]+):([^@\s]+)@")

ENTROPY_CANDIDATE_PATTERN = re.compile(r"[A-Za-z0-9+/=_-]{24,}")

# ---------------------------------------------------------------------------
# PII patterns
# ---------------------------------------------------------------------------

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_CANDIDATE_PATTERN = re.compile(r"\b\d(?:[ -]?\d){11,18}\b")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")
IP_PATTERN = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")

PII_CATEGORY_ORDER = ("email", "ssn", "credit_card", "phone", "ip")


def _is_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.match(value))


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: dict = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(text)
    return -sum((c / length) * log2(c / length) for c in counts.values())


class _ScrubState:
    def __init__(self, pii_map: dict | None):
        self.pii_map = dict(pii_map or {})
        self.value_to_placeholder = {v: k for k, v in self.pii_map.items()}
        self.pii_category_counters: dict = {}
        for placeholder in self.pii_map:
            match = _PLACEHOLDER_RE.match(placeholder)
            if match:
                category, index = match.group(1), int(match.group(2))
                self.pii_category_counters[category] = max(
                    self.pii_category_counters.get(category, 0), index
                )
        self.pii_counts: dict = {}
        self.secrets_found: list = []
        self.secret_value_to_placeholder: dict = {}
        self.secret_category_counters: dict = {}
        self.warnings: list = []


class Scrubber:
    """Detects and masks secrets and PII in message text.

    Example:
        >>> scrubber = Scrubber(categories=["email"])
        >>> text, report, pii_map = scrubber.scrub_text("contact bob@example.com")
        >>> report.pii_counts
        {'EMAIL': 1}
    """

    def __init__(
        self,
        categories=DEFAULT_CATEGORIES,
        on_secret: str = "warn",
        entropy_threshold: float | None = None,
        warn_callback: Callable[[str], None] | None = None,
    ):
        if on_secret not in ("mask", "warn", "raise"):
            raise ValueError(f"on_secret must be 'mask', 'warn', or 'raise', got {on_secret!r}")
        self.categories = set(categories)
        self.on_secret = on_secret
        self.entropy_threshold = entropy_threshold
        self.warn_callback = warn_callback

    def scrub_text(self, text: str, pii_map: dict | None = None):
        """Scrub a single string. Returns ``(new_text, ScrubReport, pii_map)``."""
        state = _ScrubState(pii_map)
        new_text = self._scrub(text, state)
        report = ScrubReport(
            secrets=state.secrets_found, pii_counts=state.pii_counts, warnings=state.warnings
        )
        return new_text, report, state.pii_map

    def scrub_messages(self, messages: list, pii_map: dict | None = None):
        """Scrub a list of messages. Returns ``(new_messages, ScrubReport, pii_map)``.

        Example:
            >>> scrubber = Scrubber(categories=["email"])
            >>> msgs, report, pii_map = scrubber.scrub_messages(
            ...     [{"role": "user", "content": "email me at bob@example.com"}]
            ... )
            >>> "[[EMAIL_1]]" in msgs[0]["content"]
            True
        """
        state = _ScrubState(pii_map)
        new_messages = [formats.map_text(m, lambda t: self._scrub(t, state)) for m in messages]
        report = ScrubReport(
            secrets=state.secrets_found, pii_counts=state.pii_counts, warnings=state.warnings
        )
        return new_messages, report, state.pii_map

    # -- internal -----------------------------------------------------

    def _scrub(self, text: str, state: _ScrubState) -> str:
        if not text:
            return text
        if "secrets" in self.categories:
            text = self._scrub_secrets(text, state)
        text = self._scrub_pii(text, state)
        return text

    def _emit_warning(self, found: SecretFound) -> None:
        sep = "—" if supports_unicode() else "-"
        message = (
            f"[promptgate] Potential secret detected: {found.label} {sep} "
            "treat as compromised and rotate this credential immediately."
        )
        if self.warn_callback is not None:
            self.warn_callback(message)
        else:
            print(message, file=sys.stderr)

    def _secret_placeholder(
        self, state: _ScrubState, category_token: str, label: str, value: str
    ) -> str:
        if self.on_secret == "raise":
            raise SecretFound(category_token, label)
        if value in state.secret_value_to_placeholder:
            return state.secret_value_to_placeholder[value]
        state.secret_category_counters[category_token] = (
            state.secret_category_counters.get(category_token, 0) + 1
        )
        index = state.secret_category_counters[category_token]
        placeholder = f"[[SECRET_{category_token}_{index}]]"
        state.secret_value_to_placeholder[value] = placeholder
        found = SecretFound(category_token, label)
        state.secrets_found.append(found)
        if self.on_secret == "warn":
            self._emit_warning(found)
        return placeholder

    def _pii_placeholder(self, state: _ScrubState, category_token: str, value: str) -> str:
        if value in state.value_to_placeholder:
            return state.value_to_placeholder[value]
        state.pii_category_counters[category_token] = (
            state.pii_category_counters.get(category_token, 0) + 1
        )
        index = state.pii_category_counters[category_token]
        placeholder = f"[[{category_token}_{index}]]"
        state.value_to_placeholder[value] = placeholder
        state.pii_map[placeholder] = value
        state.pii_counts[category_token] = state.pii_counts.get(category_token, 0) + 1
        return placeholder

    def _scrub_secrets(self, text: str, state: _ScrubState) -> str:
        def pem_repl(m):
            header = m.group(1).strip()
            label = f"PEM Private Key Block ({header})" if header else "PEM Private Key Block"
            return self._secret_placeholder(state, "PEM", label, m.group(0))

        text = PEM_PATTERN.sub(pem_repl, text)
        text = self._mask_prefix_patterns(text, state)
        text = self._mask_context_keywords(text, state)
        text = self._mask_entropy(text, state)
        return text

    def _mask_prefix_patterns(self, text: str, state: _ScrubState) -> str:
        for label, category_token, pattern in SECRET_PREFIX_PATTERNS:

            def repl(m, label=label, category_token=category_token):
                return self._secret_placeholder(state, category_token, label, m.group(0))

            text = pattern.sub(repl, text)

        def bearer_repl(m):
            placeholder = self._secret_placeholder(state, "BEARER", "Bearer Token", m.group(1))
            return f"Bearer {placeholder}"

        text = BEARER_PATTERN.sub(bearer_repl, text)
        return text

    def _mask_context_keywords(self, text: str, state: _ScrubState) -> str:
        def keyword_repl(m):
            key, sep, quote, value = m.group(1), m.group(2), m.group(3), m.group(4)
            if _is_placeholder(value):
                return m.group(0)
            placeholder = self._secret_placeholder(state, "CREDENTIAL", f"{key} assignment", value)
            return f"{key}{sep}{quote}{placeholder}{quote}"

        text = CONTEXT_KEYWORD_PATTERN.sub(keyword_repl, text)

        def conn_repl(m):
            prefix, password = m.group(1), m.group(2)
            if _is_placeholder(password):
                return m.group(0)
            placeholder = self._secret_placeholder(
                state, "CREDENTIAL", "connection string credential", password
            )
            return f"{prefix}:{placeholder}@"

        text = CONNECTION_STRING_PATTERN.sub(conn_repl, text)
        return text

    def _mask_entropy(self, text: str, state: _ScrubState) -> str:
        if self.entropy_threshold is None:
            return text

        def repl(m):
            token = m.group(0)
            if _is_placeholder(token):
                return token
            if _shannon_entropy(token) < self.entropy_threshold:
                return token
            return self._secret_placeholder(state, "HIGH_ENTROPY", "high-entropy string", token)

        return ENTROPY_CANDIDATE_PATTERN.sub(repl, text)

    def _scrub_pii(self, text: str, state: _ScrubState) -> str:
        for category in PII_CATEGORY_ORDER:
            if category not in self.categories:
                continue
            if category == "credit_card":
                text = self._mask_credit_card(text, state)
            else:
                token, pattern = {
                    "email": ("EMAIL", EMAIL_PATTERN),
                    "ssn": ("SSN", SSN_PATTERN),
                    "phone": ("PHONE", PHONE_PATTERN),
                    "ip": ("IP", IP_PATTERN),
                }[category]
                text = self._mask_simple(text, state, token, pattern)
        return text

    def _mask_simple(self, text: str, state: _ScrubState, token: str, pattern: re.Pattern) -> str:
        def repl(m):
            value = m.group(0)
            if _is_placeholder(value):
                return value
            return self._pii_placeholder(state, token, value)

        return pattern.sub(repl, text)

    def _mask_credit_card(self, text: str, state: _ScrubState) -> str:
        def repl(m):
            value = m.group(0)
            if _is_placeholder(value):
                return value
            digits = re.sub(r"[ -]", "", value)
            if not (13 <= len(digits) <= 16):
                return value
            return self._pii_placeholder(state, "CREDIT_CARD", value)

        return CREDIT_CARD_CANDIDATE_PATTERN.sub(repl, text)
