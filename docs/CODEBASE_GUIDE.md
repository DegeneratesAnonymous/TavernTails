# Codebase guide

Use this map to find the owner of a behavior before adding another helper or agent.
`server/main.py` registers the API routers. `client/src/index.tsx` bootstraps the
client and renders the application component in `client/src/App.tsx`.

## Feature ownership

| Behavior | Backend | Client |
| --- | --- | --- |
| Accounts and access | `server/auth.py`, `server/agents/player.py` | `agents/LoginSignupAgent.tsx`, `api.ts` |
| Campaign creation and settings | `server/agents/campaigns.py`, `campaign_card.py`, `world_skeleton.py`, `opening_setup.py`, `campaign_interpretation.py` | `components/dashboard/CampaignCardCreator.tsx`, `CampaignCreationWizard.tsx`, `CampaignSetupView.tsx`, `WorldSkeletonPanel.tsx` |
| Character CRUD and imports | `server/agents/characters.py`, `ddb_sheet.py`, `ocr_sheet.py` | `components/dashboard/CharacterWizard.tsx`, `ImportCharacterView.tsx` |
| Session start and advance | `server/agents/sessions.py`, `server/generation_workers.py` | `components/GameplayLayout.tsx`, `hooks/useSessionRequests.ts` |
| Chat and dice | `server/agents/chat.py`, `rolls.py`, `ws.py` | `components/Chat.tsx`, `components/chat/` |
| Scene presentation and player help | `server/agents/scene_view.py`, `session_assist.py`, `table_state.py`, `scene_weaver.py`, `opening_voice.py` | `components/NarrativeView.tsx`, `components/scene/` |
| World and backstory builders | `server/agents/lifepath.py`, `saved_worlds.py`, `thread_weaver.py`, `braid.py`, `goal_review.py` | `components/lifepath/`, `data/lifepath.ts`, `components/scene/GoalsDialog.tsx` |
| Scene consistency and voice | `server/agents/continuity.py`, `voice.py` | none |
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
5a. An opening that fallbacks and repairs patched together (a template, quoted setup answers,
   appended fragments) gets one last pass: `sessions._compose_final_opening` asks
   `scene_weaver.py` for a single scene written whole from the established facts, checks it
   mechanically (paragraphs, no questions or option menus, names, time of day, nothing copied from
   the player's answers or the campaign brief) and keeps it only if the contract, anchor and
   first-scene validators all accept it. Otherwise the existing scene is kept. The player's
   first-person setup answers are restated as narration by `opening_voice.py`, never quoted back.
6. `scene_privacy.py` strips GM-only fields (hidden pressure, NPC knowledge and
   wants, storyboard and arc plans) from every scene sent to a client. The full
   scene stays in `scene.json` for the AI GM; any new route or broadcast that
   sends a scene must pass it through `player_view`.

These stages have different inputs and responsibilities. Do not combine them
just because they all call a model. Preserve authored facts, NPC secrecy,
explicit action outcomes, and generation diagnostics when changing their flow.

## World and backstory builders

Two staged builders (`client/src/data/lifepath.ts` holds their stages; `LifePathBuilder.tsx` is the one
component) end in an editable narrative of the player's own choices. Roleplay only: they never write
ability scores, skills or proficiencies.

- **World** (`WorldBuilder.tsx`, opened from the describe screen): tone, genre, the trouble, powers and
  what they want, places, where it opens. The narrative fills the describe box, so the Campaign Card
  read-back still decides what was "said". Worlds can be saved (`SavedWorld`, `/worlds`) and reused; a
  campaign copies the text, so editing a saved world never changes a running campaign.
- **Backstory** (`BackstoryWizard.tsx`, offered on the first screen of the opening setup): roots, family,
  turning point, ties (ally, rival, patron), who you are, a **required link to the world's main trouble**,
  goals (long, mid, short as "wants X because Y but Z"). The result is added to the character, replaces
  its backstory (kept in `sheet.backstory_history`, one-step undo) or is kept for one campaign only
  (`player_backstories`). `POST /lifepath/narrative` drafts the text; `lifepath.check_narrative` rejects
  names, relatives, questions and a missing link that the player did not supply, and falls back to a
  plain template.

How a backstory reaches play (the B plot inside the main story):

1. `thread_weaver.ensure_threads` runs at session start. For each seated character with goals, ties or
   a link it writes one GM-only `character_thread` row (not ranked into the main conflict) connecting their goal to the world skeleton's hidden
   truth and factions (checked draft, plain fallback; rebuilt only when inputs change).
2. `braid.next_b_beat` asks, at most one scene in three, for the next character's thread to be advanced
   while the main trouble stays present; a scene that ignored the request does not reset the count.
3. The opening may hint at the character's own goal (`scene_weaver.build_facts(goals=…)`), and the
   opening questions offer the player's own backstory answers first and no longer pre-select the first
   canned option.
4. Goals are shared with the table (`goal_review.py`, the Goals button). The story only *suggests* that a
   goal moved, with a quote that must really be in the story; only the character's player changes it.
5. Continuations keep established names exact (`continuity.name_drifts`, near-misses are repaired), are
   sent back once when they echo the last three scenes, and carry a per-campaign voice sheet
   (`voice.with_voice`, built from the tone and the table's own words, no model call).

## Campaign setup

New campaigns start from the player's own description, not from a form of AI settings:

1. `POST /campaigns/card` makes one bounded model call (`campaign_card.read_campaign_card`) that
   reads the description, plus optional setting notes, into a Campaign Card. Each field is
   **said**, **guessed** or **open**. "Said" is decided by checking the value against the
   player's text, never by the model's word. Names of people, factions and places that the player
   did not write are dropped. Two fixed follow-up questions (where it opens, what is wrong) are
   asked only when those fields are open. If the model fails, the card holds the text and the
   chosen starter. The card's content rating and limits go into the contract's `safety_policy`
   (limits as `avoid`), which narration and validation read.
2. `POST /campaigns` with `card` turns the confirmed card into settings and variables
   (`card_to_campaign`). Canon policy, creativity and posture are derived from the card's
   "how much may the storyteller invent" field instead of being asked for.
3. A background task (`world_skeleton.run_world_skeleton`) makes four small calls: hidden truth,
   factions, NPCs, clock. Right after the truth it prepares the first session's opening seed. Every
   valid piece is written at once as GM-only `CampaignEntity` rows (tag `world_skeleton`) and a
   `ticking_clock` hook, which the context orchestrator already ranks into scene context. The truth's
   secret goes in `gm_notes`, which is a "do not reveal" constraint, never in `current_situation`.
   A failed piece stays open for play to fill in, and `POST /campaigns/{id}/world` retries only
   those pieces.
4. `GET /campaigns/{id}/world` returns progress to the owner or GM. It returns the contents only
   when the owner chose "Show me the world", or to a DM. Only the owner may change that choice.
   Campaign metadata holds only progress and row ids, never the contents, because the campaign
   list and detail routes return metadata whole. A piece is marked ready only after its rows are
   saved. For a player-owner who chose "surprise", the `/memory` GM tools also hide the
   skeleton's rows and refuse the context and next-actions summaries
   (`world_skeleton.hidden_from`).
5. Every change to the skeleton's state goes through `db.update_campaign_metadata`. That helper
   and every other whole-metadata writer in `db.py` (settings, variables, sessions, metadata keys)
   hold `METADATA_LOCK` plus a row lock, so no writer saves a stale copy over another's change.
   Postgres is safe across processes. SQLite is safe within one process only; run one worker on
   SQLite.
6. The first opening questionnaire waits up to 25 s for a running truth (`wait_for_opening`), then
   consumes the prepared seed once (`take_opening_seed`, a compare-and-set). If no seed is ready,
   the questionnaire reads the premise with the hidden truth in mind; `premise_seed.reveals_secret`
   rejects a seed that states the secret.
7. If the truth fails, factions, NPCs and the clock wait for it (`needs_truth`) instead of being
   built without it. "Stick to what I wrote" (strict canon) builds no skeleton at all.

The classic creation paths stay behind "Use the classic setup" until the card flow has been
play-tested. They do not build a world skeleton.

## Taking in a scene and acting on it

The play screen shows the story as one column of prose, then plain information: who the story has
named (`scene_view.py`, built from the story text, never from GM-only fields), the one unanswered
question, and what the player's character notices. It does not list actions: the player types what
they do, and presses **Suggest** only if they want an idea.

| Route (`session_assist.py`) | What it does |
| --- | --- |
| `POST /sessions/{id}/suggest-action` | One action for the caller's own character, built from the story text and their character only. Rejected (and replaced by a safe fallback) if it names something the story has not shown, repeats GM-only text, states an outcome, or repeats an earlier suggestion. The model is never sent GM-only fields. |
| `POST /sessions/{id}/notice` | What the caller's character picks up on, once per scene and character, under the same checks. |
| `GET /sessions/{id}/recap` | "Previously": earlier scenes, where things stand, who is here, what is open. |
| `GET /sessions/{id}/round` | Who has acted and who is ready this round, and whether the table is paused. |
| `POST /sessions/{id}/table-safety` | Any player can pause the table or ask the story to leave something out (carried into the next scene's contract by `table_state.with_table_safety`); only the owner or DM resumes. Scene advance returns 409 while paused. |

Each new scene also stores `round_recap` (what the table did and rolled to reach it), shown as "Last
round". `choices` and `suggested_actions` stay on the scene as data for the validators but are not
shown to players. Client pieces live in `client/src/components/scene/`.

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

## Generation and request efficiency

- Synchronous generation stages run through `generation_workers.py` with a
  four-worker limit separate from ordinary API requests. Model transport keeps
  its own inference limit; WebSocket broadcasts stay on the request event loop.
- A D&D Beyond export is a fillable form with fixed field names; `ddb_sheet.py` reads
  every value from those fields exactly (proficiencies, passives, spellcasting, spell
  levels, features by section, attacks) and replaces the generic extractors' guesses.
- A scanned sheet has no form data. `server/ocr_client.py` sends each page image to Steward's OCR nodes
  (`POST /api/games/taverntails/ocr`, ColemanPC then HeatherPC, pages in parallel) and falls back to a local
  `TAVERNTAILS_TESSERACT_CMD`; tesseract's word table is rebuilt into `ocr_sheet.layout_text` (each value on its
  label's line). Spells, spell slots and skill modifiers are then read from that layout by rule: spell rows under
  the "1st LEVEL" headings, each skill row's number checked against the character's ability modifier (which also
  recovers a dropped minus sign). The local model proposes the remaining fields and each value is kept only if it
  appears near its own label. The proficiency bonus, spell save DC and spell attack bonus are derived from level and
  casting ability when the scan lost them (listed as `fields_derived`). The import is flagged for review.
- Character imports call `references.search_queries` once for their features and
  spells, reading one corpus snapshot and deduplicating queries. Failed queries
  do not discard successful matches. The single-query API remains available.
- Dashboard effects ignore responses after their campaign/session changes.
  `useSessionRequests.ts` shares pending metadata reads and auto-created sessions
  until the campaign list catches up; failures can retry. Metadata merges retain
  newer state, and campaign lists accept only the latest request's response.
- `sessions._write_scene` uses one approved request for the initial attempt and
  retry, adding validation feedback without losing the opening seed or context.
- Memory ranking reads scoring fields for every supported active entity, then
  hydrates at most 17 full records for selected context and clue constraints.
  Recently updated order still breaks ties; older relevant entities remain eligible.

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
`test_reference_search_efficiency.py`, `test_import_lookup_cleanup.py`, `test_generation_workers.py`,
`hooks/useSessionRequests.test.ts`, and `components/chat/messageFilters.test.ts`. See [CONTRIBUTING.md](CONTRIBUTING.md)
for the full commands. CI checks Ruff, the reviewed mypy baseline, backend tests,
frontend lint, native TypeScript checks, Jest, and a production build.
