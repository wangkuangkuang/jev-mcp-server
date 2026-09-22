"""Optional response cache (OFF by default).

Enable with ``JEVMCP_CACHE=1``. The cache key is the SHA-256 of the exact
question payload (model, question type, criteria/levels, question, context),
so an identical decision repeated within a run returns in ~0 ms at zero API
cost and ``usage`` is reported as ``{"cached": true}``. Keep it off when
decisions must stay fresh (e.g. live triage of changing data).
"""

from __future__ import annotations

import hashlib
import json
import os

from . import config


def _hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _path(payload: dict):
    return config.cache_dir() / f"{_hash(payload)}.json"


def lookup(payload: dict) -> dict | None:
    if not config.cache_enabled():
        return None
    try:
        return json.loads(_path(payload).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def store(payload: dict, answer: dict) -> None:
    if not config.cache_enabled():
        return
    directory = config.cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    tmp_path = directory / f"{_hash(payload)}.json.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(answer, handle, ensure_ascii=False)
        os.replace(tmp_path, _path(payload))
    except OSError:
        try:
            tmp_path.unlink()
        except OSError:
            pass
