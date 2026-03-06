# Work Order

## Title
WO-012: AI Model Configuration Upgrade & Per-Campaign Model Selection

## Goal
Upgrade the default AI model from `gpt-4o-mini` to `gpt-4o` and add per-campaign model selection so operators and campaign hosts can choose the most appropriate model for their use case.

## Research Briefing
_See: Tech Lead Assessment 2026-03-06 — model configuration identified as needed for production readiness._
_"gpt 5.4" referenced in project brief; nearest available OpenAI model series is gpt-4o / gpt-4.1 family._

## Context
- All LLM calls in `narrative.py` (and soon `generate.py` post-WO-011) use `os.environ.get("OPENAI_MODEL", "gpt-4o-mini")` as a global default.
- `gpt-4o-mini` is cost-effective but lower quality for narrative generation; production campaigns may want `gpt-4o` or future models.
- There is currently no mechanism for a campaign host to override the model; it's operator-only via env var.
- New OpenAI models (gpt-4o, gpt-4.1, o4-mini) provide better instruction following and longer context — valuable for scene narration and NPC generation.
- `server/.env.example` currently does not document the `OPENAI_MODEL` variable.

## Scope / Non-Goals
- **In scope:**
  - Change the default model from `gpt-4o-mini` to `gpt-4o` in `narrative.py` (and `generate.py`)
  - Add `OPENAI_MODEL` to `server/.env.example` and root `.env.template` with documentation of supported values
  - Add optional `ai_model` field to `CampaignSettings` (stored in `campaign_settings` JSON column) that overrides the global env default for that campaign
  - Backend: read `ai_model` from campaign settings in `narrative.py` and `generate.py` when present
  - Update `docs/LOCAL_DEV.md` with model configuration guidance
- **Out of scope:**
  - Supporting non-OpenAI providers (Anthropic, local models) — future WO
  - Per-session or per-request model override
  - Token quota per campaign

## Acceptance Criteria
- [ ] Default model is `gpt-4o` (env var still overrides globally)
- [ ] `OPENAI_MODEL` is documented in `.env.example` and `.env.template` with a list of recommended values
- [ ] Campaign settings API accepts and persists `ai_model` field
- [ ] Narrative generation uses campaign's `ai_model` when set, falling back to env/default
- [ ] Generate endpoints (post-WO-011) use campaign's `ai_model` similarly
- [ ] Tests verify: campaign-level model override is passed to LLM call (mock)
- [ ] Documentation updated: `docs/LOCAL_DEV.md` and `docs/AI_AGENT_ONBOARDING.md`

## Implementation Notes
- **Files to modify:**
  - `server/agents/narrative.py` — change default, add campaign model lookup
  - `server/agents/generate.py` — same (coordinate with WO-011)
  - `server/agents/campaigns.py` — accept `ai_model` in settings payload
  - `server/.env.example` — document `OPENAI_MODEL`
  - `.env.template` — document `OPENAI_MODEL`
  - `docs/LOCAL_DEV.md` — add AI model section
- **Supported model values to document:**
  - `gpt-4o` (recommended default — best quality)
  - `gpt-4o-mini` (cost-efficient — suitable for dev/testing)
  - `gpt-4.1` (high capability, newer)
  - `o4-mini` (reasoning-optimized, higher latency)
- **Campaign settings schema addition:**
  ```json
  { "ai_model": "gpt-4o" }
  ```
  No migration needed — stored in existing JSON column.

## Test Plan
- `python -m pytest server/tests/test_campaign_settings.py -q`
- `python -m pytest server/tests/test_narrative_llm.py -q`

## Rollback
- Revert default back to `gpt-4o-mini` in narrative.py and generate.py
- Remove `ai_model` from settings handling (backwards-compatible; old settings without the field unaffected)
