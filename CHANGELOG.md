# Changelog

## 0.2.3 — 2026-09-23

### Fixed

- `install` raised `AttributeError: module 'sys' has no attribute 'environ'` whenever the API key came from `TYPESAFE_API_KEY` or the interactive prompt. Passing `--key` short-circuited the bad expression, which is why it worked for some and failed for everyone else. If you installed **0.2.0–0.2.2**, this was the cause — upgrade.
- A client config carrying a UTF-8 BOM (written by PowerShell `>` / `Set-Content -Encoding utf8`, or by Notepad) was silently **replaced wholesale**, destroying every other MCP server entry in that file. A config that cannot be parsed is now reported and left untouched.
- A key file with a BOM no longer yields a key with a leading U+FEFF character.
- `install claude-code` no longer flashes a console window on Windows.
- Running `install` without a terminal — `jev-mcp-server install pi < /dev/null` — now prints a one-line explanation instead of a `getpass` traceback.
- `install codex` preserves an existing CRLF config's line endings instead of appending LF blocks to it.

### Changed

- Config and key files are written atomically (temp file + `os.replace`), so an interrupted or failed write can no longer leave a truncated file behind. Modified configs are still backed up to `*.bak` first.
- The `0600` chmod on the key file is skipped on Windows, where it is a no-op that does not actually restrict access — confidentiality there comes from your user profile's ACL. It also no longer fails on DrvFs / FAT32 / network shares that cannot express POSIX modes.
- CI now runs on macOS and Windows as well as Linux, across Python 3.10 / 3.12 / 3.13, and verifies the built wheel actually contains the whole package and that `server.json` agrees with `pyproject.toml` on the version.

## 0.2.2 — 2026-09-23

- Added MCP Registry ownership marker to the README (`mcp-name`); no functional changes.

## 0.2.1 — 2026-09-23

- README: badges now link to their target pages instead of the badge images; cross-language doc links use absolute URLs so they resolve on PyPI as well as GitHub; added a pip install path, real-call examples, a when-to-use section, and a new FAQ entry; copy pass over both languages to remove AI-writing patterns.

## 0.2.0 — 2026-09-23

- `jev-mcp-server install <client>` — one-command client setup (pi, claude-code, cursor, opencode, codex): resolves the API key from `--key` / env / prompt, merges the `jev` entry into the client config, backs up modified files to `*.bak`, idempotent unless `--force`.
- New tools:
  - `compare` — A/B judgment returning the preferred side plus the visible probability split.
  - `verify` — claim-vs-evidence support degree (0-1) for fact-checks and symptom-vs-log matching.
- README: quickstart reduced to one install command, tools table, measured latency/cost table, FAQ.

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
