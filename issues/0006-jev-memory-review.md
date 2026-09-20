# Jev reviews for memory maintenance

Implemented 2026-09-20. Follow-up to [the inline Jev tool](0005-jev-tool.md).

## Why

Distillation previously accepted any parseable harvest JSON or nonempty merge
containing bullets. That establishes format, not fidelity. A main model can
turn a pending task into completed work, broaden a limited test result, or
drop a durable constraint. Jev can make focused semantic judgments about these
specific transformations; it cannot generate the replacement summary.

## Contract and cost

- Input: original source plus the main model's candidate knowledge. Even when
  extraction used a generated summary, review uses the original source.
- One Decisions request per candidate, with four independent choice questions:
  grounding, coverage, status, continuing constraints. Questions and criteria are centralized in
  `bin/helpers/nala_memory_review.py`; there are no confidence thresholds.
- Accept only four passes. A problem, unclear judgment, API/protocol failure,
  or request exceeding the existing tool/model limits keeps the original.
  No automatic semantic retries; the user/agent can inspect and revise.
- Default in the CLI's harvest and merge apply passes. `--no-jev-review` is an
  explicit bypass. Dry-run, no-harvest deletion, index summaries, graduation,
  and automatic checkpoints do not gain API calls.
- Full request/response data is in the ordinary report, including human output;
  nala-shell captures it inline. No Jev directory, record files, or references
  replacing the actual exchange. Existing knowledge files, merge backups and
  harvest ledger retain their normal purposes. Library callers can inject a
  reviewer; the CLI supplies the default.
- Additional input tokens and latency are reported by Jev, not included in
  existing dry-run extraction estimates. Failed reviews preserve rather than
  reclaim the source, so maintenance may free less space.

## Compaction

The bundled compaction prompt has the existing editing worker review the
candidate against original evidence through the native Jev tag. Its full call
lives inline in that worker's ordinary conversation. Copying the old source
back into the shortened parent as an audit would undo the compaction.

This is prompt-guided, not a driver-enforced gate. Long conversations require
selected evidence and must report partial coverage. On inconclusive reviews,
the worker is instructed to retain relevant source passages. Custom prompts
can override this behavior. No claim of guaranteed lossless compaction.

## Validation and remaining questions

Live failure analysis: a binding read-only requirement was retained only as a
historical tasks_done note, yet the three general checks passed. Adding the
rule to the already compound status question produced a 0.50/0.50 tie that
still selected pass. The source and candidate were complete; missing evidence
was not the cause. The status question mixes task completion, epistemic status,
and continuing obligations. Test a separate focused obligations question,
keeping task/evidence status independent, rather than treating confidence as
proof or tuning a cutoff to this one example. The focused question rejected
the historical-only constraint while the three general checks still passed.
The fixture remains in the live regression cases, and harvest guidance now
also explicitly preserves continuing requirements in facts/decisions.

Unit tests cover acceptance, rejection, errors, preserved originals/backups,
reviewing original text after a summarization stage, default CLI behavior,
explicit bypass, dry/no-harvest behavior, and complete transcript-safe output.

The initial live feasibility batch distinguished a faithful summary from three
seeded errors (broadened test success, reversed constraint, omitted next task).
This is a small fixture check, not calibration or a measured production error
rate. Further validation should use real, labeled memory transformations with
user-reviewed expected outcomes. No universal confidence cutoff is justified.

The final questions matched all seven expected decisions in the
opt-in fixtures in `tests/eval_jev_memory.py`: two faithful rewrites accepted;
invented test success, reversed constraint, omitted task, historical-only
constraint, and lost qualification rejected. Observed Jev latency was
0.698–0.850 seconds and cost was $0.000049–$0.000064 per fixture review. Run
`uv run python tests/eval_jev_memory.py` to repeat (seven paid API calls;
complete exchanges printed inline to stdout).
Rejected candidates still consume the configured harvest source-byte budget.

The full suite ran 365 tests: 363 passed and two optional live tests skipped.
A clean wheel installed through uv and passed all 11 command entry-point checks.
An isolated live compaction used the native Jev action and retained the seeded
constraint, decision, test limits and next task. Inspection caught the main
model labeling selected/retold evidence as the full source. The prompt now
defines full-body coverage as verbatim text and requires an explicit coverage
field. This observed limitation is why the prompt review is not described as
an enforced completeness guarantee.

The initial live CLI harvest exercised extraction, review, then reclamation
of a 538-byte synthetic source. Its candidate exposed the historical-only
constraint failure discussed above. The full report is inline in `distill-demo`
conversation under `/home/ays/Work/nala-research/jev-memory-2026-09-20/.nala/`.
The `compact-demo` fixture went from 44,627 to 29,092 bytes including its
unchanged initial context; the compacted body is 1,641 bytes. Its editing
conversation contains the complete native Jev request/result, with no duplicate
audit added to the shortened parent. These are local evidence paths, not
required runtime storage or request/response sidecars.

Open: a scalable full-source review for archives exceeding Jev's context/input
limits. For now such distillation reviews fail and keep the original; do not
silently truncate evidence or pretend a summary proves its own fidelity.

References: [TypeSafe agent skill](https://docs.typesafe.ai/agent-skill),
[skill source](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md),
[Jev limits](https://docs.typesafe.ai/model-jaggedness/jev-1.13).
