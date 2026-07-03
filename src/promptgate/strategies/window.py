"""Sliding window compression with pinning.

Keeps pinned messages and the last ``keep_last`` messages verbatim, then
walks backward from there adding older messages until the budget runs out.
Never evicts the most recent user message. Runs :func:`safety.repair`
after eviction so orphaned tool results never survive, and never returns
an empty list for a non-empty input.
"""

from __future__ import annotations

from promptgate import counters, safety


def apply(
    messages: list,
    budget: int | None,
    keep_last: int = 6,
    pin=("system",),
    counter=None,
):
    """Return ``(new_messages, warnings)`` fit to ``budget``.

    Example:
        >>> messages = [{"role": "user", "content": "hi"}]
        >>> result, warnings = apply(messages, budget=1000)
        >>> result == messages
        True
    """
    if not messages:
        return [], []
    if budget is None:
        return list(messages), []

    total = counters.count_messages(messages, counter)
    if total <= budget:
        return messages, []

    n = len(messages)
    pin_roles = {p for p in pin if isinstance(p, str)}
    pin_indices = {p for p in pin if isinstance(p, int)}

    forced = {i for i, m in enumerate(messages) if m.get("role") in pin_roles}
    forced |= {i for i in pin_indices if 0 <= i < n}

    tail_start = max(0, n - keep_last) if keep_last > 0 else n
    forced |= set(range(tail_start, n))

    most_recent_user_index = None
    for i in range(n - 1, -1, -1):
        if messages[i].get("role") == "user":
            most_recent_user_index = i
            break
    if most_recent_user_index is not None:
        forced.add(most_recent_user_index)

    kept = set(forced)
    used = sum(counters.count_message(messages[i], counter) for i in kept)

    for i in range(tail_start - 1, -1, -1):
        if i in kept:
            continue
        cost = counters.count_message(messages[i], counter)
        if used + cost <= budget:
            kept.add(i)
            used += cost
        else:
            break

    warnings = []
    if not kept:
        kept = {n - 1}
        warnings.append(
            f"message at index {n - 1} was force-kept to avoid returning an empty result"
        )

    result = [messages[i] for i in sorted(kept)]
    result = safety.repair(result)

    final_total = counters.count_messages(result, counter)
    if final_total > budget:
        warnings.append(
            f"kept messages total {final_total} tokens, exceeding budget {budget} "
            "because pinned/tail/most-recent-user messages cannot be evicted"
        )

    return result, warnings
