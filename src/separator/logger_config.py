"""
logger_config.py — Centralised loguru configuration for the separator.

Configures custom log levels with distinct colors and icons, and sets
up a single stderr sink. All separator modules import this to get
consistent logging.
"""

import sys

from loguru import logger

# ---------------------------------------------------------------------------
# Remove default handler ONCE and add the separator sink.
# This module is imported first by separator.py, so later imports
# just use `from loguru import logger` without calling remove/add.
# ---------------------------------------------------------------------------

# Custom log levels for separator operations
CUSTOM_LEVELS = [
    {"name": "CHUNK",     "no": 25, "color": "<blue><bold>",    "icon": "📦"},
    {"name": "FOUND",     "no": 25, "color": "<yellow><bold>",  "icon": "🔍"},
    {"name": "OPENED",    "no": 25, "color": "<cyan><bold>",    "icon": "📂"},
    {"name": "CONTINUED", "no": 25, "color": "<magenta><bold>", "icon": "🔗"},
    {"name": "RESOLVED",  "no": 25, "color": "<green><bold>",   "icon": "✅"},
    {"name": "TREE",      "no": 25, "color": "<white><bold>",   "icon": "🌳"},
    {"name": "AGENT",     "no": 25, "color": "<light-blue><bold>", "icon": "🤖"},
    {"name": "VERIFY",    "no": 25, "color": "<light-green><bold>", "icon": "🔎"},
    {"name": "RETRY",     "no": 25, "color": "<light-red><bold>",  "icon": "🔄"},
    {"name": "DESCRIBE",  "no": 25, "color": "<light-magenta><bold>", "icon": "📝"},
]

_configured = False


def configure_separator_logger() -> None:
    """
    Set up the separator logger. Safe to call multiple times — only
    configures once.
    """
    global _configured
    if _configured:
        return
    _configured = True

    logger.remove()
    logger.add(
        sys.stderr,
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <10}</level> | "
            "<level>{message}</level>"
        ),
        level="DEBUG",
    )

    for lvl in CUSTOM_LEVELS:
        try:
            logger.level(lvl["name"], no=lvl["no"], color=lvl["color"], icon=lvl["icon"])
        except TypeError:
            pass  # Level already exists
