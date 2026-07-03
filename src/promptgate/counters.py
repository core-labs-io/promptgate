"""Token counting.

Three ways to count, in priority order: a caller-supplied ``counter``
callable, the optional ``tiktoken`` extra (``pip install promptgate[openai]``),
or a stdlib-only heuristic. The heuristic is deliberately pessimistic — it
rounds up — because promptgate must never let a budget silently overflow
when it can't count exactly (Design Principle 6).
"""

from __future__ import annotations

import math
from typing import Callable

from promptgate.formats import get_text

Counter = Callable[[str], int]

# Fixed per-message overhead for role/structure framing (name, separators,
# etc). Chat APIs add a handful of hidden tokens per message beyond the raw
# text; this constant approximates that without requiring a real tokenizer.
MESSAGE_OVERHEAD_TOKENS = 4

# Conservative chars-per-token ratio for the heuristic fallback. Real
# tokenizers average ~4 chars/token for English text; dividing by 3
# overestimates on purpose so we never undercount a budget.
_HEURISTIC_CHARS_PER_TOKEN = 3

_tiktoken_encoding = None
_tiktoken_unavailable = False


def _get_tiktoken_encoding():
    global _tiktoken_encoding, _tiktoken_unavailable
    if _tiktoken_unavailable:
        return None
    if _tiktoken_encoding is not None:
        return _tiktoken_encoding
    try:
        import tiktoken
    except ImportError:
        _tiktoken_unavailable = True
        return None
    _tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
    return _tiktoken_encoding


def _heuristic_count(text: str) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / _HEURISTIC_CHARS_PER_TOKEN)


def count_text(text: str, counter: Counter | None = None) -> int:
    """Count tokens in a string.

    Uses ``counter`` if given, else ``tiktoken`` if installed, else a
    pessimistic stdlib heuristic that rounds up.

    Example:
        >>> count_text("hello world") > 0
        True
    """
    if not text:
        return 0
    if counter is not None:
        return counter(text)
    encoding = _get_tiktoken_encoding()
    if encoding is not None:
        return len(encoding.encode(text, disallowed_special=()))
    return _heuristic_count(text)


def count_message(message: dict, counter: Counter | None = None) -> int:
    """Count tokens in a single message, including a per-message overhead.

    Also counts tool-call names/arguments, since those cost tokens too.

    Example:
        >>> count_message({"role": "user", "content": "hello"}) > 0
        True
    """
    total = MESSAGE_OVERHEAD_TOKENS
    total += count_text(get_text(message), counter)

    name = message.get("name")
    if name:
        total += count_text(str(name), counter)

    tool_calls = message.get("tool_calls")
    if tool_calls:
        for call in tool_calls:
            function = call.get("function", {}) if isinstance(call, dict) else {}
            total += count_text(str(function.get("name", "")), counter)
            total += count_text(str(function.get("arguments", "")), counter)

    return total


def count_messages(messages: list, counter: Counter | None = None) -> int:
    """Count total tokens across a list of messages.

    Example:
        >>> count_messages([{"role": "user", "content": "hi"}]) > 0
        True
    """
    return sum(count_message(message, counter) for message in messages)
