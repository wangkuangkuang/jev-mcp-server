# Changelog

## 0.1.0 — 2026-09-22

Initial release.

- Tools mapping 1:1 to the official System One question types:
  - `choice` — pick ONE of 2-100 mutually exclusive options with calibrated probabilities.
  - `score` — grade on an ordered rubric of 2-8 levels (fractional index + per-level probabilities).
  - `noul` — yes/no question with a 0-1 degree.
- `classify` — batch-classify up to 100 items against one shared category set.
- `setup` — one-time API key onboarding: live verification, then stored with 0600 permissions.
- Optional response cache (off by default, `JEVMCP_CACHE=1`).
- Response validation (probabilities sum, winner consistency, bounds), retry on 429/503/529.
- Bilingual documentation (English / 简体中文).
- Config snippets for Claude Code, Codex, OpenCode, pi, and generic stdio clients.
