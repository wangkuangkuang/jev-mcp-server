# jev-mcp-server

[English](README.md)

![CI](https://github.com/wangkuangkuang/jev-mcp-server/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/jev-mcp-server.svg)
![Python](https://img.shields.io/pypi/pyversions/jev-mcp-server.svg)
![License](https://img.shields.io/pypi/l/jev-mcp-server.svg)
![Downloads](https://img.shields.io/pypi/dm/jev-mcp-server.svg)

**Jev（TypeSafe System One 模型）的 MCP 服务器**：官方三种问题类型（**choice / score / noul**）忠实实现，外加 **compare**、**verify**、批量 **classify** 和一键客户端安装。

Jev 以不足一秒的延迟、不到一厘钱的成本返回"类型化决策 + 校准概率"——那些前沿大模型跑起来太慢太贵的机械判断（分流、路由、打分、卡点）。

## 快速开始

```bash
# 1. 获取 key：https://console.typesafe.ai/settings/keys

# 2. 一行命令装进你的客户端（配置自动写入）：
uvx jev-mcp-server install claude-code    # 也可：pi | cursor | opencode | codex

# 3. 客户端在运行中的话重启一下，然后问：
#    "这三个发版方案哪个风险最低？给我概率分布。"
```

没有 `uv`？`curl -LsSf https://astral.sh/uv/install.sh | sh`（或 `brew install uv` / `pip install uv`）。

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

不想把 key 写进配置？去掉 env 块，在 agent 里调一次 `setup` 工具——它会真调 API 验证后以 0600 权限落盘。
</details>

## 工具一览

| 工具 | 官方类型 | 作用 | 典型场景 |
|---|---|---|---|
| `choice` | `choice` | 从 2–100 个互斥选项中选 1 个；返回**全部**选项的概率，平局可见 | 分流、路由、tie-break |
| `score` | `score` | 按 2–8 级有序量表打分；小数索引（1.88 = 介于 1、2 级之间偏 2） | 风险 / 严重度 / 质量评级 |
| `noul` | `noul` | 是非题，返回 0–1 程度值 | "这个改动 breaking 吗？" |
| `compare` | `choice`（A/B） | 两个候选谁更好，概率分布可见 | 标题、方案、文案二选一 |
| `verify` | `noul`（断言/证据） | 一条断言对照给定证据的支持度 | 核对报告、日志与症状匹配 |
| `classify` | `choice`（批量） | ≤100 条条目 × 同一套类别，汇总聚合 | 打标、排序队列 |
| `setup` | — | 验证并保存 key（0600），一次即可 | 免环境变量的引导 |

## 为什么用 Jev、为什么用这个 server

Jev 输出的是**决策而不是文本**：类型化答案 + 校准概率 + 置信度，从不解释。这就是一次调用只要 ~$0.00001–0.0001、~0.5–1 秒的原因——同样的判断，前沿 LLM 要数秒、贵百倍。（你的助手补充的任何"理由"都是它对数字的解读，请当作假设看待。）

真实使用实测（单次调用，仅供参考）：

| 调用 | 延迟 | 输入 tokens | 成本* |
|---|---|---|---|
| `choice`，6 个带上下文的选项 | ~0.6–0.7s | ~1.7k | ≈ $0.00007 |
| `noul` / `verify`，短上下文 | ~0.4–0.6s | ~0.3–0.5k | ≈ $0.00002 |
| `classify`，100 条 | 串行约 1 分钟 | 约为上者 ×100 | ≈ $0.007 |

\* 按 $42 / 十亿 input tokens 计算。

本服务器忠实映射官方 System One API（同款三种问题类型、响应校验、429/503/529 重试），增加批量、缓存和一键安装，除 `mcp` 与 `httpx` 外零依赖。

## 配置

| 变量 | 含义 | 默认 |
|---|---|---|
| `TYPESAFE_API_KEY` | API key；环境变量优先于 `setup` 存的文件 | — |
| `JEVMCP_BASE_URL` | API 端点覆盖（接中转/实验用） | `https://api.typesafe.ai/v1/systemone` |
| `JEVMCP_MODEL` | 模型名 | `jev-latest` |
| `JEVMCP_CACHE` | `1`/`true`/`on` 开启响应缓存 | 关 |
| `JEVMCP_CACHE_DIR` / `JEVMCP_CONFIG_DIR` | 缓存 / key 存储位置 | `~/.cache/jev-mcp`、`~/.config/jev-mcp` |

开启 `JEVMCP_CACHE=1` 后，相同问题载荷直接从磁盘命中，零成本（`usage.cached: true`）；`classify` 自动去重批内重复条目。

## 常见问题

**Jev 为什么从不解释选择？** 产品设计如此——"decisions, not strings"。概率分布就是全部输出；解释会花掉这个模型赖以生存的延迟和 token。

**需要另外的大模型或本地装 Jev 吗？** 不需要。Jev 是云端 API，没有本地模型、没有辅助 LLM。你的 agent 主模型本来就负责决定何时调用、如何解读数字。

**还有别的 Jev MCP 吗？** 有——[`jkudish/jev-mcp`](https://github.com/jkudish/jev-mcp)（Node/npm，十个工作流工具），另有 Go 实现。本服务器是 Python/uvx 这一边：官方问题类型忠实实现、一键安装、双语文档、MIT。

## 许可证

MIT
