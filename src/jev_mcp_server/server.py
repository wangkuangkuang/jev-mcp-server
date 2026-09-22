"""MCP server: Jev (TypeSafe System One) judgment tools.

Tools map 1:1 to the official System One question types — ``choice``, ``score``,
``noul`` — plus ``classify`` (batch) and ``setup`` (one-time key onboarding).

Jev returns decisions and calibrated probabilities, never explanations: any
"reason" an assistant adds on top is its own interpretation of the numbers.
"""

from __future__ import annotations

import json
import math
import sys
import time

from mcp.server.fastmcp import FastMCP

from . import cache, client, config

mcp = FastMCP("jev")

MAX_OPTIONS = 100
MAX_ITEMS = 100


def _answer(questions: dict) -> tuple[dict, bool]:
    """Cache-aware entry to the API. Returns (response, from_cache)."""
    cached = cache.lookup(questions)
    if cached is not None:
        return cached, True
    result = client.ask(questions)
    cache.store(questions, result)
    return result, False


def _meta(result: dict, started: float, from_cache: bool) -> dict:
    usage = result.get("usage", {})
    if from_cache:
        usage = {"input_tokens": 0, "output_tokens": 0, "cached": True}
    return {
        "model": result.get("model", "jev-latest"),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": usage,
    }


def _validated_choice(answer: dict, ids: set) -> dict:
    try:
        probs = answer["probabilities"]
        numbers = [*probs.values(), answer["confidence"]]
        valid = (
            answer["choice"] in ids
            and set(probs) == ids
            and all(type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1 for n in numbers)
            and abs(sum(probs.values()) - 1) < 0.02
            and probs[answer["choice"]] >= max(probs.values()) - 1e-6
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Invalid TypeSafe response; no decision returned.")
    return answer


def _validated_score(answer: dict, count: int) -> tuple[float, dict[int, float]]:
    """Validate a score response and return ``(value, probabilities)``.

    Validation lives here rather than inline in ``score`` so ``value`` and the
    probabilities are only ever read inside the guarded block — reading them
    after a ``valid`` flag that an ``except`` can clear is correct at runtime but
    impossible to verify statically, and that static check is what catches the
    next edit to this function.

    The returned keys are ``int``, not the wire's digit strings: the check below
    already proves they are exactly ``0..count-1``, so this is the one place
    that knows it, rather than leaving callers an unstated assumption.
    """
    try:
        raw = answer["probabilities"]
        value = answer["score"]
        valid = (
            type(value) in (int, float)
            and math.isfinite(value)
            and 0 <= value <= count - 1
            and set(raw) == {str(i) for i in range(count)}
            and all(type(v) in (int, float) and 0 <= v <= 1 for v in raw.values())
            and abs(sum(raw.values()) - 1) < 0.02
        )
        if valid:
            # Keys are exactly "0".."count-1" (checked above), so int() cannot
            # raise and every index lands in range. Returning from inside the
            # guarded block is what keeps this statically checkable.
            return value, {int(key): prob for key, prob in raw.items()}
    except (KeyError, TypeError, ValueError):
        pass
    raise ValueError("Invalid TypeSafe response; no score returned.")


def _validated_options(options: dict[str, str]) -> None:
    if len(options) != len(set(options)) or not 2 <= len(options) <= MAX_OPTIONS:
        raise ValueError(f"Provide between 2 and {MAX_OPTIONS} uniquely-keyed options.")
    if any(not str(k).strip() or not str(v).strip() for k, v in options.items()):
        raise ValueError("Option ids and descriptions must be non-empty strings.")


@mcp.tool()
def choice(question: str, options: dict[str, str], context: str = "") -> str:
    """Ask Jev (TypeSafe System One) to pick ONE of 2-100 mutually exclusive options, with calibrated probabilities.

    The official `choice` question type — for fast, cheap structured decisions:
    triage, routing, classification, prioritization, tie-breaking among enumerated
    candidates. Returns probabilities over ALL options (not just the winner), so
    near-ties are visible. NOT for open-ended generation or multi-step reasoning —
    use an LLM for those.

    Args:
        question: The decision, e.g. "Which error class is most likely the root cause?"
        options: Mapping of short unique id -> one-line description. 2-100 options.
        context: Optional background facts that inform the decision. Keep it short.

    Returns:
        JSON string: {choice, confidence, probabilities (sorted desc), runner_up,
                      model, latency_ms, usage}
    """
    _validated_options(options)
    started = time.perf_counter()
    result, from_cache = _answer(
        {
            "decision": {
                "type": "choice",
                "criteria": options,
                "instructions": {"question": question, "context": context},
            }
        }
    )
    answer = _validated_choice(result.get("answers", {}).get("decision", {}), set(options))
    probs = dict(sorted(answer["probabilities"].items(), key=lambda kv: -kv[1]))
    ranked = list(probs)
    return json.dumps(
        {
            "choice": answer["choice"],
            "confidence": answer["confidence"],
            "probabilities": probs,
            "runner_up": ranked[1] if len(ranked) > 1 else None,
            **_meta(result, started, from_cache),
        },
        ensure_ascii=False,
    )


@mcp.tool()
def score(question: str, levels: list[str], context: str = "") -> str:
    """Ask Jev (TypeSafe System One) to grade something on an ORDERED scale of 2-8 levels.

    The official `score` question type — risk/severity/quality rubrics, e.g.
    levels ["minor", "moderate", "severe", "critical"]. Returns a fractional
    0-based index into `levels` (1.88 = between levels[1] and levels[2], leaning
    to levels[2]), plus confidence and per-level probabilities.

    Args:
        question: What to grade, e.g. "Regression risk of renaming public config key X".
        levels: 2-8 unique ordered scale points, low to high.
        context: Optional background facts. Keep it short.

    Returns:
        JSON string: {score, nearest_level, confidence, probabilities (sorted desc),
                      model, latency_ms, usage}
    """
    if not 2 <= len(levels) <= 8:
        raise ValueError("Provide between 2 and 8 levels.")
    if len(set(levels)) != len(levels) or any(not str(level).strip() for level in levels):
        raise ValueError("Levels must be unique, non-empty strings.")
    started = time.perf_counter()
    result, from_cache = _answer(
        {"score": {"type": "score", "criteria": levels, "instructions": {"question": question, "context": context}}}
    )
    answer = result.get("answers", {}).get("score", {})
    value, probs = _validated_score(answer, len(levels))
    readable = {levels[i]: v for i, v in probs.items()}
    nearest = min(probs, key=lambda i: abs(i - value))
    return json.dumps(
        {
            "score": value,
            "nearest_level": levels[nearest],
            "confidence": answer.get("confidence"),
            "probabilities": dict(sorted(readable.items(), key=lambda kv: -kv[1])),
            **_meta(result, started, from_cache),
        },
        ensure_ascii=False,
    )


@mcp.tool()
def noul(question: str, context: str = "") -> str:
    """Ask Jev (TypeSafe System One) a yes/no question; returns a 0-1 degree (>= 0.5 leans yes).

    The official `noul` question type — fast, cheap binary checks: "is this change
    breaking?", "does this log line match the reported symptom?". No probability
    list, just the degree. NOT for questions that need multi-step reasoning — use
    an LLM for those.

    Args:
        question: A yes/no question, e.g. "Is renaming a public config key a breaking change?"
        context: Optional background facts. Keep it short.

    Returns:
        JSON string: {noul, verdict, model, latency_ms, usage}
    """
    started = time.perf_counter()
    result, from_cache = _answer({"noul": {"type": "noul", "instructions": {"question": question, "context": context}}})
    answer = result.get("answers", {}).get("noul", {})
    value = answer.get("noul")
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid TypeSafe response; no verdict returned.")
    return json.dumps(
        {"noul": value, "verdict": "yes" if value >= 0.5 else "no", **_meta(result, started, from_cache)},
        ensure_ascii=False,
    )


@mcp.tool()
def compare(question: str, a: str, b: str, context: str = "") -> str:
    """Ask Jev (TypeSafe System One) which of two candidates — a or b — better satisfies the question.

    The official `choice` type as a focused A/B judgment: "which error message is
    clearer?", "which rollout plan fits this service better?", "title A or B?".
    Returns the preferred side PLUS the probability split, so a 52/48 coin flip
    is visible instead of hidden.

    Args:
        question: What to judge, phrased so one side can win, e.g. "Which error message is clearer?"
        a: Candidate A text.
        b: Candidate B text.
        context: Optional background facts. Keep it short.

    Returns:
        JSON string: {preferred: "a"|"b", confidence, probabilities: {a, b},
                      runner_up, model, latency_ms, usage}
    """
    a = str(a).strip()
    b = str(b).strip()
    if not a or not b:
        raise ValueError("Both a and b must be non-empty strings.")
    if a == b:
        raise ValueError("a and b must differ, otherwise there is nothing to compare.")
    options = {"a": a, "b": b}
    started = time.perf_counter()
    result, from_cache = _answer(
        {
            "decision": {
                "type": "choice",
                "criteria": options,
                "instructions": {"question": question, "context": context},
            }
        }
    )
    answer = _validated_choice(result.get("answers", {}).get("decision", {}), {"a", "b"})
    # Annotated so the value type survives the loose ``dict`` that
    # ``_validated_choice`` returns; without it ``min`` below cannot be checked.
    ranked: dict[str, float] = answer["probabilities"]
    probs: dict[str, float] = dict(sorted(ranked.items(), key=lambda kv: -kv[1]))
    return json.dumps(
        {
            "preferred": answer["choice"],
            "confidence": answer["confidence"],
            "probabilities": probs,
            "runner_up": min(probs, key=lambda key: probs[key]),
            **_meta(result, started, from_cache),
        },
        ensure_ascii=False,
    )


@mcp.tool()
def verify(claim: str, evidence: str) -> str:
    """Check ONE claim against supplied evidence; returns a 0-1 support degree (>= 0.5 leans supported).

    The official `noul` type framed as claim-vs-evidence: fact-check a report
    line against its source, confirm a log excerpt actually shows the reported
    symptom, validate a summary against the document it summarizes. Evidence is
    passed as context — Jev judges only what it is given, never invents evidence.

    Args:
        claim: A single falsifiable claim, e.g. "The 404s come from edhub, not the gateway".
        evidence: The evidence text to check the claim against (log excerpt, doc paragraph, diff).

    Returns:
        JSON string: {noul, verdict, model, latency_ms, usage}
    """
    claim = str(claim).strip()
    evidence = str(evidence).strip()
    if not claim or not evidence:
        raise ValueError("Both claim and evidence must be non-empty strings.")
    started = time.perf_counter()
    result, from_cache = _answer(
        {
            "noul": {
                "type": "noul",
                "instructions": {
                    "question": f"Is this claim supported by the evidence?\nClaim: {claim}",
                    "context": evidence,
                },
            }
        }
    )
    answer = result.get("answers", {}).get("noul", {})
    value = answer.get("noul")
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid TypeSafe response; no verdict returned.")
    return json.dumps(
        {
            "noul": value,
            "verdict": "supported" if value >= 0.5 else "not supported",
            **_meta(result, started, from_cache),
        },
        ensure_ascii=False,
    )


@mcp.tool()
def classify(
    items: list[str],
    options: dict[str, str],
    question: str = "Which category does this item belong to?",
    context: str = "",
) -> str:
    """Batch-classify up to 100 items against ONE shared set of categories using Jev.

    Runs the official `choice` question type once per item and aggregates the
    results — routing support tickets, labeling log lines, triaging inbox items
    against your own label set. Much cheaper and faster than an LLM for
    mechanical labeling.

    Args:
        items: 1-100 non-empty strings to classify.
        options: Mapping of short unique id -> one-line category description. 2-100 options.
        question: Per-item question; the item itself is appended automatically.
        context: Optional background facts shared by all items.

    Returns:
        JSON string: {results: [{item, choice, confidence, probabilities}], summary
                      (counts per choice, sorted desc), model, total_latency_ms,
                      usage: {input_tokens, output_tokens, calls, cached_calls}}
    """
    if not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError(f"Provide between 1 and {MAX_ITEMS} items.")
    if any(not str(item).strip() for item in items):
        raise ValueError("Items must be non-empty strings.")
    _validated_options(options)
    ids = set(options)
    results = []
    summary: dict[str, int] = {}
    usage_in = usage_out = calls = cached_calls = 0
    model = "jev-latest"
    started = time.perf_counter()
    for item in items:
        payload = {
            "decision": {
                "type": "choice",
                "criteria": options,
                "instructions": {"question": f"{question}\nItem: {item}", "context": context},
            }
        }
        result, from_cache = _answer(payload)
        answer = _validated_choice(result.get("answers", {}).get("decision", {}), ids)
        picked = answer["choice"]
        summary[picked] = summary.get(picked, 0) + 1
        results.append(
            {
                "item": item,
                "choice": picked,
                "confidence": answer["confidence"],
                "probabilities": dict(sorted(answer["probabilities"].items(), key=lambda kv: -kv[1])),
            }
        )
        model = result.get("model", model)
        item_usage = result.get("usage", {})
        if from_cache:
            cached_calls += 1
        else:
            usage_in += item_usage.get("input_tokens", 0)
            usage_out += item_usage.get("output_tokens", 0)
            calls += 1
    return json.dumps(
        {
            "results": results,
            "summary": dict(sorted(summary.items(), key=lambda kv: -kv[1])),
            "model": model,
            "total_latency_ms": round((time.perf_counter() - started) * 1000),
            "usage": {
                "input_tokens": usage_in,
                "output_tokens": usage_out,
                "calls": calls,
                "cached_calls": cached_calls,
            },
        },
        ensure_ascii=False,
    )


@mcp.tool()
def setup(api_key: str) -> str:
    """One-time onboarding: verify a TypeSafe API key with a live call, then store it locally.

    Use when TYPESAFE_API_KEY is not set in the server environment: pass your key
    once (get one at https://console.typesafe.ai/settings/keys). It is verified
    against the live API, then saved to ~/.config/jev-mcp/key (permissions 0600)
    and never echoed back. An existing TYPESAFE_API_KEY env var always takes
    precedence over the stored file.

    Args:
        api_key: Your TypeSafe API key (from console.typesafe.ai/settings/keys).

    Returns:
        JSON string: {ok, stored_path, verified}
    """
    key = str(api_key).strip()
    if not key:
        raise ValueError("api_key must be a non-empty string.")
    client.verify_key(key)
    path = config.save_key(key)
    return json.dumps({"ok": True, "stored_path": str(path), "verified": True}, ensure_ascii=False)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        from . import installer

        sys.exit(installer.cli(sys.argv[2:]))
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
