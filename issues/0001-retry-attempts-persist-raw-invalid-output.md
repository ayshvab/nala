# 0001 — Retry attempts still persist raw invalid output

Status: implemented in nala; broader model-quality evaluation remains open
Filed: 2026-06-13
Area: `bin/nala` — `run_agent_loop` retry branches

## Nala fix — 2026-09-19

We implemented option 1 below after a real DeepSeek V4.1 Flash conversation
repeated DSML-style calls and echoed driver-generated result/status frames.
Keeping those rejected attempts in the next prompt supplied more examples of
the unwanted protocol. This fixes the upstream inconsistency; it does not change
which tags the parser accepts or translate DSML into executable commands.

Both format-retry paths now save the exact raw response in a unique
`{conversation}.invalid.{guid}` sidecar before retrying. Its header records the
attempt number, turn, time, and detailed rejection reason. The working
conversation receives only a fixed correction, the sidecar filename, and a
turn-status line linking the GUID and preserving cumulative token counts.
Detailed parser errors stay in the sidecar too, because they can quote invalid
attributes or raw response fragments.

Mixed valid/junk responses retain the existing cleanup behavior. The limit is
still three attempts per step, provider-error handling is unchanged, and
rejected attempts never execute. This is append-only and leaves existing saved
conversations untouched; historical malformed turns are not retroactively
removed.

The cost is one diagnostic file and write per rejected attempt. Sidecar garbage
collection remains the separate open issue 0002. No parser redesign or extra
model call is introduced.

### Verification

Regression tests failed before the change, then passed. The full suite ran
343 tests: 341 passed and two opt-in live tests were skipped. New coverage checks
DSML-only output, unclosed known tags (including a valid action before the
malformation), invalid attributes, empty output, and three-attempt exhaustion.
Assertions cover exact raw preservation, diagnostic links, clean subsequent
requests, no rejected execution, exactly-once accepted execution, and unchanged
token accounting. Existing mixed-output cleanup tests also pass.

The wheel also passed the isolated uv installation check: all 10 commands,
independent project roots, bundled helper execution, credential isolation,
and installed prompt/context lookup.

A controlled live comparison used OpenRouter's `deepseek/deepseek-v4.1-flash`,
a fixed initial context/user request, and two rejected-output fixtures: an
observed DSML-only response and a synthetic unclosed shell tag. Each fixture
was tried twice with the old retry prompt (raw response plus correction) and
twice with the new correction-only prompt. Generated commands were parsed but
never executed. Results for the immediate next response:

| Fixture | Old: valid/attempts | New: valid/attempts |
| --- | --- | --- |
| Observed DSML | 1/2 | 2/2 |
| Unclosed shell | 2/2 | 2/2 |
| Total | 3/4 | 4/4 |

All accepted responses in this sample were also free of ignored content.
An earlier comparison batch was interrupted by an upstream provider internal
server error; it is excluded from these counts. These are small controlled
next-response probes, not a full-session benchmark or proof of statistical
non-regression. The deterministic guarantee is that rejected text no longer
enters subsequent requests; broader recovery-rate evaluation remains open.

## Original upstream report

## Context

Commit 065168c made the success path bias-safe: a turn that contained
non-protocol content (a leaked `<thought>`, an echoed wrapper, stray prose) is
stored *cleaned* in the conversation, and the raw output is preserved in a
`{conversation}.invalid.{guid}` sidecar linked from `<nala-turn-status>`. The
conversation — which is the next generation's input — therefore can't bias the
model toward repeating the bad pattern.

The two *retry* branches in `run_agent_loop` were left out of that treatment:

- **Malformed known tag** (hard parse error, e.g. unclosed `<nala-write>`):
  appends `<agent-response>{raw}</agent-response>` + a `<system>` correction,
  then retries.
- **No actionable tags** (the turn was only junk): same shape, then retries.

Both still write the raw model output into the conversation verbatim.

## The problem (data)

A turn that needs N format-retries leaves N raw malformed attempts in the
conversation, e.g.:

    [raw malformed attempt 1][<system> correction]
    [raw malformed attempt 2][<system> correction]
    [raw good attempt 3]

Those failed attempts persist for the rest of the run and act as few-shot
examples — exactly the bias the success-path fix removes. In the observed
collide-gemini run, `<thought>` leaks compounded across turns once they
appeared.

Why it was deferred: keeping the raw on a retry helps the model *self-correct
within the same turn* (it sees what it just got wrong), and the conversation is
**append-only** (`append_to_conversation` only appends). Stripping a failed
attempt after a later attempt succeeds means rewriting earlier bytes of the
file, not appending — a larger change than the success-path fix.

## Options (with cost)

1. **Strip on retry too, immediately.** Store only the `<system>` correction
   (which already names the specific error, e.g. "missing `</nala-write>`")
   plus a sidecar of the raw; never store the raw inline.
   - Cost: small code change; risk that the model self-corrects worse without
     seeing its own prior text. Unverified — would need an A/B on a leak-prone
     provider (Gemini) to confirm the correction message alone is enough.
2. **Keep raw during the turn, sweep on success.** Leave attempts inline while
   retrying; once the turn finally produces valid tags, rewrite the turn's
   region to drop the failed attempts (move them to a sidecar).
   - Cost: breaks the append-only invariant for one region; more code; must be
     careful not to corrupt the file mid-write. Highest fidelity to "model sees
     its mistakes while it matters, conversation stays clean afterward."
3. **Do nothing.** Accept that retry-attempt bias is rarer now that leniency +
   EOF-capture catch most malformations before they become hard errors.
   - Cost: zero; residual bias only on turns that still hard-error or go
     all-junk.

## Recommendation

Start with option 1 (strip on retry, sidecar the raw, lean on the specific
`<system>` correction), measured against a leak-prone provider before
committing. Escalate to option 2 only if self-correction quality drops.

## Done criteria

- A multi-retry turn leaves no raw malformed output in the conversation.
- Each stripped attempt is reconstructable from a sidecar.
- Self-correction success rate on a leak-prone provider is no worse than today
  (measured, not assumed).
