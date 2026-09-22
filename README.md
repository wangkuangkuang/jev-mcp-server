# jev-mcp-server

[![CI](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/jev-mcp-server.svg)](https://pypi.org/project/jev-mcp-server/)
[![Python](https://img.shields.io/pypi/pyversions/jev-mcp-server.svg)](https://pypi.org/project/jev-mcp-server/)
[![License: MIT](https://img.shields.io/pypi/l/jev-mcp-server.svg)](https://github.com/wangkuangkuang/jev-mcp-server/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/jev-mcp-server.svg)](https://pypi.org/project/jev-mcp-server/)

[简体中文](https://github.com/wangkuangkuang/jev-mcp-server/blob/main/README.zh-CN.md)

<!-- mcp-name: io.github.wangkuangkuang/jev-mcp-server -->

MCP server for Jev, TypeSafe's System One model. It exposes the three official question types (choice, score, noul) plus compare, verify, batch classify, and a one-command installer that writes your client config for you.

## What is Jev

Jev is a hosted decision model from [TypeSafe](https://typesafe.ai). You send a structured question with enumerated options; it returns a typed answer with calibrated probabilities and a confidence value. It does not write prose and it does not explain itself. A single call costs roughly $0.00002 to $0.0001 and returns in about half a second, which is what makes it practical for the small, repeated judgments (triage, routing, grading, gating) that a frontier model is too slow and too expensive to run on every item.

You need a [TypeSafe API key](https://console.typesafe.ai/settings/keys). There is no local model, no second LLM, and nothing else to install.

## Quickstart

```bash
# 1. Get a key: https://console.typesafe.ai/settings/keys

# 2. Install into your client (config is written for you):
uvx jev-mcp-server install claude-code    # or: pi | cursor | opencode | codex

# 3. Restart the client if it is running, then ask:
#    "Which of these rollout plans is safest? Show me the probability split."
```

No `uv` yet? `curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`, or `pip install uv`. A plain `pip install jev-mcp-server` works too; the installer subcommand is the same either way.

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

Prefer not to put the key in config at all? Skip the env block and call the `setup` tool once from your agent. It verifies the key live and stores it with 0600 permissions.
</details>

## Tools

| Tool | Official type | What it does | Typical use |
|---|---|---|---|
| `choice` | `choice` | Pick 1 of 2-100 options; probabilities over **all** options, so near-ties are visible | Triage, routing, tie-breaking |
| `score` | `score` | Grade on an ordered 2-8 level rubric; fractional index (1.88 = between levels 1 and 2, leaning to 2) | Risk / severity / quality grading |
| `noul` | `noul` | Yes/no question with a 0-1 degree | "Is this change breaking?" |
| `compare` | `choice` (A/B) | Which of two candidates wins, with the visible probability split | Titles, plans, messages |
| `verify` | `noul` (claim/evidence) | Support degree of ONE claim against evidence you supply | Fact-check lines, log-vs-symptom |
| `classify` | `choice` (batch) | Up to 100 items against one shared category set, aggregated | Labeling queues, sorting inboxes |
| `setup` | (none) | Verify a key once, store it locally (0600) | Onboarding without env config |

## Examples

Real calls; responses quoted as returned (only `usage` and `model` trimmed).

**choice**: which change is most likely a breaking change for API consumers? Options: rename an existing config key, add an optional response field, change the log format.

```json
{"choice": "rename_config_key", "confidence": 1.0,
 "probabilities": {"rename_config_key": 1.0, "add_optional_field": 0.0, "change_log_format": 0.0}}
```

**score**: regression risk of rewriting an auth middleware in place, no tests written yet, on a minor/moderate/severe rubric:

```json
{"score": 1.98, "nearest_level": "severe", "confidence": 0.96}
```

**verify**: claim "all tests in the latest CI run passed", evidence "the CI log shows 3 failed tests out of 250":

```json
{"noul": 0.01, "verdict": "not supported"}
```

## When to use it

Good fit:

- Enumerated options: triage, routing, tie-breaks, A/B calls
- Rubric grading: risk, severity, review triage
- Binary checks at volume: breaking-change gates, claim-vs-evidence checks
- Batch labeling: 100 items against one label set for about $0.007

Poor fit:

- Open-ended reasoning or long-context analysis
- Anything that needs an explanation attached. Jev returns numbers; any "reason" your assistant adds is its own reading of those numbers, not output from the model

## Cost and latency (measured)

Single calls, indicative only; cost at $42 per 1B input tokens.

| Call | Latency | Input tokens | Cost |
|---|---|---|---|
| `choice`, 6 rich options + context | ~0.6-0.7s | ~1.7k | ≈ $0.00007 |
| `noul` / `verify`, short context | ~0.4-0.6s | ~0.3-0.5k | ≈ $0.00002 |
| `classify`, 100 items | ~1 min sequential | ~100× a single call | ≈ $0.007 |

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `TYPESAFE_API_KEY` | API key; env var beats the file stored by `setup` | required |
| `JEVMCP_BASE_URL` | API endpoint override (experiment with relays) | `https://api.typesafe.ai/v1/systemone` |
| `JEVMCP_MODEL` | Model name | `jev-latest` |
| `JEVMCP_CACHE` | `1`/`true`/`on` enables the response cache | off |
| `JEVMCP_CACHE_DIR` / `JEVMCP_CONFIG_DIR` | Relocate cache / key storage | `~/.cache/jev-mcp`, `~/.config/jev-mcp` |

With `JEVMCP_CACHE=1`, identical question payloads are answered from disk at zero cost (`usage.cached: true`); `classify` deduplicates repeated items automatically.

## FAQ

**Why does Jev never explain its choice?** By design; "decisions, not strings" is the product. The probability distribution is the output. Explanations would cost the latency and tokens this model exists to avoid.

**Do I need another LLM or a local Jev install?** No. Jev is a cloud API; there is no local model and no helper LLM. Your agent's main model decides when to call these tools and reads the numbers.

**Why not just ask my main LLM?** You can, and for one-off questions you probably should. The difference shows up in loops: an LLM's stated confidence is not calibrated, a call costs 100× more, and it takes seconds instead of milliseconds. Per item across a batch, that gap compounds.

**Is there another Jev MCP?** Yes. [`jkudish/jev-mcp`](https://github.com/jkudish/jev-mcp) (Node/npm) offers ten workflow-shaped tools, and a Go server exists. This one is the Python/uvx side: faithful official question types, one-command install, bilingual docs, MIT.

## License

[MIT](https://github.com/wangkuangkuang/jev-mcp-server/blob/main/LICENSE)
