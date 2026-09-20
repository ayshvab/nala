"""The optional Jev tool must never be a dependency of ordinary nala work."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import uuid

from test_nala_jev import BIN, http_response, jev, load_tool, request, response


class JevOptInTests(unittest.TestCase):
    def test_disabled_by_default_blocks_native_and_standalone_without_credentials(self):
        mod = load_tool("nala")
        cli = load_tool("nala-ask-jev")
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text("{}")
            env = {"NALA_CONFIG": str(config)}
            with patch.dict(os.environ, env), patch.object(jev, "credential_env_var") as creds, patch.object(jev.urllib.request, "urlopen") as api:
                os.environ.pop("NALA_JEV_ENABLED", None)
                result = jev.ask_jev(json.dumps(request()))
                self.assertEqual(result["status"], "error")
                self.assertIn("disabled", result["error"].lower())
                conv = Path(tmp) / "conversation"; conv.write_text("")
                tags, _, _ = mod.parse_response('<nala-ask-jev>' + json.dumps(request()) + '</nala-ask-jev>')
                _, _, continued = mod.process_tags(tags, conv, Path(tmp), mod.LlmSettings("openrouter", "main"), BIN / "nala", "test", mod.TokenStats())
                self.assertTrue(continued)
                self.assertIn("disabled", conv.read_text().lower())
                with patch.object(sys, "argv", ["nala-ask-jev", "--file", "-", "--json"]), patch("sys.stdin", io.StringIO(json.dumps(request()))), patch("sys.stdout", new_callable=io.StringIO) as out:
                    self.assertEqual(cli.main(), 1)
                self.assertIn("disabled", json.loads(out.getvalue())["error"].lower())
                creds.assert_not_called()
                api.assert_not_called()

    def test_config_requires_boolean_true_and_environment_overrides_it(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            os.environ.pop("NALA_JEV_ENABLED", None)
            config = Path(tmp) / "config.json"
            for value, expected in [(True, True), (False, False), ("true", False), (1, False), (None, False)]:
                config.write_text(json.dumps({"jev_enabled": value}))
                self.assertEqual(jev.jev_enabled(config), expected)
            config.write_text('{"jev_enabled": true}')
            os.environ["NALA_JEV_ENABLED"] = "0"
            self.assertFalse(jev.jev_enabled(config))
            config.write_text('{"jev_enabled": false}')
            os.environ["NALA_JEV_ENABLED"] = "1"
            self.assertTrue(jev.jev_enabled(config))
            os.environ["NALA_JEV_ENABLED"] = "typo"
            self.assertFalse(jev.jev_enabled(config))
            os.environ.pop("NALA_JEV_ENABLED")
            config.write_text("not JSON")
            self.assertFalse(jev.jev_enabled(config))

    def test_custom_config_enables_native_tag_and_cli(self):
        mod = load_tool("nala")
        cli = load_tool("nala-ask-jev")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch.object(jev.urllib.request, "urlopen", side_effect=lambda *a, **kw: http_response(response())) as api:
            os.environ.pop("NALA_JEV_ENABLED", None)
            config = Path(tmp) / "custom.json"; config.write_text('{"jev_enabled":true}')
            conv = Path(tmp) / "conversation"; conv.write_text("")
            tags, _, _ = mod.parse_response('<nala-ask-jev>' + json.dumps(request()) + '</nala-ask-jev>')
            mod.process_tags(tags, conv, Path(tmp), mod.LlmSettings("openrouter", "main", config_path=config), BIN / "nala", "test", mod.TokenStats())
            self.assertIn('"status": "ok"', conv.read_text())
            with patch.object(sys, "argv", ["nala-ask-jev", "--config", str(config), "--file", "-", "--json"]), patch("sys.stdin", io.StringIO(json.dumps(request()))), patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(cli.main(), 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "ok")
            self.assertEqual(api.call_count, 2)

    def test_disabled_tool_is_not_advertised_in_initial_context(self):
        mod = load_tool("nala")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"; bindir.mkdir()
            tool = bindir / "nala-ask-jev"
            tool.write_text('#!/bin/sh\necho "JEV_DISCOVERY_MARKER"\n'); tool.chmod(0o755)
            with patch.object(mod, "tool_search_dirs", return_value=[bindir]), patch.object(mod, "git_repo_context", return_value=""), patch.object(mod, "load_root_context", return_value=""), patch.dict(os.environ, {"NALA_JEV_ENABLED": "0"}):
                text = mod.build_initial_context(root, BIN / "nala", "user", "test")
                self.assertNotIn("JEV_DISCOVERY_MARKER", text)
                self.assertNotIn("<nala-ask-jev>", text)
                self.assertIn("Jev is disabled", text)
                os.environ["NALA_JEV_ENABLED"] = "1"
                text = mod.build_initial_context(root, BIN / "nala", "user", "test")
                self.assertIn("JEV_DISCOVERY_MARKER", text)
                self.assertIn("<nala-ask-jev>", text)

    def test_api_outage_is_inline_and_main_conversation_finishes(self):
        mod = load_tool("nala")
        error = urllib.error.HTTPError(jev.ENDPOINT, 503, "unavailable", {}, io.BytesIO(b'{"error":"unavailable"}'))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"NALA_JEV_ENABLED": "1", "OPENROUTER_API_KEY": "test-key"}), patch.object(jev.urllib.request, "urlopen", side_effect=error) as api:
            root = Path(tmp); conv = root / "conversation"; conv.write_text("")
            outputs = iter(['<nala-ask-jev>' + json.dumps(request()) + '</nala-ask-jev>', '<nala-response>Continuing without Jev.</nala-response>'])
            with patch.object(mod, "call_llm", side_effect=lambda *args: (next(outputs), None)) as main:
                code, responses = mod.run_agent_loop(conv, root, mod.LlmSettings("openrouter", "main"), "Check evidence", "test", json_mode=True)
            self.assertEqual(code, 0)
            self.assertEqual(responses, ["Continuing without Jev."])
            self.assertEqual(main.call_count, 2)
            api.assert_called_once()
            self.assertIn('"http_status": 503', conv.read_text())
            self.assertIn('"status": "error"', conv.read_text())

    def test_distillation_and_merge_never_call_jev_even_when_enabled(self):
        cli = load_tool("nala-distill")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"NALA_JEV_ENABLED": "1"}), patch.object(jev.urllib.request, "urlopen", side_effect=AssertionError("Maintenance must not call Jev")):
            root = Path(tmp); (root / "conversations").mkdir()
            archive = root / "conversations" / f"latest-fixture-1-{uuid.uuid4()}"
            archive.write_text("User: continue read-only")
            for merge in (False, True):
                argv = ["nala-distill", "--root", tmp, "--apply", "--json"] + (["--merge"] if merge else [])
                output = "# Facts\n- Continue read-only" if merge else '{"facts":["Continue read-only"]}'
                with patch.object(sys, "argv", argv), patch.object(cli, "resolve_from_args", return_value=("openrouter", "main")), patch.object(cli, "generate_text", return_value=output), patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", io.StringIO()):
                    self.assertEqual(cli.main(), 0)
                self.assertNotIn("jev_reviews", json.dumps(json.loads(out.getvalue())))
            self.assertFalse(archive.exists())


if __name__ == "__main__":
    unittest.main()
