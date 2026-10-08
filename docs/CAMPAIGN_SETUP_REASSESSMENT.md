# Campaign setup reassessment (Oct 8 2026)

Triggered by two user reports: narratives not loading, and the selected character not sticking.
Everything below was measured from the live server's log and session folders, not assumed.

## What the platform can actually do

| Capability | Measured |
| --- | --- |
| Model | One local `qwen3:14b` on ColemanPC, reached through Steward. Successful calls take 15–25 s each (narrative 17.5 s, composer 24 s, scene director 23 s, plot 18 s, visual 15 s). |
| Concurrency | `server/steward_llm.py` lets **one** call run at a time when `STEWARD_HOST` is set. Calls that look parallel (`asyncio.gather`, the "director" fan-out) are queued: `queue_ms` was routinely 25–50 s. |
| Overload | When the PC is busy a call burns 90 s on Steward and then 60 s on direct Ollama against the *same* machine before giving up. |
| Deterministic content | Genre seed pools, the campaign contract, character sheets (DDB/OCR) and now the rollable tables cost **no** model time. |

## What a player goes through today

create campaign → pick/create character → create session → opening questionnaire → `/start`.
`/start` runs plot + director, then scene director, composer, narrative (1–3 attempts), and later the
visual and analysis calls. On session `ddc183d5` the stored scene appeared **2 min 48 s** after the
setup answers were submitted. The client code still says the pipeline "can take 10–60 s".

## Defects found

| # | Symptom | Cause | Status |
| --- | --- | --- | --- |
| 1 | Selected character is lost | Steward SSO login stored only the token. The dashboard finds "my" party member by matching `localStorage` `user_email`/`user_username`, which SSO never set, so it matched nobody. | **Fixed** (identity stored at SSO; `/player/me` fallback and now returns email/username). |
| 2 | Brief says one place, scene opens in another ("Iron Tower" vs "Stonecrest Barrow") | The questionnaire and `/start` each drew their own random opening seed. | **Fixed** (seed stored on the session; every opening-path draw reuses it). |
| 3 | "Narratives aren't loading" | ~3 min start on a one-call-at-a-time model, a double timeout on overload (150 s), and no progress or failure surface: one start path ignores a failed `/start` (`if (!boot.ok) return`) and the other never reads the response status. | **Open** — needs the decisions below. |
| 4 | Setup endpoint trusts client-supplied answer text | 26 specified-but-unimplemented tests in the untracked `test_opening_setup_security.py`. | **Open**, separate hardening task. |

## Proposed redesign (needs your decision)

Principle: the player waits on **model calls**, so spend them deliberately and make everything else
deterministic and visible.

1. **One opening plan, drawn once.** Seed (genre pool + a rolled twist from the tables), brief, character
   anchor and place are created together at setup and stored. Nothing downstream re-draws (defect 2 was
   the first instance of this rule).
2. **Character is server-side state**, returned as `me` with the session. The client stops matching
   identities (defect 1's root cause).
3. **Cut the start pipeline from ~8 calls to ~3.** Fold plot, narrative director and scene director into one
   planning call; keep composer + narrative as one prose call; run visual and analysis after the scene is
   shown. Target: first scene in under a minute.
4. **Show progress and failures.** Step-by-step status while `/start` runs, a Retry on failure, and a
   server-side "scene ready" check so a reload resumes instead of restarting.
5. **Stop double-waiting on overload.** Do not retry the same busy machine after a Steward read timeout.
6. **Optional:** allow 2 concurrent model calls (PC `OLLAMA_NUM_PARALLEL`) if VRAM allows; this halves
   queueing without changing any prompt.

Items 3 and 4 change the narrative architecture and the client's setup screens, so they should be
agreed before anything is built.
