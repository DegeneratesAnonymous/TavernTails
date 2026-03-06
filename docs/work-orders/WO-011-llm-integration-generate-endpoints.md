# Work Order

## Title
WO-011: LLM Integration for Generate Endpoints (NPC / Location / Loot)

## Goal
Replace the placeholder stub responses in `/generate/npc`, `/generate/location`, and `/generate/loot` with real LLM-powered generation that respects campaign context and ruleset.

## Research Briefing
_See: Tech Lead Assessment 2026-03-06 — generate.py TODOs identified as highest-impact backend gap._

## Context
- `server/agents/generate.py` contains three endpoints (`/generate/npc`, `/generate/location`, `/generate/loot`) that build rich context objects but return hardcoded placeholder data due to three open `# TODO: Integrate with LLM` comments.
- `server/agents/narrative.py` already has a working LLM integration pattern: reads `OPENAI_API_KEY` + `OPENAI_MODEL` env vars, calls `openai.ChatCompletion.create`, handles structured JSON responses with graceful fallback.
- `server/agents/srd.py` provides `build_ruleset_prompt_context()` for ruleset-aware prompting (already plumbed into generate context).
- The frontend calls these endpoints from campaign management to help GMs prepare content; stubs currently give a poor experience.

## Scope / Non-Goals
- **In scope:**
  - Implement LLM calls in `generate_npc`, `generate_location`, and `generate_loot` following the pattern in `narrative.py`
  - System prompts that use campaign context (world name, tone, themes, factions, ruleset) and return structured JSON
  - Graceful fallback to existing placeholder when no `OPENAI_API_KEY` is configured
  - Add `server/tests/test_generate_llm.py` covering both LLM and no-key fallback paths (mock openai)
- **Out of scope:**
  - Frontend changes (endpoints already wired)
  - Image generation for NPCs/locations (WO future)
  - Streaming responses (batch for now)
  - Saving generated content to DB (separate WO)

## Acceptance Criteria
- [ ] When `OPENAI_API_KEY` is set, `/generate/npc` returns LLM-generated name, description, personality, and motivation
- [ ] When `OPENAI_API_KEY` is set, `/generate/location` returns LLM-generated name, description, atmosphere, and points-of-interest
- [ ] When `OPENAI_API_KEY` is set, `/generate/loot` returns LLM-generated item list appropriate to CR and ruleset
- [ ] All three endpoints fall back gracefully when no API key is configured
- [ ] Campaign context (world name, tone, themes, factions, content rating) is used in prompts
- [ ] Ruleset context from `build_ruleset_prompt_context()` is included in NPC and loot prompts
- [ ] System prompts do not reproduce copyrighted rules text (use mechanic descriptors only)
- [ ] Tests cover: LLM path (mocked), fallback path, missing campaign (404), wrong owner (403)
- [ ] No `# TODO` comments remain in generate.py

## Implementation Notes
- **File to modify:** `server/agents/generate.py`
- **Pattern to follow:** `server/agents/narrative.py` lines 51–122 (openai import, key check, ChatCompletion.create, JSON parse, graceful fallback)
- **Suggested system prompts:**
  - NPC: "You are a tabletop GM creating an NPC. Given the world/tone/factions context, produce a JSON object with fields: name, description, personality, motivation, appearance, faction_affiliation. Keep it concise and avoid reproducing copyrighted rules text."
  - Location: "Produce a JSON object with fields: name, description, atmosphere, points_of_interest (list), rumors (list), connections_to_factions."
  - Loot: "Produce a JSON object with fields: name, description, items (list of {name, quantity, type, rarity, description}), total_value_gp. Items should be appropriate for CR {cr} in {ruleset}."
- **Model selection:** Use `os.environ.get("OPENAI_MODEL", "gpt-4o")` (same as narrative.py)
- **New test file:** `server/tests/test_generate_llm.py`
  - Use `unittest.mock.patch('openai.ChatCompletion.create', return_value=...)` or patch the openai module
  - Test NPC, location, and loot endpoints with mocked LLM response
  - Test fallback when `OPENAI_API_KEY` is not set

## Test Plan
- `python -m pytest server/tests/test_generate_llm.py -q`
- Manual: Set `OPENAI_API_KEY=sk-...` and call `/generate/npc` with a campaign ID; verify structured response

## Rollback
- Revert `server/agents/generate.py` to stub version
- Remove `server/tests/test_generate_llm.py`
