"""The unified explain() report — both pillars (Save + Protect) in one output."""

from __future__ import annotations

from dataclasses import dataclass, field

from promptgate._console import supports_unicode

SECRET_LABELS = {
    "ANTHROPIC": ("Anthropic key", "Anthropic keys"),
    "OPENAI": ("OpenAI key", "OpenAI keys"),
    "AWS": ("AWS key", "AWS keys"),
    "GITHUB": ("GitHub token", "GitHub tokens"),
    "SLACK": ("Slack token", "Slack tokens"),
    "GOOGLE": ("Google key", "Google keys"),
    "STRIPE": ("Stripe key", "Stripe keys"),
    "JWT": ("JWT", "JWTs"),
    "BEARER": ("Bearer token", "Bearer tokens"),
    "PEM": ("private key", "private keys"),
    "CREDENTIAL": ("credential", "credentials"),
    "HIGH_ENTROPY": ("high-entropy secret", "high-entropy secrets"),
}

PII_LABELS = {
    "EMAIL": ("email", "emails"),
    "PHONE": ("phone", "phones"),
    "SSN": ("SSN", "SSNs"),
    "CREDIT_CARD": ("credit card", "credit cards"),
    "IP": ("IP address", "IP addresses"),
}


def _pluralize(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


@dataclass
class ExplainReport:
    """Structured result of :meth:`Gate.explain`.

    Example:
        >>> report = ExplainReport(
        ...     tokens_before=100, tokens_after=50, secrets=[],
        ...     pii_counts={}, structure_valid=True,
        ... )
        >>> report.percent_saved
        50.0
    """

    tokens_before: int
    tokens_after: int
    secrets: list = field(default_factory=list)
    pii_counts: dict = field(default_factory=dict)
    structure_valid: bool = True
    warnings: list = field(default_factory=list)

    @property
    def tokens_saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def percent_saved(self) -> float:
        if self.tokens_before <= 0:
            return 0.0
        return (self.tokens_saved / self.tokens_before) * 100

    def _secrets_summary(self) -> str:
        if not self.secrets:
            return "none found"
        counts: dict = {}
        for secret in self.secrets:
            counts[secret.category] = counts.get(secret.category, 0) + 1
        parts = []
        for category, count in counts.items():
            singular, plural = SECRET_LABELS.get(category, (category.lower(), category.lower()))
            parts.append(_pluralize(count, singular, plural))
        return ", ".join(parts) + " BLOCKED (one-way)"

    def _pii_summary(self) -> str:
        if not self.pii_counts:
            return "none found"
        parts = []
        for category, count in self.pii_counts.items():
            singular, plural = PII_LABELS.get(category, (category.lower(), category.lower()))
            parts.append(_pluralize(count, singular, plural))
        return ", ".join(parts) + " masked (reversible)"

    def __str__(self) -> str:
        if supports_unicode():
            divider, arrow, ok_mark, fail_mark = "─", "→", "✓", "✗"
        else:
            divider, arrow, ok_mark, fail_mark = "-", "->", "[OK]", "[FAIL]"

        lines = ["promptgate report", divider * 17]
        tokens_line = f"Tokens:  {self.tokens_before:,} {arrow} {self.tokens_after:,}"
        if self.tokens_before > 0:
            tokens_line += f"  ({self.percent_saved:.0f}% saved)"
        lines.append(tokens_line)
        lines.append(f"Secrets: {self._secrets_summary()}")
        lines.append(f"PII:     {self._pii_summary()}")
        structure_mark = f"valid {ok_mark}" if self.structure_valid else f"INVALID {fail_mark}"
        lines.append(f"Structure: {structure_mark}")
        if self.warnings:
            lines.append("Warnings:")
            for warning in self.warnings:
                lines.append(f"  - {warning}")
        return "\n".join(lines)
