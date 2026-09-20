"""Opt-in live fixture check: uv run python tests/eval_jev_memory.py

Uses the saved OpenRouter key and makes seven paid Jev requests. Full exchanges
go to stdout, never to request/response files. These small fixtures check wiring
and obvious regressions; they do not estimate accuracy on real conversations.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin/helpers"))
from nala_jev import dumps
from nala_memory_review import review_memory


def fixtures():
    source = (
        "User requires read-only investigation. Do not edit files. Parser tests: "
        "6 passed. Full suite has not run. Next task: investigate loader cache "
        "invalidation. Accepted decision: retain existing JSON format."
    )
    faithful = {
        "facts": ["Parser tests: 6 passed; full suite not run"],
        "decisions": ["Read-only investigation; no edits", "Retain existing JSON format"],
        "tasks_open": ["Investigate loader cache invalidation"],
    }
    for name, candidate, expected in [
        ("faithful_harvest", faithful, True),
        ("invented_success", {**faithful, "facts": ["All tests passed"]}, False),
        ("reversed_constraint", {**faithful, "decisions": ["Proceed with file edits", "Retain existing JSON format"]}, False),
        ("lost_task", {**faithful, "tasks_open": []}, False),
    ]:
        yield name, "harvest", source, candidate, expected

    # A real smoke-test failure: the constraint survives only as past compliance.
    source = (
        "<user-prompt>Investigate loader cache invalidation, read-only. Do not edit project source. Retain the current JSON config format.</user-prompt>\n"
        "<nala-shell-result>exit_code: 0\nstdout: tests/test_parser.py: 6 passed. Only parser tests ran; full suite has not run.</nala-shell-result>\n"
        "<nala-response>Decision: retain the JSON format. Investigation is read-only; no project source was edited. Parser tests passed (6); full suite unrun. Cache invalidation remains unverified. Open task: investigate loader cache invalidation.</nala-response>\n"
    )
    historical = {
        "facts": [
            {"statement": "Loader cache invalidation remains unverified.", "detail": ""},
            {"statement": "Only tests/test_parser.py was run; the full test suite has not run.", "detail": ""},
            {"statement": "tests/test_parser.py contains parser tests.", "detail": ""},
        ],
        "decisions": [{"statement": "Retain the current JSON configuration format.", "detail": "The user required retaining JSON; no format change was pursued."}],
        "tasks_done": [
            {"statement": "Ran parser tests in tests/test_parser.py.", "detail": "6 passed; only parser tests ran."},
            {"statement": "Kept the investigation read-only and did not edit project source.", "detail": "Per user instruction."},
        ],
        "tasks_open": [{"statement": "Investigate loader cache invalidation.", "detail": "Started read-only; cache invalidation remains unverified."}],
        "questions": [{"statement": "Does loader cache invalidation work correctly?", "detail": "Raised by the investigation and not answered."}],
        "playbooks": [], "files": [],
    }
    yield "active_constraint_as_history", "harvest", source, historical, False

    source = (
        "# Facts\n- Loader caches parsed JSON [from: conv-a, 2026-09-20]\n"
        "- Loader caches parsed JSON [from: conv-b, 2026-09-20]\n"
        "- Cache invalidation is unverified [from: conv-a, 2026-09-20]"
    )
    merged = "# Facts\n- Loader caches parsed JSON [from: conv-a, 2026-09-20] [from: conv-b, 2026-09-20]"
    yield "faithful_merge", "merge", source, merged + "\n- Cache invalidation is unverified [from: conv-a, 2026-09-20]", True
    yield "lost_qualification", "merge", source, merged, False


def main():
    results = []
    for name, purpose, source, candidate, expected in fixtures():
        result = review_memory(source, candidate, purpose=purpose)
        matches = result["consultation"]["status"] == "ok" and result["accepted"] == expected
        results.append({"case": name, "expected_accept": expected, "matches": matches, **result})
    print(dumps(results))
    return 0 if all(result["matches"] for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
