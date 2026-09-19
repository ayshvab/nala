# Jev integration: nala-ask-jev

Status: implemented and verified (2026-09-20)

The main model needs a callable decision model with inspectable evidence and
questions. The command and native tag are both named `nala-ask-jev`. This is a
Tier 2 tool change under the data-oriented-design rules.

Contract: one JSON object contains `state` (string/object/array) and `questions`
(a nonempty map of independent Choice, Score, or Noul questions). The pinned
OpenRouter model is `typesafe/jev-1.13`. A single question uses the same batch
path. The main model owns evidence selection and wording; Jev returns typed
judgments, never code or reasoning explanations. Question IDs only correlate
answers, so instructions must identify their state fields explicitly.

Observed data: the September 19 probes used 3–8 questions per request, 491–1,505
reported input tokens, and 0.61–0.83 seconds per HTTP call. There is no real-task
distribution yet. ASSUMPTION: small evidence excerpts are the common case;
this affects the inline tag interface. A 128 KiB serialized request limit is
a local bound, not a token-window guarantee. OpenRouter enforces its model
context limit. Invalid shapes, non-finite values, missing answers, and service
errors return explicit failures, without interpreting them as judgments.

Data flow: JSON input → validate → one HTTPS request → validate response →
print CLI result / append conversation result. Per the user's explicit storage
requirement, the conversation itself owns the call's input and output. There
are no separate Jev records or path references. Credentials remain in headers
and are never deliberately serialized. Questions and state live in the action;
the result includes model identity, time, response or error, usage, and elapsed
time. CLI JSON includes the request as well, so a shell call is self-contained.

The native action contains the entire input JSON; the orchestrator appends the
actual result before the next main-model call. Result JSON escapes angle brackets
to preserve tag boundaries. Successful usage contributes to native-call token
totals. A killed process can leave a call without a result; there is no hidden
retry or fabricated success. Existing conversation compaction applies normally.

Cost on this Python/Linux CLI: one network request per consultation and inline
request/result tokens on subsequent conversation turns. No latency improvement
is claimed. No additional storage lifecycle or global skill installation is added.
There is no performance-sensitive pointer layout or native-code hot path.

Simplification: reuse saved OpenRouter credentials and stdlib HTTP; keep one
client for CLI and tag; batch questions; retain the existing main model and
deterministic parser; omit automatic retries, verdict thresholds, reviewers,
provider abstractions, and automatic action gating. The bundled guide teaches
when/how to consult Jev and remains available through tool discovery and --help.

Done requires failing-then-passing tests for schemas, failures, inline inputs,
transcript visibility/order, and accounting; the existing suite; a clean uv
wheel install with all commands; and small live standalone and agent probes.
Integration correctness does not establish semantic reliability on real tasks.

Verification:

- The new test module first failed because the tool did not exist. Changing the
  storage requirement produced failing tests for the old separate-file behavior;
  the final implementation passes with entirely inline input/output.
- 13 focused tests cover all three primitives, invalid input/answers, missing
  credentials, HTTP/timeout/incomplete-response failures, non-finite JSON,
  credential redaction, stdin/file CLI use, tag validation, transcript ordering,
  escaping of embedded tags, no record writes, and token accounting.
- Full suite: 356 tests, 354 passed and two optional live tests skipped.
- The built wheel passed clean uv installation checks: all 11 commands,
  bundled Jev guide, separate project roots, and existing helper/resources.
- A live standalone batch returned all three answer types through OpenRouter.
  In a separate live DeepSeek conversation, nala discovered/read the guide,
  constructed its own state and question, invoked the native tag once, and
  explained the authentic returned judgment. Jev classified the whole-suite
  claim as insufficiently supported (probability 0.96, confidence 0.93), with
  462 input / 48 output tokens, reported cost $0.000019404, elapsed 0.621 s.
  The fresh root contained only `.gitignore` and the ordinary conversation;
  that conversation held the full request and response before the final answer.
  These are small integration checks, not an accuracy benchmark.

No unresolved implementation questions remain for this scope. Automatic reviews,
fixed decision thresholds, and broader semantic evaluation remain outside this
callable-tool integration.

References: [agent guidance](https://docs.typesafe.ai/agent-skill),
[upstream skill](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md),
[API](https://docs.typesafe.ai/api), and
[OpenRouter Decisions](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request).
