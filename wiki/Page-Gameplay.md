# Gameplay / Session View

> Screenshot auto-updated on every merge to `main` via the
> [screenshot-update](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/screenshot-update.yml) workflow.

![Gameplay / Session View](https://raw.githubusercontent.com/DegeneratesAnonymous/TavernTails/main/docs/screenshots/10-gameplay.png)

The main play screen — where the actual game session happens.  Reached by
clicking **Start Session** on any campaign card.

## Layout Overview

The session view is a split-panel layout:

### Left Panel — Scene Stage
- **Scene image** — AI-generated artwork for the current scene (when the Image
  agent is enabled; falls back to a placeholder if disabled or unavailable).
- **Scene title** — displayed prominently so all players know where in the story
  they are.
- **Continue button** (header) — advances the AI narrative to the next beat.

### Right Panel — Tools

| Tab | Purpose |
|---|---|
| **Chat** | Real-time chat for all session participants. Type narrative actions, dialogue, or commands. Dice roll syntax (e.g. `1d20+5`, `2d6`) is detected automatically and roll results are posted inline. Type `!notes` to request a session recap. |
| **Character** | Full interactive character sheet (same content as the [[Character Sheet Modal|Page-Characters]]). Stats, spells, features, and inventory are always one click away without leaving the session. |
| **Journal** | Auto-generated session notes plus any manually added entries. The Notes Agent adds key events, NPC encounters, and plot beats automatically. |

## Additional Controls

| Control | Location | Description |
|---|---|---|
| **NPC Index** | Header button | View a snapshot of all NPCs tracked in this session |
| **Documents** | Header button | Access campaign reference PDFs during the session |
| **Image Gallery** | Header button | Browse all AI-generated scene images from the session |
| **Pinned Messages** | Pin icon on messages | Pin important messages (key clues, rules rulings) to a persistent bar at the top of chat |
| **Invite Players** | Invite button | Share a join link so additional players can enter the session |

## Dice Rolling

Dice expressions entered anywhere in the chat input are rolled server-side for
fairness and the full formula + result is posted as a special roll message.
Beyond 20 users can also roll from their D&D Beyond character sheet and have
results relayed automatically (see [[Beyond 20|Page-Beyond20]]).

## AI Agents Active in Session

| Agent | Responsibility |
|---|---|
| **Narrative Agent** | Scene narration, NPC dialogue, story advancement |
| **Scene Analysis Agent** | Detects when dice rolls are needed; prompts players |
| **NPC/Enemy Manager** | Tracks NPC stats, motivations, and combat initiative |
| **Notes Agent** | Logs events; responds to `!notes` requests |
| **Image Generation Agent** | Creates scene artwork (requires API key configuration) |

---

_← Back to [[Home]]_
