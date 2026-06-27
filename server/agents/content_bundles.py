"""Content Bundles — structured game content that must exist before narration.

Each bundle corresponds to a situation type and carries the validated game
state the Narrative Writer is allowed to render.

Also contains:
  - Starter seed generator for fresh campaign openings
  - Bundle builder (maps scene director output → bundle for current situation)
  - Freshness tracker (prevents repeated generic motifs)
"""
from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from .situation_contracts import (
    SITUATION_CONTRACTS,
    validate_situation,
)

# ---------------------------------------------------------------------------
# Bundle type names
# ---------------------------------------------------------------------------

BUNDLE_TYPES = frozenset({
    "OpeningBundle",
    "CombatBundle",
    "DialogueBundle",
    "InvestigationBundle",
    "TravelBundle",
    "DowntimeBundle",
    "DiscoveryBundle",
    "FactionMoveBundle",
    "ConsequenceBundle",
})

_SITUATION_TO_BUNDLE: dict[str, str] = {
    "campaign_opening": "OpeningBundle",
    "new_scene_opening": "OpeningBundle",
    "combat_setup": "CombatBundle",
    "combat_round": "CombatBundle",
    "combat_resolution": "CombatBundle",
    "interrogation": "DialogueBundle",
    "conversation": "DialogueBundle",
    "social_conflict": "DialogueBundle",
    "investigation": "InvestigationBundle",
    "discovery": "DiscoveryBundle",
    "mystery_reveal": "InvestigationBundle",
    "travel": "TravelBundle",
    "arrival": "TravelBundle",
    "return_to_known_location": "TravelBundle",
    "downtime": "DowntimeBundle",
    "rest": "DowntimeBundle",
    "shopping": "DowntimeBundle",
    "faction_move": "FactionMoveBundle",
    "consequence": "ConsequenceBundle",
    "npc_reappearance": "DialogueBundle",
    "quest_offer": "DialogueBundle",
    "quest_turn_in": "DialogueBundle",
}


# ---------------------------------------------------------------------------
# Freshness tracker data
# ---------------------------------------------------------------------------

_LOCATION_TYPES = [
    "border village", "desert caravan camp", "mountain monastery",
    "river ferry station", "ruined watchtower", "mining settlement",
    "coastal shrine", "occupied city district", "forest road camp",
    "noble estate", "swamp causeway", "battlefield hospital",
    "arcane observatory", "market square", "frontier fort",
    "ship at sea", "underground refuge", "temple courtyard",
    "burned farmstead", "frozen pass",
]

_INCITING_EVENTS = [
    "someone returns without what they left with",
    "a trusted object appears in the wrong place",
    "a public ritual fails",
    "a messenger arrives too late",
    "a safe road becomes unsafe",
    "a settlement resource disappears overnight",
    "a witness refuses to speak",
    "a faction makes an unexpected move",
    "a creature behaves unnaturally",
    "a corpse carries a living message",
]

_OPENING_QUESTIONS = [
    "Who brought this here?",
    "Why did the road go silent?",
    "Who is lying?",
    "What changed overnight?",
    "Why did the warning arrive too late?",
    "What does this symbol mean?",
    "Who benefits if no one acts?",
    "What was taken that wasn't noticed until now?",
    "Why does no one want to talk about it?",
    "What is the creature guarding?",
]

_AVOID_REPEAT_WINDOW = 5


def empty_freshness() -> dict[str, Any]:
    return {
        "recent_location_types": [],
        "recent_opening_events": [],
        "recent_symbols": [],
        "recent_npc_roles": [],
        "recent_threat_types": [],
        "scene_count": 0,
    }


def pick_fresh(pool: list[str], recent: list[str], rng: random.Random | None = None) -> str:
    """Pick an item from pool that isn't in the recent list."""
    r = rng or random
    available = [x for x in pool if x not in recent[-_AVOID_REPEAT_WINDOW:]]
    if not available:
        available = pool
    return r.choice(available)


# ---------------------------------------------------------------------------
# Starter Seed Generator
# ---------------------------------------------------------------------------

def generate_starter_seed(
    campaign_settings: dict[str, Any] | None = None,
    campaign_contract: dict[str, Any] | None = None,
    freshness_context: dict[str, Any] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a concrete opening seed for a campaign with low context.

    Returns the fields required for an OpeningBundle's required_content.
    Guarantees: no tavern defaults, no generic threats, concrete entities.
    """
    settings = campaign_settings or {}
    contract = campaign_contract or {}
    freshness = freshness_context or empty_freshness()
    rng = random.Random(seed) if seed is not None else random.Random()

    genre = str(settings.get("genre") or contract.get("campaign_dna", {}).get("genre") or "fantasy")
    tone = str(settings.get("tone") or contract.get("campaign_dna", {}).get("tone") or "balanced")
    pillars = list((contract.get("campaign_dna") or {}).get("preferred_scene_types") or [])
    premise_seed = _seed_from_campaign_premise(settings, contract, genre, rng)
    if premise_seed:
        return premise_seed

    # Choose fresh location type
    recent_locs = freshness.get("recent_location_types") or []
    location_type = pick_fresh(_LOCATION_TYPES, recent_locs, rng)

    # Flavour the location name based on genre/tone
    location_name = _name_location(location_type, genre, tone, rng)

    # Choose fresh inciting event
    recent_events = freshness.get("recent_opening_events") or []
    inciting_event = pick_fresh(_INCITING_EVENTS, recent_events, rng)

    # Choose opening question
    opening_question = rng.choice(_OPENING_QUESTIONS)

    # Generate a named NPC (not generic)
    npc_name = _generate_npc_name(genre, rng)
    npc_role = _npc_role_for_location(location_type, rng)

    # Stakes — concrete, tied to the location type
    stakes = _stakes_for_location(location_type, inciting_event)

    # Player decision — always a real choice, never "what will you do?"
    player_decision = _player_decision(location_type, inciting_event)

    return {
        "starting_location": location_name,
        "location_type": location_type,
        "location_identity": f"A {location_type} where {inciting_event}.",
        "inciting_event": inciting_event.capitalize() + ".",
        "named_npc_or_visible_threat": f"{npc_name} ({npc_role})",
        "immediate_problem": f"The {npc_role.lower()} {npc_name} needs help, but is not saying everything.",
        "specific_stakes": stakes,
        "first_clue_or_question": opening_question,
        "player_decision": player_decision,
        "memory_updates": [
            {"type": "location", "name": location_name, "status": "provisional"},
            {"type": "npc", "name": npc_name, "role": npc_role, "status": "provisional"},
        ],
        "generated_by": "starter_seed",
        "freshness_consumed": {
            "location_type": location_type,
            "event": inciting_event,
        },
    }


def _campaign_premise_text(settings: dict[str, Any], contract: dict[str, Any]) -> str:
    dna = contract.get("campaign_dna") or {}
    return " ".join([
        str(settings.get("setting_summary") or ""),
        str(settings.get("world_name") or ""),
        str(contract.get("campaign_name") or ""),
        str(contract.get("campaign_pitch") or ""),
        str(dna.get("setting_summary") or ""),
        str(dna.get("starting_promise") or ""),
        " ".join(str(x) for x in (dna.get("central_questions") or [])[:4]),
        str(contract.get("agent_output_contract") or "")[:1200],
    ]).strip()


def _seed_from_campaign_premise(
    settings: dict[str, Any],
    contract: dict[str, Any],
    genre: str,
    rng: random.Random,
) -> dict[str, Any] | None:
    premise = _campaign_premise_text(settings, contract)
    hay = premise.lower()
    if not premise:
        return None

    escaped_forced_march = (
        any(w in hay for w in ("slave army", "slave-army", "forced army", "pressed army", "conscript", "enslaved"))
        and any(w in hay for w in ("escape", "escaped", "slipped away", "fled", "deserted"))
    )
    woods_hiding = any(w in hay for w in ("woods", "forest", "treeline", "hidden out", "hiding in the woods", "hiding in a forest"))
    north_march = any(w in hay for w in ("marching north", "north for months", "northern march"))

    if escaped_forced_march:
        location = "The Northwood Hiding Place" if woods_hiding else "The Frozen March Road"
        npc_name = _generate_npc_name(genre, rng)
        location_identity = (
            "A concealed camp beneath winter-bent trees, far enough from the army road "
            "to feel possible and close enough that every snapped branch matters."
        ) if woods_hiding else (
            "A wind-scoured stretch of northern road where the forced march has left tracks, "
            "discarded bindings, and fear behind it."
        )
        inciting = (
            "A distant horn answers from the army road, then a second horn sounds closer than it should."
            if north_march else
            "Fresh bootprints appear near the hiding place where there were none at dawn."
        )
        stakes = (
            "If the trail is found before nightfall, the escape becomes a hunt and the army learns exactly where to search."
        )
        decision = (
            "Break camp and risk exposure, hide and watch who is searching, or set a false trail before the patrol reaches the trees."
        )
        return {
            "starting_location": location,
            "location_type": "forest road camp" if woods_hiding else "frozen pass",
            "location_identity": location_identity,
            "inciting_event": inciting,
            "named_npc_or_visible_threat": f"{npc_name} (fellow escapee)",
            "immediate_problem": "The escape has held for weeks, but signs of pursuit are beginning to close around the hiding place.",
            "specific_stakes": stakes,
            "first_clue_or_question": "How did the searchers get this close without being seen?",
            "player_decision": decision,
            "memory_updates": [
                {"type": "location", "name": location, "status": "campaign_opening"},
                {"type": "npc", "name": npc_name, "role": "fellow escapee", "status": "provisional"},
            ],
            "generated_by": "premise_seed",
            "freshness_consumed": {
                "location_type": "forest road camp" if woods_hiding else "frozen pass",
                "event": "pursuit closes on escaped conscripts",
            },
        }

    if woods_hiding:
        location = "The Hidden Woodline"
        npc_name = _generate_npc_name(genre, rng)
        return {
            "starting_location": location,
            "location_type": "forest road camp",
            "location_identity": "A rough place of concealment under close trees, built for silence rather than comfort.",
            "inciting_event": "A sound from the trees repeats twice, too deliberate to be an animal.",
            "named_npc_or_visible_threat": f"{npc_name} (watchful survivor)",
            "immediate_problem": "The hidden camp may no longer be hidden.",
            "specific_stakes": "If the camp is discovered, safety, supplies, and the next route all vanish at once.",
            "first_clue_or_question": "Who found the camp first: an ally, a hunter, or the enemy?",
            "player_decision": "Stay silent and observe, move the camp, or confront the watcher in the trees.",
            "memory_updates": [
                {"type": "location", "name": location, "status": "campaign_opening"},
                {"type": "npc", "name": npc_name, "role": "watchful survivor", "status": "provisional"},
            ],
            "generated_by": "premise_seed",
            "freshness_consumed": {
                "location_type": "forest road camp",
                "event": "hidden camp is found",
            },
        }

    return None


_LOCATION_PREFIXES: dict[str, list[str]] = {
    "fantasy": ["Iron", "Thornwatch", "Ashveil", "Greywood", "Stonecrest", "Duskholm", "Coldwater"],
    "horror": ["Blackmere", "Ashfall", "Dreadhollow", "Grimward", "Pale", "Mourning"],
    "sci-fi": ["Outpost", "Station", "Platform", "Colony", "Waypoint", "Relay"],
    "mystery": ["Crowfield", "Saltmarsh", "Millhaven", "Aldgate", "Whisper", "Clearbrook"],
    "default": ["Thornwick", "Ironpass", "Coldbrook", "Ashfield", "Greymoor", "Dustwall"],
}


def _name_location(location_type: str, genre: str, tone: str, rng: random.Random) -> str:
    prefixes = _LOCATION_PREFIXES.get(genre.lower(), _LOCATION_PREFIXES["default"])
    prefix = rng.choice(prefixes)
    suffix_map = {
        "border village": "Post", "desert caravan camp": "Junction",
        "mountain monastery": "Abbey", "river ferry station": "Ford",
        "ruined watchtower": "Watchtower", "mining settlement": "Vein",
        "coastal shrine": "Shrine", "occupied city district": "Quarter",
        "forest road camp": "Camp", "noble estate": "Estate",
        "swamp causeway": "Crossing", "battlefield hospital": "Barracks",
        "arcane observatory": "Observatory", "market square": "Market",
        "frontier fort": "Fort", "ship at sea": "Vessel",
        "underground refuge": "Hold", "temple courtyard": "Courtyard",
        "burned farmstead": "Farmstead", "frozen pass": "Pass",
    }
    suffix = suffix_map.get(location_type, "Keep")
    return f"{prefix} {suffix}"


_NPC_NAMES: dict[str, list[str]] = {
    "fantasy": [
        "Elara Voss", "Tarek Grimshaw", "Mira Holt", "Daven Ashcroft",
        "Soren Blackwell", "Lirien Coldwater", "Hadwin Crowe", "Yala Thorn",
    ],
    "horror": [
        "Edgar Pale", "Mira Dunne", "Callum Grieve", "Aldous Mourne",
        "Rosalind Vane", "Tobias Fell", "Cecily Ash",
    ],
    "sci-fi": [
        "Kael Reyes", "Zara Ohmsted", "Marcus Venn", "Aiko Sato",
        "Dex Halcyon", "Nieva Strand",
    ],
    "default": [
        "Theron Cray", "Yuna Silt", "Bram Hollow", "Sera Vane",
        "Colm Dustfield", "Rynn Morrow",
    ],
}


def _generate_npc_name(genre: str, rng: random.Random) -> str:
    pool = _NPC_NAMES.get(genre.lower(), _NPC_NAMES["default"])
    return rng.choice(pool)


_ROLES_BY_LOCATION: dict[str, list[str]] = {
    "border village": ["Garrison Commander", "Fence Keeper", "Smuggler"],
    "desert caravan camp": ["Caravan Leader", "Water Merchant", "Desert Guide"],
    "mountain monastery": ["Archivist", "Prior", "Pilgrim"],
    "river ferry station": ["Ferry Operator", "Customs Officer", "River Warden"],
    "ruined watchtower": ["Survivor", "Scavenger Leader", "Trapped Scout"],
    "mining settlement": ["Mine Foreman", "Company Agent", "Trapped Miner"],
    "coastal shrine": ["Shrine Keeper", "Shipwreck Survivor", "Smuggling Contact"],
    "occupied city district": ["Resistance Contact", "Occupation Officer", "Informant"],
    "noble estate": ["Estate Steward", "Visiting Noble", "Disgraced Heir"],
    "arcane observatory": ["Observatory Director", "Researcher", "Fugitive Scholar"],
    "frontier fort": ["Fort Commander", "Deserter", "Dispatch Rider"],
    "default": ["Local Authority", "Traveler", "Witness"],
}


def _npc_role_for_location(location_type: str, rng: random.Random) -> str:
    pool = _ROLES_BY_LOCATION.get(location_type, _ROLES_BY_LOCATION["default"])
    return rng.choice(pool)


def _stakes_for_location(location_type: str, inciting_event: str) -> str:
    stakes_map = {
        "border village": "If nothing is done, the garrison will blame the next outsider.",
        "desert caravan camp": "Water supply runs out in 48 hours. Conflict will follow.",
        "mountain monastery": "The records at risk contain something someone wants destroyed.",
        "mining settlement": "The company will seal the mine with workers still inside.",
        "frontier fort": "Without reinforcements, the fort falls. The region falls with it.",
        "arcane observatory": "The phenomenon will not repeat for a decade.",
    }
    fallback = f"The situation triggered by '{inciting_event}' will escalate if ignored."
    return stakes_map.get(location_type, fallback)


def _player_decision(location_type: str, inciting_event: str) -> str:
    decision_map = {
        "border village": "Help the garrison commander investigate — or protect the person they're blaming.",
        "desert caravan camp": "Secure the water source or negotiate a truce between competing factions.",
        "mountain monastery": "Retrieve the records before they disappear — or find out why someone wants them gone.",
        "mining settlement": "Enter the mine, or find another way to locate the missing workers.",
        "frontier fort": "Send for help and hold the fort, or abandon it and warn the region.",
        "arcane observatory": "Document the phenomenon, or use it before it vanishes.",
    }
    fallback = "Act on what is immediately visible, or investigate what lies beneath the surface first."
    return decision_map.get(location_type, fallback)


# ---------------------------------------------------------------------------
# UI Payload Builder
# ---------------------------------------------------------------------------

def build_ui_payload(
    situation_type: str,
    bundle: dict[str, Any],
    scene_director_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the structured UI payload from a validated content bundle.

    Returns fields the frontend resolution panel can consume directly
    without scraping prose.
    """
    sdo = scene_director_output or {}
    base: dict[str, Any] = {
        "situation_type": situation_type,
        "bundle_type": _SITUATION_TO_BUNDLE.get(situation_type, "OpeningBundle"),
    }

    if situation_type in ("campaign_opening", "new_scene_opening"):
        base.update({
            "objective": bundle.get("immediate_problem") or sdo.get("central_conflict") or "",
            "first_hook": bundle.get("inciting_event") or "",
            "starting_question": bundle.get("first_clue_or_question") or "",
            "key_location": bundle.get("starting_location") or sdo.get("location", {}).get("name") or "",
            "key_npc": bundle.get("named_npc_or_visible_threat") or sdo.get("primary_npc", {}).get("name") or "",
            "suggested_first_actions": _default_actions(situation_type),
            "experience_mode": "quiet_scene",
        })

    elif situation_type in ("combat_setup", "combat_round", "combat_resolution"):
        base.update({
            "initiative_order": bundle.get("round_state", {}).get("initiative_order") or [],
            "active_combatant": bundle.get("active_combatant") or "",
            "enemy_cards": [
                {
                    "name": c.get("name"),
                    "hp": c.get("hp"),
                    "ac": c.get("ac"),
                    "role": c.get("role"),
                    "tactics": c.get("tactics"),
                }
                for c in (bundle.get("combatants") or [])
                if isinstance(c, dict)
            ],
            "terrain_features": (bundle.get("battlefield") or {}).get("terrain_features") or [],
            "hazards": (bundle.get("battlefield") or {}).get("hazards") or [],
            "victory_conditions": bundle.get("victory_conditions") or [],
            "failure_consequences": bundle.get("failure_consequences") or [],
            "non_combat_options": bundle.get("non_combat_options") or [],
            "experience_mode": "combat_imminent",
        })

    elif situation_type in ("interrogation", "conversation", "social_conflict", "npc_reappearance"):
        npc = bundle.get("npc") or {}
        base.update({
            "npc_name": npc.get("name") if isinstance(npc, dict) else str(npc),
            "npc_attitude": (npc.get("attitude") if isinstance(npc, dict) else None) or "neutral",
            "npc_goal": npc.get("goal") if isinstance(npc, dict) else "",
            "visible_emotional_tells": npc.get("fear") if isinstance(npc, dict) else "",
            "known_leverage": bundle.get("pressure_points") or [],
            "possible_checks": bundle.get("possible_checks") or [],
            "discovered_secrets": [],
            "failure_forward": bundle.get("failure_forward_options") or [],
            "experience_mode": "dramatic_reveal" if situation_type == "interrogation" else "quiet_scene",
        })

    elif situation_type in ("investigation", "discovery", "mystery_reveal"):
        base.update({
            "mystery_question": bundle.get("mystery_question") or "",
            "visible_clues": bundle.get("visible_clues") or [],
            "leads": [
                rc.get("conclusion")
                for rc in (bundle.get("required_conclusions") or [])
                if isinstance(rc, dict) and rc.get("conclusion")
            ],
            "theories": [],
            "available_checks": bundle.get("possible_checks") or [],
            "time_pressure": bundle.get("time_pressure") or "",
            "failure_forward": bundle.get("failure_forward") or [],
            "experience_mode": "investigation",
        })

    elif situation_type in ("travel", "arrival", "return_to_known_location"):
        base.update({
            "origin": bundle.get("origin") or bundle.get("location") or "",
            "destination": bundle.get("destination") or "",
            "route": bundle.get("route") or "",
            "travel_time": bundle.get("travel_time") or "",
            "weather": bundle.get("weather") or "",
            "road_conditions": bundle.get("road_conditions") or "",
            "encounter_risk": bundle.get("encounter_risk") or "low",
            "resource_cost": bundle.get("resource_cost") or "",
            "what_changed": bundle.get("what_changed") or "",
            "experience_mode": "chapter_transition",
        })

    else:
        base.update({
            "experience_mode": "quiet_scene",
            "suggested_actions": _default_actions(situation_type),
        })

    return base


def _default_actions(situation_type: str) -> list[str]:
    defaults: dict[str, list[str]] = {
        "campaign_opening": [
            "Approach the most visible person nearby",
            "Examine what triggered the immediate problem",
            "Scan the area for additional context",
            "Ask a direct question",
        ],
        "new_scene_opening": [
            "Investigate the immediate situation",
            "Speak to anyone present",
            "Look for clues or context",
            "Decide on a course of action",
        ],
    }
    return defaults.get(situation_type, [
        "Act on the immediate situation",
        "Gather more information first",
        "Look for alternatives",
    ])


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------

def build_content_bundle(
    situation_type: str,
    scene_director_output: dict[str, Any] | None = None,
    world_state: dict[str, Any] | None = None,
    campaign_contract: dict[str, Any] | None = None,
    previous_scene: dict[str, Any] | None = None,
    freshness_context: dict[str, Any] | None = None,
    campaign_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Game Content Bundle for the given situation type.

    Uses scene director output as the primary data source, filling gaps
    from world state and generating missing required fields deterministically.
    """
    sdo = scene_director_output or {}
    required_content: dict[str, Any] = {}

    if situation_type in ("campaign_opening", "new_scene_opening"):
        scene_count = (freshness_context or {}).get("scene_count") or 0
        prev_location = (previous_scene or {}).get("location") or ""
        loc_name = sdo.get("location", {}).get("name") or ""

        # If location is empty or looks like a tavern default with no context, seed it
        needs_seed = (
            not loc_name
            or (scene_count == 0 and _looks_like_tavern_default(loc_name))
        )
        if needs_seed:
            seed_data = generate_starter_seed(
                campaign_settings=campaign_settings,
                campaign_contract=campaign_contract,
                freshness_context=freshness_context,
            )
            required_content = seed_data
        else:
            required_content = {
                "starting_location": loc_name,
                "location_identity": (sdo.get("location") or {}).get("type") or "",
                "inciting_event": sdo.get("inciting_incident") or "",
                "named_npc_or_visible_threat": (sdo.get("primary_npc") or {}).get("name") or "",
                "immediate_problem": sdo.get("central_conflict") or "",
                "specific_stakes": sdo.get("immediate_stakes") or "",
                "first_clue_or_question": (sdo.get("player_visible_clues") or [""])[0],
                "player_decision": (sdo.get("possible_actions") or [""])[0],
                "memory_updates": [],
            }

    elif situation_type in ("combat_setup", "combat_round"):
        required_content = _build_combat_bundle(sdo, previous_scene, world_state)

    elif situation_type in ("interrogation", "conversation", "social_conflict"):
        required_content = _build_dialogue_bundle(sdo)

    elif situation_type in ("investigation", "discovery", "mystery_reveal"):
        required_content = _build_investigation_bundle(sdo)

    elif situation_type in ("travel", "arrival"):
        required_content = _build_travel_bundle(sdo, previous_scene, world_state)

    elif situation_type == "return_to_known_location":
        required_content = _build_return_bundle(sdo, previous_scene)

    elif situation_type == "npc_reappearance":
        required_content = _build_reappearance_bundle(sdo, previous_scene)

    else:
        required_content = {"situation_type": situation_type, "scene_director_summary": str(sdo)[:200]}

    # Validate
    validation = validate_situation(situation_type, required_content)

    # Build UI payload
    ui_payload = build_ui_payload(situation_type, required_content, sdo)

    bundle_id = hashlib.sha1(
        f"{situation_type}:{sdo.get('scene_title','')}:{str(required_content)[:80]}".encode()
    ).hexdigest()[:12]

    return {
        "bundle_id": bundle_id,
        "bundle_type": _SITUATION_TO_BUNDLE.get(situation_type, "OpeningBundle"),
        "situation_type": situation_type,
        "scene_id": sdo.get("scene_id") or "",
        "required_content": required_content,
        "generated_content": {},
        "validated": validation["valid"],
        "validation_result": validation,
        "memory_updates": required_content.get("memory_updates") or [],
        "ui_payload": ui_payload,
    }


def _looks_like_tavern_default(name: str) -> bool:
    low = name.lower()
    return any(w in low for w in ("tavern", "inn", "alehouse", "flagon", "tankard", "wayward"))


def _build_combat_bundle(sdo: dict[str, Any], previous_scene: dict[str, Any] | None, world_state: dict[str, Any] | None) -> dict[str, Any]:
    prev_bundle = (previous_scene or {}).get("content_bundle", {}).get("required_content", {})
    combatants = prev_bundle.get("combatants") or []
    if not combatants:
        world_enemies = (world_state or {}).get("active_enemies") or []
        combatants = [
            {
                "name": e.get("name") or "Enemy",
                "type": e.get("type") or "humanoid",
                "role": e.get("role") or "brute",
                "hp": e.get("hp") or 10,
                "ac": e.get("ac") or 12,
                "initiative": 0,
                "stats": e.get("stats") or {},
                "attacks": e.get("attacks") or [{"name": "Strike", "damage": "1d6", "hit_bonus": 2}],
                "tactics": e.get("tactics") or "Attack nearest target.",
                "goal": e.get("goal") or "Defeat or drive off the party.",
                "loot": [],
            }
            for e in world_enemies[:4]
        ]

    location = sdo.get("location") or {}
    return {
        "encounter_id": hashlib.sha1(str(sdo).encode()).hexdigest()[:8],
        "combatants": combatants,
        "battlefield": {
            "location": location.get("name") or "",
            "terrain_features": location.get("sensory_details") or [],
            "hazards": [],
            "cover": [],
            "exits": [],
            "interactive_objects": [],
        },
        "stakes": sdo.get("immediate_stakes") or "Survive and learn what triggered the confrontation.",
        "non_combat_options": ["Negotiate", "Flee", "Surrender"],
        "victory_conditions": ["Defeat or drive off all combatants", "Achieve the encounter objective"],
        "failure_consequences": ["Party is captured, injured, or driven back"],
        "round_state": prev_bundle.get("round_state") or {},
    }


def _build_dialogue_bundle(sdo: dict[str, Any]) -> dict[str, Any]:
    npc = sdo.get("primary_npc") or {}
    return {
        "npc": {
            "name": npc.get("name") or "",
            "role": npc.get("role") or "",
            "goal": npc.get("what_they_want") or "",
            "fear": "",
            "leverage": "",
            "attitude": "neutral",
            "truthfulness": "selective",
            "knows": npc.get("what_they_know") or [],
            "believes": [],
            "is_hiding": [],
        },
        "secrets": [],
        "pressure_points": [],
        "trust_state": "neutral",
        "relationship_changes": [],
        "possible_checks": ["Persuasion", "Insight", "Deception"],
        "failure_forward_options": ["Learn a partial truth", "Antagonize the NPC but gain a clue", "Be dismissed but overhear something useful"],
    }


def _build_investigation_bundle(sdo: dict[str, Any]) -> dict[str, Any]:
    clues = sdo.get("player_visible_clues") or []
    return {
        "mystery_question": sdo.get("central_conflict") or "What happened here?",
        "scene_location": (sdo.get("location") or {}).get("name") or "",
        "visible_clues": clues[:4],
        "hidden_clues": [],
        "required_conclusions": [
            {
                "conclusion": sdo.get("central_conflict") or "The truth of the situation",
                "clue_paths": clues[:3] if len(clues) >= 3 else clues + ["Physical evidence", "Witness account", "Paper trail"][:3 - len(clues)],
            }
        ],
        "red_herrings": [],
        "witnesses": [],
        "time_pressure": sdo.get("immediate_stakes") or "",
        "failure_forward": ["Partial evidence found at cost", "Witness speaks after a setback", "Trail grows cold but leaves one clear lead"],
    }


def _build_travel_bundle(sdo: dict[str, Any], previous_scene: dict[str, Any] | None, world_state: dict[str, Any] | None) -> dict[str, Any]:
    loc = sdo.get("location") or {}
    prev_loc = (previous_scene or {}).get("location") or ""
    return {
        "origin": prev_loc,
        "destination": loc.get("name") or "",
        "route": "",
        "distance": "",
        "travel_time": "several hours",
        "weather": (world_state or {}).get("weather") or "clear",
        "road_conditions": (world_state or {}).get("road_conditions") or "passable",
        "landmark": "",
        "complication_or_discovery": (sdo.get("player_visible_clues") or ["Something unexpected marks the route."])[0],
        "resource_cost": "standard travel rations",
        "choice_point": "",
        "encounter_risk": "moderate",
        "arrival_state": sdo.get("inciting_incident") or "Arrived safely.",
    }


def _build_return_bundle(sdo: dict[str, Any], previous_scene: dict[str, Any] | None) -> dict[str, Any]:
    loc = sdo.get("location") or {}
    prev_loc_name = (previous_scene or {}).get("location") or loc.get("name") or ""
    return {
        "location": prev_loc_name,
        "last_known_state": "",
        "what_changed": sdo.get("inciting_incident") or "Something has changed since the last visit.",
        "npcs_present": [],
        "open_threads_here": sdo.get("threads_to_advance") or [],
        "new_visible_detail": (sdo.get("player_visible_clues") or [""])[0],
        "current_tension": sdo.get("immediate_stakes") or "",
        "prompt": (sdo.get("possible_actions") or ["What do you do?"])[0],
    }


def _build_reappearance_bundle(sdo: dict[str, Any], previous_scene: dict[str, Any] | None) -> dict[str, Any]:
    npc = sdo.get("primary_npc") or {}
    return {
        "npc": npc.get("name") or "Returning NPC",
        "last_seen": "",
        "relationship_to_party": "",
        "what_changed_for_npc": npc.get("current_emotional_state") or "Something has changed.",
        "what_npc_wants_now": npc.get("what_they_want") or "Unspecified",
        "new_information": npc.get("what_they_know") or "",
        "prompt": f"How does {npc.get('name') or 'the NPC'} approach you?",
    }
