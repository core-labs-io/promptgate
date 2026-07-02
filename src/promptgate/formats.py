"""Message-format helpers.

Isolates all knowledge of the OpenAI-style message dict shape
(``{"role": ..., "content": str | list-of-parts, ...}``) so that future
Anthropic/Gemini adapters only need to add a module here, not touch the
rest of the pipeline.

Content can be a plain string or a list of parts (``{"type": "text", ...}``,
``{"type": "image_url", ...}``, etc). Non-text parts are treated as opaque
and passed through untouched everywhere in promptgate — see the multimodal
passthrough limitation in the README.
"""

from __future__ import annotations

from typing import Any, Callable

Message = dict


def get_text(message: Message) -> str:
    """Return the concatenated text content of a message.

    Non-text parts (e.g. images) are skipped. Missing/``None`` content
    returns an empty string.

    Example:
        >>> get_text({"role": "user", "content": "hello"})
        'hello'
        >>> get_text({"role": "user", "content": [{"type": "text", "text": "hi"}]})
        'hi'
    """
    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return ""


def has_multimodal(message: Message) -> bool:
    """Return True if a message contains any non-text content part.

    Example:
        >>> has_multimodal({"role": "user", "content": [{"type": "image_url", "image_url": {}}]})
        True
    """
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(part, dict) and part.get("type") != "text" for part in content)


def map_text(message: Message, fn: Callable[[str], str]) -> Message:
    """Return a new message with ``fn`` applied to its text content.

    Non-text parts are left untouched. The input message is not mutated.

    Example:
        >>> map_text({"role": "user", "content": "hi"}, str.upper)
        {'role': 'user', 'content': 'HI'}
    """
    content = message.get("content")
    new_message = dict(message)
    if content is None:
        return new_message
    if isinstance(content, str):
        new_message["content"] = fn(content)
        return new_message
    if isinstance(content, list):
        new_parts: list[Any] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                new_part = dict(part)
                new_part["text"] = fn(part.get("text", ""))
                new_parts.append(new_part)
            elif isinstance(part, str):
                new_parts.append(fn(part))
            else:
                new_parts.append(part)
        new_message["content"] = new_parts
        return new_message
    return new_message
