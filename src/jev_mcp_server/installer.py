"""One-command client installation: ``jev-mcp-server install <client>``.

Writes the MCP client configuration for you, the way mainstream MCP servers do
(``playwright mcp install`` & co.): resolves your TypeSafe API key from
``--key``, the environment, or an interactive prompt, then merges a ``jev``
server entry into the target client's config file. Existing files get a
``.bak`` backup before being modified, and an existing ``jev`` entry is left
alone unless ``--force`` is given.
"""

from __future__ import annotations

import argparse
import getpass
import json
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_NAME = "jev"
KEY_URL = "https://console.typesafe.ai/settings/keys"
CLIENTS = ("pi", "claude-code", "cursor", "opencode", "codex")

def _mcp_entry(key: str) -> dict:
    return {"command": "uvx", "args": ["jev-mcp-server"], "env": {"TYPESAFE_API_KEY": key}}

def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}

def _write_json(path: Path, data: dict) -> None:
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if existed:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def _merge_server(path: Path, key: str, force: bool, lifecycle: bool = False) -> str:
    data = _load_json(path)
    servers = data.setdefault("mcpServers", {})
    if SERVER_NAME in servers and not force:
        return f"already configured in {path} (use --force to overwrite)"
    entry = _mcp_entry(key)
    if lifecycle:
        entry["lifecycle"] = "lazy"
    servers[SERVER_NAME] = entry
    _write_json(path, data)
    return f"written to {path}"

def install_pi(key: str, force: bool) -> str:
    return _merge_server(Path.home() / ".pi" / "agent" / "mcp.json", key, force, lifecycle=True)

def install_cursor(key: str, force: bool) -> str:
    return _merge_server(Path.home() / ".cursor" / "mcp.json", key, force)

def install_claude_code(key: str, force: bool) -> str:
    cli = shutil.which("claude")
    if cli:
        try:
            result = subprocess.run(
                [cli, "mcp", "add", SERVER_NAME, "-s", "user", "--env", f"TYPESAFE_API_KEY={key}", "--", "uvx", "jev-mcp-server"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0:
            return "registered via `claude mcp add` (user scope)"
    return _merge_server(Path.home() / ".claude.json", key, force)

def install_opencode(key: str, force: bool) -> str:
    path = Path.home() / ".config" / "opencode" / "opencode.json"
    data = _load_json(path)
    section = data.setdefault("mcp", {})
    if SERVER_NAME in section and not force:
        return f"already configured in {path} (use --force to overwrite)"
    section[SERVER_NAME] = {"type": "local", "command": ["uvx", "jev-mcp-server"], "env": {"TYPESAFE_API_KEY": key}}
    _write_json(path, data)
    return f"written to {path}"

def install_codex(key: str, force: bool) -> str:
    path = Path.home() / ".codex" / "config.toml"
    marker = f"[mcp_servers.{SERVER_NAME}]"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if marker in text:
            return f"already configured in {path} (edit the file manually to change it)"
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        body = text.rstrip("\n") + "\n\n"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = ""
    body += f'{marker}\ncommand = "uvx"\nargs = ["jev-mcp-server"]\n\n[mcp_servers.{SERVER_NAME}.env]\nTYPESAFE_API_KEY = "{key}"\n'
    path.write_text(body, encoding="utf-8")
    return f"written to {path}"

INSTALLERS = {"pi": install_pi, "claude-code": install_claude_code, "cursor": install_cursor, "opencode": install_opencode, "codex": install_codex}

def _resolve_key(flag_key: str | None) -> str:
    key = (flag_key or "").strip() or sys.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        print(f"No key given. Get one at {KEY_URL}, then paste it here (input hidden).")
        key = getpass.getpass("TypeSafe API key: ").strip()
    if not key:
        sys.exit("No API key provided; nothing was written.")
    return key

def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jev-mcp-server install",
        description="Write the jev MCP server configuration into a client. Existing files are backed up to *.bak.",
    )
    parser.add_argument("client", choices=CLIENTS, help="which MCP client to configure")
    parser.add_argument("--key", help="TypeSafe API key (default: TYPESAFE_API_KEY env var, then interactive prompt)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing jev entry")
    args = parser.parse_args(argv)
    key = _resolve_key(args.key)
    outcome = INSTALLERS[args.client](key, args.force)
    masked = f"{key[:8]}…" if len(key) > 8 else "***"
    print(f"jev {outcome} (key: {masked})")
    print(f"Restart {args.client} if it is running, then ask your agent e.g.:")
    print('  "Which of these options is safest? Give me the probability split."')
    return 0
