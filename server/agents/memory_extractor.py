"""Memory Extractor — extracts structured memory from a validated scene.

Runs after scene validation and before the Canon Manager commit.
Produces the canonical memory delta used by canon_manager and UI payload.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

_NPC_LABEL_PREFIXES = ("npc:", "character:", "ally:", "villain:", "contact:", "enemy:")
_LOCATION_LABEL_PREFIXES = ("location:", "place:", "setting:", "city:", "town:", "region:")
_FACTION_LABEL_PREFIXES = ("faction:", "guild:", "order:", "organization:", "house:")
_CLUE_LABEL_PREFIXES = ("clue:", "evidence:", "fact:", "lead:", "discovery:")
_THREAD_LABEL_PREFIXES = ("thread:", "quest:", "hook:", "objective:")

_MENTIONED_ENTITY_PATTERN = re.compile(
    r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,3})\b"
)

_RELATIONSHIP_PHRASES = [
    (r"(?P<a>[A-Z][a-z]+ [A-Z][a-z]+) (?:trusted?|allied with|betray(?:ed|s)?|murdered?|killed?) (?P<b>[A-Z][a-z]+ [A-Z][a-z]+)", "related"),
    (r"(?P<a>[A-Z][a-z]+ [A-Z][a-z]+) (?:is|became|was) (?P<rel>\w+) (?:of|to) (?P<b>[A-Z][a-z]+ [A-Z][a-z]+)", "role_of"),
]

_COMPILED_REL = [(re.compile(p, re.IGNORECASE), kind) for p, kind in _RELATIONSHIP_PHRASES]


def _extract_labeled_entities(sources: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Extract explicitly labeled entities from scene text sources."""
    npcs, locations, factions = [], [], []
    for text in sources:
        for line in text.splitlines():
            line = line.strip()
            low = line.lower()
            for prefix in _NPC_LABEL_PREFIXES:
                if low.startswith(prefix):
                    name = line[len(prefix):].strip().strip("\"'").split(",")[0].strip()
                    if name:
                        npcs.append({"name": name, "source": "labeled"})
            for prefix in _LOCATION_LABEL_PREFIXES:
                if low.startswith(prefix):
                    name = line[len(prefix):].strip().strip("\"'").split(",")[0].strip()
                    if name:
                        locations.append({"name": name, "source": "labeled"})
            for prefix in _FACTION_LABEL_PREFIXES:
                if low.startswith(prefix):
                    name = line[len(prefix):].strip().strip("\"'").split(",")[0].strip()
                    if name:
                        factions.append({"name": name, "source": "labeled"})
    return {"npcs": npcs, "locations": locations, "factions": factions}


def _extract_mentioned_npcs(narrative_text: str, known_canon: list[str]) -> list[str]:
    """Find proper noun sequences that match known canon or look like NPC names."""
    found = []
    for m in _MENTIONED_ENTITY_PATTERN.finditer(narrative_text):
        name = m.group(1)
        if len(name.split()) < 2:
            continue
        if name in known_canon or any(cn.startswith(name) for cn in known_canon):
            found.append(name)
    return list(dict.fromkeys(found))


def _extract_relationships(text: str) -> list[dict[str, Any]]:
    relationships = []
    for pattern, kind in _COMPILED_REL:
        for m in pattern.finditer(text):
            try:
                rel = {
                    "entity_a": m.group("a"),
                    "entity_b": m.group("b"),
                    "relationship_type": kind,
                    "context_snippet": text[max(0, m.start() - 30): m.end() + 30],
                }
                relationships.append(rel)
            except IndexError:
                pass
    return relationships


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


def _dedupe_dicts(items: list[dict], key: str = "name") -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        k = str(item.get(key) or "")
        if k and k not in seen:
            seen.add(k)
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# Primary extractor
# ---------------------------------------------------------------------------

def extract_memory(
    scene: dict[str, Any],
    world_state: dict[str, Any],
    simulation_delta: dict[str, Any],
    content_bundle: dict[str, Any] | None = None,
    campaign_contract: dict[str, Any] | None = None,
    previous_scene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract the full memory delta from a validated scene.

    Returns the canonical memory delta dict used by canon_manager and UI payload.
    """
    sd = scene.get("scene_director_data") or {}
    npc_data = sd.get("primary_npc") or {}
    loc_data = sd.get("location") or {}
    composer = scene.get("composer_data") or {}
    bundle_content = (content_bundle or {}).get("required_content") or {}

    # Pull text sources
    narrative_text = scene.get("narrative_body") or scene.get("text") or ""
    player_prompt = scene.get("player_prompt") or ""
    full_text = f"{narrative_text}\n{player_prompt}"

    # Known canon names (from campaign contract)
    canon_names: list[str] = []
    if campaign_contract:
        for entity in (campaign_contract.get("player_canon") or []):
            if isinstance(entity, dict) and entity.get("name"):
                canon_names.append(entity["name"])
        for entity in (campaign_contract.get("provisional_entities") or []):
            if isinstance(entity, dict) and entity.get("name"):
                canon_names.append(entity["name"])

    # ---------------------------------------------------------------------------
    # NPCs
    # ---------------------------------------------------------------------------
    new_npcs: list[dict[str, Any]] = []
    updated_npcs: list[dict[str, Any]] = []

    primary_npc_name = npc_data.get("name") or bundle_content.get("named_npc_or_visible_threat") or ""
    if primary_npc_name and primary_npc_name not in [e.get("name") for e in (campaign_contract or {}).get("player_canon") or []]:
        new_npcs.append({
            "name": primary_npc_name,
            "role": npc_data.get("role") or npc_data.get("what_they_want") or "",
            "first_seen": scene.get("id") or "",
            "canon_status": "provisional",
            "data": {k: v for k, v in npc_data.items() if k in ("role", "what_they_know", "what_they_want", "current_emotional_state")},
        })

    # NPCs mentioned in narrative that match known canon names
    mentioned = _extract_mentioned_npcs(full_text, canon_names)
    for name in mentioned:
        if name != primary_npc_name:
            updated_npcs.append({"name": name, "mentioned_in": scene.get("id") or ""})

    # ---------------------------------------------------------------------------
    # Locations
    # ---------------------------------------------------------------------------
    current_location = loc_data.get("name") or scene.get("location") or ""
    prev_location = (previous_scene or {}).get("location") or ""

    new_locations: list[dict[str, Any]] = []
    updated_locations: list[dict[str, Any]] = []

    if current_location and current_location != prev_location:
        new_locations.append({
            "name": current_location,
            "type": loc_data.get("type") or "",
            "description": loc_data.get("description") or "",
            "first_seen": scene.get("id") or "",
            "canon_status": "provisional",
        })
    elif current_location:
        updated_locations.append({
            "name": current_location,
            "last_seen": scene.get("id") or "",
        })

    # ---------------------------------------------------------------------------
    # Clues
    # ---------------------------------------------------------------------------
    visible_clues = scene.get("visible_clues") or sd.get("player_visible_clues") or []
    new_clues: list[str] = _dedupe([c for c in visible_clues if c])
    discovered_clues: list[str] = []

    # From investigation bundle
    bundle_clues = bundle_content.get("visible_clues") or []
    for clue in bundle_clues:
        if clue and clue not in new_clues:
            new_clues.append(clue)

    # ---------------------------------------------------------------------------
    # Story Threads
    # ---------------------------------------------------------------------------
    active_threads = scene.get("active_threads") or sd.get("threads_to_advance") or []
    prev_threads = (previous_scene or {}).get("active_threads") or []

    new_threads = [t for t in active_threads if t and t not in prev_threads]
    updated_threads = [t for t in active_threads if t and t in prev_threads]

    # ---------------------------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------------------------
    new_relationships = _extract_relationships(narrative_text)
    updated_relationships = simulation_delta.get("relationship_changes") or []

    # ---------------------------------------------------------------------------
    # Consequences
    # ---------------------------------------------------------------------------
    new_consequences = simulation_delta.get("consequences_triggered") or []
    resolved_items = simulation_delta.get("resolved_items") or []

    # ---------------------------------------------------------------------------
    # World state changes
    # ---------------------------------------------------------------------------
    world_state_changes: list[dict[str, Any]] = []
    for key in ("campaign_day", "time_of_day", "weather", "global_threat_level", "season"):
        val = world_state.get(key)
        prev_val = (previous_scene or {}).get(key) if key in ("weather", "time_of_day") else None
        if val and val != prev_val:
            world_state_changes.append({"field": key, "value": val})

    # ---------------------------------------------------------------------------
    # Backstory hooks used
    # ---------------------------------------------------------------------------
    backstory_hooks_used: list[str] = []
    if campaign_contract:
        hooks = (campaign_contract.get("backstory_profiles") or [])
        for hook in hooks:
            hook_npc = hook.get("spotlight_npc") or ""
            if hook_npc and hook_npc in full_text:
                backstory_hooks_used.append(hook_npc)

    # ---------------------------------------------------------------------------
    # Content bundle updates
    # ---------------------------------------------------------------------------
    bundle_updates: list[dict[str, Any]] = []
    situation_type = scene.get("situation_type") or ""
    if content_bundle and content_bundle.get("bundle_id"):
        bundle_updates.append({
            "bundle_id": content_bundle["bundle_id"],
            "situation_type": situation_type,
            "validated": content_bundle.get("validated", True),
        })

    return {
        "new_npcs": _dedupe_dicts(new_npcs),
        "updated_npcs": _dedupe_dicts(updated_npcs),
        "new_locations": _dedupe_dicts(new_locations),
        "updated_locations": _dedupe_dicts(updated_locations),
        "new_relationships": new_relationships,
        "updated_relationships": updated_relationships,
        "new_clues": _dedupe(new_clues),
        "discovered_clues": _dedupe(discovered_clues),
        "new_threads": _dedupe(new_threads),
        "updated_threads": _dedupe(updated_threads),
        "new_consequences": new_consequences,
        "resolved_items": resolved_items,
        "world_state_changes": world_state_changes,
        "world_state_snapshot": {
            key: world_state.get(key)
            for key in ("campaign_day", "season", "time_of_day", "time_block", "weather", "global_threat_level")
        },
        "backstory_hooks_used": backstory_hooks_used,
        "game_content_bundle_updates": bundle_updates,
        "situation_type": situation_type,
        "scene_id": scene.get("id") or "",
    }
