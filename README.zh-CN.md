# jev-mcp-server

[![CI](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/jev-mcp-server.svg)](https://pypi.org/project/jev-mcp-server/)
[![Python](https://img.shields.io/pypi/pyversions/jev-mcp-server.svg)](https://pypi.org/project/jev-mcp-server/)
[![License: MIT](https://img.shields.io/pypi/l/jev-mcp-server.svg)](https://github.com/wangkuangkuang/jev-mcp-server/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/jev-mcp-server.svg)](https://pypi.org/project/jev-mcp-server/)

[English](https://github.com/wangkuangkuang/jev-mcp-server/blob/main/README.md)

Jev（TypeSafe System One 模型）的 MCP 服务器：官方三种问题类型（choice / score / noul）忠实实现，外加 compare、verify、批量 classify 和一键客户端安装器。

## Jev 是什么

Jev 是 [TypeSafe](https://typesafe.ai) 的云端决策模型。你发一个带选项的结构化问题，它返回类型化答案、校准概率和置信度，不写文本、不做解释。单次调用约 $0.00002 到 $0.0001、约半秒返回，适合高频的小判断：分流、路由、打分、卡点。这类判断交给前沿大模型，单次要数秒、贵百倍，跑批就不现实了。

需要一个 [TypeSafe API key](https://console.typesafe.ai/settings/keys)。没有本地模型、没有第二个 LLM、没有其他要装的东西。

## 快速开始

```bash
# 1. 获取 key：https://console.typesafe.ai/settings/keys

# 2. 一行命令装进你的客户端（配置自动写入）：
uvx jev-mcp-server install claude-code    # 也可：pi | cursor | opencode | codex

# 3. 客户端在运行中的话重启一下，然后问：
#    "这三个发版方案哪个风险最低？给我概率分布。"
```

没有 `uv`？`curl -LsSf https://astral.sh/uv/install.sh | sh`，或 `brew install uv`，或 `pip install uv`。直接 `pip install jev-mcp-server` 也行，安装子命令用法相同。

<details>
<summary><b>手动配置</b>（没有安装器条目的客户端）</summary>

大多数 stdio MCP 客户端通用形状：

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

Codex（`~/.codex/config.toml`）：

```toml
[mcp_servers.jev]
command = "uvx"
args = ["jev-mcp-server"]

[mcp_servers.jev.env]
TYPESAFE_API_KEY = "apikey_xxx"
```

OpenCode（`opencode.json` 的 `"mcp"` 段）：`{"jev": {"type": "local", "command": ["uvx", "jev-mcp-server"], "env": {"TYPESAFE_API_KEY": "apikey_xxx"}}}`

不想把 key 写进配置？去掉 env 块，在 agent 里调一次 `setup` 工具。它会真调 API 验证 key，然后以 0600 权限落盘。
</details>

## 工具一览

| 工具 | 官方类型 | 作用 | 典型场景 |
|---|---|---|---|
| `choice` | `choice` | 从 2-100 个互斥选项中选 1 个；返回**全部**选项的概率，平局可见 | 分流、路由、tie-break |
| `score` | `score` | 按 2-8 级有序量表打分；小数索引（1.88 = 介于 1、2 级之间，偏 2） | 风险 / 严重度 / 质量评级 |
| `noul` | `noul` | 是非题，返回 0-1 程度值 | "这个改动 breaking 吗？" |
| `compare` | `choice`（A/B） | 两个候选谁更好，概率分布可见 | 标题、方案、文案二选一 |
| `verify` | `noul`（断言/证据） | 一条断言对照给定证据的支持度 | 核对报告、日志与症状匹配 |
| `classify` | `choice`（批量） | ≤100 条条目 × 同一套类别，汇总聚合 | 打标、排序队列 |
| `setup` | （无） | 验证并保存 key（0600），一次即可 | 免环境变量的引导 |

## 真实示例

以下均为真实调用，返回原样引用（仅省略 `usage` 和 `model` 字段）。

**choice**：哪个改动对 API 消费者最可能是 breaking？选项：重命名既有配置键、加可选响应字段、改日志格式。

```json
{"choice": "rename_config_key", "confidence": 1.0,
 "probabilities": {"rename_config_key": 1.0, "add_optional_field": 0.0, "change_log_format": 0.0}}
```

**score**：原地重写一个认证中间件、还没写测试，回归风险按 minor/moderate/severe 评级：

```json
{"score": 1.98, "nearest_level": "severe", "confidence": 0.96}
```

**verify**：断言"最近一次 CI 的测试全部通过"，证据"CI 日志显示 250 个测试中 3 个失败"：

```json
{"noul": 0.01, "verdict": "not supported"}
```

## 适用与不适用

适合：

- 有明确选项集合：分流、路由、tie-break、A/B 二选一
- 量表打分：风险、严重度、评审分级
- 高频二元判断：breaking 门禁、断言与证据核对
- 批量打标：100 条 × 一套标签，约 $0.007

不适合：

- 开放式推理、长上下文分析
- 需要附带解释的结论。Jev 只返回数字；助手补的任何"理由"都是它对数字的解读，不是模型输出

## 成本与延迟（实测）

单次调用、仅供参考；按 $42 / 十亿 input tokens 计算。

| 调用 | 延迟 | 输入 tokens | 成本 |
|---|---|---|---|
| `choice`，6 个带上下文的选项 | ~0.6-0.7s | ~1.7k | ≈ $0.00007 |
| `noul` / `verify`，短上下文 | ~0.4-0.6s | ~0.3-0.5k | ≈ $0.00002 |
| `classify`，100 条 | 串行约 1 分钟 | 约为单次 ×100 | ≈ $0.007 |

## 配置

| 变量 | 含义 | 默认 |
|---|---|---|
| `TYPESAFE_API_KEY` | API key；环境变量优先于 `setup` 存的文件 | 必填 |
| `JEVMCP_BASE_URL` | API 端点覆盖（接中转/实验用） | `https://api.typesafe.ai/v1/systemone` |
| `JEVMCP_MODEL` | 模型名 | `jev-latest` |
| `JEVMCP_CACHE` | `1`/`true`/`on` 开启响应缓存 | 关 |
| `JEVMCP_CACHE_DIR` / `JEVMCP_CONFIG_DIR` | 缓存 / key 存储位置 | `~/.cache/jev-mcp`、`~/.config/jev-mcp` |

开启 `JEVMCP_CACHE=1` 后，相同问题载荷直接从磁盘命中，零成本（`usage.cached: true`）；`classify` 自动去重批内重复条目。

## 常见问题

**Jev 为什么从不解释选择？** 产品设计如此，"decisions, not strings" 就是产品本身。概率分布是全部输出；解释会花掉这个模型赖以生存的延迟和 token。

**需要另外的大模型或本地装 Jev 吗？** 不需要。Jev 是云端 API，没有本地模型、没有辅助 LLM。你的 agent 主模型负责决定何时调用、如何解读数字。

**为什么不直接问主 LLM？** 一次性问题确实可以直接问。差距在循环里：LLM 的置信度没有校准，单次贵约百倍，延迟以秒计。逐条跑批时，这个差距会累积。

**还有别的 Jev MCP 吗？** 有。[`jkudish/jev-mcp`](https://github.com/jkudish/jev-mcp)（Node/npm，十个工作流工具），另有 Go 实现。本服务器是 Python/uvx 这一边：官方问题类型忠实实现、一键安装、双语文档、MIT。

## 许可证

[MIT](https://github.com/wangkuangkuang/jev-mcp-server/blob/main/LICENSE)
