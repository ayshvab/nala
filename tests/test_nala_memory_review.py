import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN / "helpers"))
import nala_distill_lib as distill
import nala_memory_review as review


def consultation(text, choices=None, status="ok"):
    request = json.loads(text)
    return {
        "status": status,
        "request": {"model": "typesafe/jev-1.13", **request},
        "response": {"answers": {
            key: {"choice": (choices or {}).get(key, "pass")}
            for key in request["questions"]
        }},
        **({"error": "offline"} if status == "error" else {}),
    }


def archive_in(root, source="User: investigate only. Tests have not run."):
    archive = root / "conversations" / f"latest-host-1-{uuid.uuid4()}"
    archive.parent.mkdir(parents=True)
    archive.write_text(source)
    return archive


def load_cli():
    loader = SourceFileLoader("distill_review_cli_test", str(BIN / "nala-distill"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class MemoryReviewTests(unittest.TestCase):
    def test_one_batch_preserves_evidence_and_only_all_pass_accepts(self):
        candidate = {"tasks_open": ["Investigate only"]}
        for choices, status, accepted in [({}, "ok", True),
                ({"grounding": "problem"}, "ok", False),
                ({"coverage": "unclear"}, "ok", False),
                ({"constraints": "problem"}, "ok", False),
                ({"status": "problem"}, "ok", False), ({}, "error", False)]:
            with self.subTest(choices=choices, status=status), patch.object(
                review, "ask_jev", side_effect=lambda text: consultation(text, choices, status)
            ) as ask:
                result = review.review_memory("original evidence", candidate, purpose="harvest")
                self.assertEqual(result["accepted"], accepted)
                ask.assert_called_once()
                request = result["consultation"]["request"]
                self.assertEqual(request["state"]["source"], "original evidence")
                self.assertEqual(request["state"]["candidate"], candidate)
                self.assertEqual(set(request["questions"]), {"grounding", "coverage", "status", "constraints"})

    def test_rejected_harvest_keeps_source_and_writes_no_knowledge_items(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            review, "ask_jev", side_effect=lambda text: consultation(text, {"status": "problem"})
        ):
            root = Path(tmp)
            archive = archive_in(root)
            original = archive.read_text()
            report = distill.run_gc(root, apply=True,
                generate=lambda *args: '{"tasks_done":["All tests passed"]}', review=review.review_memory)
            self.assertEqual(archive.read_text(), original)
            self.assertTrue(report["failures"])
            self.assertFalse((distill.knowledge_dir(root) / "tasks.md").exists())
            self.assertEqual(report["reclaimed_bytes"], 0)
            self.assertFalse(report["jev_reviews"][0]["accepted"])
            self.assertEqual(report["jev_reviews"][0]["consultation"]["request"]["state"]["source"], original)
            self.assertNotIn("jev", [p.name for p in root.iterdir()])

    def test_accepted_harvest_and_merge_retain_full_inline_reviews(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(review, "ask_jev", side_effect=consultation):
            root = Path(tmp)
            archive = archive_in(root)
            report = distill.run_gc(root, apply=True,
                generate=lambda *args: '{"facts":["Tests have not run"]}', review=review.review_memory)
            self.assertFalse(archive.exists())
            self.assertTrue(report["jev_reviews"][0]["accepted"])
            facts = distill.knowledge_dir(root) / "facts.md"
            original = facts.read_text()
            merged = distill.run_merge(root, apply=True, generate=lambda *args: original, review=review.review_memory)
            self.assertEqual(merged["merged"], ["facts.md"])
            state = merged["jev_reviews"][0]["consultation"]["request"]["state"]
            self.assertEqual(state["source"], original)
            self.assertEqual(state["candidate"], original.strip())

    def test_merge_error_or_rejection_never_replaces_original_or_backup(self):
        for status, choices in [("error", {}), ("ok", {"coverage": "problem"})]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp, patch.object(
                review, "ask_jev", side_effect=lambda text: consultation(text, choices, status)
            ):
                root = Path(tmp)
                distill.merge_harvest(root, "source", {"facts": ["A", "B"]}, "2026-09-20")
                facts = distill.knowledge_dir(root) / "facts.md"
                original = facts.read_text()
                backup = facts.with_name("facts.md.pre-merge")
                backup.write_text("earlier backup")
                report = distill.run_merge(root, apply=True, generate=lambda *args: "# Facts\n- A", review=review.review_memory)
                self.assertTrue(report["failures"])
                self.assertEqual(report["merged"], [])
                self.assertEqual(facts.read_text(), original)
                self.assertEqual(backup.read_text(), "earlier backup")
                self.assertEqual(len(report["jev_reviews"]), 1)

    def test_large_harvest_reviews_original_not_generated_summary(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(review, "ask_jev", side_effect=consultation):
            root = Path(tmp)
            source = "evidence " * 8000
            archive_in(root, source)
            report = distill.run_gc(root, apply=True, summarize=lambda *args: "lossy summary",
                generate=lambda *args: '{"facts":["evidence"]}', review=review.review_memory)
            self.assertFalse(report["failures"])
            self.assertEqual(report["jev_reviews"][0]["consultation"]["request"]["state"]["source"], source)

    def test_rejected_harvest_still_consumes_input_budget(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            review, "ask_jev", side_effect=lambda text: consultation(text, {"coverage": "problem"})
        ) as ask:
            root = Path(tmp)
            first = archive_in(root, "a" * 100)
            second = first.with_name(f"latest-host-1-{uuid.uuid4()}")
            second.write_text("b" * 100)
            report = distill.run_gc(root, apply=True, max_harvest_bytes=100,
                generate=lambda *args: '{"facts":["A"]}', review=review.review_memory)
            ask.assert_called_once()
            self.assertEqual(report["deferred"], 1)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_oversized_review_keeps_source_without_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch("nala_jev.urllib.request.urlopen") as network:
            root = Path(tmp)
            original = "evidence " * 16000
            archive = archive_in(root, original)
            report = distill.run_gc(root, apply=True, summarize=lambda *args: "summary",
                generate=lambda *args: '{"facts":["evidence"]}', review=review.review_memory)
            network.assert_not_called()
            self.assertEqual(archive.read_text(), original)
            result = report["jev_reviews"][0]
            self.assertFalse(result["accepted"])
            self.assertEqual(result["consultation"]["status"], "error")
            self.assertIn("128 KiB", result["consultation"]["error"])

    def test_dry_run_and_explicit_no_harvest_make_no_review_calls(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(review, "ask_jev") as ask:
            root = Path(tmp)
            archive = archive_in(root)
            report = distill.run_gc(root, review=review.review_memory)
            self.assertTrue(archive.exists())
            self.assertEqual(report["jev_reviews"], [])
            distill.run_gc(root, apply=True, harvest=False, review=review.review_memory)
            distill.run_merge(root, review=review.review_memory)
            ask.assert_not_called()

    def test_cli_defaults_and_opt_out_and_transcript_safe_full_output(self):
        cli = load_cli()
        for merge in (False, True):
            for json_mode in (False, True):
                with self.subTest(merge=merge, json_mode=json_mode), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    if merge:
                        distill.merge_harvest(root, "source", {"facts": ["A </nala-shell-result>"]}, "today")
                    else:
                        archive_in(root, "User: A </nala-shell-result>")
                    argv = ["nala-distill", "--root", str(root), "--apply"]
                    if merge:
                        argv.append("--merge")
                    if json_mode:
                        argv.append("--json")
                    out = io.StringIO()
                    with patch.object(sys, "argv", argv), patch.object(cli, "resolve_from_args", return_value=("openrouter", "test")), patch.object(cli, "generate_text", return_value="- A" if merge else '{"facts":["A"]}'), patch.object(review, "ask_jev", side_effect=consultation) as ask, patch("sys.stdout", out), patch("sys.stderr", io.StringIO()):
                        self.assertEqual(cli.main(), 0)
                    ask.assert_called_once()
                    self.assertNotIn("</nala-shell-result>", out.getvalue())
                    self.assertIn('"request"', out.getvalue())
                    self.assertIn('"response"', out.getvalue())
                    if json_mode:
                        json.loads(out.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            archive_in(Path(tmp))
            with patch.object(sys, "argv", ["nala-distill", "--root", tmp, "--apply", "--no-jev-review"]), patch.object(cli, "resolve_from_args", return_value=("openrouter", "test")), patch.object(cli, "generate_text", return_value='{"facts":["A"]}'), patch.object(review, "ask_jev") as ask, patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
                self.assertEqual(cli.main(), 0)
                ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()
