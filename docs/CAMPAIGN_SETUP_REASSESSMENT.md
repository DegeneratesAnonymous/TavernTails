# Campaign setup reassessment (Oct 8 2026)

Triggered by two user reports: narratives not loading, and the selected character not sticking.
Everything below was measured from the live server's log and session folders, then re-checked by driving
the real UI in a browser (Playwright/Chromium against an isolated copy: own database, fresh client build,
the real model path).

## What the platform can actually do

| Capability | Measured |
| --- | --- |
| Model | One local `qwen3:14b` on ColemanPC, reached through Steward. Calls take 4–25 s (plot 4 s, scene director 13 s, composer 15–17 s, narrative 10–11 s, visual 4 s). |
| Concurrency | `server/steward_llm.py` runs **one** call at a time when `STEWARD_HOST` is set. "Parallel" calls queue (`queue_ms` of 25–50 s was routine). |
| Overload | A busy PC burns 90 s on Steward and then 60 s on direct Ollama against the *same* machine. |
| Deterministic content | Genre seed pools, the campaign contract, character sheets and the rollable tables cost no model time. |

A clean start is **5 model calls, ≈ 50 s**: plot, scene director, composer, narrative, visual.

## What was wrong, and what was done

| # | Symptom | Cause | Status |
| --- | --- | --- | --- |
| 1 | Selected character is lost | Steward SSO stored only the token; the dashboard finds "my" party member by matching `localStorage` `user_email`/`user_username`, which SSO never set. | **Fixed.** SSO stores identity; `/player/me` fallback (now returns email/username). Browser-verified: a token-only login re-learned the identity, and a returning player still saw their chosen character. Not confirmed: the character card after a token-only return (the test context did not reopen the session). |
| 2 | Brief says one place, scene opens in another | The questionnaire and `/start` each drew their own random seed. | **Fixed.** The seed is stored on the session and every opening-path draw reuses it. |
| 3 | Scene takes ~3 min and shows "Setup Pending" the whole time | **`/start` had no guard.** One session received 5 start requests (dashboard, `NarrativeView` fallback, reloads), each a full pipeline through the one-at-a-time model: 22 calls instead of 5. | **Fixed.** `/start` joins a running pipeline; one pipeline per session. Measured: **54 s**, one request. |
| 4 | Nothing to look at while it runs | Every new session ships a placeholder `scene.json` that *already contains narration text*, so the UI showed it as the story and a "ready" check would call it done. | **Fixed.** Placeholder (`setup_pending`) is the waiting state; real progress panel (5 stages, elapsed time, Try again on failure); resumes after a reload mid-generation. |
| 5 | Returning mid-setup was a dead end | "Setup Pending" had no action. | **Fixed.** "One more step before the story begins" with a Continue setup button. |
| 6 | The opening ignored the player's premise | `_seed_from_campaign_premise` is hand-written keyword templates, and they match on single words (a lighthouse premise containing "drowned" + "tide" opened at a "reef gate"); everything else got a random pool pick. | **Fixed.** One bounded model call (≈ 10 s, 45 s cap) reads the premise into the seed; templates and pools are the fallback. Verified on the live model for a toll-crossing premise; the lighthouse re-check is below. |
| 7 | Opening read as boilerplate | The model's prose was *thrown away* and replaced by the deterministic template when it failed any soft check (copied a brief sentence, no invented hook/timer). The rule meant to prevent this applied only to premises with an "authored object". | **Fixed.** Model prose is kept; copied brief sentences are trimmed. A real failure still falls back. |
| 8 | Rolled table ingredient could sink an opening | Two creature-encounter rolls (a storm-giant reunion at a marsh lighthouse) pushed the draft to score 45 of 70. | **Fixed.** Openings roll one gentle detail (sensory/clue/rumour/event); a draft that misses the bar is retried without rolls. |
| 9 | UI defects | Premise textarea overflowed its card and used small-caps; errors were gold, not red; "My Campaigns" was dark-on-dark; story text was monospace; the character card covered World/Focus/Debug; header said "Not started yet" forever; long answers were all-caps; selected radio showed "x". | **Fixed.** Checked in the browser via computed styles and hit-testing, except the answer-option text and radio glyph, which were changed but not re-screenshotted. |
| 10 | Setup endpoint trusts client-supplied answer text | 26 specified-but-unimplemented tests in the untracked `test_opening_setup_security.py`. | **Open**, separate hardening task. |

## Not verified

The last three changes (premise-first extraction, one gentle opening roll, retry without rolls) have unit
tests and were each exercised live earlier, but the final end-to-end browser run was cut short: the model
backend on ColemanPC stopped answering (direct Ollama calls hung past 170 s with the model loaded).
Re-run the walkthrough once the GPU is free.

## Still open (design, not bugs)

- "Quick Start" exposes about eight decisions (canon, AI creativity, playstyle, "Session zero preview",
  "Posture") for a flow that promises "pick a genre and name your campaign".
- Wizard cards are a fixed ~770 px column, left-aligned, on wide screens.
- 90 s + 60 s double timeout on overload (retrying the same busy machine).
