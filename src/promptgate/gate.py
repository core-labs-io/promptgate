"""The public entry point: ``Gate`` orchestrates scrub -> compress -> validate.

Pipeline order (fixed):

    messages -> scrub secrets -> mask PII -> truncate stale tool outputs
              -> fit window to budget -> validated output
                      ^ PII mapping stays in the caller's process ^
"""

from __future__ import annotations

import re

from promptgate import counters, safety
from promptgate.report import ExplainReport
from promptgate.scrub import Scrubber
from promptgate.strategies import tool_truncate, window

_COMPRESS_MODES = ("window", "truncate_tools", "hybrid")

_PLACEHOLDER_TOKEN_RE = re.compile(
    r"\[\[\s*([A-Z][A-Z0-9_]*_\d+)\s*\]\]"
    r"|\[\s*([A-Z][A-Z0-9_]*_\d+)\s*\]"
    r"|\b([A-Z][A-Z0-9_]*_\d+)\b"
)


class Gate:
    """A stateless prompt firewall: compress conversation history, scrub secrets/PII.

    Example:
        >>> gate = Gate(budget=8000)
        >>> messages = [{"role": "user", "content": "email me at bob@example.com"}]
        >>> safe_messages, pii_map = gate.prepare(messages)
        >>> "[[EMAIL_1]]" in safe_messages[0]["content"]
        True
    """

    def __init__(
        self,
        budget: int | None = None,
        compress: str = "hybrid",
        scrub=("secrets", "email", "phone"),
        on_secret: str = "warn",
        keep_last: int = 6,
        pin=("system",),
        counter=None,
    ):
        if compress not in _COMPRESS_MODES:
            raise ValueError(f"compress must be one of {_COMPRESS_MODES}, got {compress!r}")
        self.budget = budget
        self.compress = compress
        self.scrub_categories = tuple(scrub)
        self.on_secret = on_secret
        self.keep_last = keep_last
        self.pin = tuple(pin)
        self.counter = counter
        self._scrubber = Scrubber(categories=self.scrub_categories, on_secret=on_secret)

    def prepare(self, messages: list, pii_map: dict | None = None):
        """Scrub secrets/PII and fit ``messages`` to the configured budget.

        Returns ``(safe_messages, pii_map)``. Pass a prior ``pii_map`` back
        in on the next turn to keep placeholders consistent across a
        conversation (Design Principle 1: state lives with the caller).

        Example:
            >>> gate = Gate()
            >>> safe, pii_map = gate.prepare([{"role": "user", "content": "hi"}])
            >>> safe
            [{'role': 'user', 'content': 'hi'}]
        """
        messages = list(messages)
        scrubbed, _scrub_report, new_pii_map = self._scrubber.scrub_messages(messages, pii_map)
        compressed, _warnings = self._compress(scrubbed)
        compressed = safety.repair(compressed)
        safety.validate(compressed)
        return compressed, new_pii_map

    def explain(self, messages: list) -> ExplainReport:
        """Dry-run: report what prepare() would do, without mutating anything.

        Example:
            >>> gate = Gate(budget=8000)
            >>> report = gate.explain([{"role": "user", "content": "hi"}])
            >>> report.structure_valid
            True
        """
        tokens_before = counters.count_messages(messages, self.counter)

        # explain() never raises or leaves warnings on stderr, regardless of
        # the configured on_secret mode -- it only reports what was found.
        report_scrubber = Scrubber(categories=self.scrub_categories, on_secret="mask")
        scrubbed, scrub_report, _pii_map = report_scrubber.scrub_messages(list(messages))

        compressed, warnings = self._compress(scrubbed)
        compressed = safety.repair(compressed)

        try:
            safety.validate(compressed)
            structure_valid = True
        except safety.StructureError:
            structure_valid = False

        tokens_after = counters.count_messages(compressed, self.counter)

        return ExplainReport(
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            secrets=scrub_report.secrets,
            pii_counts=scrub_report.pii_counts,
            structure_valid=structure_valid,
            warnings=warnings,
        )

    def rehydrate(self, text: str, pii_map: dict) -> str:
        """Restore PII placeholders in ``text`` using ``pii_map``.

        Secrets are never restored -- they were never placed in ``pii_map``
        (Design Principle 5). Tolerates light model mangling of the
        placeholder format (extra spaces, single brackets, missing brackets).

        Example:
            >>> gate = Gate()
            >>> gate.rehydrate("contact [[ EMAIL_1 ]]", {"[[EMAIL_1]]": "bob@example.com"})
            'contact bob@example.com'
        """
        if not pii_map or not text:
            return text

        lookup = {}
        for placeholder, value in pii_map.items():
            match = re.match(r"^\[\[([A-Z][A-Z0-9_]*_\d+)\]\]$", placeholder)
            if match:
                lookup[match.group(1)] = value

        def repl(m):
            token = m.group(1) or m.group(2) or m.group(3)
            return lookup.get(token, m.group(0))

        return _PLACEHOLDER_TOKEN_RE.sub(repl, text)

    # -- internal -----------------------------------------------------

    def _compress(self, messages: list):
        if self.budget is None:
            return messages, []
        if self.compress == "truncate_tools":
            return tool_truncate.apply(messages, counter=self.counter), []
        if self.compress == "window":
            return window.apply(
                messages, self.budget, keep_last=self.keep_last, pin=self.pin, counter=self.counter
            )
        # hybrid: tool_truncate first, then window only if still over budget
        truncated = tool_truncate.apply(messages, counter=self.counter)
        total = counters.count_messages(truncated, self.counter)
        if total <= self.budget:
            return truncated, []
        return window.apply(
            truncated, self.budget, keep_last=self.keep_last, pin=self.pin, counter=self.counter
        )
