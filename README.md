[English](README.md) | [简体中文](README.zh-CN.md)

# jev-mcp-server

[![CI](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/jev-mcp-server)](https://pypi.org/project/jev-mcp-server/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/jev-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**MCP server for [Jev](https://typesafe.ai) (TypeSafe System One) — a faithful mapping of the three official question types, plus batch classify.**

When your coding agent needs a judgment — which log line is the root cause, how risky is this diff, is this change breaking — it usually burns a frontier LLM call and gets prose back. Jev answers with a **typed decision and calibrated probabilities** in a fraction of a second, for a fraction of a cent:

| Question type | Tool | Returns | Measured* |
|---|---|---|---|
| `choice` | pick 1 of 2-100 options | winner + probabilities over ALL options + confidence | ~0.6 s, ~$0.00002 |
| `score` | grade on a rubric of 2-8 levels | fractional index + per-level probabilities | ~0.5 s, ~$0.00002 |
| `noul` | yes / no | 0-1 degree | ~0.4 s, ~$0.00001 |
| `classify` | label up to 100 items | per-item choice + aggregate summary | ~0.5 s × items |

\* Measured against `jev-1.13.0`, 2026-09, from real sessions (see [Benchmarks](#benchmarks)).

## Why this one

- **1:1 with the official API.** Tool names match the System One question types (`choice` / `score` / `noul`), so anything you learn from [TypeSafe's docs](https://typesafe.ai) transfers directly. No invented abstractions.
- **Decisions, not explanations.** Jev never returns reasons — any "why" your assistant writes is its own interpretation of the probability distribution. The README (and the tool docs) say so explicitly, so reports built on top stay honest.
- **Batch `classify`** for routing/labeling workflows, with per-item caching.
- **One-time `setup` tool**: paste your API key once in chat; it's verified live, stored with `0600` permissions, and never echoed back.
- **Bilingual docs** (English / 简体中文), configs for Claude Code, Codex, OpenCode, pi, and any stdio MCP client.
- Offline-tested (no network in CI), retries on 429/503/529, response validation (probabilities sum to 1, winner is the max), optional response cache.

## Quickstart

1. Get a TypeSafe API key at [console.typesafe.ai/settings/keys](https://console.typesafe.ai/settings/keys).
2. Register the server with your client (pick one below).
3. Either export `TYPESAFE_API_KEY`, or just ask your agent: *"run the jev setup tool with key `tsk_...`"*.

### Claude Code

```bash
claude mcp add jev --env TYPESAFE_API_KEY=YOUR_KEY -- uvx jev-mcp-server
```

### Codex (`~/.codex/config.toml`)

```toml
[mcp_servers.jev]
command = "uvx"
args = ["jev-mcp-server"]
env = { TYPESAFE_API_KEY = "YOUR_KEY" }
```

### OpenCode (`~/.config/opencode/opencode.json`)

```json
{
  "mcp": {
    "jev": { "type": "local", "command": ["uvx", "jev-mcp-server"], "enabled": true }
  }
}
```

### pi (`~/.pi/agent/mcp.json`)

```json
{
  "mcpServers": {
    "jev": { "command": "uvx", "args": ["jev-mcp-server"], "lifecycle": "lazy" }
  }
}
```

### Any stdio MCP client

```json
{ "command": "uvx", "args": ["jev-mcp-server"] }
```

### From source (this repo)

```json
{ "command": "uv", "args": ["run", "--directory", "/path/to/jev-mcp-server", "jev-mcp-server"] }
```

## Tools

### `choice(question, options, context="")`

Pick ONE of 2-100 mutually exclusive options. Returns probabilities over all options (near-ties are visible), confidence, and the runner-up.

```json
{"choice": "E1", "confidence": 0.67,
 "probabilities": {"E1": 0.72, "E6": 0.2, "E5": 0.05, "E2": 0.01, "E3": 0.01, "E4": 0.01},
 "runner_up": "E6", "model": "jev-1.13.0", "latency_ms": 678,
 "usage": {"input_tokens": 1677, "output_tokens": 66}}
```

### `score(question, levels, context="")`

Grade on an ordered rubric of 2-8 levels. `score` is a fractional 0-based index: `2.22` with levels `["minor","moderate","severe","critical"]` means *severe, leaning critical*.

```json
{"score": 2.22, "nearest_level": "severe", "confidence": 0.59,
 "probabilities": {"severe": 0.6, "critical": 0.2, "moderate": 0.2}, "...": "..."}
```

### `noul(question, context="")`

Yes/no with a 0-1 degree (`>= 0.5` leans yes). No probability list — the degree is the answer.

```json
{"noul": 0.76, "verdict": "yes", "model": "jev-1.13.0", "latency_ms": 402, "usage": {"...": "..."}}
```

### `classify(items, options, question=..., context="")`

Batch-label up to 100 items against one shared category set. One `choice` call per item, aggregated:

```json
{"results": [{"item": "ticket #1", "choice": "billing", "confidence": 0.81, "probabilities": {"...": "..."}}],
 "summary": {"billing": 12, "bug": 7, "howto": 3},
 "usage": {"input_tokens": 8210, "output_tokens": 210, "calls": 22, "cached_calls": 0}}
```

### `setup(api_key)`

One-time onboarding: verifies the key with a live call, stores it at `~/.config/jev-mcp/key` (0600), never echoes it. An env var `TYPESAFE_API_KEY` always wins over the stored file.

## Caching (off by default)

Set `JEVMCP_CACHE=1` to enable. The cache key is the SHA-256 of the exact question payload, so:

- Identical repeated decisions (retries, re-runs, deterministic pipelines) return in ~0 ms at **zero API cost**; `usage` then reports `{"cached": true}`.
- `classify` benefits automatically: duplicate items inside one batch are single-billed.

Keep it **off** when decisions must stay fresh (live triage of changing data). Cache files live in `~/.cache/jev-mcp/` (override with `JEVMCP_CACHE_DIR`); delete them anytime.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `TYPESAFE_API_KEY` | — | API key (env wins over the file written by `setup`) |
| `JEVMCP_MODEL` | `jev-latest` | Model name sent to the API |
| `JEVMCP_BASE_URL` | `https://api.typesafe.ai/v1/systemone` | Point at a compatible gateway (experimental) |
| `JEVMCP_CACHE` | off | `1`/`true` enables the response cache |
| `JEVMCP_CACHE_DIR` | `~/.cache/jev-mcp` | Cache location |
| `JEVMCP_CONFIG_DIR` | `~/.config/jev-mcp` | Where `setup` stores the key |

> **Note on OpenRouter**: Jev was announced for OpenRouter (`~typesafe/jev-latest`), but at publish time it does **not** appear in OpenRouter's public model catalog, and we could not verify a compatible call shape. If you route Jev through a gateway, set `JEVMCP_BASE_URL` accordingly and please open an issue with your findings.

## Decisions, not explanations

Jev's contract is: a decision, calibrated probabilities, and nothing else — no rationale text. That is why it is fast and cheap. When your assistant narrates *"jev chose E1 because..."*, that explanation is the assistant's **interpretation** of the numbers, not Jev's output. For formal reports (root-cause analyses, review verdicts), either let the LLM reason itself, or use the two-step pattern — Jev decides, LLM explains, clearly labeled.

## Benchmarks

Measured 2026-09 against `jev-1.13.0`, single questions, real sessions:

| Call | Latency | Input tokens | Output tokens |
|---|---|---|---|
| `choice`, 6 options | 615-678 ms | 344-1677 | 31-66 |
| `score`, 3 levels | ~500 ms | ~350 | ~30 |
| `noul` | ~400 ms | ~300 | ~25 |

At [$42 / 1B input tokens](https://typesafe.ai) a typical call costs ≈ $0.00002 — roughly two orders of magnitude below a frontier-LLM judgment call.

## Alternatives (fair and square)

- [jkudish/jev-mcp](https://github.com/jkudish/jev-mcp) — Node/npm, ten opinionated workflow tools (verify, screen, rerank, gate...). Pick it if you want ready-made agent-safety workflows.
- [itsmostafa/typesafe-mcp](https://github.com/itsmostafa/typesafe-mcp) — Go binary, one generic `evaluate` tool, one-command client setup.

`jev-mcp-server` is the close-to-the-metal option: the three official question types, named exactly as TypeSafe names them, with batch classify, bilingual docs, and measured numbers. Pick whichever fits your taste — they're all MIT.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest -q
```

Tests are fully offline (the HTTP layer is mocked; CI never spends API credits).

## License

[MIT](LICENSE)
