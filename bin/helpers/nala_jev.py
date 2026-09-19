"""Jev's batched Decisions API and inline results (shared by CLI/tag)."""

from datetime import datetime, timezone
from http.client import HTTPException
import json
import math
import os
import time
import urllib.error
import urllib.request

from nala_llm import credential_env_var

MODEL = "typesafe/jev-1.13"
ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MAX_REQUEST_BYTES = 128 * 1024
TIMEOUT_SECONDS = 45


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        _constant(value)
    return parsed


def loads(text):
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)


def dumps(value):
    # JSON escapes keep all provider/input strings inside their transcript block.
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def validate_request(value):
    _require(isinstance(value, dict) and set(value) == {"state", "questions"},
             "Request must contain exactly state and questions; model is selected by nala-ask-jev.")
    _require(isinstance(value["state"], (str, dict, list)), "state must be a string, object, or array.")
    questions = value["questions"]
    _require(isinstance(questions, dict) and bool(questions), "questions must be a nonempty object.")
    for name, q in questions.items():
        _require(_text(name) and isinstance(q, dict), "Each question needs a nonempty ID and an object.")
        _require(set(q) <= {"type", "instructions", "criteria"}, f"Question {name}: unknown fields.")
        kind = q.get("type")
        _require(kind in ("choice", "score", "noul"), f"Question {name}: type must be choice, score, or noul.")
        instructions = q.get("instructions")
        _require((_text(instructions) or isinstance(instructions, (dict, list)) and bool(instructions)),
                 f"Question {name}: instructions must be nonempty text, an object, or an array.")
        criteria = q.get("criteria")
        if kind == "choice":
            _require(isinstance(criteria, dict) and len(criteria) >= 2 and
                     all(_text(k) and (v is None or _text(v)) for k, v in criteria.items()),
                     f"Question {name}: choice criteria need at least two named options with text or null descriptions.")
        elif kind == "score":
            _require(isinstance(criteria, list) and len(criteria) >= 2 and all(_text(v) for v in criteria),
                     f"Question {name}: score criteria need at least two ordered text levels.")
        elif "criteria" in q:
            _require(isinstance(criteria, dict) and set(criteria) == {"true", "false"} and
                     all(_text(v) for v in criteria.values()),
                     f"Question {name}: optional noul criteria must describe true and false.")
    payload = {"model": MODEL, **value}
    _require(len(dumps(payload).encode("utf-8")) <= MAX_REQUEST_BYTES,
             f"Request exceeds the local {MAX_REQUEST_BYTES}-byte limit; select smaller evidence excerpts.")
    return payload


def validate_response(response, questions):
    _require(isinstance(response, dict), "Jev response must be an object.")
    _require(_text(response.get("model")), "Jev response is missing its model identity.")
    answers = response.get("answers")
    _require(isinstance(answers, dict) and set(answers) == set(questions), "Jev must return exactly one answer per question ID.")
    for name, q in questions.items():
        a = answers[name]
        kind = q["type"]
        _require(isinstance(a, dict) and a.get("type") == kind, f"Answer {name}: wrong type.")
        if kind == "noul":
            _require(_number(a.get("noul"), 0, 1), f"Answer {name}: noul must be a finite probability.")
            continue
        expected = set(q["criteria"]) if kind == "choice" else {str(i) for i in range(len(q["criteria"]))}
        probs = a.get("probabilities")
        _require(isinstance(probs, dict) and set(probs) == expected and
                 all(_number(p, 0, 1) for p in probs.values()), f"Answer {name}: invalid probability distribution.")
        # Provider distributions can be rounded; never normalize or change them.
        _require(math.isclose(sum(probs.values()), 1, abs_tol=0.02), f"Answer {name}: probabilities must sum to one (rounding tolerance 0.02).")
        _require(_number(a.get("confidence"), 0, 1), f"Answer {name}: invalid confidence.")
        if kind == "choice":
            _require(isinstance(a.get("choice"), str) and a["choice"] in expected,
                     f"Answer {name}: choice is outside the supplied options.")
        else:
            _require(_number(a.get("score"), 0, len(expected) - 1), f"Answer {name}: score is outside the rubric.")
            _require(a.get("legend") == {str(i): label for i, label in enumerate(q["criteria"])},
                     f"Answer {name}: legend differs from the supplied rubric.")
    if "usage" in response:
        usage = response["usage"]
        _require(isinstance(usage, dict), "Invalid usage object.")
        for key in ("input_tokens", "output_tokens"):
            if key in usage:
                _require(type(usage[key]) is int and usage[key] >= 0, f"Invalid usage.{key}.")
        if "cost" in usage:
            _require(_number(usage["cost"], 0, float("inf")), "Invalid usage.cost.")


def ask_jev(text):
    """One state × many questions → an inline result; this function writes no files.

    Failures return status=error. The caller owns the transcript. API calls are
    never automatically retried, including when a response may have been lost.
    """
    started = time.monotonic()
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "error", "endpoint": ENDPOINT, "request_text": text,
    }
    try:
        _require(len(text.encode("utf-8")) <= MAX_REQUEST_BYTES, "Input exceeds the local 128 KiB limit.")
        payload = validate_request(loads(text))
        record["request"] = payload
        del record["request_text"]
        env_var = credential_env_var("openrouter")
        if env_var is None:
            raise ValueError("OpenRouter missing credentials: set OPENROUTER_API_KEY or save ~/.config/nala/openrouter.key.")
        key = os.environ[env_var]
        req = urllib.request.Request(ENDPOINT, data=dumps(payload).encode("utf-8"), headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as http:
                raw = http.read().decode("utf-8").replace(key, "[redacted credential]")
        except urllib.error.HTTPError as exc:
            record["http_status"] = exc.code
            record["raw_response"] = exc.read().decode("utf-8", errors="replace").replace(key, "[redacted credential]")
            raise ValueError(f"OpenRouter Decisions returned HTTP {exc.code}; see raw_response in this result.") from exc
        record["http_status"] = 200
        # Retain malformed responses as text; strict JSON rejects NaN/duplicates.
        record["raw_response"] = raw
        body = loads(raw)
        record["response"] = body
        del record["raw_response"]
        validate_response(body, payload["questions"])
        record["status"] = "ok"
    except (ValueError, OSError, urllib.error.URLError, HTTPException) as exc:
        record.update(status="error", error=str(exc))
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return record


def human_result(record):
    lines = ["Request:", dumps(record.get("request", record.get("request_text"))), f"Jev: {record['status']}"]
    if record["status"] == "ok":
        response = record["response"]
        lines.append(f"Model: {response['model']}")
        for name, answer in response["answers"].items():
            kind = answer["type"]
            value = answer["choice"] if kind == "choice" else answer[kind]
            lines.append(f"{name}: {value}" + (f" (confidence {answer['confidence']})" if "confidence" in answer else ""))
            if "probabilities" in answer:
                lines.append("  probabilities: " + json.dumps(answer["probabilities"]))
        if "usage" in response:
            lines.append("Usage: " + json.dumps(response["usage"]))
    else:
        lines.append("Error: " + record["error"])
    lines.append(f"Elapsed: {record['elapsed_seconds']} seconds")
    return "\n".join(lines)
