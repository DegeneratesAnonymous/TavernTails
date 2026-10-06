# Player playthrough review — 2026-10-06

## Goal and scope

Follow the README's solo-player journey through campaign creation, opening
setup, starting play, declaring actions, advancing scenes and reloading saved
state. A useful turn must preserve the authored premise, resolve only new
actions, and render grammatical prose about the actual target.

This change covers backend continuity, opening facts, narrative planning and
QA repair. It does not redesign the UI or change campaign scope.

## Reproduced through the application routes

Brief: Alderbrook's clocks stopped at breakfast. Clockmaker Ada Reed has a
stopped brass pocket watch on her workbench. Investigate without frightening
the neighbors.

| Player action / setup | Observed defect | Change |
| --- | --- | --- |
| Create and start the clock mystery | An unrelated garrison, contact and sealed letter replaced the supplied setup | Conservative prose introductions become source facts; anchored fallback seeds retain the factual setup and explicitly supplied possession |
| Inspect the named pocket watch | Continuation fell back to a generic marked clue | Preserve an opening's approved physical object in fallback context |
| Ask a follow-up question | The director was still instructed to produce an opening | Continuation requests carry the new actions separately and explicitly require their resolution |
| Long rest, then ask a question | Previously resolved chat was eligible for simulation again | Persist a message-ID watermark with each completed scene; query new input without the old 20-message truncation |
| Reload an older save and advance with no new chat | No action watermark existed | Migrate using saved story time and retain the full history watermark |
| Apply scene QA repairs | “The first answer is rehearsed. is moved…” and “chosen to I…” | Stop synthesizing evidence-removal facts from clue sentences; quote declarations, deduplicate repairs and avoid appending standalone object fragments |
| Inspect an ordinary campsite | Fallback could introduce an escaped slave army | Restrict that specialized branch to established Northwood / slave-army / escapee context |
| Generate the nested creative brief | Its large response schema had a 350-token output limit | Allow 1,200 tokens for composer and director JSON; live evaluation remains necessary |

The prose recognizer is intentionally limited: explicit `At/In <named place>,`
introductions and a small set of role-plus-name introductions. Arbitrary prose
and unsupported templates still need model interpretation or structured setup.
It does not claim to be a general natural-language entity parser.

## Verification

Focused automated coverage:

```bash
python -m pytest server/tests/test_playthrough_quality.py \
  server/tests/test_generation_coherence.py server/tests/test_session_workflow.py \
  server/tests/test_session_bootstrap.py server/tests/test_chat.py \
  tests/test_scene_quality.py -q
```

At review time: **233 passed, 1 skipped**. The skipped test is the explicitly
opt-in live-model journey. These checks exercise actual API routes and saved
state; they are not a browser playthrough or proof of live-model prose quality.

## Live release check

Use a disposable local data environment with Steward, Ollama or an
OpenAI-compatible provider configured, then run:

```bash
python -m pytest server/tests/test_playthrough_quality.py --llm -v --basetemp=.qa-playthrough
```

The live test creates a QA campaign and writes `live-playthrough.json` beneath
pytest's temporary directory. It inspects the watch, questions Ada and moves to
the square. It rejects a deterministic scene director as proof of live-model
validation. Provider calls may incur their normal cost.

Read the transcript after the automated checks. Verify that inspection yields
a concrete observation, Ada actually answers or gives a grounded reason she
cannot answer, movement reaches the intended location, and subsequent turns
remember those results. Check that a fictional deadline, pursuit, suspect or
NPC secret was not introduced merely to satisfy a numeric quality score.
Keyword assertions alone cannot establish these qualities.

No live provider was configured in the review workspace. The remote browser
could not open the local app. Live narration and visual UX remain unverified;
existing deterministic fallbacks can still give a vague answer despite passing
structural checks. Do not treat this PR as a complete narrative-quality sign-off.

Broader final verification: `python -m pytest server/tests tests
--ignore-glob='*import*.py' -q` completed with **784 passed, 9 skipped**.
Character-import-inclusive runs were attempted but remained slow in this
environment; there is no complete-suite pass. Backend Ruff, frontend ESLint,
TypeScript, Jest (1 test), and the React production build passed. The production
build ran directly through `react-scripts` to avoid the package's QA-data purge
prebuild hook.

## Rollback

Revert this change to restore previous behavior. The added scene field
`last_resolved_message_id` is additive and older code ignores it; no database
migration is required. Do not remove the field on active saves unless falling
back to the legacy story-time migration intentionally.
