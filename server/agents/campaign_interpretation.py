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


def _unique_entities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        entity_type = str(item.get("type") or item.get("relationship") or "entity").strip()
        if not name:
            continue
        key = (name.lower(), entity_type.lower())
        if key in seen:
            continue
        seen.add(key)
        cleaned = dict(item)
        cleaned["name"] = name
        cleaned["type"] = entity_type
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
        ("investigation", ("mystery", "investigation", "clue", "detective", "slow-burn", "slow burn")),
        ("social", ("roleplay", "roleplay-heavy", "roleplay heavy", "political", "intrigue", "relationship", "dialogue")),
        ("combat", ("combat", "tactical", "tactical combat", "battle", "boss", "fight")),
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


def _canon_policy(hay: str, posture: str, settings: dict[str, Any] | None = None, variables: dict[str, Any] | None = None) -> str:
    explicit = str((settings or {}).get("canon_policy") or (settings or {}).get("canon_mode") or (variables or {}).get("canon_policy") or (variables or {}).get("canon_mode") or "").strip()
    if explicit in {"strict_canon", "guided_canon", "flexible_canon"}:
        return explicit
    if any(w in hay for w in ("strict canon", "only canon", "do not invent", "approved lore")):
        return "strict_canon"
    if posture == "lore_importer" or any(w in hay for w in ("canon", "lore", "setting bible")):
        return "guided_canon"
    if any(w in hay for w in ("improvise", "surprise me", "invent freely", "sandbox")):
        return "flexible_canon"
    return "guided_canon"


def _creativity_level(hay: str, posture: str, settings: dict[str, Any] | None = None, variables: dict[str, Any] | None = None) -> str:
    explicit = str((settings or {}).get("ai_creativity_level") or (settings or {}).get("creativity_level") or (variables or {}).get("ai_creativity_level") or (variables or {}).get("creativity_level") or "").strip()
    if explicit in {"conservative", "balanced", "expansive"}:
        return explicit
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
    if any(w in hay for w in ("missing", "vanished", "murder", "stolen", "sealed", "forbidden")):
        conflicts.append("unresolved danger")
    story_types = []
    if any(w in hay for w in ("wilderness", "supplies", "scarcity", "cold", "desert")):
        story_types.append("survival")
    if any(w in hay for w in ("mystery", "clue", "secret", "vanished", "missing", "forbidden")):
        story_types.append("investigation")
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
    unresolved_hooks = []
    if any(w in hay for w in ("missing", "vanished", "disappeared")):
        unresolved_hooks.append("A disappearance in the imported lore needs an answer.")
    if any(w in hay for w in ("sealed", "forbidden", "locked", "buried")):
        unresolved_hooks.append("A sealed or forbidden truth can surface through clues.")
    if any(w in hay for w in ("debt", "owed", "bargain", "promise")):
        unresolved_hooks.append("An old obligation can be called in during play.")
    if any(w in hay for w in ("betrayed", "traitor", "double agent")):
        unresolved_hooks.append("A betrayal thread should remain playable until revealed.")

    ambiguous_terms = []
    for word in ("unknown", "unclear", "maybe", "rumor", "rumour", "contradicts", "contradiction"):
        if word in hay:
            ambiguous_terms.append(f"Lore contains '{word}', so this detail should be confirmed before becoming canon.")

    return {
        "natural_story_types": _unique(story_types or ["adventure"]),
        "recurring_conflicts": _unique(conflicts),
        "recurring_symbols": _unique(symbols),
        "implicit_themes": _unique([c.replace(" pressure", "") for c in conflicts]),
        "power_structures": _unique([p for p in ("guild", "temple", "council", "crown") if p in hay]),
        "safe_places": _unique(safe_places[:4]),
        "dangerous_places": _unique(dangerous_places[:4]),
        "unresolved_hooks": _unique(unresolved_hooks),
        "canon_sensitive_entities": canon_entities,
        "provisional_entities": provisional_entities,
        "all_named_entities": entities,
        "ambiguities": _unique(ambiguities + ambiguous_terms),
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
    rivals: list[dict[str, Any]] = []
    enemies: list[dict[str, Any]] = []
    family: list[dict[str, Any]] = []
    promises: list[str] = []
    fears: list[str] = []
    desires: list[str] = []
    wounds: list[str] = []
    hard_boundaries: list[str] = []
    items: list[dict[str, Any]] = []
    factions: list[dict[str, Any]] = []

    def _named_after(label: str) -> str:
        match = re.search(
            rf"\b{label}\b(?: named| called| is| was)?\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?)",
            raw,
        )
        return match.group(1).strip() if match and match.group(1) else ""

    mentor_match = re.search(r"\bmentor\b(?: named| called)?\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?)?", raw)
    if "mentor" in hay:
        mentor_name = mentor_match.group(1) if mentor_match and mentor_match.group(1) else "missing mentor"
        people.append({
            "name": mentor_name,
            "type": "npc",
            "status": "unknown" if any(w in hay for w in ("missing", "disappeared", "lost")) else "established",
            "relationship": "mentor",
            "canon_status": "player_canon" if mentor_name != "missing mentor" else "provisional_backstory",
        })
        unresolved.append(f"What happened to {character_name or 'the character'}'s mentor?")
        hooks.append("A sign connected to the mentor appears where it should not.")
    for label in ("academy", "temple", "village", "city", "guild", "camp", "house"):
        m = re.search(rf"\b([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?)\s+{label}\b", raw)
        if m:
            canon_status = "player_canon" if m.group(0) in raw else "provisional_backstory"
            places.append({"name": f"{m.group(1)} {label.title()}", "type": "place", "subtype": label, "canon_status": canon_status})
    for label in ("mother", "father", "sister", "brother", "parent", "child", "spouse"):
        if label in hay:
            name = _named_after(label)
            person = {
                "name": name or label,
                "type": "npc",
                "relationship": label,
                "status": "established",
                "canon_status": "player_canon" if name else "provisional_backstory",
            }
            family.append(person)
            people.append(person)
            hooks.append("A family request creates pressure without removing player choice.")
    rival_name = _named_after("rival")
    enemy_name = _named_after("enemy")
    if rival_name or "rival" in hay:
        rival = {
            "name": rival_name or "unnamed rival",
            "type": "npc",
            "relationship": "rival",
            "status": "active",
            "canon_status": "player_canon" if rival_name else "provisional_backstory",
        }
        rivals.append(rival)
        people.append(rival)
        hooks.append("A rival complication appears with a demand or accusation.")
    if enemy_name or "enemy" in hay:
        enemy = {
            "name": enemy_name or "old enemy",
            "type": "npc",
            "relationship": "enemy",
            "status": "active",
            "canon_status": "player_canon" if enemy_name else "provisional_backstory",
        }
        enemies.append(enemy)
        people.append(enemy)
        hooks.append("An old enemy appears with leverage, not an automatic defeat.")
    if "debt" in hay or "owe" in hay:
        stakes.append("A debt from the past can be called in at a dangerous moment.")
        hooks.append("Someone arrives to collect an old debt.")
    if "secret" in hay:
        unresolved.append("What happens if the secret is exposed?")
        hooks.append("A past secret is threatened through implication, not immediate reveal.")
    if any(w in hay for w in ("fled", "exile", "banished", "escaped")):
        stakes.append("The past may catch up, but major accusations require player-facing setup.")
        wounds.append("forced flight or exile")
    if any(w in hay for w in ("promised", "vow", "swore", "oath")):
        promises.append("unresolved promise or oath")
        hooks.append("A promise comes due when keeping it costs something.")
    if any(w in hay for w in ("afraid", "fear", "terrified")):
        fears.append("past fear should be challenged with consent and care")
    if any(w in hay for w in ("wants", "seeks", "dreams", "desire")):
        desires.append("personal desire from backstory can shape rewards and choices")
    if any(w in hay for w in ("amulet", "sword", "ring", "letter", "journal", "map")):
        items.append({"name": "significant keepsake", "type": "item", "canon_status": "player_canon"})
        hooks.append("A lost item or keepsake is recognized by someone unexpected.")
    for label in ("guild", "order", "cult", "house", "clan", "council"):
        if label in hay:
            factions.append({"name": label, "type": "faction", "canon_status": "provisional_backstory"})

    if any(p in hay for p in ("no family danger", "do not endanger family", "don't endanger family", "family is off limits")):
        hard_boundaries.append("family_danger")
    if any(p in hay for p in ("no secret reveal", "do not reveal", "secret is private", "keep secret private")):
        hard_boundaries.append("secret_reveal")
    if any(p in hay for p in ("no betrayal", "no betrayal twist", "do not betray")):
        hard_boundaries.append("betrayal_twist")
    if any(p in hay for p in ("no hidden lineage", "not secretly royal", "do not change my origin")):
        hard_boundaries.append("identity_retcon")

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
        "rivals": rivals,
        "enemies": enemies,
        "family": family,
        "mentors": [p for p in people if p.get("relationship") == "mentor"],
        "lost_people": [p for p in people if p.get("status") == "unknown"],
        "debts": ["old debt"] if ("debt" in hay or "owe" in hay) else [],
        "promises": promises,
        "secrets": ["protected secret"] if "secret" in hay else [],
        "fears": fears,
        "desires": desires,
        "beliefs": beliefs,
        "values": beliefs,
        "wounds": wounds,
        "unresolved_questions": unresolved,
        "personal_stakes": stakes,
        "places_from_past": places,
        "items_of_significance": items,
        "factions_connected": factions,
        "possible_hooks": hooks,
        "private_facts": ["protected secret"] if "secret" in hay else [],
        "hard_boundaries": hard_boundaries,
        "spotlight_preferences": {
            "frequency": "high" if any(w in hay for w in ("spotlight", "personal arc", "character arc")) else "balanced",
            "approval_required_for": hard_boundaries + (["secret_reveal"] if "secret" in hay else []),
        },
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
        elif "enemy" in lowered:
            hook_type = "old_enemy_appears"
        elif "family" in lowered:
            hook_type = "family_request"
        elif "secret" in lowered:
            hook_type = "secret_threatened"
        elif "promise" in lowered or "oath" in lowered or "vow" in lowered:
            hook_type = "promise_due"
        elif "lost item" in lowered or "keepsake" in lowered:
            hook_type = "lost_item_found"
        elif "home" in lowered:
            hook_type = "home_location_in_trouble"
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
            "requires_user_approval": hook_type in {"secret_threatened", "family_request", "old_enemy_appears"},
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


def _backstory_contract_entities(profiles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    player_canon: list[dict[str, Any]] = []
    provisional: list[dict[str, Any]] = []
    entity_fields = (
        "important_people",
        "places_from_past",
        "items_of_significance",
        "factions_connected",
    )
    for profile in profiles:
        character_id = str(profile.get("character_id") or "")
        for field in entity_fields:
            for entity in profile.get(field) or []:
                if not isinstance(entity, dict):
                    continue
                cleaned = dict(entity)
                cleaned["source"] = cleaned.get("source") or "character_backstory"
                cleaned["character_id"] = character_id
                if cleaned.get("canon_status") == "player_canon":
                    player_canon.append(cleaned)
                else:
                    provisional.append(cleaned)
    return _unique_entities(player_canon), _unique_entities(provisional)


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
    canon = _canon_policy(hay, posture, settings, variables)
    creativity = _creativity_level(hay, posture, settings, variables)
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
    import_interp = interpretation.get("import_interpretation") or {}
    backstory_player_canon, backstory_provisional = _backstory_contract_entities(backstory_profiles or [])
    player_canon = _unique_entities([
        *(import_interp.get("canon_sensitive_entities") or []),
        *backstory_player_canon,
    ])
    provisional_entities = _unique_entities([
        *(import_interp.get("provisional_entities") or []),
        *backstory_provisional,
    ])

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
        "backstory_profiles": backstory_profiles or [],
        "backstory_hooks": backstory_hooks or [],
        "safety_policy": interpretation.get("safety_profile", {}),
        "player_canon": player_canon,
        "provisional_entities": provisional_entities,
        "import_interpretation": import_interp,
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
        "expectation_checks": ["agency", "tone", "canon", "backstory_boundaries"],
        "require_multiple_approaches": True,
        "reject_single_solution": True,
        "require_concrete_clues": "investigation" in pillars,
        "preserve_unanswered_questions": "investigation" in pillars,
        "canon_mode": canon_mode,
        "flag_major_inventions": canon_mode == "strict_canon",
        "canon_violations": {
            "contradict_player_canon": "reject",
            "major_invention_without_approval": "reject" if canon_mode == "strict_canon" else "flag",
            "minor_detail": "allow_as_provisional",
        },
        "backstory_boundary_checks": {
            "family_danger": backstory_policy.get("allow_family_danger", False),
            "secret_reveal": backstory_policy.get("allow_secret_reveals", "with_setup"),
            "identity_retcon": backstory_policy.get("allow_retcons", False),
        },
        "agency_checks": {"reject_single_solution": True, "require_visible_choices": True},
        "tone_checks": {"respect_content_rating": True, "respect_campaign_tone": True},
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


def build_campaign_scale_profile(
    *,
    campaign_id: str,
    interpretation: dict[str, Any],
    settings: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or {}
    variables = variables or {}
    text = _text(interpretation, settings, variables).lower()
    selected = str(
        variables.get("campaign_length")
        or settings.get("campaign_length")
        or settings.get("campaign_scale")
        or variables.get("scale")
        or ""
    ).lower()
    if selected not in {"one_shot", "short", "standard", "long", "endless"}:
        if any(term in text for term in ("one-shot", "oneshot", "single session", "one session")):
            selected = "one_shot"
        elif any(term in text for term in ("endless", "sandbox", "west marches", "living world", "open ended")):
            selected = "endless"
        elif any(term in text for term in ("long campaign", "epic", "season", "saga")):
            selected = "long"
        elif any(term in text for term in ("short campaign", "mini campaign", "few sessions")):
            selected = "short"
        else:
            selected = "standard"

    defaults = {
        "one_shot": (1, "definitive", "current_session", 3, "light", "minimal"),
        "short": (4, "partial", "next_3_sessions", 5, "moderate", "light"),
        "standard": (12, "partial", "current_arc", 8, "balanced", "moderate"),
        "long": (30, "seasonal", "current_season", 12, "deep", "high"),
        "endless": (None, "open_ended", "living_world", 10, "ongoing", "high"),
    }
    expected, resolution, horizon, max_threads, backstory_depth, faction_depth = defaults[selected]
    if settings.get("expected_sessions"):
        try:
            expected = int(settings["expected_sessions"])
        except Exception:
            pass
    return {
        "campaign_id": campaign_id,
        "campaign_length": selected,
        "expected_sessions": expected,
        "session_length_minutes": settings.get("session_length_minutes") or variables.get("session_length_minutes"),
        "resolution_style": resolution,
        "planning_horizon": horizon,
        "max_open_threads": max_threads,
        "thread_retirement_policy": selected in {"long", "endless"},
        "backstory_depth": backstory_depth,
        "faction_depth": faction_depth,
    }


def build_story_shape_profile(
    *,
    campaign_id: str,
    interpretation: dict[str, Any],
    scale_profile: dict[str, Any],
    settings: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or {}
    variables = variables or {}
    text = _text(interpretation, settings, variables).lower()
    selected = str(
        variables.get("primary_story_model")
        or settings.get("primary_story_model")
        or settings.get("story_shape")
        or ""
    ).lower()
    valid = {
        "hero_cycle", "three_act", "five_room", "mystery_web", "faction_fronts",
        "episodic", "west_marches", "character_web", "custom",
    }
    if selected not in valid:
        pillars = interpretation.get("primary_play_pillars") or []
        length = scale_profile.get("campaign_length")
        if "investigation" in pillars or any(term in text for term in ("mystery", "secret", "clue")):
            selected = "mystery_web"
        elif any(term in text for term in ("faction", "politic", "front", "war", "court")):
            selected = "faction_fronts"
        elif length == "one_shot":
            selected = "five_room"
        elif length == "endless":
            selected = "west_marches" if "exploration" in pillars else "episodic"
        elif any(term in text for term in ("backstory", "relationship", "character drama")):
            selected = "character_web"
        else:
            selected = "three_act"

    stage_map = {
        "hero_cycle": ["call_to_adventure", "threshold", "trials", "ordeal", "reward", "return_changed"],
        "three_act": ["setup", "complication", "crisis", "climax", "resolution"],
        "five_room": ["hook", "challenge", "setback", "climax", "reward_or_revelation"],
        "mystery_web": ["central_question", "clue_nodes", "revelation_layers", "false_leads", "earned_reveal"],
        "faction_fronts": ["fronts", "goals", "clocks", "intervention_points", "fallout"],
        "episodic": ["episode_hook", "local_complication", "choice", "resolution", "world_update"],
        "west_marches": ["home_base", "expedition_targets", "route_risk", "discoverable_sites", "return_consequences"],
        "character_web": ["backstory_hooks", "relationships", "secrets", "debts", "values_challenged"],
        "custom": ["pressure", "choice", "consequence"],
    }
    notes = {
        "hero_cycle": "Use stages as optional pressures; never force refusal, acceptance, travel, or transformation.",
        "mystery_web": "Maintain redundant clue paths and revelation layers; preserve unanswered questions until earned.",
        "faction_fronts": "Track fronts, goals, clocks, and player intervention points.",
        "west_marches": "Plan expeditions, route risk, discoverable sites, and return consequences.",
    }.get(selected, "Use the model to shape pressure and pacing without scripting player decisions.")
    stages = stage_map[selected]
    return {
        "campaign_id": campaign_id,
        "primary_story_model": selected,
        "secondary_story_models": list(variables.get("secondary_story_models") or []),
        "current_arc_stage": stages[0],
        "stage_goals": stages,
        "stage_do_not_force": [
            "player decisions",
            "single required path",
            "predetermined outcomes",
        ],
        "model_notes": notes,
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
    spotlight = build_spotlight_trackers(hooks)
    scale_profile = build_campaign_scale_profile(
        campaign_id=campaign_id,
        interpretation=interpretation,
        settings=settings,
        variables=variables,
    )
    story_shape_profile = build_story_shape_profile(
        campaign_id=campaign_id,
        interpretation=interpretation,
        scale_profile=scale_profile,
        settings=settings,
        variables=variables,
    )
    contract["backstory_thread_links"] = thread_links
    contract["backstory_spotlight"] = spotlight
    contract["campaign_scale_profile"] = scale_profile
    contract["story_shape_profile"] = story_shape_profile
    return {
        "campaign_interpretation": interpretation,
        "campaign_contract": contract,
        "campaign_scale_profile": scale_profile,
        "story_shape_profile": story_shape_profile,
        "backstory_profiles": profiles,
        "backstory_hooks": hooks,
        "backstory_thread_links": thread_links,
        "backstory_spotlight": spotlight,
        "session_zero": build_session_zero_summary(interpretation, contract, profiles),
        "debug": {
            "user_input": {
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "description": description,
                "settings": settings or {},
                "variables": variables or {},
                "imported_document_count": len(docs or []),
                "backstory_count": len(backstories or []),
            },
            "campaign_interpretation": interpretation,
            "campaign_contract": contract,
            "campaign_scale_profile": scale_profile,
            "story_shape_profile": story_shape_profile,
            "backstory_profiles": profiles,
            "backstory_hooks": hooks,
            "backstory_thread_links": thread_links,
            "backstory_spotlight": spotlight,
            "low_confidence_assumptions": interpretation.get("low_confidence_items", []),
            "agent_output_contract": contract.get("agent_output_contract", ""),
            "validator_policy": contract.get("validator_policy", {}),
            "ui_policy": contract.get("ui_policy", {}),
        },
    }
