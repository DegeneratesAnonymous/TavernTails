# Narrative follow-up to PR #194

This branch builds on `e1119b0`, including the owner's local-model verification
and fallback-object fixes. It addresses the six follow-ups in
[the review comment](https://github.com/DegeneratesAnonymous/TavernTails/pull/194#issuecomment-6022439482).

## Player-facing changes

- Explicit `has a/an/the … on/in/beside` possessions become user-sourced object
  facts in the shared opening intent. Denied and hypothetical possessions do
  not qualify. Model bundles, opening contracts, prompts and later scenes carry
  the same object; keyword tables cannot replace it with a sealed letter.
- Inline object phrases normalize leading articles without lowercasing proper
  names. Object-only clues render as complete sentences.
- The director supplies indexed `action_resolutions` for direct questions:
  an actual reply, or an inability to answer with a reason. The narrator must
  include the planned reply verbatim. Posture descriptions and omitted replies
  trigger fallback even when the numeric prose score passes.
- When generation fails, the fallback explicitly admits insufficient
  information rather than fabricating a winding time, guilty reaction or secret.
  It does not solve a mystery. An inspection fallback repeats established
  evidence without inventing damage or forensic results.
- Continuations retain the previous location and primary NPC until an explicit
  movement action. Conservative named-entity checks reject new names in prose
  when the party stays put. Movement updates the scene location and keeps the
  existing object as a lead, without claiming that another version lies there.
- Valid model openings are no longer unconditionally replaced by premise seeds.
  For authored-object scenes, generated personal hooks/timers do not by
  themselves justify replacing grounded prose. Other fact, grammar, agency and
  opening checks remain in force.

## Model diagnostics and local concurrency

Opening `scene_debug.fallback_used` includes writer fallback and concrete
opening-contract replacement. Advance responses report fallback under
`simulation_debug.scene_validator`; it is also saved in
`scene.generation_debug`. Director and writer diagnostics include elapsed time,
source/attempts, and fallback reason. The live check uses the actual advance
response fields and requires a model director as well as model-written prose.

With `STEWARD_HOST` or `OLLAMA_HOST`, each server process defaults to one
in-flight completion. Calls queue **before** their provider deadline starts.
Queue time and acquisition status are logged with task scope; prompts and
credentials are not logged. Set `TAVERNTAILS_LLM_MAX_CONCURRENCY` for a multi-node
Steward installation (zero disables gating).
`TAVERNTAILS_LLM_QUEUE_TIMEOUT` defaults to 300 seconds. This gate is per process,
not a distributed reservation across web-server workers or other Steward clients.

## Type-check debt

`tools/mypy_baseline.json` records the 185 existing diagnostics at `e1119b0`, with
mypy 2.1.0 targeting Python 3.11. `python scripts/check_mypy_baseline.py` fails
for a new path/message or an increased duplicate count. Line shifts alone do
not fail. Tool/config failures fail the check. CI now runs this as a blocking
check and runs on stacked PRs too.

The baseline is not a type-clean claim. Reduce entries as errors are fixed;
review any proposed new entry rather than regenerating it to silence failures.

## Verification and limits

Validated here: **804 passed, 9 skipped** in the non-import regression suite;
lint passed; the type gate reported **136 current diagnostics, 0 new** against
the reviewed baseline. Explicit dictionary annotations removed several prior
inference errors. This is not a complete import-inclusive suite or live-model run.

Run the regression suite and lint:

```bash
python -m pytest server/tests tests --ignore-glob='*import*.py' -q
python -m ruff check server scripts/check_mypy_baseline.py tests/test_mypy_baseline.py
python scripts/check_mypy_baseline.py
```

Use a disposable data environment with the local provider configured for the
live journey:

```bash
python -m pytest server/tests/test_playthrough_quality.py --llm -v --basetemp=.qa-followup
```

Review the saved transcript for meaningful observations, truthful answers,
movement and continuity. The structural checks are conservative heuristics;
they cannot establish that an answer is sensible or supported by all prior
events. New names are allowed after recognized movement, and this is not a
general parser for every way of asking a question or describing travel.
Deterministic fallback remains limited and is now visible as fallback.

The owner's previous live evidence applies to `e1119b0`. This follow-up has
automated validation here; no local-model endpoint is configured in this
workspace, so it needs another live transcript before narrative-quality sign-off.

Reverting this follow-up restores the PR #194 behavior. Added JSON diagnostics,
object facts and action resolutions are additive; there is no DB migration.
