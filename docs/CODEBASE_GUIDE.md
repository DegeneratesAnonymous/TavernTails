# Codebase guide

Use this map to find the owner of a behavior before adding another helper or agent.
`server/main.py` registers the API routers. `client/src/index.tsx` bootstraps the
client and renders the application component in `client/src/App.tsx`.

## Feature ownership

| Behavior | Backend | Client |
| --- | --- | --- |
| Accounts and access | `server/auth.py`, `server/agents/player.py` | `agents/LoginSignupAgent.tsx`, `api.ts` |
| Campaign creation and settings | `server/agents/campaigns.py`, `opening_setup.py`, `campaign_interpretation.py` | `components/dashboard/CampaignCreationWizard.tsx`, `CampaignSetupView.tsx` |
| Character CRUD and imports | `server/agents/characters.py` | `components/dashboard/CharacterWizard.tsx`, `ImportCharacterView.tsx` |
| Session start and advance | `server/agents/sessions.py` | `components/GameplayLayout.tsx` |
| Chat and dice | `server/agents/chat.py`, `rolls.py`, `ws.py` | `components/Chat.tsx`, `components/chat/` |
| Campaign memory | `server/agents/campaign_memory.py`, `context_orchestrator.py` | campaign/session views |
| Documents and references | `server/agents/documents.py`, `references.py`, `server/storage/documents.py` | `components/DocumentsPanel.tsx` |
| Persistent records | `server/db.py` | accessed through `api.ts` |
| Model transport and concurrency | `server/steward_llm.py` | server API calls |

Client paths in this table are relative to `client/src/`. Adjacent filenames in
backend cells are relative to `server/agents/`.

## Generation flow

The session routes in `sessions.py` coordinate generation and persist its result:

1. Load campaign settings, character data, and the previous scene. Campaign
   interpretation supplies the campaign contract; `generation_intent.py` tracks
   which facts are authored, confirmed, or provisional.
2. `context_orchestrator.py` ranks campaign memory and produces separate context
   blocks for narration, analysis, and visuals. `context_collector.py` remains
   the compact fallback and the campaign context API implementation. Session
   start/advance use fresh packets (`use_cache=False`).
3. `narrative_director.py` supplies story guidance; `scene_director.py` builds the
   structured scene. `narrative_composer.py` enriches its presentation, and
   `content_bundles.py` carries required content across scenes.
4. `narrative.py` writes prose. `action_resolution.py`, `narrative_linter.py`,
   `scene_validator.py`, and the opening checks in `sessions.py` enforce replies,
   continuity, and grounding. Failed output may be retried or replaced with a
   deterministic fallback; diagnostics record that choice.
5. `simulation.py` advances world time and state on continuation. The session
   stores the scene/story and updates memory/storyboard/visual state.

These stages have different inputs and responsibilities. Do not combine them
just because they all call a model. Preserve authored facts, NPC secrecy,
explicit action outcomes, and generation diagnostics when changing their flow.

## Storage boundaries

- SQLModel records in `db.py` hold accounts, characters, campaigns, entities,
  relationships, hooks, and change logs.
- `server/sessions/<session_id>/` holds session metadata, scene/story JSON,
  party data, simulation state, and generation diagnostics.
- Document storage supports local files or S3 through `storage/documents.py`.
- React state belongs in its owning view/context. `api.ts` owns HTTP/WebSocket
  address construction and authenticated requests.

Avoid reading the same session file twice during one context collection. Reuse
that call's snapshot; a second read adds work and can mix different versions.

## Simplification pass (October 2026)

- The compact collector now reuses its story and scene snapshot for both ranking
  and output instead of loading each file twice.
- Reference text search reuses a bounded four-entry TF-IDF index keyed by
  corpus contents. Repeated feature queries reuse token counts and document
  norms; edits change the key. Visibility metadata is read fresh, and embedding
  searches retain their existing path.
- Faction relevance uses a set of affiliation names instead of comparing every
  NPC affiliation with every faction. Duplicate faction names still match.
- Question validation indexes resolutions once, preserves the first duplicate
  entry, and shares director/writer checks. Narration is case-folded once.
- Chat tab counts and visible messages use one memoized pass instead of six
  filtered arrays on every render. Dice stay visible in All; message order and
  identity are preserved.
- Starfinder fixture seeding uses its explicit package path instead of changing
  global `sys.path`, which collided with the top-level test package.
- Context construction no longer has a placeholder relationship lookup or an
  unused scoring argument. Explicit scene problems/stakes survive without a
  story thread; token trimming reports the final estimate.

## Second cleanup pass

- Removed the earlier D&D extractor definition that Python immediately replaced
  with the active implementation. There is now one definition to maintain.
- Seven system extractors share `_WidgetLookup` in `characters.py`. It keeps
  pattern priority and field insertion order, skips the same empty values, and
  compiles each regex once per lookup instead of calling `re.search` per field.
- Seventeen session routes share `_require_session_member` in `sessions.py`.
  Existing metadata loading, missing-file behavior, owner/invite/member policy,
  and denial responses remain in their original route scopes.

## Where further cleanup needs care

`characters.py`, `sessions.py`, `LoggedInDashboard.tsx`, and `GameplayLayout.tsx`
are the largest behavior owners. Split these by an existing feature boundary
when working on that feature, keeping endpoint/prop contracts stable. Moving
thousands of lines into generic utilities would make navigation harder without
reducing complexity. The two context collectors also have different output
contracts; replacing one requires checking all callers first.

## Verification

Backend regression tests live in `server/tests/`; type-baseline tests live in
`tests/`. Focused coverage for this pass is `test_context_efficiency.py`,
`test_reference_search_efficiency.py`, `test_import_lookup_cleanup.py`, and
`components/chat/messageFilters.test.ts`. See [CONTRIBUTING.md](CONTRIBUTING.md)
for the full commands. CI checks Ruff, the reviewed mypy baseline, backend tests,
frontend lint, native TypeScript checks, Jest, and a production build.
