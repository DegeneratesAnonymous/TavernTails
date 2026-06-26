"""Persistent campaign simulation helpers for TavernTails sessions.

The simulation layer keeps world facts outside the prose generator so changing
the LLM changes writing style, not the campaign reality.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LOCK_TTL_MINUTES = 10

TIME_BLOCKS = ("morning", "afternoon", "evening", "night")

BAD_PRESENTATION_FRAGMENTS = (
    "[character:",
    "campaign docs",
    "campaign memory",
    "genre:",
    "tone:",
    "class:",
    "level ",
    "backstory:",
    "personality:",
    "ideals:",
    "bonds:",
    "flaws:",
    "the party",
    "find someone who can help",
    "learn what changed",
    "i kneel",
    "i ask",
    "i scan",
    "i quietly",
    "i tell",
    "i compare",
    "i prepare",
    "i send",
    "i turn",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _lock_path(folder: Path) -> Path:
    return folder / "advance_scene_lock.json"


def acquire_scene_lock(folder: Path, session_id: str) -> tuple[bool, dict[str, Any]]:
    """Create a recoverable per-session advance lock.

    Returns ``(True, lock)`` when this caller owns the lock. Duplicate calls get
    the active lock status. Failed or expired locks are replaced.
    """
    path = _lock_path(folder)
    now = utc_now()
    expires = now + timedelta(minutes=LOCK_TTL_MINUTES)
    generation_id = uuid.uuid4().hex
    lock = {
        "generation_id": generation_id,
        "session_id": session_id,
        "status": "running",
        "started_at": now.isoformat(),
        "expires_at": expires.isoformat(),
    }

    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, "w") as handle:
            json.dump(lock, handle, indent=2, sort_keys=True)
        return True, lock
    except FileExistsError:
        existing = read_json(path, {})
        status = existing.get("status")
        expires_at = _parse_dt(existing.get("expires_at"))
        recoverable = status in {"failed", "complete"} or not expires_at or expires_at <= now
        if not recoverable:
            return False, existing
        atomic_write_json(path, lock)
        return True, lock


def complete_scene_lock(folder: Path, lock: dict[str, Any], status: str) -> dict[str, Any]:
    final = dict(lock)
    final["status"] = status
    final["completed_at"] = iso_now()
    atomic_write_json(_lock_path(folder), final)
    return final


def default_world_state() -> dict[str, Any]:
    return {
        "campaign_day": 1,
        "season": "spring",
        "time_of_day": "08:00",
        "time_block": "morning",
        "weather": "clear",
        "temperature": "mild",
        "wind_direction": "west",
        "wind_strength": "light",
        "visibility": "good",
        "moon_phase": "waxing crescent",
        "road_conditions": "passable",
        "local_morale": "steady",
        "global_threat_level": "low",
        "market_day": False,
        "active_world_events": [],
        "active_world_clocks": [],
        "last_tick_at": iso_now(),
    }


def load_world_state(folder: Path) -> dict[str, Any]:
    state = read_json(folder / "world_state.json", {})
    if not isinstance(state, dict) or not state:
        state = default_world_state()
    merged = default_world_state()
    merged.update(state)
    return merged


def _minutes_for_actions(actions: list[str]) -> int:
    text = " ".join(actions).lower()
    if any(word in text for word in ("long rest", "sleep", "rest for the night")):
        return 8 * 60
    if any(word in text for word in ("travel", "journey", "ride", "march", "road")):
        return 60
    if any(word in text for word in ("fight", "attack", "combat", "initiative")):
        return 3
    if any(word in text for word in ("search", "investigate", "examine", "study", "track")):
        return 20
    if any(word in text for word in ("shop", "market", "buy", "sell", "downtime")):
        return 45
    if any(word in text for word in ("talk", "ask", "parley", "negotiate", "persuade")):
        return 5
    return 10


def _block_for_hour(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def resolve_time(world_state: dict[str, Any], player_actions: list[str]) -> dict[str, Any]:
    elapsed = _minutes_for_actions(player_actions)
    old_day = int(world_state.get("campaign_day") or 1)
    old_season = str(world_state.get("season") or "spring")
    raw_time = str(world_state.get("time_of_day") or "08:00")
    match = re.match(r"^(\d{1,2}):(\d{2})$", raw_time)
    hour = int(match.group(1)) if match else 8
    minute = int(match.group(2)) if match else 0
    total = hour * 60 + minute + elapsed
    day_delta, day_minutes = divmod(total, 24 * 60)
    new_hour, new_minute = divmod(day_minutes, 60)
    new_day = old_day + day_delta
    time_block = _block_for_hour(new_hour)
    seasons = ("spring", "summer", "autumn", "winter")
    new_season = seasons[((new_day - 1) // 30) % len(seasons)]
    return {
        "elapsed_minutes": elapsed,
        "campaign_day": new_day,
        "time_of_day": f"{new_hour:02d}:{new_minute:02d}",
        "time_block": time_block,
        "day_changed": new_day != old_day,
        "week_changed": ((new_day - 1) // 7) != ((old_day - 1) // 7),
        "season_changed": new_season != old_season,
        "season": new_season,
    }


def _empty_delta() -> dict[str, list[Any]]:
    return {
        "time_changes": [],
        "weather_changes": [],
        "npc_movements": [],
        "faction_advances": [],
        "rumors_spread": [],
        "quest_updates": [],
        "threat_updates": [],
        "relationship_changes": [],
        "consequences_triggered": [],
    }


def _load_list(folder: Path, name: str) -> list[dict[str, Any]]:
    raw = read_json(folder / name, [])
    return raw if isinstance(raw, list) else []


def _save_list(folder: Path, name: str, value: list[dict[str, Any]]) -> None:
    atomic_write_json(folder / name, value)


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    lower = text.lower()
    if text.startswith("{") or text.startswith("[") or "campaign_day" in lower or "elapsed_minutes" in lower:
        return fallback
    if "[simulation state]" in lower or "\n" in text:
        return fallback
    if any(fragment in lower for fragment in BAD_PRESENTATION_FRAGMENTS):
        return fallback
    # Remove leftover bullets/labels without flattening legitimate prose.
    text = re.sub(r"^\s*(objective|stakes|location|thread)\s*:\s*", "", text, flags=re.IGNORECASE)
    return text.strip() or fallback


def presentation_objective(scene: dict[str, Any]) -> str:
    sd = scene.get("scene_director_data") or {}
    npc = sd.get("primary_npc") or {}
    location = scene.get("location") or (sd.get("location") or {}).get("name") or "this place"
    candidates = [
        scene.get("current_objective"),
        sd.get("central_conflict"),
        sd.get("inciting_incident"),
        npc.get("what_they_want"),
    ]
    for candidate in candidates:
        clean = _clean_text(candidate)
        if clean and len(clean) >= 12:
            return clean[:220]
    npc_name = _clean_text(npc.get("name"), "someone")
    if npc_name != "someone":
        return f"Find out why {npc_name} came to {location} looking for help."
    return f"Inspect the evidence at {location} and learn who is in danger."


def presentation_player_name(scene: dict[str, Any]) -> str:
    candidates = [
        scene.get("active_player"),
        scene.get("player_name"),
        scene.get("active_character_name"),
        (scene.get("character_context") or {}).get("name")
        if isinstance(scene.get("character_context"), dict)
        else "",
    ]
    for candidate in candidates:
        clean = _clean_text(candidate)
        if clean:
            return clean[:80]
    return ""


def presentation_stakes(scene: dict[str, Any]) -> str:
    sd = scene.get("scene_director_data") or {}
    clean = _clean_text(scene.get("immediate_stakes") or sd.get("immediate_stakes"))
    if clean:
        return clean[:220]
    npc = sd.get("primary_npc") or {}
    npc_name = _clean_text(npc.get("name"), "the people nearby")
    return f"If the players delay, {npc_name} loses the chance to act before the trail goes cold."


def presentation_visible_clues(scene: dict[str, Any]) -> list[str]:
    clues = [_clean_text(item) for item in (scene.get("visible_clues") or [])]
    clues = [item for item in clues if item]
    if clues:
        return list(dict.fromkeys(clues))[:5]
    sd = scene.get("scene_director_data") or {}
    npc = sd.get("primary_npc") or {}
    location = scene.get("location") or (sd.get("location") or {}).get("name") or "the room"
    generated = [
        f"{_clean_text(npc.get('name'), 'The contact')}'s story has a detail that does not fit.",
        f"Fresh signs of haste mark {location}.",
        "The nearest witnesses are watching to see who takes charge.",
    ]
    return generated[:3]


def presentation_world_moves(scene: dict[str, Any], world_state: dict[str, Any], simulation_delta: dict[str, Any]) -> list[str]:
    moves = [_clean_text(item) for item in (scene.get("world_moves") or [])]
    for key in ("weather_changes", "npc_movements", "rumors_spread", "threat_updates", "quest_updates"):
        for item in simulation_delta.get(key, [])[:2]:
            if isinstance(item, dict):
                if item.get("npc") and item.get("to"):
                    moves.append(f"{item['npc']} moves toward {item['to']}.")
                elif item.get("to"):
                    moves.append(f"The weather turns {item['to']}.")
                elif item.get("global_threat_level"):
                    moves.append(f"Pressure across the region rises to {item['global_threat_level']}.")
                else:
                    moves.append(json.dumps(item, sort_keys=True))
            else:
                moves.append(str(item))
    moves = [_clean_text(item) for item in moves if _clean_text(item)]
    if len(moves) >= 2:
        return list(dict.fromkeys(moves))[:4]
    location = scene.get("location") or "the settlement"
    weather = world_state.get("weather") or scene.get("weather") or "clear"
    fallback = [
        f"Outside {location}, traffic thins as people lower their voices.",
        f"The {weather} weather changes how quickly tracks, rumors, and witnesses will last.",
        "Someone nearby has already decided whether to help or stay silent.",
    ]
    return list(dict.fromkeys(moves + fallback))[:4]


def normalize_scene_presentation(scene: dict[str, Any], world_state: dict[str, Any], simulation_delta: dict[str, Any]) -> dict[str, Any]:
    """Patch weak generated fields into useful player-facing presentation data."""
    normalized = dict(scene)
    prompt = str(normalized.get("player_prompt") or "").strip()
    player_name = presentation_player_name(normalized)
    if player_name and (not prompt or "the party" in prompt.lower() or "[character:" in prompt.lower()):
        prompt = f"What does {player_name} do?"
        normalized["player_prompt"] = prompt
    narrative = str(normalized.get("narrative_body") or "").strip()
    if prompt and narrative.endswith(prompt):
        normalized["narrative_body"] = narrative[: -len(prompt)].rstrip()
        narrative = str(normalized.get("narrative_body") or "").strip()
    if prompt and narrative:
        normalized["text"] = f"{narrative}\n\n{prompt}".strip()
    normalized["current_objective"] = presentation_objective(normalized)
    normalized["immediate_stakes"] = presentation_stakes(normalized)
    normalized["visible_clues"] = presentation_visible_clues(normalized)
    normalized["world_moves"] = presentation_world_moves(normalized, world_state, simulation_delta)
    current_situation = dict(normalized.get("current_situation") or {})
    current_situation["current_objective"] = normalized["current_objective"]
    current_situation["immediate_stakes"] = normalized["immediate_stakes"]
    current_situation["visible_clues"] = normalized["visible_clues"]
    normalized["current_situation"] = current_situation
    if not normalized.get("suggested_actions"):
        clues = normalized["visible_clues"]
        normalized["suggested_actions"] = [
            "Ask what happened",
            f"Inspect {clues[0].lower()}" if clues else "Inspect the scene",
            "Read the room",
            "Step outside and look for changes",
        ]
    normalized["suggested_actions"] = [
        _clean_text(action)
        for action in normalized.get("suggested_actions", [])
        if _clean_text(action)
    ][:5]
    return normalized


def seed_persistent_npcs(folder: Path, scene: dict[str, Any]) -> list[dict[str, Any]]:
    npcs = _load_list(folder, "persistent_npcs.json")
    known = {str(n.get("name", "")).lower() for n in npcs}
    sd = scene.get("scene_director_data") or {}
    candidates = []
    primary = sd.get("primary_npc") or {}
    if primary.get("name"):
        candidates.append(primary)
    for name in sd.get("secondary_entities") or []:
        candidates.append({"name": name, "role": "supporting character"})
    location = scene.get("location") or (sd.get("location") or {}).get("name") or ""
    for item in candidates:
        name = str(item.get("name") or "").strip()
        if not name or name.lower() in known:
            continue
        npcs.append({
            "name": name,
            "role": item.get("role") or "local figure",
            "home_location_id": location,
            "current_location_id": location,
            "routine": {
                "morning": location,
                "afternoon": location,
                "evening": location,
                "night": "home",
            },
            "current_task": item.get("what_they_want") or "pursuing their own business",
            "current_mood": item.get("current_emotional_state") or "watchful",
            "immediate_goal": item.get("what_they_want") or "",
            "long_term_goal": "",
            "relationships": [],
            "knowledge": [item.get("what_they_know")] if item.get("what_they_know") else [],
            "beliefs": [],
            "secrets": [],
            "availability": "available",
        })
        known.add(name.lower())
    _save_list(folder, "persistent_npcs.json", npcs)
    return npcs


def seed_location_state(folder: Path, scene: dict[str, Any], world_state: dict[str, Any]) -> list[dict[str, Any]]:
    locations = _load_list(folder, "locations_dynamic.json")
    by_name = {str(l.get("name", "")).lower(): l for l in locations}
    sd = scene.get("scene_director_data") or {}
    loc = sd.get("location") or {}
    name = str(scene.get("location") or loc.get("name") or "").strip()
    if not name:
        return locations
    current = by_name.get(name.lower())
    if not current:
        current = {
            "name": name,
            "static": {
                "architecture": "",
                "history": "",
                "culture": "",
                "landmarks": [],
                "shops_services": [],
            },
            "dynamic": {
                "current_weather": world_state.get("weather", ""),
                "population_mood": "steady",
                "npcs_present": [],
                "rumors": [],
                "visible_clues": [],
                "active_threats": [],
                "recent_events": [],
                "open_hooks": [],
            },
        }
        locations.append(current)
    dynamic = current.setdefault("dynamic", {})
    dynamic["current_weather"] = world_state.get("weather", "")
    if scene.get("visible_clues"):
        dynamic["visible_clues"] = list(dict.fromkeys(dynamic.get("visible_clues", []) + scene.get("visible_clues", [])))[:8]
    if scene.get("world_moves"):
        dynamic["recent_events"] = list(dict.fromkeys(scene.get("world_moves", []) + dynamic.get("recent_events", [])))[:10]
    _save_list(folder, "locations_dynamic.json", locations)
    return locations


def tick_world(
    folder: Path,
    world_state: dict[str, Any],
    time_result: dict[str, Any],
    player_actions: list[str],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Advance only simulation systems whose policy is due."""
    updated = dict(world_state)
    delta = _empty_delta()
    policies = ["always", "per_turn", "per_scene"]
    if time_result["elapsed_minutes"] >= 60:
        policies.append("hourly")
    if time_result["time_block"] in TIME_BLOCKS:
        policies.append(time_result["time_block"])
    if time_result["day_changed"]:
        policies.append("daily")
    if time_result["week_changed"]:
        policies.append("weekly")
    action_text = " ".join(player_actions).lower()
    if any(w in action_text for w in ("travel", "journey", "road", "ride", "march")):
        policies.append("travel")
    if any(w in action_text for w in ("attack", "fight", "combat", "initiative")):
        policies.append("combat")

    old_time = updated.get("time_of_day")
    updated["campaign_day"] = time_result["campaign_day"]
    updated["time_of_day"] = time_result["time_of_day"]
    updated["time_block"] = time_result["time_block"]
    updated["season"] = time_result["season"]
    updated["last_tick_at"] = iso_now()
    delta["time_changes"].append({
        "from": old_time,
        "to": updated["time_of_day"],
        "elapsed_minutes": time_result["elapsed_minutes"],
        "campaign_day": updated["campaign_day"],
    })

    if "daily" in policies or "travel" in policies:
        weather_cycle = ["clear", "cloudy", "rain", "fog", "windy"]
        idx = (int(updated["campaign_day"]) + len(updated.get("active_world_events", []))) % len(weather_cycle)
        old_weather = updated.get("weather")
        updated["weather"] = weather_cycle[idx]
        updated["visibility"] = "poor" if updated["weather"] in {"fog", "rain"} else "good"
        updated["road_conditions"] = "muddy" if updated["weather"] == "rain" else "passable"
        if old_weather != updated["weather"]:
            delta["weather_changes"].append({"from": old_weather, "to": updated["weather"]})

    npcs = _load_list(folder, "persistent_npcs.json")
    for npc in npcs:
        routine = npc.get("routine") or {}
        target = routine.get(updated["time_block"])
        if target and target != npc.get("current_location_id"):
            old_loc = npc.get("current_location_id")
            npc["current_location_id"] = target
            npc["availability"] = "resting" if updated["time_block"] == "night" else "available"
            npc["current_task"] = f"{updated['time_block']} routine"
            delta["npc_movements"].append({"npc": npc.get("name"), "from": old_loc, "to": target})
    _save_list(folder, "persistent_npcs.json", npcs)

    if "daily" in policies:
        updated["market_day"] = int(updated["campaign_day"]) % 5 == 0
        if updated["market_day"]:
            delta["rumors_spread"].append("Market-day talk carries rumors between settlements.")

    if "weekly" in policies:
        levels = ["low", "watchful", "dangerous", "severe"]
        current = updated.get("global_threat_level", "low")
        next_level = levels[min(levels.index(current) + 1, len(levels) - 1)] if current in levels else "watchful"
        updated["global_threat_level"] = next_level
        delta["threat_updates"].append({"global_threat_level": next_level})

    return updated, delta, policies


def orchestrated_simulation_context(
    world_state: dict[str, Any],
    simulation_delta: dict[str, Any],
    location_name: str = "",
    npcs: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        "[SIMULATION STATE]",
        f"Day {world_state.get('campaign_day')} at {world_state.get('time_of_day')} ({world_state.get('time_block')}); {world_state.get('weather')} weather; {world_state.get('season')}.",
        f"Visibility: {world_state.get('visibility')}; roads: {world_state.get('road_conditions')}; threat: {world_state.get('global_threat_level')}.",
    ]
    if location_name:
        lines.append(f"Current location: {location_name}.")
    present = [
        str(n.get("name"))
        for n in (npcs or [])
        if not location_name or n.get("current_location_id") == location_name
    ][:4]
    if present:
        lines.append("NPCs present by simulation: " + ", ".join(present))
    changes = []
    for values in simulation_delta.values():
        for value in values[:2]:
            changes.append(value if isinstance(value, str) else json.dumps(value, sort_keys=True))
    if changes:
        lines.append("Recent simulation changes: " + " | ".join(changes[:6]))
    return "\n".join(lines)


def select_scene_templates(player_actions: list[str], time_result: dict[str, Any], delta: dict[str, Any]) -> list[str]:
    text = " ".join(player_actions).lower()
    templates: list[str] = []
    if any(w in text for w in ("travel", "road", "journey", "ride", "march")):
        templates.append("Travel")
    if any(w in text for w in ("arrive", "enter", "return")):
        templates.append("Arrival")
    if any(w in text for w in ("talk", "ask", "parley", "negotiate")):
        templates.append("Conversation")
    if any(w in text for w in ("search", "investigate", "examine", "track")):
        templates.append("Investigation")
    if any(w in text for w in ("fight", "attack", "combat")):
        templates.append("Combat Setup")
    if any(w in text for w in ("rest", "camp", "sleep")):
        templates.append("Long Rest" if time_result["elapsed_minutes"] >= 480 else "Camp")
    if delta.get("weather_changes"):
        templates.append("Weather")
    if delta.get("npc_movements"):
        templates.append("NPC Return")
    if delta.get("threat_updates") or delta.get("consequences_triggered"):
        templates.append("Consequence")
    if not templates:
        templates.append("Scene Opening")
    return list(dict.fromkeys(templates))[:4]


def build_director_guidance(
    base: dict[str, Any] | None,
    templates: list[str],
    delta: dict[str, Any],
    world_state: dict[str, Any],
) -> dict[str, Any]:
    guidance = dict(base or {})
    guidance["selected_templates"] = templates
    guidance.setdefault("scene_purpose", "Present the most important world change")
    guidance.setdefault("target_emotion", "curiosity")
    guidance.setdefault("scene_question", "What changed, and how will the players respond?")
    guidance.setdefault("target_tension", 40)
    if delta.get("consequences_triggered"):
        guidance["consequence_to_trigger"] = str(delta["consequences_triggered"][0])
    if delta.get("weather_changes"):
        guidance["scene_question"] = f"How does the {world_state.get('weather')} change the players' options?"
    return guidance


def build_memory_delta(scene: dict[str, Any], world_state: dict[str, Any], simulation_delta: dict[str, Any]) -> dict[str, Any]:
    sd = scene.get("scene_director_data") or {}
    loc = sd.get("location") or {}
    npc = sd.get("primary_npc") or {}
    return {
        "new_npcs": [npc.get("name")] if npc.get("name") else [],
        "updated_npcs": [],
        "new_locations": [loc.get("name")] if loc.get("name") else [],
        "updated_locations": [scene.get("location")] if scene.get("location") else [],
        "new_relationships": [],
        "updated_relationships": [],
        "new_clues": scene.get("visible_clues") or [],
        "discovered_clues": [],
        "new_threads": scene.get("active_threads") or [],
        "updated_threads": [],
        "new_consequences": simulation_delta.get("consequences_triggered", []),
        "resolved_items": [],
        "world_state_changes": simulation_delta,
        "world_state_snapshot": {
            key: world_state.get(key)
            for key in ("campaign_day", "season", "time_of_day", "time_block", "weather", "global_threat_level")
        },
    }


def determine_experience_mode(
    templates: list[str],
    world_state: dict[str, Any],
    scene: dict[str, Any],
) -> str:
    template_text = " ".join(templates).lower()
    threat = str(world_state.get("global_threat_level") or scene.get("current_threat") or "").lower()
    if "combat" in template_text or threat in {"dangerous", "severe"}:
        return "combat_imminent"
    if "travel" in template_text:
        return "travel_montage"
    if "investigation" in template_text or scene.get("visible_clues"):
        return "investigation"
    if "long rest" in template_text or "downtime" in template_text or "camp" in template_text:
        return "downtime"
    if "discovery" in template_text or "reveal" in template_text:
        return "dramatic_reveal"
    if "session end" in template_text:
        return "session_ending"
    if "arrival" in template_text:
        return "chapter_transition"
    return "quiet_scene"


def build_structured_scene_fields(
    scene: dict[str, Any],
    world_state: dict[str, Any],
    simulation_delta: dict[str, Any],
    memory_delta: dict[str, Any],
    templates: list[str],
    dice_rolls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return frontend-facing structured presentation fields.

    The frontend should render this data directly and avoid scraping narrative
    prose for metadata.
    """
    visual = scene.get("visual_state") or {}
    current_situation = {
        "current_objective": presentation_objective(scene),
        "immediate_stakes": presentation_stakes(scene),
        "active_thread": scene.get("active_thread") or (scene.get("active_threads") or [""])[0],
        "visible_clues": presentation_visible_clues(scene),
        "current_mood": visual.get("mood") or "",
        "current_threat": visual.get("threat_level") or world_state.get("global_threat_level") or "",
        "known_danger": scene.get("known_danger") or "",
        "time_pressure": scene.get("time_pressure") or "",
    }
    world_clock = {
        "campaign_day": world_state.get("campaign_day"),
        "time_of_day": world_state.get("time_of_day"),
        "time_block": world_state.get("time_block"),
        "weather": world_state.get("weather"),
        "wind_direction": world_state.get("wind_direction"),
        "wind_strength": world_state.get("wind_strength"),
        "temperature": world_state.get("temperature"),
        "moon_phase": world_state.get("moon_phase"),
        "threat_level": world_state.get("global_threat_level"),
    }
    raw_image = scene.get("image")
    image_url = raw_image.get("url") if isinstance(raw_image, dict) else raw_image
    while isinstance(image_url, dict):
        image_url = image_url.get("url")
    image_payload = {
        "url": image_url,
        "visual_type": visual.get("visual_type") or "scene_mood",
        "location": visual.get("location_name") or scene.get("location") or "",
        "mood": visual.get("mood") or "",
        "weather": scene.get("weather") or world_state.get("weather") or "",
        "refresh_reason": visual.get("last_refresh_reason") or "",
    }
    story_threads = [
        {"title": thread, "status": "active", "last_update": scene.get("current_objective") or ""}
        for thread in (scene.get("active_threads") or [])
        if thread
    ]
    relationships_changed = memory_delta.get("updated_relationships") or memory_delta.get("relationship_changes") or []
    return {
        "current_situation": current_situation,
        "world_clock": world_clock,
        "story_threads": story_threads,
        "relationships_changed": relationships_changed,
        "dice_rolls": dice_rolls or [],
        "image": image_payload,
        "experience_mode": determine_experience_mode(templates, world_state, scene),
        "memory_updates": memory_delta,
    }


def append_canon_memory(folder: Path, scene_id: str, memory_delta: dict[str, Any]) -> None:
    path = folder / "canon_memory.json"
    raw = read_json(path, [])
    entries = raw if isinstance(raw, list) else []
    entries.append({
        "scene_id": scene_id,
        "status": "provisional",
        "created_at": iso_now(),
        "memory_delta": memory_delta,
    })
    atomic_write_json(path, entries)
