"""Thin HTTP client for the TypeSafe System One API."""

from __future__ import annotations

import time

import httpx

from . import __version__, config

RETRY_STATUS = {429, 503, 529}
USER_AGENT = f"jev-mcp-server/{__version__} (+https://github.com/wangkuangkuang/jev-mcp-server)"
MISSING_KEY_MESSAGE = (
    "No TypeSafe API key found. Either set TYPESAFE_API_KEY in the server environment, "
    "or call the `setup` tool once with your key. Get a key at https://console.typesafe.ai/settings/keys"
)

_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(http2=True, timeout=25, headers={"User-Agent": USER_AGENT})
    return _client


def ask(questions: dict) -> dict:
    """Send one or more typed questions to System One and return the full response."""
    key = config.resolve_key()
    if not key:
        raise RuntimeError(MISSING_KEY_MESSAGE)
    body = {"model": config.model_name(), "state": {}, "questions": questions}
    for attempt in range(3):
        try:
            response = _http().post(config.base_url(), json=body, headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError as error:
            raise RuntimeError(f"TypeSafe connection failed ({type(error).__name__}); no decision made.") from None
        if response.status_code in RETRY_STATUS and attempt < 2:
            time.sleep(0.5 * 2**attempt)
            continue
        if response.is_error:
            raise RuntimeError(f"TypeSafe returned HTTP {response.status_code}: {response.text[:200]}")
        return response.json()
    raise RuntimeError("TypeSafe unavailable after retries; no decision made.")


def verify_key(key: str) -> dict:
    """Prove a key works with a cheap live call before storing it."""
    body = {
        "model": config.model_name(),
        "state": {},
        "questions": {
            "handshake": {"type": "noul", "instructions": {"question": "Is the sky blue?", "context": "key verification"}}
        },
    }
    try:
        response = _http().post(config.base_url(), json=body, headers={"Authorization": f"Bearer {key.strip()}"})
    except httpx.HTTPError as error:
        raise RuntimeError(f"TypeSafe connection failed ({type(error).__name__}); key NOT stored.") from None
    if response.is_error:
        raise RuntimeError(f"Key rejected (HTTP {response.status_code}); key NOT stored.")
    return response.json()
