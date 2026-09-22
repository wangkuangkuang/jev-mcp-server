"""One-command client installation: ``jev-mcp-server install <client>``.

Writes the MCP client configuration for you, the way mainstream MCP servers do
(``playwright mcp install`` & co.): resolves your TypeSafe API key from
``--key``, the environment, or an interactive prompt, then merges a ``jev``
server entry into the target client's config file. Existing files get a
``.bak`` backup before being modified, and an existing ``jev`` entry is left
alone unless ``--force`` is given.

Cross-platform notes (macOS, Linux, Windows):

* All config paths are built from ``Path.home()``, which expands to
  ``$HOME`` on POSIX and ``%USERPROFILE%`` on Windows.
* Files are read as ``utf-8-sig`` so a UTF-8 BOM — which Windows editors and
  PowerShell's ``>`` / ``Set-Content -Encoding utf8`` add by default — neither
  corrupts an existing config nor silently discards it.
* Configs are written atomically (temp file + ``os.replace``) so an
  interrupted run cannot truncate your client configuration.
* An existing config that cannot be parsed is reported instead of being
  overwritten, so a malformed file never costs you your other MCP servers.
* When the ``claude`` CLI is on PATH it is invoked without a console window
  on Windows; if that fails for any reason we fall back to writing
  ``~/.claude.json`` directly.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ._fsutil import atomic_write_text, backup, read_text

SERVER_NAME = "jev"
KEY_URL = "https://console.typesafe.ai/settings/keys"
CLIENTS = ("pi", "claude-code", "cursor", "opencode", "codex")

# Keep the child console hidden on Windows; plain 0 is the only value POSIX
# accepts, so this is a no-op everywhere else.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class InstallerError(RuntimeError):
    """Raised when an existing config cannot be safely modified."""


def _mcp_entry(key: str) -> dict:
    return {"command": "uvx", "args": ["jev-mcp-server"], "env": {"TYPESAFE_API_KEY": key}}


def _load_json(path: Path) -> dict:
    """Return the parsed object, ``{}`` for a missing file.

    A file that exists but is not a JSON object raises rather than returning
    ``{}`` — otherwise the next write would silently replace the user's whole
    client config (every other MCP server included) with just our entry.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise InstallerError(f"{path} is not valid JSON ({exc}). Fix or delete it, then re-run this command.") from exc
    except OSError as exc:
        # read_text already names the path.
        raise InstallerError(str(exc)) from exc
    if not isinstance(data, dict):
        raise InstallerError(f"{path} does not contain a JSON object; refusing to overwrite it.")
    return data


def _write_json(path: Path, data: dict) -> None:
    if path.exists():
        backup(path)
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


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
                [
                    cli,
                    "mcp",
                    "add",
                    SERVER_NAME,
                    "-s",
                    "user",
                    "--env",
                    f"TYPESAFE_API_KEY={key}",
                    "--",
                    "uvx",
                    "jev-mcp-server",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                creationflags=_CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0:
            return "registered via `claude mcp add` (user scope)"
    # Either no `claude` on PATH or the CLI refused; write the JSON directly.
    # Claude Code reads %USERPROFILE%\.claude.json on Windows, ~/.claude.json elsewhere.
    return _merge_server(Path.home() / ".claude.json", key, force)


def install_opencode(key: str, force: bool) -> str:
    # opencode uses ~/.config/opencode/opencode.json on every OS, including
    # Windows (i.e. %USERPROFILE%\.config\opencode\opencode.json).
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
    newline = "\n"
    existing = ""
    if path.exists():
        try:
            existing = read_text(path)
        except OSError as exc:
            # read_text already names the path.
            raise InstallerError(str(exc)) from exc
        if marker in existing:
            return f"already configured in {path} (edit the file manually to change it)"
        # Match the file's own line endings so a Windows-authored CRLF config
        # does not end up with mixed endings after we append.
        if "\r\n" in existing:
            newline = "\r\n"
        backup(path)
    body = (existing.rstrip("\r\n") + newline + newline) if existing else ""
    body += newline.join(
        [
            marker,
            'command = "uvx"',
            'args = ["jev-mcp-server"]',
            "",
            f"[mcp_servers.{SERVER_NAME}.env]",
            f'TYPESAFE_API_KEY = "{key}"',
            "",
        ]
    )
    atomic_write_text(path, body)
    return f"written to {path}"


INSTALLERS = {
    "pi": install_pi,
    "claude-code": install_claude_code,
    "cursor": install_cursor,
    "opencode": install_opencode,
    "codex": install_codex,
}


def _resolve_key(flag_key: str | None) -> str:
    key = (flag_key or "").strip() or os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        print(f"No key given. Get one at {KEY_URL}, then paste it here (input hidden).")
        try:
            key = getpass.getpass("TypeSafe API key: ").strip()
        except (EOFError, KeyboardInterrupt):
            # Non-interactive shell (CI, `install pi < /dev/null`): say why
            # instead of dumping a getpass traceback.
            sys.exit("No API key provided (no terminal to prompt on). Pass --key or set TYPESAFE_API_KEY.")
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
    try:
        outcome = INSTALLERS[args.client](key, args.force)
    except InstallerError as exc:
        sys.exit(f"error: {exc}")
    masked = f"{key[:8]}…" if len(key) > 8 else "***"
    print(f"jev {outcome} (key: {masked})")
    print(f"Restart {args.client} if it is running, then ask your agent e.g.:")
    print('  "Which of these options is safest? Give me the probability split."')
    return 0
