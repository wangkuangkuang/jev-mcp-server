# jev-mcp-server

[中文文档](README.zh-CN.md) | [CI](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml/badge.svg)

![CI](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/jev-mcp-server.svg)
![Python](https://img.shields.io/pypi/pyversions/jev-mcp-server.svg)
![License](https://img.shields.io/pypi/l/jev-mcp-server.svg)
![Downloads](https://img.shields.io/pypi/dm/jev-mcp-server.svg)

MCP server for **Jev — TypeSafe's System One model**: the three official question types (**choice / score / noul**), plus **compare**, **verify**, batch **classify**, and a one-command client installer.

Jev returns typed decisions with calibrated probabilities in well under a second for a fraction of a cent — the cheap mechanical judgments (triage, routing, scoring, gating) that a frontier model is too slow and too expensive to run on every candidate, claim, or list.

## Quickstart

```bash
# 1. Get a key: https://console.typesafe.ai/settings/keys

# 2. Install into your client — one command, config written for you:
uvx jev-mcp-server install claude-code    # or: pi | cursor | opencode | codex

# 3. Restart the client if running, then ask:
#    "Which of these rollout plans is safest? Give me the probability split."
```

No `uv` yet? `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `brew install uv` / `pip install uv`).

<details>
<summary><b>Manual config</b> (clients without an installer entry)</summary>

Most stdio MCP clients take this shape:

```json
{
  "mcpServers": {
    "jev": {
      "command": "uvx",
      "args": ["jev-mcp-server"],
      "env": { "TYPESAFE_API_KEY": "apikey_xxx" }
    }
  }
}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.jev]
command = "uvx"
args = ["jev-mcp-server"]

[mcp_servers.jev.env]
TYPESAFE_API_KEY = "apikey_xxx"
```

OpenCode (`opencode.json`, `"mcp"` section): `{"jev": {"type": "local", "command": ["uvx", "jev-mcp-server"], "env": {"TYPESAFE_API_KEY": "apikey_xxx"}}}`

Prefer not to put the key in config at all? Skip the env block and call the `setup` tool once from your agent — it verifies the key live and stores it with 0600 permissions.
</details>

## Tools

| Tool | Official type | What it does | Typical use |
|---|---|---|---|
| `choice` | `choice` | Pick 1 of 2–100 options; probabilities over **all** options, so near-ties are visible | Triage, routing, tie-breaking |
| `score` | `score` | Grade on an ordered 2–8 level rubric; fractional index (1.88 = between levels 1 and 2) | Risk / severity / quality grading |
| `noul` | `noul` | Yes/no question with a 0–1 degree | "Is this change breaking?" |
| `compare` | `choice` (A/B) | Which of two candidates wins, with the visible probability split | Titles, plans, messages |
| `verify` | `noul` (claim/evidence) | Support degree of ONE claim against evidence you supply | Fact-check lines, log-vs-symptom |
| `classify` | `choice` (batch) | Up to 100 items against one shared category set, aggregated | Labeling queues, sorting inboxes |
| `setup` | — | Verify a key once, store it locally (0600) | Onboarding without env config |

## Why Jev, why this server

Jev outputs **decisions, not strings**: a typed answer plus calibrated probabilities and a confidence value — never an explanation. That is why a call costs ~$0.00001–0.0001 and lands in ~0.5–1s, where a frontier LLM takes seconds and costs 100×+ for the same judgment. (Any "reason" your assistant adds is its own interpretation of the numbers — treat it as a hypothesis.)

Measured on real usage (single calls, indicative only):

| Call | Latency | Input tokens | Cost* |
|---|---|---|---|
| `choice`, 6 rich options + context | ~0.6–0.7s | ~1.7k | ≈ $0.00007 |
| `noul` / `verify`, short context | ~0.4–0.6s | ~0.3–0.5k | ≈ $0.00002 |
| `classify`, 100 items | ~1 min sequential | ~100× above | ≈ $0.007 |

\* at $42 / 1B input tokens.

This server maps the official System One API faithfully (same three question types, validated responses, retry on 429/503/529), adds batching, caching, and the installer, and stays a single small Python package with zero dependencies beyond `mcp` and `httpx`.

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `TYPESAFE_API_KEY` | API key; env var beats the file stored by `setup` | — |
| `JEVMCP_BASE_URL` | API endpoint override (experiment with relays) | `https://api.typesafe.ai/v1/systemone` |
| `JEVMCP_MODEL` | Model name | `jev-latest` |
| `JEVMCP_CACHE` | `1`/`true`/`on` enables the response cache | off |
| `JEVMCP_CACHE_DIR` / `JEVMCP_CONFIG_DIR` | Relocate cache / key storage | `~/.cache/jev-mcp`, `~/.config/jev-mcp` |

With `JEVMCP_CACHE=1`, identical question payloads are answered from disk at zero cost (`usage.cached: true`); `classify` deduplicates repeated items automatically.

## FAQ

**Why does Jev never explain its choice?** By design — "decisions, not strings" is the product. The probability distribution is the output; explanations cost the latency and tokens this model exists to avoid.

**Do I need another LLM or local Jev install?** No. Jev is a cloud API — no local model, no helper LLM. Your agent's main model already handles when to call these tools and how to read the numbers.

**Is there another Jev MCP?** Yes — [`jkudish/jev-mcp`](https://github.com/jkudish/jev-mcp) (Node/npm) offers ten workflow-shaped tools; a Go server also exists. This one is the Python/uvx side: faithful official question types, one-command install, bilingual docs, MIT.

## License

MIT
