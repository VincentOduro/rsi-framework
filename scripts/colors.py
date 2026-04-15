"""Shared terminal color and formatting utilities for RSI framework."""


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


def bar(value: int, max_width: int = 20, filled: str = "\u2588", empty: str = "\u2591") -> str:
    clamped = max(0, min(value, max_width))
    return filled * clamped + empty * (max_width - clamped)
