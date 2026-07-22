"""Console-safe text helpers.

Some terminals (notably the default Windows console, cp1252/cp437) can't
encode box-drawing lines, arrows, or checkmarks. Rather than crash on
print(), callers pick an ASCII-safe fallback when the current output
streams can't represent the preferred glyphs.
"""

from __future__ import annotations

import sys

_PROBE_CHARS = "─→✓✗—"


def supports_unicode() -> bool:
    """Return True if stdout and stderr can both encode promptgate's report glyphs.

    Example:
        >>> isinstance(supports_unicode(), bool)
        True
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, "encoding", None) or "utf-8"
        try:
            _PROBE_CHARS.encode(encoding)
        except (UnicodeEncodeError, LookupError):
            return False
    return True
