"""Shared terminal color and formatting utilities for RSI framework.

Windows-safe: detects cp1252/ASCII terminals and falls back to ASCII
symbols. No Unicode crashes on Windows cmd/PowerShell.
"""

import sys


def _supports_unicode() -> bool:
    """Check if the terminal supports Unicode output."""
    try:
        encoding = sys.stdout.encoding or ""
        if encoding.lower() in ("utf-8", "utf8"):
            return True
        # Check if we can encode a test character
        "\u2713".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError, AttributeError):
        return False


_UNICODE = _supports_unicode()

# Safe symbols — Unicode with ASCII fallback
CHECK = "\u2713" if _UNICODE else "+"  # ✓ or +
CROSS = "\u2717" if _UNICODE else "x"  # ✗ or x
WARN = "\u26a0" if _UNICODE else "!"  # ⚠ or !
ARROW = "\u2192" if _UNICODE else "->"  # → or ->
BLOCK = "#" if not _UNICODE else "\u2588"  # █ or #
EMPTY = "." if not _UNICODE else "\u2591"  # ░ or .


def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def cyan(msg: str) -> str:
    return f"\033[96m{msg}\033[0m"


def bold(msg: str) -> str:
    return f"\033[1m{msg}\033[0m"


def dim(msg: str) -> str:
    return f"\033[2m{msg}\033[0m"


def header(title: str, width: int = 60) -> str:
    return f"{'=' * width}\n{title}\n{'=' * width}"


def bar(value: int, max_width: int = 20) -> str:
    clamped = max(0, min(value, max_width))
    return BLOCK * clamped + EMPTY * (max_width - clamped)
