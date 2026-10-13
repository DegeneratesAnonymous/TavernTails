# Agent and code ownership

TavernTAIls combines feature API routers with generation services. The current
entry points, storage boundaries, and generation flow are mapped in
[docs/CODEBASE_GUIDE.md](docs/CODEBASE_GUIDE.md).

| Generation responsibility | Implementation |
| --- | --- |
| Narration and prose quality | `server/agents/narrative.py`, `narrative_linter.py` |
| Scene planning and validation | `server/agents/scene_director.py`, `scene_validator.py` |
| Opening scene composition | `server/agents/scene_weaver.py`, `opening_voice.py`, `opening_setup.py` |
| What a player sees and can ask for | `server/agents/scene_view.py`, `session_assist.py`, `table_state.py` |
| NPC profiles and state | `server/agents/npc.py`, `campaign_memory.py`, `simulation.py` |
| Story guidance and continuity | `server/agents/narrative_director.py`, `storyboard.py` |
| Campaign setup and the world underneath | `server/agents/campaign_card.py`, `world_skeleton.py` |
| World and backstory builders, B-plot threads, goals | `server/agents/lifepath.py`, `saved_worlds.py`, `thread_weaver.py`, `braid.py`, `goal_review.py` |
| Scene consistency and campaign voice | `server/agents/continuity.py`, `voice.py` |
| Notes and recaps | `server/agents/notes.py`, `memory_extractor.py` |
| Images and visual continuity | `server/agents/image.py`, `visual_director.py`, `visual_state.py` |

Adjacent filenames in the table are relative to `server/agents/`. Session
start/advance orchestration belongs to `server/agents/sessions.py`; model calls
and local inference concurrency belong to `server/steward_llm.py`.

The client uses `GameplayLayout.tsx` and its panels for active play. Components
in `client/src/agents/` also expose individual agent tools; they are not a
one-to-one map of the session generation pipeline.

When editing generation, preserve authored/confirmed facts, player agency,
secrecy boundaries, and fallback diagnostics. Keep route wiring in
`server/main.py` and feature behavior in the feature's existing owner. See
[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for validation commands.
