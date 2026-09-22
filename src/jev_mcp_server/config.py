"""Key and runtime configuration resolution.

Precedence for the TypeSafe API key:
1. ``TYPESAFE_API_KEY`` environment variable
2. key file written by the ``setup`` tool (``~/.config/jev-mcp/key`` by default)

All directories can be relocated via environment variables, mainly for tests.
"""

from __future__ import annotations

import os
from pathlib import Path

from ._fsutil import atomic_write_text, read_text, restrict

CONFIG_DIR_ENV = "JEVMCP_CONFIG_DIR"
CACHE_DIR_ENV = "JEVMCP_CACHE_DIR"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "jev-mcp"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "jev-mcp"
TRUTHY = {"1", "true", "yes", "on"}


def config_dir() -> Path:
    return Path(os.environ.get(CONFIG_DIR_ENV, str(DEFAULT_CONFIG_DIR)))


def key_file() -> Path:
    return config_dir() / "key"


def resolve_key() -> str | None:
    env_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        value = read_text(key_file()).strip()
    except OSError:
        return None
    return value or None


def save_key(api_key: str) -> Path:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    restrict(directory, 0o700)
    target = key_file()
    atomic_write_text(target, api_key.strip() + "\n")
    restrict(target, 0o600)
    return target


def base_url() -> str:
    return os.environ.get("JEVMCP_BASE_URL", "https://api.typesafe.ai/v1/systemone").rstrip("/")


def model_name() -> str:
    return os.environ.get("JEVMCP_MODEL", "jev-latest")


def cache_enabled() -> bool:
    return os.environ.get("JEVMCP_CACHE", "").strip().lower() in TRUTHY


def cache_dir() -> Path:
    return Path(os.environ.get(CACHE_DIR_ENV, str(DEFAULT_CACHE_DIR)))
