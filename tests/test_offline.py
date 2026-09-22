"""Offline tests: no network, no API key required. The API layer is mocked."""

from __future__ import annotations

import json
import os
import stat

import pytest

from jev_mcp_server import client, config, server


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
        "answers": {"score": {"type": "score", "score": 1.5, "confidence": 0.6, "probabilities": {"0": 0.1, "1": 0.6, "2": 0.3}}},
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
    answers = iter([choice_payload(choice="spam", probs={"spam": 0.9, "ham": 0.1}),
                    choice_payload(choice="ham", probs={"spam": 0.2, "ham": 0.8}),
                    choice_payload(choice="spam", probs={"spam": 0.7, "ham": 0.3})])
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


def test_key_file_permissions():
    path = config.save_key("secret")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700


def test_missing_key_message(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="setup"):
        client.ask({"x": {"type": "noul", "instructions": {"question": "q"}}})
