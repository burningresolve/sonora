"""Subtle ANSI color palette, auto-disabled when the terminal can't show them."""

import os
import sys

_RESET = "\x1b[0m"

# code -> escape sequence; kept minimal: no backgrounds, no bright colors.
_CODES = {
    "dim": "\x1b[2m",      # secondary text: indices, hints, channel names
    "bold": "\x1b[1m",     # track titles
    "success": "\x1b[32m", # confirmations, "playing" state
    "error": "\x1b[31m",   # error messages
    "warn": "\x1b[33m",    # "paused" state, deprecation-ish notes
    "accent": "\x1b[36m",  # playlist names, headers
    "active": "\x1b[32m",  # active playlist marker
}

_enabled = None


def configure(no_color: bool | None = None) -> bool:
    """Set color usage: True/False forces it, None auto-detects."""
    global _enabled
    if no_color is True:
        _enabled = False
    elif no_color is False:
        _enabled = True
    else:
        _enabled = _autodetect()
    return _enabled


def enabled() -> bool:
    if _enabled is None:
        configure()
    return _enabled


def _autodetect() -> bool:
    # NO_COLOR convention: present and non-empty disables colors everywhere.
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def paint(text: str, role: str) -> str:
    """Wrap text in the color for `role`; plain text when colors are off."""
    if not enabled():
        return text
    return f"{_CODES[role]}{text}{_RESET}"


def dim(text: str) -> str:
    return paint(text, "dim")


def bold(text: str) -> str:
    return paint(text, "bold")


def success(text: str) -> str:
    return paint(text, "success")


def error(text: str) -> str:
    return paint(text, "error")


def warn(text: str) -> str:
    return paint(text, "warn")


def accent(text: str) -> str:
    return paint(text, "accent")


def active(text: str) -> str:
    return paint(text, "active")
