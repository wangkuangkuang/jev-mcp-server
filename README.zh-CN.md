[English](README.md) | [简体中文](README.zh-CN.md)

# jev-mcp-server

[![CI](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/jev-mcp-server)](https://pypi.org/project/jev-mcp-server/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/jev-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**[Jev](https://typesafe.ai)（TypeSafe System One）的 MCP server——与官方三种问题类型一一对应的忠实实现，外加批量分类。**

当你的编码 agent 需要一个判断——哪条日志是根因、这个 diff 风险多高、这个改动是否 breaking——通常会烧掉一次前沿 LLM 调用还只换来一段散文。Jev 用**类型化决策 + 校准概率**作答，零点几秒、不到一厘钱：

| 问题类型 | 用途 | 返回 | 实测* |
|---|---|---|---|
| `choice` | 从 2-100 个选项中选 1 | 胜者 + 全部选项的概率分布 + 置信度 | ~0.6 s，约 $0.00002 |
| `score` | 按 2-8 级 rubric 打分 | 小数索引 + 各等级概率 | ~0.5 s，约 $0.00002 |
| `noul` | 是 / 否 | 0-1 程度值 | ~0.4 s，约 $0.00001 |
| `classify` | 给最多 100 条内容打标签 | 每条的选择结果 + 汇总统计 | ~0.5 s × 条数 |

\* 基于 `jev-1.13.0`，2026-09 真实会话实测（见[基准数据](#基准数据)）。

## 为什么选这个

- **与官方 API 一一对应。** 工具名就是 System One 的问题类型（`choice` / `score` / `noul`），[TypeSafe 文档](https://typesafe.ai)里学到的任何东西直接迁移，没有发明新抽象。
- **决策，不是解释。** Jev 从不返回理由——assistant 写的任何"为什么"都是它对概率分布的自行解读。本 README 和工具文档都明确说了这一点，让你构建的报告保持诚实。
- **批量 `classify`**：路由/打标工作流，逐条自动缓存。
- **一次性 `setup` 工具**：在聊天里贴一次 key，真调 API 验证后以 `0600` 权限落盘，永不回显。
- **中英双语文档**，提供 Claude Code、Codex、OpenCode、pi 及任意 stdio MCP 客户端的配置。
- 离线测试（CI 不联网）、429/503/529 自动重试、响应校验（概率和为 1、胜者即最大值）、可选响应缓存。

## 快速开始

1. 在 [console.typesafe.ai/settings/keys](https://console.typesafe.ai/settings/keys) 申请 TypeSafe API key。
2. 按下面的片段把 server 注册进你的客户端。
3. 要么导出 `TYPESAFE_API_KEY`，要么直接对 agent 说："用 jev 的 setup 工具配置 key `tsk_...`"。

### Claude Code

```bash
claude mcp add jev --env TYPESAFE_API_KEY=YOUR_KEY -- uvx jev-mcp-server
```

### Codex（`~/.codex/config.toml`）

```toml
[mcp_servers.jev]
command = "uvx"
args = ["jev-mcp-server"]
env = { TYPESAFE_API_KEY = "YOUR_KEY" }
```

### OpenCode（`~/.config/opencode/opencode.json`）

```json
{
  "mcp": {
    "jev": { "type": "local", "command": ["uvx", "jev-mcp-server"], "enabled": true }
  }
}
```

### pi（`~/.pi/agent/mcp.json`）

```json
{
  "mcpServers": {
    "jev": { "command": "uvx", "args": ["jev-mcp-server"], "lifecycle": "lazy" }
  }
}
```

### 任意 stdio MCP 客户端

```json
{ "command": "uvx", "args": ["jev-mcp-server"] }
```

### 从源码运行（本仓库）

```json
{ "command": "uv", "args": ["run", "--directory", "/path/to/jev-mcp-server", "jev-mcp-server"] }
```

## 工具说明

### `choice(question, options, context="")`

从 2-100 个互斥选项中选一个。返回全部选项的概率分布（险胜看得见）、置信度和第二名。

```json
{"choice": "E1", "confidence": 0.67,
 "probabilities": {"E1": 0.72, "E6": 0.2, "E5": 0.05, "E2": 0.01, "E3": 0.01, "E4": 0.01},
 "runner_up": "E6", "model": "jev-1.13.0", "latency_ms": 678,
 "usage": {"input_tokens": 1677, "output_tokens": 66}}
```

### `score(question, levels, context="")`

按 2-8 级有序 rubric 打分。`score` 是 0 起始的小数索引：等级为 `["minor","moderate","severe","critical"]` 时 `2.22` 表示 *severe 偏 critical*。

```json
{"score": 2.22, "nearest_level": "severe", "confidence": 0.59,
 "probabilities": {"severe": 0.6, "critical": 0.2, "moderate": 0.2}, "...": "..."}
```

### `noul(question, context="")`

带 0-1 程度值的判断题（`>= 0.5` 偏"是"）。没有概率列表——程度值就是答案。

```json
{"noul": 0.76, "verdict": "yes", "model": "jev-1.13.0", "latency_ms": 402, "usage": {"...": "..."}}
```

### `classify(items, options, question=..., context="")`

对最多 100 条内容按同一套类目批量打标。每条一次 `choice` 调用，自动汇总：

```json
{"results": [{"item": "工单 #1", "choice": "billing", "confidence": 0.81, "probabilities": {"...": "..."}}],
 "summary": {"billing": 12, "bug": 7, "howto": 3},
 "usage": {"input_tokens": 8210, "output_tokens": 210, "calls": 22, "cached_calls": 0}}
```

### `setup(api_key)`

一次性配置：真调 API 验证 key，存到 `~/.config/jev-mcp/key`（0600 权限），永不回显。环境变量 `TYPESAFE_API_KEY` 始终优先于落盘的 key。

## 缓存（默认关闭）

设置 `JEVMCP_CACHE=1` 开启。缓存键是问题载荷的 SHA-256，因此：

- 完全相同的重复决策（重试、重跑、确定性流水线）以 ~0 ms 返回、**零 API 成本**，`usage` 会显示 `{"cached": true}`。
- `classify` 自动受益：同一批次里的重复条目只计费一次。

当决策必须保持新鲜时（如对变化数据的实时分流）请保持**关闭**。缓存文件在 `~/.cache/jev-mcp/`（可用 `JEVMCP_CACHE_DIR` 改路径），随时可删。

## 配置项

| 变量 | 默认值 | 用途 |
|---|---|---|
| `TYPESAFE_API_KEY` | — | API key（env 优先于 `setup` 落盘的文件） |
| `JEVMCP_MODEL` | `jev-latest` | 发送给 API 的模型名 |
| `JEVMCP_BASE_URL` | `https://api.typesafe.ai/v1/systemone` | 指向兼容网关（实验性） |
| `JEVMCP_CACHE` | 关 | `1`/`true` 开启响应缓存 |
| `JEVMCP_CACHE_DIR` | `~/.cache/jev-mcp` | 缓存位置 |
| `JEVMCP_CONFIG_DIR` | `~/.config/jev-mcp` | `setup` 存 key 的目录 |

> **关于 OpenRouter**：Jev 曾宣布上架 OpenRouter（`~typesafe/jev-latest`），但发布时点它**没有**出现在 OpenRouter 公开模型目录里，我们也无法验证兼容的调用格式。如果你通过网关路由 Jev，请设置 `JEVMCP_BASE_URL` 并欢迎提 issue 分享结果。

## 决策，不是解释

Jev 的契约是：一个决策、校准的概率，仅此而已——没有理由文本。这是它快和便宜的原因。当你的 assistant 叙述"jev 选了 E1 是因为……"时，那番解释是 assistant 对数字的**自行解读**，不是 Jev 的输出。正式报告（根因分析、评审结论）要么让 LLM 自己推理，要么用两段式——Jev 决策、LLM 解释，并明确标注解释是推断。

## 基准数据

2026-09 基于 `jev-1.13.0` 实测，单问题、真实会话：

| 调用 | 延迟 | 输入 tokens | 输出 tokens |
|---|---|---|---|
| `choice`，6 个选项 | 615-678 ms | 344-1677 | 31-66 |
| `score`，3 级 | ~500 ms | ~350 | ~30 |
| `noul` | ~400 ms | ~300 | ~25 |

按 [$42 / 10 亿输入 tokens](https://typesafe.ai) 计，一次典型调用约 $0.00002——比前沿 LLM 做同样判断低约两个数量级。

## 同类项目（有一说一）

- [jkudish/jev-mcp](https://github.com/jkudish/jev-mcp) —— Node/npm，十个面向工作流的工具（verify、screen、rerank、gate……）。想要现成 agent 安全工作流选它。
- [itsmostafa/typesafe-mcp](https://github.com/itsmostafa/typesafe-mcp) —— Go 二进制，单一通用 `evaluate` 工具，一条命令装好客户端。

`jev-mcp-server` 是贴近底层 API 的那个选项：三种官方问题类型、与 TypeSafe 命名完全一致，外加批量分类、双语文档和实测数据。都是 MIT，按口味选。

## 开发

```bash
uv sync
uv run ruff check .
uv run pytest -q
```

测试完全离线（HTTP 层 mock，CI 不花 API 额度）。

## 许可证

[MIT](LICENSE)
