# uv migration verification

Verified on Linux on 2026-09-19 with uv 0.12.15.

## Automated tests

`uv run python -m unittest discover -s tests`:

```text
Ran 340 tests in 49.420s
OK (skipped=2)
```

338 tests passed. The two opt-in network tests were skipped in this run.
New tests cover saved-key loading, environment-key precedence, and missing or
empty key files. The saved-key test failed before implementation.

## Build and independent installation

`uv build` produced both `nala-0.2.0.tar.gz` and
`nala-0.2.0-py3-none-any.whl`; the wheel was built from the source archive.

`uv run python tests/verify_install.py dist/nala-0.2.0-py3-none-any.whl 3.11`
passed with an isolated home, uv tool directory, and executable directory:

```text
PASS: clean uv tool installation; all 10 command entry points run
PASS: independent .nala roots in two unrelated Git projects
PASS: installed file-split launches its bundled Python helper
PASS: clean home reports missing credentials without using host configuration
PASS: installed prompt and context resources resolve outside checkout
```

The check also puts a deliberately failing `python3` executable in an unrelated
virtual environment first on PATH. Installed commands and their child helpers
still use nala's own interpreter. The wheel is checked for bundled context and
prompts and for absence of Python bytecode/cache files. An earlier clean-install
check also passed with Python 3.14.

## Live installed-tool test

The local command resolved to:

```text
/home/ays/.local/share/uv/tools/nala/bin/nala
```

From a temporary Git project outside the checkout, with `OPENROUTER_API_KEY`,
`NALA_CONFIG`, `PYTHONPATH`, and `VIRTUAL_ENV` removed from the environment,
the installed command loaded `~/.config/nala/openrouter.key` and used the default
OpenRouter model `deepseek/deepseek-v4.1-flash`.

The request asked nala to read `proof.txt` and return its verification marker.
The resulting conversation contained a real `<nala-read-result>` and the bundled
data-oriented context. The output was:

```json
{
  "exit_code": 0,
  "responses": ["The verification marker is UV-NALA-58291."],
  "turn_count": 2,
  "tokens_in": 12701,
  "tokens_out": 69
}
```

No source-checkout executable path appeared in that conversation. Temporary
projects were removed after the checks. Credentials were neither committed nor
printed. macOS and Windows were not tested; the application uses POSIX shell
commands.

## Reproduce

```bash
uv sync --locked
uv run python -m unittest discover -s tests -v
uv build
uv run python tests/verify_install.py dist/nala-0.2.0-py3-none-any.whl 3.11
```

For live source tests with your saved key or environment key:

```bash
NALA_LIVE_TESTS=1 uv run python -m unittest discover -s tests -p test_nala.py -k LiveIntegrationTests -v
```
