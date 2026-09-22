"""Offline tests: no network, no API key required. The API layer is mocked."""

from __future__ import annotations

import json
import os
import shutil
import stat

import pytest

from jev_mcp_server import client, config, installer, server


def choice_payload(choice="a", probs=None, confidence=0.8):
    probs = probs or {"a": 0.7, "b": 0.3}
    return {
        "model": "jev-test",
        "answers": {"decision": {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": probs}},
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("JEVMCP_CACHE", raising=False)
    monkeypatch.delenv("JEVMCP_BASE_URL", raising=False)
    monkeypatch.setenv("JEVMCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("JEVMCP_CACHE_DIR", str(tmp_path / "cache"))
    yield


def test_choice_happy(monkeypatch):
    monkeypatch.setattr(client, "ask", lambda q: choice_payload())
    data = json.loads(server.choice("pick one", {"a": "first", "b": "second"}))
    assert data["choice"] == "a"
    assert data["runner_up"] == "b"
    assert data["model"] == "jev-test"
    assert data["probabilities"]["a"] == 0.7


def test_choice_option_validation():
    with pytest.raises(ValueError):
        server.choice("q", {"only": "one option"})
    with pytest.raises(ValueError):
        server.choice("q", {"": "empty id", "b": "second"})
    with pytest.raises(ValueError):
        server.choice("q", {str(i): f"opt {i}" for i in range(server.MAX_OPTIONS + 1)})


def test_choice_response_validation(monkeypatch):
    monkeypatch.setattr(client, "ask", lambda q: choice_payload(choice="zzz"))
    with pytest.raises(ValueError):
        server.choice("q", {"a": "first", "b": "second"})
    monkeypatch.setattr(client, "ask", lambda q: choice_payload(probs={"a": 0.5, "b": 0.4}))
    with pytest.raises(ValueError):
        server.choice("q", {"a": "first", "b": "second"})


def test_score_happy(monkeypatch):
    payload = {
        "model": "jev-test",
        "answers": {
            "score": {"type": "score", "score": 1.5, "confidence": 0.6, "probabilities": {"0": 0.1, "1": 0.6, "2": 0.3}}
        },
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    monkeypatch.setattr(client, "ask", lambda q: payload)
    data = json.loads(server.score("grade it", ["minor", "moderate", "severe"]))
    assert data["score"] == 1.5
    assert data["nearest_level"] == "moderate"
    assert data["probabilities"]["moderate"] == 0.6


def test_score_level_validation():
    with pytest.raises(ValueError):
        server.score("q", ["only"])
    with pytest.raises(ValueError):
        server.score("q", ["a", "a", "b"])
    with pytest.raises(ValueError):
        server.score("q", [f"level{i}" for i in range(9)])


def _score_payload(answer):
    return {"model": "jev-test", "answers": {"score": answer}, "usage": {"input_tokens": 1, "output_tokens": 1}}


@pytest.mark.parametrize(
    "answer",
    [
        {"confidence": 0.5, "probabilities": {"0": 0.5, "1": 0.5}},  # no score
        {"score": 0.5, "confidence": 0.5},  # no probabilities
        {"score": 2.5, "probabilities": {"0": 0.5, "1": 0.5}},  # above range
        {"score": -0.5, "probabilities": {"0": 0.5, "1": 0.5}},  # below range
        {"score": 0.5, "probabilities": {"0": 0.5, "1": 0.5, "2": 0.0}},  # wrong key set
        {"score": 0.5, "probabilities": "nope"},  # probabilities not a mapping
        {"score": 0.5, "probabilities": {"0": 0.2, "1": 0.2}},  # does not sum to 1
        {"score": 0.5, "probabilities": {"0": 1.5, "1": -0.5}},  # probability out of bounds
        {"score": "high", "probabilities": {"0": 0.5, "1": 0.5}},  # non-numeric score
        {"score": float("nan"), "probabilities": {"0": 0.5, "1": 0.5}},  # non-finite score
    ],
)
def test_score_rejects_malformed_response(monkeypatch, answer):
    """Everything the inline validation used to catch must still be rejected."""
    monkeypatch.setattr(client, "ask", lambda q: _score_payload(answer))
    with pytest.raises(ValueError, match="Invalid TypeSafe response"):
        server.score("grade it", ["minor", "moderate"])


@pytest.mark.parametrize("value, expected", [(0.0, "low"), (1.0, "high"), (0.5, "low")])
def test_score_accepts_boundary_values(monkeypatch, value, expected):
    """The extracted validator must not reject what the inline one accepted."""
    payload = _score_payload({"score": value, "probabilities": {"0": 1.0 - value, "1": value}})
    monkeypatch.setattr(client, "ask", lambda q: payload)
    data = json.loads(server.score("grade it", ["low", "high"]))
    assert data["score"] == value
    assert data["nearest_level"] == expected


def test_noul_happy(monkeypatch):
    payload = {
        "model": "jev-test",
        "answers": {"noul": {"type": "noul", "noul": 0.65}},
        "usage": {"input_tokens": 5, "output_tokens": 1},
    }
    monkeypatch.setattr(client, "ask", lambda q: payload)
    data = json.loads(server.noul("is it blue?"))
    assert data["noul"] == 0.65 and data["verdict"] == "yes"


def test_noul_range_validation(monkeypatch):
    payload = {"model": "jev-test", "answers": {"noul": {"noul": 1.5}}, "usage": {}}
    monkeypatch.setattr(client, "ask", lambda q: payload)
    with pytest.raises(ValueError):
        server.noul("q")


def test_classify_aggregation(monkeypatch):
    answers = iter(
        [
            choice_payload(choice="spam", probs={"spam": 0.9, "ham": 0.1}),
            choice_payload(choice="ham", probs={"spam": 0.2, "ham": 0.8}),
            choice_payload(choice="spam", probs={"spam": 0.7, "ham": 0.3}),
        ]
    )
    monkeypatch.setattr(client, "ask", lambda q: next(answers))
    data = json.loads(server.classify(["a", "b", "c"], {"spam": "junk", "ham": "legit"}))
    assert data["summary"] == {"spam": 2, "ham": 1}
    assert len(data["results"]) == 3
    assert data["usage"]["calls"] == 3
    assert data["results"][0]["item"] == "a"


def test_cache_roundtrip(monkeypatch):
    monkeypatch.setenv("JEVMCP_CACHE", "1")
    calls = {"n": 0}

    def fake_ask(q):
        calls["n"] += 1
        return choice_payload()

    monkeypatch.setattr(client, "ask", fake_ask)
    first = json.loads(server.choice("same question", {"a": "1", "b": "2"}))
    second = json.loads(server.choice("same question", {"a": "1", "b": "2"}))
    assert calls["n"] == 1
    assert first["usage"]["input_tokens"] == 10
    assert second["usage"]["cached"] is True
    assert second["choice"] == first["choice"]


def test_cache_disabled_by_default(monkeypatch):
    calls = {"n": 0}

    def fake_ask(q):
        calls["n"] += 1
        return choice_payload()

    monkeypatch.setattr(client, "ask", fake_ask)
    server.choice("q", {"a": "1", "b": "2"})
    server.choice("q", {"a": "1", "b": "2"})
    assert calls["n"] == 2


def test_key_resolution_env_wins(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")
    config.save_key("file-key")
    assert config.resolve_key() == "env-key"
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert config.resolve_key() == "file-key"


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows has no POSIX mode bits; key confidentiality comes from the profile ACL",
)
def test_key_file_permissions():
    path = config.save_key("secret")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700


def test_missing_key_message(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="setup"):
        client.ask({"x": {"type": "noul", "instructions": {"question": "q"}}})


# --- compare ---


def test_compare_happy(monkeypatch):
    monkeypatch.setattr(
        client, "ask", lambda q: choice_payload(choice="b", probs={"a": 0.45, "b": 0.55}, confidence=0.55)
    )
    data = json.loads(server.compare("which title is clearer?", "old title", "new title"))
    assert data["preferred"] == "b"
    assert data["runner_up"] == "a"
    assert data["probabilities"] == {"b": 0.55, "a": 0.45}


def test_compare_validation():
    with pytest.raises(ValueError):
        server.compare("q", "same text", "same text")
    with pytest.raises(ValueError):
        server.compare("q", "", "b")


# --- verify ---


def test_verify_happy(monkeypatch):
    captured = {}
    payload = {
        "model": "jev-test",
        "answers": {"noul": {"type": "noul", "noul": 0.82}},
        "usage": {"input_tokens": 5, "output_tokens": 1},
    }

    def fake_ask(questions):
        captured.update(questions)
        return payload

    monkeypatch.setattr(client, "ask", fake_ask)
    data = json.loads(server.verify("the sky is blue", "photo shows a blue sky"))
    assert data["noul"] == 0.82 and data["verdict"] == "supported"
    assert "the sky is blue" in captured["noul"]["instructions"]["question"]
    assert captured["noul"]["instructions"]["context"] == "photo shows a blue sky"


def test_verify_validation():
    with pytest.raises(ValueError):
        server.verify("claim", "")


# --- installer ---


@pytest.fixture
def fake_home(monkeypatch, tmp_path):
    # Path.home() reads $HOME on POSIX but %USERPROFILE% on Windows — ntpath's
    # expanduser ignores HOME entirely — so redirect both. Without this the
    # installer tests would write into the real user profile on Windows.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    return tmp_path


def test_install_pi_writes_config(fake_home):
    status = installer.install_pi("apikey_test1234", force=False)
    assert "written" in status
    data = json.loads((fake_home / ".pi" / "agent" / "mcp.json").read_text())
    entry = data["mcpServers"]["jev"]
    assert entry["command"] == "uvx"
    assert entry["args"] == ["jev-mcp-server"]
    assert entry["env"]["TYPESAFE_API_KEY"] == "apikey_test1234"
    assert entry["lifecycle"] == "lazy"


def test_install_preserves_existing_servers(fake_home):
    path = fake_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    installer.install_cursor("apikey_test1234", force=False)
    data = json.loads(path.read_text())
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["jev"]["command"] == "uvx"


def test_install_skips_existing_without_force(fake_home):
    installer.install_pi("apikey_first", force=False)
    status = installer.install_pi("apikey_second", force=False)
    assert "already configured" in status
    data = json.loads((fake_home / ".pi" / "agent" / "mcp.json").read_text())
    assert data["mcpServers"]["jev"]["env"]["TYPESAFE_API_KEY"] == "apikey_first"


def test_install_force_overwrites_with_backup(fake_home):
    installer.install_pi("apikey_first", force=False)
    installer.install_pi("apikey_second", force=True)
    data = json.loads((fake_home / ".pi" / "agent" / "mcp.json").read_text())
    assert data["mcpServers"]["jev"]["env"]["TYPESAFE_API_KEY"] == "apikey_second"
    backup = json.loads((fake_home / ".pi" / "agent" / "mcp.json.bak").read_text())
    assert backup["mcpServers"]["jev"]["env"]["TYPESAFE_API_KEY"] == "apikey_first"


def test_install_claude_fallback_writes_json(fake_home):
    status = installer.install_claude_code("apikey_test1234", force=False)
    assert "written" in status
    data = json.loads((fake_home / ".claude.json").read_text())
    assert data["mcpServers"]["jev"]["args"] == ["jev-mcp-server"]


def test_install_opencode_shape(fake_home):
    installer.install_opencode("apikey_test1234", force=False)
    data = json.loads((fake_home / ".config" / "opencode" / "opencode.json").read_text())
    assert data["mcp"]["jev"]["type"] == "local"
    assert data["mcp"]["jev"]["command"] == ["uvx", "jev-mcp-server"]
    assert data["mcp"]["jev"]["env"]["TYPESAFE_API_KEY"] == "apikey_test1234"


def test_install_codex_appends_and_skips(fake_home):
    installer.install_codex("apikey_test1234", force=False)
    text = (fake_home / ".codex" / "config.toml").read_text()
    assert "[mcp_servers.jev]" in text
    assert 'TYPESAFE_API_KEY = "apikey_test1234"' in text
    status = installer.install_codex("apikey_other", force=False)
    assert "already configured" in status


def test_cli_bad_client_exits(fake_home):
    with pytest.raises(SystemExit):
        installer.cli(["not-a-client", "--key", "k"])


def test_cli_reads_key_from_env(fake_home, monkeypatch):
    """No --key on the command line: the key must come from the env var."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_from_env")
    assert installer.cli(["pi"]) == 0
    data = json.loads((fake_home / ".pi" / "agent" / "mcp.json").read_text())
    assert data["mcpServers"]["jev"]["env"]["TYPESAFE_API_KEY"] == "apikey_from_env"


def test_resolve_key_flag_beats_env(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_env")
    assert installer._resolve_key("apikey_flag") == "apikey_flag"


# --- cross-platform robustness (macOS / Linux / Windows) ---


def _raise_eof(*args, **kwargs):
    raise EOFError


def test_install_tolerates_utf8_bom(fake_home):
    """Windows editors and PowerShell add a BOM; it must not cost your other servers."""
    path = fake_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_bytes('\ufeff{"mcpServers": {"other": {"command": "x"}}}'.encode())
    installer.install_cursor("apikey_test1234", force=False)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["jev"]["command"] == "uvx"


def test_install_refuses_to_clobber_corrupt_config(fake_home):
    """An unparseable config must be reported, never replaced wholesale."""
    path = fake_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    original = '{"mcpServers": {"other": {"command": "x"}},}'  # trailing comma
    path.write_text(original, encoding="utf-8")
    with pytest.raises(installer.InstallerError):
        installer.install_cursor("apikey_test1234", force=False)
    assert path.read_text(encoding="utf-8") == original


def test_install_refuses_non_object_json(fake_home):
    path = fake_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(installer.InstallerError):
        installer.install_cursor("apikey_test1234", force=False)
    assert path.read_text(encoding="utf-8") == "[1, 2, 3]"


def test_cli_reports_corrupt_config_as_error(fake_home):
    path = fake_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        installer.cli(["cursor", "--key", "apikey_test1234"])
    assert "not valid JSON" in str(excinfo.value)


def test_no_key_on_a_non_interactive_shell(fake_home, monkeypatch):
    """`install pi < /dev/null` used to dump a getpass EOFError traceback."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(installer.getpass, "getpass", _raise_eof)
    with pytest.raises(SystemExit) as excinfo:
        installer.cli(["pi"])
    assert "TYPESAFE_API_KEY" in str(excinfo.value)


def test_key_file_read_survives_bom(monkeypatch):
    """A Notepad-written key file must not yield a key starting with U+FEFF."""
    path = config.save_key("apikey_clean")
    path.write_bytes("\ufeffapikey_bom\n".encode())
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert config.resolve_key() == "apikey_bom"


def test_atomic_write_leaves_no_temp_file(fake_home):
    installer.install_pi("apikey_test1234", force=False)
    agent_dir = fake_home / ".pi" / "agent"
    assert [p.name for p in agent_dir.iterdir() if p.name.endswith(".tmp")] == []


def test_json_written_with_lf_on_every_os(fake_home):
    """newline="" keeps output byte-identical regardless of the host OS."""
    installer.install_pi("apikey_test1234", force=False)
    raw = (fake_home / ".pi" / "agent" / "mcp.json").read_bytes()
    assert b"\r\n" not in raw


def test_codex_preserves_existing_crlf(fake_home):
    """A CRLF config written on Windows must not end up with mixed endings."""
    path = fake_home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'model = "gpt-5"\r\n')
    installer.install_codex("apikey_test1234", force=False)
    raw = path.read_bytes()
    assert b'model = "gpt-5"\r\n\r\n[mcp_servers.jev]\r\n' in raw
    assert raw.count(b"\r\n") == raw.count(b"\n")  # no bare LF
