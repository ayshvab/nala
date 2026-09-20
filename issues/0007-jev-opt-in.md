# Keep Jev optional

The user requested removing the automatic Jev integrations after reviewing
[the memory-review experiment](0006-jev-memory-review.md). The successful small
fixtures did not establish a benefit for normal compaction. Adding API/model
failure paths to existing workflows was not justified.

## Current behavior

- `jev_enabled` defaults to `false` in nala config. Only JSON boolean `true`
  enables it. Existing config lookup, `--config`, and `NALA_CONFIG` apply.
- `NALA_JEV_ENABLED=1` (or `true`) enables a command and its children;
  `NALA_JEV_ENABLED=0` disables it even when config enables it. Other environment
  values are treated as disabled. A malformed optional setting stays disabled.
- Enforcement is shared by the native tag and standalone command, before
  credential lookup or network access. Disabled tools are omitted from initial
  context discovery. Old conversation instructions cannot bypass the API check.
- Calls preserve their actual inputs/results inline. One request per call,
  existing socket timeout, no automatic retry. API failures are tool results;
  the main conversation continues. The standalone CLI returns nonzero on a
  failed consultation, as other command-line tools do.
- Distillation and merging have no Jev dependency or review flags. The previous
  compaction prompt is restored exactly. Automatic checkpoints are unchanged.
- Retained independent improvements: explicit continuing constraints in the
  harvest prompt and counting failed extractions toward the source-byte budget.

Removed the automatic review helper, maintenance callbacks/reports, associated
tests/evaluation script, and mandatory compaction review instructions. No new
fallback model, retry service, record directory, or background job is needed.
Disabled use incurs no Jev API cost; enabled use pays only for explicit calls.

## Verification

Tests exercise default-off calls with credentials/network forbidden, config and
environment precedence, custom config, hidden tool discovery, successful enabled
calls, and an injected HTTP 503 followed by a successful main-model continuation.
Maintenance tests prohibit Jev network calls even while the tool is enabled.
The existing request/response, inline storage, validation, and credential
redaction tests remain. The harvest budget regression is retained separately.

Full suite: 363 tests run, 361 passed and two optional live tests skipped.
Clean Python 3.12 wheel installation: all 11 entry points passed, including
default-disabled Jev and explicit opt-in reaching credential validation.
The restored compaction prompt was compared byte-for-byte with commit 7a65d69.
