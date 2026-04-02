from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from satmi_agent.config import settings

logger = logging.getLogger("satmi_agent.prompt_loader")

DEFAULT_SYSTEM_PROMPT = (
    "You are the SATMI Intelligent Shopping & Support Expert. "
    "Resolve user queries using catalog data and policy context. "
    "Use Markdown tables for comparisons. Use bold for product names and prices. "
    "Always provide a Next Step. Do not process cancellations in chat; "
    "redirect to https://accounts.satmi.in. Do not add new facts. "
    "Preserve order IDs, statuses, and key actions exactly."
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_prompt_path() -> Path:
    configured = Path(settings.system_prompt_path)
    if configured.is_absolute():
        return configured
    return _project_root() / configured


@lru_cache(maxsize=1)
def get_system_prompt() -> str:
    """Load the system prompt from the configured file path.

    Falls back to a hardcoded default if the file is missing or unreadable.
    The result is cached after the first call for the lifetime of the process.
    """
    path = _resolve_prompt_path()
    if not path.exists():
        logger.warning("System prompt file not found at %s, using default.", path)
        return DEFAULT_SYSTEM_PROMPT

    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            logger.warning("System prompt file at %s is empty, using default.", path)
            return DEFAULT_SYSTEM_PROMPT
        logger.info("Loaded system prompt from %s (%d chars).", path, len(content))
        return content
    except Exception as exc:
        logger.warning("Failed to read system prompt from %s: %s. Using default.", path, exc)
        return DEFAULT_SYSTEM_PROMPT


def reload_system_prompt() -> str:
    """Clear the cache and reload the system prompt from disk.

    Useful for tests or hot-reload scenarios.
    """
    get_system_prompt.cache_clear()
    return get_system_prompt()
