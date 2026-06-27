"""Campaign interpretation and contract generation.

This layer turns campaign setup inputs into durable operating rules that agents
can consume. It is intentionally deterministic first: user expectations should
not disappear when the underlying model changes.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


POSTURES = {
    "player_fast_start",
    "guided_builder",
    "lore_importer",
    "system_designer",
    "gm_assist",
    "hybrid",
}


def _text(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif isinstance(value, dict):
            parts.extend(str(v) for v in value.values())
    return " ".join(parts).lower()


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = str(item or "").strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def _split_terms(value: Any) -> list[str]:
    if isinstance(value, list):
        return _unique([str(v) for v in value])
    if isinstance(value, str):
        return _unique([p.strip() for p in re.split(r"[,;\n]+", value) if p.strip()])
    return []


def detect_creation_posture(settings: dict[str, Any], variables: dict[str, Any], docs: list[str] | None = None) -> tuple[str, float]:
    explicit = str(settings.get("creation_posture") or variables.get("creation_posture") or "").strip()
    if explicit in POSTURES:
        return explicit, 1.0

    hay = _text(settings, variables, docs or [])
    docs_len = sum(len(d or "") for d in (docs or []))
    advanced_fields = sum(1 for key in ("house_rules", "factions", "npc_archetypes", "naming_style") if variables.get(key) or settings.get(key))

    scores = {
        "player_fast_start": 0.45,
        "guided_builder": 0.35,
        "lore_importer": 0.2 + (0.45 if docs_len > 800 else 0) + (0.2 if any(w in hay for w in ("lore", "canon", "import", "pdf", "setting bible")) else 0),
        "system_designer": 0.15 + (0.14 * advanced_fields) + (0.2 if any(w in hay for w in ("custom", "house rule", "homebrew", "difficulty", "sandbox")) else 0),
        "gm_assist": 0.15 + (0.5 if any(w in hay for w in ("human gm", "gm assist", "prep", "notes only", "player-run", "player_run")) else 0),
    }
    if scores["lore_importer"] >= 0.55 and scores["system_designer"] >= 0.45:
        return "hybrid", 0.72
    posture, score = max(scores.items(), key=lambda kv: kv[1])
    return posture, round(min(score, 0.95), 2)


def _play_pillars(hay: str, variables: dict[str, Any]) -> tuple[list[str], list[str]]:
    explicit = _split_terms(variables.get("themes"))
    primary: list[str] = []
    secondary: list[str] = []
    checks = [
        ("investigation", ("mystery", "investigation", "clue", "detective", "slow-burn")),
        ("social", ("roleplay", "political", "intrigue", "relationship", "dialogue")),
        ("combat", ("combat", "tactical", "battle", "boss", "fight")),
        ("exploration", ("exploration", "travel", "discover", "expedition", "hex")),
        ("survival", ("survival", "scarcity", "weather", "supplies", "fatigue")),
        ("character_drama", ("backstory", "drama", "personal", "betrayal", "mentor")),
    ]
    for pillar, words in checks:
        if any(w in hay for w in words):
            primary.append(pillar)
    if not primary:
        primary = ["exploration", "social"]
    for theme in explicit:
        lowered = theme.lower()
        if "betray" in lowered and "character_drama" not in primary:
            secondary.append("character_drama")
        if "surviv" in lowered and "survival" not in primary:
            secondary.append("survival")
    for pillar, _ in checks:
        if pillar not in primary and pillar not in secondary:
            secondary.append(pillar)
        if len(secondary) >= 3:
            break
    return _unique(primary[:3]), _unique(secondary[:3])


def _canon_policy(hay: str, posture: str) -> str:
    if any(w in hay for w in ("strict canon", "only canon", "do not invent", "approved lore")):
        return "strict_canon"
    if posture == "lore_importer" or any(w in hay for w in ("canon", "lore", "setting bible")):
        return "guided_canon"
    if any(w in hay for w in ("improvise", "surprise me", "invent freely", "sandbox")):
        return "flexible_canon"
    return "guided_canon"


def _creativity_level(hay: str, posture: str) -> str:
    if any(w in hay for w in ("conservative", "low invention", "do not invent", "strict")):
        return "conservative"
    if any(w in hay for w in ("expansive", "surprise me", "wild", "improvise", "invent freely")):
        return "expansive"
    if posture == "player_fast_start":
        return "balanced"
    return "balanced"


def _profile(level: str = "medium", **extra: Any) -> dict[str, Any]:
    return {"intensity": level, **extra}


def _description_depth(hay: str) -> str:
    if any(w in hay for w in ("rich description", "detailed description", "immersive", "atmospheric", "cannot see")):
        return "high"
    if any(w in hay for w in ("brief", "concise", "fast")):
        return "medium-low"
    return "medium-high"


def _extract_named_entities(docs: list[str]) -> list[dict[str, Any]]:
    """Extract named entities (NPCs, places, factions) from lore text and tag with canon status."""
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Labelled entity lines (highest confidence — user explicitly declared these)
    _ENTITY_LABELS: dict[str, str] = {
        "npc": "npc", "character": "npc", "villain": "npc", "ally": "npc",
        "enemy": "npc", "contact": "npc", "boss": "npc", "patron": "npc",
        "location": "place", "place": "place", "town": "place", "city": "place",
        "village": "place", "dungeon": "place", "keep": "place", "fortress": "place",
        "region": "place", "landmark": "place",
        "faction": "faction", "guild": "faction", "order": "faction", "house": "faction",
        "cult": "faction", "clan": "faction", "council": "faction",
    }
    for doc in docs:
        for line in doc.splitlines():
            stripped = line.strip()
            lower = stripped.lower()
            for label, entity_type in _ENTITY_LABELS.items():
                if lower.startswith(label + ":") or lower.startswith(label + " -"):
                    raw_name = stripped[len(label):].lstrip(":- \t").split(",")[0].split(".")[0].strip()
                    # Take only the first word-group that looks like a proper name
                    name_match = re.match(r"([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})", raw_name)
                    name = name_match.group(1).strip() if name_match else raw_name[:60].strip()
                    key = name.lower()
                    if name and key not in seen:
                        seen.add(key)
                        entities.append({
                            "name": name,
                            "type": entity_type,
                            "canon_status": "player_canon",
                            "source": "labelled_lore",
                            "note": "",
                        })
                    break

    # Inline proper-noun extraction for unlabelled mentions of known-entity words
    # Pattern: "The <ProperNoun> <keyword>" or "<ProperNoun> <keyword>"
    _INLINE_PATTERNS = [
        (r"\bThe\s+([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+)?)\s+(?:Guild|Order|Cult|House|Clan|Council|Brotherhood|Syndicate)\b", "faction"),
        (r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+)?)\s+(?:Guild|Order|Cult|House|Clan|Council|Brotherhood|Syndicate)\b", "faction"),
        (r"\b(?:Lord|Lady|King|Queen|Duke|Duchess|Count|Baron|Captain|General|Elder|Master|High Priest|Archon)\s+([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+)?)\b", "npc"),
        (r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+)?)\s+(?:City|Town|Village|Keep|Fortress|Temple|Academy|Isle|Pass|Vale|Crossing|Gate|Bridge)\b", "place"),
        (r"\bThe\s+([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+)?)\s+(?:City|Town|Village|Keep|Fortress|Temple|Academy)\b", "place"),
    ]
    full_text = "\n".join(docs)
    for pattern, entity_type in _INLINE_PATTERNS:
        for m in re.finditer(pattern, full_text):
            name = m.group(1).strip()
            key = name.lower()
            if name and key not in seen and len(name) > 2:
                seen.add(key)
                entities.append({
                    "name": name,
                    "type": entity_type,
                    "canon_status": "provisional",
                    "source": "inline_mention",
                    "note": "Mentioned in lore; promote to player_canon if confirmed.",
                })

    return entities


def _detect_contradictions(entities: list[dict[str, Any]]) -> list[str]:
    """Flag names that appear with conflicting entity types."""
    by_name: dict[str, list[str]] = {}
    for e in entities:
        key = e["name"].lower()
        t = e["type"]
        by_name.setdefault(key, [])
        if t not in by_name[key]:
            by_name[key].append(t)
    return [
        f"'{name}' appears as both {' and '.join(types)} — clarify which it is."
        for name, types in by_name.items()
        if len(types) > 1
    ]


def interpret_imports(docs: list[str] | None = None) -> dict[str, Any]:
    docs = docs or []
    hay = _text(docs)
    symbols = [w for w in ("sand", "water", "lantern", "ash", "blood", "ice", "crown", "gate", "storm") if w in hay]
    conflicts = []
    if any(w in hay for w in ("merchant", "guild", "coin", "debt")):
        conflicts.append("economic pressure")
    if any(w in hay for w in ("god", "temple", "cult", "priest")):
        conflicts.append("religious tension")
    if any(w in hay for w in ("king", "queen", "council", "faction", "house")):
        conflicts.append("political intrigue")
    story_types = []
    if any(w in hay for w in ("wilderness", "supplies", "scarcity", "cold", "desert")):
        story_types.append("survival")
    if conflicts:
        story_types.append("political intrigue" if "political intrigue" in conflicts else "investigation")

    entities = _extract_named_entities(docs)
    canon_entities = [e for e in entities if e["canon_status"] == "player_canon"]
    provisional_entities = [e for e in entities if e["canon_status"] == "provisional"]
    ambiguities = _detect_contradictions(entities)

    # Identify dangerous/safe places from entity list and inline keywords
    safe_places = [e["name"] for e in entities if e["type"] == "place" and any(
        w in hay for w in ("sanctuary", "safe", "refuge", "home", "tavern", "inn", "guild hall")
    )]
    dangerous_places = [e["name"] for e in entities if e["type"] == "place" and any(
        w in hay for w in ("dungeon", "tomb", "forbidden", "cursed", "ruins", "enemy", "dangerous")
    )]

    return {
        "natural_story_types": _unique(story_types or ["adventure"]),
        "recurring_conflicts": _unique(conflicts),
        "recurring_symbols": _unique(symbols),
        "implicit_themes": _unique([c.replace(" pressure", "") for c in conflicts]),
        "power_structures": _unique([p for p in ("guild", "temple", "council", "crown") if p in hay]),
        "safe_places": _unique(safe_places[:4]),
        "dangerous_places": _unique(dangerous_places[:4]),
        "unresolved_hooks": [],
        "canon_sensitive_entities": canon_entities,
        "provisional_entities": provisional_entities,
        "all_named_entities": entities,
        "ambiguities": ambiguities,
    }


def interpret_backstory(
    *,
    character_id: str | int | None = None,
    player_id: str | int | None = None,
    character_name: str = "",
    text: str = "",
) -> dict[str, Any]:
    raw = (text or "").strip()
    hay = raw.lower()

    people: list[dict[str, Any]] = []
    places: list[dict[str, Any]] = []
    unresolved: list[str] = []
    hooks: list[str] = []
    stakes: list[str] = []

    mentor_match = re.search(r"\bmentor\b(?: named| called)?\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?)?", raw)
    if "mentor" in hay:
        people.append({
            "name": (mentor_match.group(1) if mentor_match and mentor_match.group(1) else "missing mentor"),
            "status": "unknown" if any(w in hay for w in ("missing", "disappeared", "lost")) else "established",
            "relationship": "mentor",
            "canon_status": "provisional_backstory",
        })
        unresolved.append(f"What happened to {character_name or 'the character'}'s mentor?")
        hooks.append("A sign connected to the mentor appears where it should not.")
    for label in ("academy", "temple", "village", "city", "guild", "camp", "house"):
        m = re.search(rf"\b([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?)\s+{label}\b", raw)
        if m:
            places.append({"name": f"{m.group(1)} {label.title()}", "type": label, "canon_status": "provisional_backstory"})
    if "debt" in hay or "owe" in hay:
        stakes.append("A debt from the past can be called in at a dangerous moment.")
        hooks.append("Someone arrives to collect an old debt.")
    if "secret" in hay:
        unresolved.append("What happens if the secret is exposed?")
        hooks.append("A past secret is threatened through implication, not immediate reveal.")
    if "rival" in hay or "enemy" in hay:
        hooks.append("A rival complication appears with a demand or accusation.")
    if any(w in hay for w in ("fled", "exile", "banished", "escaped")):
        stakes.append("The past may catch up, but major accusations require player-facing setup.")

    beliefs = []
    for word in ("justice", "freedom", "knowledge", "family", "faith", "power", "truth"):
        if word in hay:
            beliefs.append(word)

    summary = raw[:320] if raw else ""
    return {
        "character_id": str(character_id or ""),
        "player_id": str(player_id or ""),
        "character_name": character_name,
        "backstory_summary": summary,
        "origin": "",
        "formative_events": [],
        "important_people": people,
        "rivals": [],
        "enemies": [],
        "family": [],
        "mentors": [p for p in people if p.get("relationship") == "mentor"],
        "lost_people": [p for p in people if p.get("status") == "unknown"],
        "debts": ["old debt"] if ("debt" in hay or "owe" in hay) else [],
        "promises": [],
        "secrets": ["protected secret"] if "secret" in hay else [],
        "fears": [],
        "desires": [],
        "beliefs": beliefs,
        "values": beliefs,
        "wounds": [],
        "unresolved_questions": unresolved,
        "personal_stakes": stakes,
        "places_from_past": places,
        "items_of_significance": [],
        "factions_connected": [],
        "possible_hooks": hooks,
        "hard_boundaries": [],
        "spotlight_preferences": {},
        "canon_status": "player_canon" if raw else "ai_inferred",
    }


def build_backstory_hooks(profile: dict[str, Any]) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    char_id = str(profile.get("character_id") or "")
    for idx, summary in enumerate(profile.get("possible_hooks") or []):
        lowered = str(summary).lower()
        if "mentor" in lowered:
            hook_type = "mentor_message"
        elif "debt" in lowered:
            hook_type = "debt_called_in"
        elif "rival" in lowered:
            hook_type = "rival_complication"
        elif "secret" in lowered:
            hook_type = "secret_threatened"
        else:
            hook_type = "symbol_reappears"
        hook_id = hashlib.sha1(f"{char_id}:{idx}:{summary}".encode("utf-8")).hexdigest()[:12]
        hooks.append({
            "hook_id": hook_id,
            "character_id": char_id,
            "type": hook_type,
            "summary": summary,
            "subtle_version": summary,
            "direct_version": summary,
            "stakes": "; ".join(profile.get("personal_stakes") or [])[:240],
            "related_entities": [
                *(p.get("name") for p in profile.get("important_people", []) if isinstance(p, dict) and p.get("name")),
                *(p.get("name") for p in profile.get("places_from_past", []) if isinstance(p, dict) and p.get("name")),
            ],
            "canon_status": "provisional_backstory",
            "requires_user_approval": hook_type in {"secret_threatened", "family_request"},
        })
    return hooks


def build_spotlight_trackers(hooks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "character_id": hook.get("character_id", ""),
            "backstory_hook_id": hook.get("hook_id", ""),
            "importance": 50,
            "last_used_scene_id": "",
            "last_used_session_id": "",
            "times_used": 0,
            "status": "dormant",
            "next_possible_callback": "Use only when it reinforces the current scene.",
            "escalation_level": 0,
        }
        for hook in hooks
    ]


def build_backstory_thread_links(hooks: list[dict[str, Any]], campaign_dna: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach personal hooks to campaign DNA without making them mandatory plot rails."""
    threads = campaign_dna.get("initial_story_threads") or campaign_dna.get("central_questions") or ["main_thread"]
    links: list[dict[str, Any]] = []
    for idx, hook in enumerate(hooks):
        hook_type = str(hook.get("type") or "")
        if hook_type in {"symbol_reappears", "past_failure_echo", "belief_challenged", "value_tested", "wound_reopened"}:
            connection = "symbolic"
        elif hook_type in {"mentor_message", "person_returns", "old_enemy_appears", "family_request", "rival_complication"}:
            connection = "NPC"
        elif hook_type in {"home_location_in_trouble", "lost_item_found"}:
            connection = "location"
        elif hook_type in {"secret_threatened"}:
            connection = "secret"
        elif hook_type in {"debt_called_in", "promise_due"}:
            connection = "consequence"
        else:
            connection = "symbolic"
        thread = str(threads[idx % len(threads)] or "main_thread")
        links.append({
            "thread_id": re.sub(r"[^a-z0-9]+", "_", thread.lower()).strip("_") or "main_thread",
            "character_id": hook.get("character_id", ""),
            "backstory_hook_id": hook.get("hook_id", ""),
            "connection_type": connection,
            "strength": "subtle" if hook.get("requires_user_approval") else "moderate",
            "revealed_to_player": False,
        })
    return links


def interpret_campaign(
    *,
    campaign_id: str,
    campaign_name: str,
    description: str = "",
    settings: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    docs: list[str] | None = None,
    backstory_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = settings or {}
    variables = variables or {}
    docs = docs or []
    hay = _text(campaign_name, description, settings, variables, docs)
    posture, confidence = detect_creation_posture(settings, variables, docs)
    primary, secondary = _play_pillars(hay, variables)
    canon = _canon_policy(hay, posture)
    creativity = _creativity_level(hay, posture)
    import_interp = interpret_imports(docs)

    clarifying: list[str] = []
    low_conf: list[dict[str, Any]] = []
    if confidence < 0.6:
        low_conf.append({"setting": "creation_posture", "value": posture, "confidence": confidence, "source": "deterministic setup inference"})
        clarifying.append("Do you want a quick start, guided setup, or strict lore-import workflow?")
    if "investigation" in primary and "combat" not in primary:
        low_conf.append({"setting": "combat_frequency", "value": "low-medium", "confidence": 0.55, "source": "inferred from investigation/social emphasis"})

    return {
        "campaign_id": campaign_id,
        "creation_posture": posture,
        "onboarding_flow": _onboarding_flow(posture),
        "confidence": confidence,
        "source_summary": (description or settings.get("setting_summary") or campaign_name)[:500],
        "interpreted_genre": settings.get("genre") or variables.get("genre") or "fantasy",
        "interpreted_tone": settings.get("tone") or variables.get("narrative_style") or "balanced",
        "primary_play_pillars": primary,
        "secondary_play_pillars": secondary,
        "player_experience_goal": _experience_goal(primary, hay),
        "canon_policy": canon,
        "ai_creativity_level": creativity,
        "difficulty_profile": _profile("medium", resource_pressure="high" if "survival" in primary else "medium"),
        "pacing_profile": _pacing_profile(hay, variables),
        "roleplay_profile": _profile("high" if "social" in primary or "character_drama" in primary else "medium", npc_depth="high" if "social" in primary else "medium"),
        "combat_profile": _profile("high" if "combat" in primary else "medium-low", terrain_importance="high" if "tactical" in hay else "medium"),
        "mystery_profile": _profile("high" if "investigation" in primary else "medium", reveal_speed="slow" if "slow-burn" in hay or "mystery" in hay else "balanced", three_clue_rule="investigation" in primary),
        "exploration_profile": _profile("high" if "exploration" in primary else "medium"),
        "survival_profile": _profile("high" if "survival" in primary else "low", weather_importance="survival" in primary),
        "description_profile": _profile(_description_depth(hay), depth=_description_depth(hay), include_context_on_opening=True),
        "agency_profile": _profile("high", avoid_single_solution=True, player_choice_visibility="high"),
        "safety_profile": _safety_profile(hay, variables),
        "ui_emphasis": _ui_emphasis(primary),
        "assumptions": _assumptions(primary, canon, creativity),
        "low_confidence_items": low_conf,
        "clarifying_questions": clarifying,
        "import_interpretation": import_interp,
        "backstory_profiles": backstory_profiles or [],
    }


def _experience_goal(primary: list[str], hay: str) -> str:
    if "investigation" in primary:
        return "Uncover concrete clues, preserve mystery, and reward careful player reasoning."
    if "combat" in primary:
        return "Create tactically meaningful danger where positioning, resources, and intent matter."
    if "survival" in primary:
        return "Make weather, scarcity, shelter, and travel choices feel consequential."
    if "social" in primary:
        return "Center NPC desire, relationship memory, and emotionally meaningful dialogue."
    return "Deliver an open-ended adventure with vivid scenes and meaningful player choices."


def _onboarding_flow(posture: str) -> dict[str, Any]:
    flows = {
        "player_fast_start": {
            "mode": "minimal",
            "steps": ["confirm_defaults", "choose_character", "start_play"],
            "question_depth": "low",
        },
        "guided_builder": {
            "mode": "guided",
            "steps": ["tone", "pillars", "canon", "backstory", "session_zero"],
            "question_depth": "medium",
        },
        "lore_importer": {
            "mode": "lore_review",
            "steps": ["import_sources", "canon_policy", "ambiguities", "backstory", "session_zero"],
            "question_depth": "as_needed",
        },
        "system_designer": {
            "mode": "advanced",
            "steps": ["rules", "pacing", "creativity", "validators", "ui_emphasis", "session_zero"],
            "question_depth": "high",
        },
        "gm_assist": {
            "mode": "support",
            "steps": ["prep_scope", "notes", "encounters", "handoff_controls", "session_zero"],
            "question_depth": "medium",
        },
        "hybrid": {
            "mode": "hybrid",
            "steps": ["import_sources", "advanced_rules", "canon_policy", "ui_emphasis", "session_zero"],
            "question_depth": "adaptive",
        },
    }
    return flows.get(posture, flows["guided_builder"])


def _pacing_profile(hay: str, variables: dict[str, Any]) -> dict[str, Any]:
    pacing = str(variables.get("pacing") or "").lower()
    if not pacing:
        pacing = "slow" if "slow" in hay or "slow-burn" in hay else "fast" if "fast" in hay else "moderate"
    return {"speed": pacing, "scene_variety": "high", "downtime_frequency": "regular" if pacing == "slow" else "occasional"}


def _safety_profile(hay: str, variables: dict[str, Any]) -> dict[str, Any]:
    rating = variables.get("content_rating") or ("mature" if "mature" in hay else "pg-13")
    return {
        "content_rating": rating,
        "violence_detail": "low" if rating == "family" else "moderate",
        "fade_to_black": True,
        "respect_backstory_boundaries": True,
    }


def _ui_emphasis(primary: list[str]) -> dict[str, Any]:
    widgets: list[str] = ["objective", "observed", "risk"]
    if "investigation" in primary:
        widgets += ["noteworthy", "open_questions", "suspects"]
    if "social" in primary or "character_drama" in primary:
        widgets += ["relationships", "npc_motives"]
    if "survival" in primary:
        widgets += ["weather", "supplies", "fatigue", "travel_risk"]
    if "combat" in primary:
        widgets += ["initiative", "terrain", "conditions", "enemy_intent"]
    return {
        "primary_widgets": _unique(widgets[:6]),
        "secondary_widgets": _unique(widgets[6:]),
        "right_panel_default": "scene_relevant",
        "archive_default": "dashboard_cards",
        "noteworthy_label": "Noteworthy",
        "hidden_by_default": ["raw_logs", "debug_panels"],
        "mode_defaults": {"play": "story_first", "world": "archive_dashboard", "read": "book_spread"},
    }


def _assumptions(primary: list[str], canon: str, creativity: str) -> list[str]:
    return [
        f"Primary play pillars are {', '.join(primary)}.",
        f"Canon mode is {canon}.",
        f"AI creativity level is {creativity}.",
    ]


def build_campaign_dna(interpretation: dict[str, Any], variables: dict[str, Any] | None = None) -> dict[str, Any]:
    variables = variables or {}
    themes = _unique(_split_terms(variables.get("themes")) + interpretation.get("primary_play_pillars", []))
    return {
        "themes": themes[:6],
        "tone": interpretation.get("interpreted_tone", "balanced"),
        "genre": interpretation.get("interpreted_genre", "fantasy"),
        "recurring_symbols": interpretation.get("import_interpretation", {}).get("recurring_symbols", [])[:6],
        "central_questions": _central_questions(interpretation),
        "preferred_scene_types": interpretation.get("primary_play_pillars", []),
        "core_conflicts": interpretation.get("import_interpretation", {}).get("recurring_conflicts", [])[:6],
        "starting_promise": interpretation.get("player_experience_goal", ""),
        "initial_story_threads": interpretation.get("primary_play_pillars", [])[:3],
    }


def _central_questions(interpretation: dict[str, Any]) -> list[str]:
    pillars = interpretation.get("primary_play_pillars", [])
    questions = []
    if "investigation" in pillars:
        questions.append("What truth is being hidden, and who benefits from hiding it?")
    if "social" in pillars:
        questions.append("Who can be trusted when everyone wants something?")
    if "survival" in pillars:
        questions.append("What will the characters risk to endure another day?")
    if not questions:
        questions.append("What changes because the characters choose to act?")
    return questions


def build_campaign_contract(
    *,
    campaign_id: str,
    campaign_name: str,
    interpretation: dict[str, Any],
    settings: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    backstory_profiles: list[dict[str, Any]] | None = None,
    backstory_hooks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = settings or {}
    variables = variables or {}
    dna = build_campaign_dna(interpretation, variables)
    canon_mode = interpretation.get("canon_policy") or "guided_canon"
    creativity = interpretation.get("ai_creativity_level") or "balanced"
    backstory_policy = _backstory_policy(interpretation, backstory_profiles or [])
    ui_policy = interpretation.get("ui_emphasis") or _ui_emphasis(interpretation.get("primary_play_pillars", []))
    validator_policy = _validator_policy(interpretation, canon_mode, backstory_policy)

    contract = {
        "campaign_id": campaign_id,
        "contract_version": 1,
        "campaign_name": campaign_name,
        "campaign_pitch": interpretation.get("source_summary") or settings.get("setting_summary") or campaign_name,
        "campaign_dna": dna,
        "canon_policy": {"mode": canon_mode, **_canon_rules(canon_mode)},
        "ai_creativity_policy": {"level": creativity, **_creativity_rules(creativity)},
        "tone_policy": {"tone": interpretation.get("interpreted_tone", "balanced"), "content_rating": interpretation.get("safety_profile", {}).get("content_rating", "pg-13")},
        "pacing_policy": interpretation.get("pacing_profile", {}),
        "difficulty_policy": interpretation.get("difficulty_profile", {}),
        "agency_policy": interpretation.get("agency_profile", {}),
        "mystery_policy": interpretation.get("mystery_profile", {}),
        "combat_policy": interpretation.get("combat_profile", {}),
        "roleplay_policy": interpretation.get("roleplay_profile", {}),
        "exploration_policy": interpretation.get("exploration_profile", {}),
        "survival_policy": interpretation.get("survival_profile", {}),
        "description_policy": interpretation.get("description_profile", {}),
        "backstory_policy": backstory_policy,
        "safety_policy": interpretation.get("safety_profile", {}),
        "memory_policy": {"promote_recurring_provisional_entities": canon_mode != "strict_canon", "preserve_player_canon": True},
        "ui_policy": ui_policy,
        "validator_policy": validator_policy,
        "agent_output_contract": "",
    }
    contract["agent_output_contract"] = build_agent_output_contract(contract, backstory_profiles or [], backstory_hooks or [])
    return contract


def _canon_rules(mode: str) -> dict[str, Any]:
    if mode == "strict_canon":
        return {"major_invention": "ask_first", "minor_detail_invention": "allowed", "new_entities_default": "provisional", "contradictions": "reject"}
    if mode == "flexible_canon":
        return {"major_invention": "allowed_if_compatible", "minor_detail_invention": "allowed", "new_entities_default": "provisional_promotable", "contradictions": "reject_major"}
    return {"major_invention": "ask_first", "minor_detail_invention": "allowed", "new_entities_default": "provisional", "contradictions": "reject"}


def _creativity_rules(level: str) -> dict[str, Any]:
    if level == "conservative":
        return {"new_elements_per_scene": 1, "subplot_creation": "rare", "prefer_existing_material": True}
    if level == "expansive":
        return {"new_elements_per_scene": 4, "subplot_creation": "active", "prefer_existing_material": True}
    return {"new_elements_per_scene": 2, "subplot_creation": "when_useful", "prefer_existing_material": True}


def _backstory_policy(interpretation: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    pillars = interpretation.get("primary_play_pillars", [])
    has_profiles = any((p.get("backstory_summary") or "").strip() for p in profiles)
    usage = "high" if "character_drama" in pillars else "medium" if has_profiles else "low"
    return {
        "usage_frequency": usage,
        "integration_style": "balanced" if has_profiles else "subtle",
        "player_control": "ask_before_major_changes",
        "spotlight_rotation": "balanced_party",
        "allow_backstory_threats": True,
        "allow_family_danger": False,
        "allow_secret_reveals": "with_setup",
        "allow_retcons": False,
        "callback_frequency": "regular" if usage == "high" else "occasional",
    }


def _validator_policy(interpretation: dict[str, Any], canon_mode: str, backstory_policy: dict[str, Any]) -> dict[str, Any]:
    pillars = interpretation.get("primary_play_pillars", [])
    return {
        "minimum_scene_score": 80 if "investigation" in pillars else 75,
        "require_multiple_approaches": True,
        "reject_single_solution": True,
        "require_concrete_clues": "investigation" in pillars,
        "preserve_unanswered_questions": "investigation" in pillars,
        "canon_mode": canon_mode,
        "flag_major_inventions": canon_mode == "strict_canon",
        "respect_backstory_boundaries": True,
        "allow_family_danger": backstory_policy.get("allow_family_danger", False),
    }


def build_agent_output_contract(contract: dict[str, Any], profiles: list[dict[str, Any]], hooks: list[dict[str, Any]]) -> str:
    dna = contract.get("campaign_dna", {})
    canon = contract.get("canon_policy", {})
    creativity = contract.get("ai_creativity_policy", {})
    mystery = contract.get("mystery_policy", {})
    backstory = contract.get("backstory_policy", {})
    lines = [
        "CAMPAIGN OUTPUT CONTRACT",
        "",
        f"Campaign: {contract.get('campaign_name') or 'Unnamed campaign'}",
        f"Genre/Tone: {dna.get('genre', 'fantasy')} / {dna.get('tone', 'balanced')}",
        f"Primary themes and pillars: {', '.join(dna.get('themes') or []) or 'open adventure'}",
        f"Canon mode: {canon.get('mode', 'guided_canon')} — major invention: {canon.get('major_invention', 'ask_first')}",
        f"AI creativity: {creativity.get('level', 'balanced')} — new elements per scene: {creativity.get('new_elements_per_scene', 2)}",
        "",
        "Write scenes that:",
        "- use uploaded/player canon before inventing new major facts",
        "- mark invented NPCs, factions, locations, and lore as provisional in memory/debug fields",
        "- offer multiple valid approaches and never force a single solution",
        "- ground stakes in concrete people, objects, deadlines, or visible consequences",
        "- include enough setting context that the player understands where they are and what can be acted on",
    ]
    if mystery.get("three_clue_rule"):
        lines.extend([
            "- preserve unanswered questions in mystery scenes",
            "- provide concrete, discoverable clues instead of abstract hints",
            "- do not reveal central mysteries too early",
        ])
    if backstory.get("usage_frequency") in {"medium", "high"} and hooks:
        lines.append("- connect events to player backstories when dramatically appropriate")
        for profile in profiles[:3]:
            name = profile.get("character_name") or profile.get("character_id") or "character"
            summary = profile.get("backstory_summary") or ""
            if summary:
                lines.append(f"- use {name}'s backstory as {backstory.get('integration_style', 'balanced')} story fuel: {summary[:140]}")
    lines.extend([
        "",
        "Do not:",
        "- contradict confirmed player canon",
        "- invent major gods, kingdoms, factions, cosmology, or historical truths when canon mode requires approval",
        "- reveal or twist backstory secrets without setup and consent",
        "- endanger protected family/backstory NPCs when policy forbids it",
        "- describe abstract stakes without concrete consequences",
    ])
    return "\n".join(lines)


def build_session_zero_summary(
    interpretation: dict[str, Any],
    contract: dict[str, Any],
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "summary": {
            "tone": f"{interpretation.get('interpreted_genre')} / {interpretation.get('interpreted_tone')}",
            "canon": contract.get("canon_policy", {}),
            "ai_creativity": contract.get("ai_creativity_policy", {}),
            "pacing": contract.get("pacing_policy", {}),
            "player_agency": contract.get("agency_policy", {}),
            "backstory_use": contract.get("backstory_policy", {}),
            "ui_emphasis": contract.get("ui_policy", {}),
            "characters_with_backstory": _unique([
                str(p.get("character_name") or p.get("character_id") or "")
                for p in profiles
                if (p.get("backstory_summary") or "").strip()
            ]),
        },
        "character_hooks": [
            {
                "character": p.get("character_name") or p.get("character_id"),
                "hooks": p.get("possible_hooks", []),
                "unresolved_questions": p.get("unresolved_questions", []),
            }
            for p in profiles
        ],
        "assumptions": interpretation.get("assumptions", []),
        "low_confidence_items": interpretation.get("low_confidence_items", []),
        "clarifying_questions": interpretation.get("clarifying_questions", []),
        "options": ["Confirm and Start", "Edit Interpretation", "Ask Me Questions", "Regenerate Interpretation"],
    }


def build_full_contract_package(
    *,
    campaign_id: str,
    campaign_name: str,
    description: str = "",
    settings: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    docs: list[str] | None = None,
    backstories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profiles = [
        interpret_backstory(
            character_id=item.get("character_id"),
            player_id=item.get("player_id"),
            character_name=item.get("character_name") or item.get("name") or "",
            text=item.get("backstory") or item.get("text") or "",
        )
        for item in (backstories or [])
    ]
    hooks = [hook for profile in profiles for hook in build_backstory_hooks(profile)]
    interpretation = interpret_campaign(
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        description=description,
        settings=settings,
        variables=variables,
        docs=docs,
        backstory_profiles=profiles,
    )
    contract = build_campaign_contract(
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        interpretation=interpretation,
        settings=settings,
        variables=variables,
        backstory_profiles=profiles,
        backstory_hooks=hooks,
    )
    thread_links = build_backstory_thread_links(hooks, contract.get("campaign_dna", {}))
    contract["backstory_thread_links"] = thread_links
    return {
        "campaign_interpretation": interpretation,
        "campaign_contract": contract,
        "backstory_profiles": profiles,
        "backstory_hooks": hooks,
        "backstory_thread_links": thread_links,
        "backstory_spotlight": build_spotlight_trackers(hooks),
        "session_zero": build_session_zero_summary(interpretation, contract, profiles),
        "debug": {
            "campaign_interpretation": interpretation,
            "campaign_contract": contract,
            "backstory_profiles": profiles,
            "backstory_hooks": hooks,
            "backstory_thread_links": thread_links,
            "low_confidence_assumptions": interpretation.get("low_confidence_items", []),
            "agent_output_contract": contract.get("agent_output_contract", ""),
            "validator_policy": contract.get("validator_policy", {}),
            "ui_policy": contract.get("ui_policy", {}),
        },
    }
