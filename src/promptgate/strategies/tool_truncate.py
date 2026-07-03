"""Stub out stale tool-call results.

The differentiator: in agent workloads, stale tool output is often 60-70%
of context. A tool result belonging to an assistant turn older than the
most recent ``keep_recent_turns`` turns, and larger than
``stub_threshold_tokens``, is replaced with a shape-preserving stub so the
message structure (and ``tool_call_id``) stays intact.
"""

from __future__ import annotations

from typing import Optional

from promptgate import counters, formats


def apply(
    messages: list,
    keep_recent_turns: int = 1,
    stub_threshold_tokens: int = 120,
    counter: Optional[callable] = None,
) -> list:
    """Return a new message list with stale, large tool results stubbed out.

    Example:
        >>> messages = [
        ...     {"role": "user", "content": "run it"},
        ...     {"role": "assistant", "content": None, "tool_calls": []},
        ...     {"role": "tool", "tool_call_id": "1", "name": "search", "content": "x" * 1000},
        ...     {"role": "user", "content": "now what"},
        ... ]
        >>> result = apply(messages, keep_recent_turns=0)
        >>> "[tool result truncated" in result[2]["content"]
        True
    """
    if not messages:
        return []

    assistant_indices = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]

    if keep_recent_turns <= 0:
        cutoff = len(messages)
    elif len(assistant_indices) <= keep_recent_turns:
        cutoff = 0
    else:
        cutoff = assistant_indices[-keep_recent_turns]

    new_messages = []
    for index, message in enumerate(messages):
        if message.get("role") == "tool" and index < cutoff:
            text = formats.get_text(message)
            token_count = counters.count_text(text, counter)
            if token_count > stub_threshold_tokens:
                stub = dict(message)
                name = message.get("name") or "tool"
                stub["content"] = f"[tool result truncated: {name} returned ~{token_count:,} tokens]"
                new_messages.append(stub)
                continue
        new_messages.append(message)
    return new_messages
