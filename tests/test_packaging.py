"""Packaging contracts; wheel installation is checked separately by verify_install.py."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin/helpers'))
import nala_llm


class SavedCredentialTests(unittest.TestCase):
    def test_saved_key_works_without_shell_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'HOME': tmp}, clear=True):
            key = Path(tmp) / '.config/nala/openrouter.key'
            key.parent.mkdir(parents=True)
            key.write_text('saved-test-key\n')
            self.assertEqual(nala_llm.credential_env_var('openrouter'), 'OPENROUTER_API_KEY')
            self.assertEqual(os.environ['OPENROUTER_API_KEY'], 'saved-test-key')

    def test_environment_key_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'HOME': tmp, 'OPENROUTER_API_KEY': 'environment-key'}, clear=True):
            key = Path(tmp) / '.config/nala/openrouter.key'
            key.parent.mkdir(parents=True)
            key.write_text('saved-test-key')
            nala_llm.credential_env_var('openrouter')
            self.assertEqual(os.environ['OPENROUTER_API_KEY'], 'environment-key')

    def test_empty_or_missing_saved_key_is_not_a_credential(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'HOME': tmp}, clear=True):
            self.assertIsNone(nala_llm.credential_env_var('openrouter'))
            key = Path(tmp) / '.config/nala/openrouter.key'
            key.parent.mkdir(parents=True)
            key.write_text(' \n')
            self.assertIsNone(nala_llm.credential_env_var('openrouter'))
