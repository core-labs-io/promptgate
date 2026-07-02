"""Structural invariants for message lists.

``validate()`` and ``repair()`` are the last line of defense: every
compression strategy runs its output through both before returning
(Design Principle 3 — compression must never produce an invalid message
list).
"""

from __future__ import annotations

_VALID_ROLES = {"system", "user", "assistant", "tool"}


class StructureError(ValueError):
    """Raised by :func:`validate` when a message list violates an invariant."""


def _tool_call_ids(message: dict) -> list:
    if message.get("role") != "assistant":
        return []
    ids = []
    for call in message.get("tool_calls") or []:
        call_id = call.get("id") if isinstance(call, dict) else None
        if call_id:
            ids.append(call_id)
    return ids


def validate(messages: list) -> None:
    """Raise :class:`StructureError` if ``messages`` violates a structural invariant.

    Checks: every role is one of system/user/assistant/tool; at most one
    system message, and it must be first if present; every ``tool``
    message's ``tool_call_id`` matches a ``tool_calls`` entry from a
    preceding assistant message.

    Example:
        >>> validate([{"role": "user", "content": "hi"}])
    """
    system_count = 0
    for index, message in enumerate(messages):
        role = message.get("role")
        if role not in _VALID_ROLES:
            raise StructureError(f"invalid role {role!r} at index {index}")
        if role == "system":
            system_count += 1
            if index != 0:
                raise StructureError("system message must be the first message")
    if system_count > 1:
        raise StructureError("at most one system message is allowed")

    seen_tool_call_ids: set = set()
    for index, message in enumerate(messages):
        role = message.get("role")
        if role == "assistant":
            seen_tool_call_ids.update(_tool_call_ids(message))
        elif role == "tool":
            call_id = message.get("tool_call_id")
            if not call_id or call_id not in seen_tool_call_ids:
                raise StructureError(
                    f"tool message at index {index} has no matching preceding tool_call_id"
                )


def repair(messages: list) -> list:
    """Drop tool-result messages whose tool call was evicted from the list.

    A ``tool`` message survives only if some preceding assistant message
    in the (already-filtered) list still declares its ``tool_call_id`` in
    ``tool_calls``. Nothing else is removed or reordered.

    Example:
        >>> repair([{"role": "tool", "tool_call_id": "missing", "content": "x"}])
        []
    """
    repaired: list = []
    seen_tool_call_ids: set = set()
    for message in messages:
        role = message.get("role")
        if role == "assistant":
            seen_tool_call_ids.update(_tool_call_ids(message))
            repaired.append(message)
        elif role == "tool":
            call_id = message.get("tool_call_id")
            if call_id and call_id in seen_tool_call_ids:
                repaired.append(message)
            # else: orphaned tool result, drop it
        else:
            repaired.append(message)
    return repaired
