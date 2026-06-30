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
    "ThreatBundle",
    "FactionMoveBundle",
    "BackstoryHookBundle",
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
    "resource_pressure": "ThreatBundle",
    "backstory_callback": "BackstoryHookBundle",
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
    "market square", "frontier fort",
    "ship at sea", "underground refuge", "temple courtyard",
    "burned farmstead", "frozen pass",
]

_INCITING_EVENTS = [
    "someone returns without what they left with",
    "a trusted object appears in the wrong place",
    "a public ritual fails",
    "a warning reaches the wrong hands first",
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

_RECYCLED_OPENING_FIXTURES = (
    "first crossroads",
    "mira vale",
    "sealed packet",
    "something has gone very wrong",
    "wayward lantern",
    "cracked lantern",
    "harness leather",
    "outer court",
    "envoy marrec",
    "docking concourse",
    "quartermaster vale",
    "rain-dark crossing",
    "waterlogged dispatch tube sealed with split red wax",
    "arcane observatory",
    "a messenger arrives too late",
    "needs help, but is not saying everything",
    "the phenomenon will not repeat for a decade",
    "conversation falters as attention turns toward the same point of trouble",
    "this was not supposed to reach us like this",
    "everyone nearby is already deciding who will risk being seen helping",
)


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
        return _vary_premise_seed(premise_seed, freshness, rng)

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
        "immediate_problem": f"The {npc_role.lower()} {npc_name} is trying to keep a fragile lead from disappearing before the party can examine it.",
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


def _vary_premise_seed(seed: dict[str, Any], freshness: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Keep premise-specific content while varying repeated opening structure."""
    recent_locs = {str(x).lower() for x in (freshness.get("recent_location_types") or [])}
    recent_events = {str(x).lower() for x in (freshness.get("recent_opening_events") or [])}
    identity = str(seed.get("location_identity") or "").lower()
    if "water seal" in identity or "glass desert" in identity or "cistern" in identity:
        return _vary_desert_premise_seed(seed, freshness, rng)
    if "blackened silver" not in identity and "silver charm" not in identity and "blackened charm" not in identity:
        return seed
    variants = [
        {
            "starting_location": "The Frostmark Road Shrine",
            "location_type": "winter road shrine",
            "location_identity": "A wind-scoured roadside shrine where blackened silver charms hang from ice-stiff cords.",
            "inciting_event": "A bloodied survivor collapses beneath the shrine and presses a forgotten symbol into the snow.",
            "named_npc_or_visible_threat": "Hadwin Crowe (winter survivor)",
            "immediate_problem": "The early winter is cutting off the road, and the survivor's symbol matches charms that failed overnight.",
            "specific_stakes": "If the warning is ignored, the next settlement loses its road, its trade, and the last witness before nightfall.",
            "first_clue_or_question": "Why did the old silver charms blacken before the survivor arrived?",
            "player_decision": "Aid the survivor, inspect the blackened charms, or follow the frozen tracks before new snow buries them.",
        },
        {
            "starting_location": "Blackpine Toll Gate",
            "location_type": "snowbound toll gate",
            "location_identity": "A locked timber toll gate where pine smoke freezes low and one blackened silver charm has been nailed through the post.",
            "inciting_event": "The toll bell rings once by itself, and a frozen handprint appears on the inside of the barred gate.",
            "named_npc_or_visible_threat": "Elska Venn (toll keeper)",
            "immediate_problem": "Elska Venn cannot open the road until someone proves whether the handprint came from a living traveler or the thing following them.",
            "specific_stakes": "If the gate stays barred until dusk, the supply sleds turn back and Frostmere runs out of lamp oil by morning.",
            "first_clue_or_question": "Who nailed the blackened silver charm to the toll post before the bell rang?",
            "player_decision": "Open the gate, test the blackened charm, or follow the handprints along the fence line.",
        },
        {
            "starting_location": "Snowmelt Cairn",
            "location_type": "roadside cairn",
            "location_identity": "A thawing cairn beside the north road where frozen tracks circle a heap of blackened silver charms.",
            "inciting_event": "Meltwater runs uphill through the stones and exposes a traveler's name carved fresh beneath old ice.",
            "named_npc_or_visible_threat": "Nera Holl (road surveyor)",
            "immediate_problem": "Nera Holl recognizes the carved name as someone who is still alive in the next village.",
            "specific_stakes": "If the cairn is covered again, the party loses the only trail that points to who winter has marked next.",
            "first_clue_or_question": "Why does the cairn carry a living person's name under old ice?",
            "player_decision": "Dig into the cairn, warn the named villager, or track the circling footprints into the trees.",
        },
        {
            "starting_location": "Ironbell Waystation",
            "location_type": "abandoned winter waystation",
            "location_identity": "An abandoned waystation where the iron bell is split and its pull-rope is threaded with blackened silver charms.",
            "inciting_event": "A supply ledger slides from beneath the bell tower door, already rimed with frost on the inside.",
            "named_npc_or_visible_threat": "Tovin Hale (teamster)",
            "immediate_problem": "Tovin Hale's missing sled is listed in the ledger as having arrived tomorrow.",
            "specific_stakes": "If no one checks the bell tower before nightfall, the road patrol follows a false arrival record into whiteout conditions.",
            "first_clue_or_question": "Who wrote tomorrow's arrival into the frozen waystation ledger?",
            "player_decision": "Break into the bell tower, compare the ledger entries, or intercept the road patrol before they leave.",
        },
        {
            "starting_location": "Hollowdrift Supply Cache",
            "location_type": "buried road cache",
            "location_identity": "A half-buried supply cache where frost has sealed the hinges and blackened silver charms are packed among the emergency rations.",
            "inciting_event": "The cache inventory lists three missing blankets and one extra name scratched into the lid from the inside.",
            "named_npc_or_visible_threat": "Mael Rusk (cache warden)",
            "immediate_problem": "Mael Rusk knows the extra name belongs to a patrol member who never reached this road.",
            "specific_stakes": "If the cache is abandoned, the next patrol follows a false supply count and freezes without shelter.",
            "first_clue_or_question": "Who scratched the extra name inside a sealed winter cache?",
            "player_decision": "Break the cache open, search for the missing blankets, or warn the patrol before the false count sends them onward.",
        },
    ]
    available = [
        item for item in variants
        if item["location_type"].lower() not in recent_locs
        and item["inciting_event"].lower() not in recent_events
        and _premise_event_type(item["inciting_event"]).lower() not in recent_events
    ] or variants
    chosen = rng.choice(available)
    return {
        **seed,
        **chosen,
        "generated_by": "premise_seed",
        "memory_updates": [
            {"type": "location", "name": chosen["starting_location"], "status": "provisional"},
            {"type": "npc", "name": chosen["named_npc_or_visible_threat"].split("(")[0].strip(), "status": "provisional"},
        ],
        "freshness_consumed": {
            "location_type": chosen["location_type"],
            "event": chosen["inciting_event"],
        },
    }


def _vary_desert_premise_seed(seed: dict[str, Any], freshness: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    recent_locs = {str(x).lower() for x in (freshness.get("recent_location_types") or [])}
    recent_events = {str(x).lower() for x in (freshness.get("recent_opening_events") or [])}
    variants = [
        {
            "starting_location": "The Suncrack Cistern",
            "location_type": "desert cistern",
            "location_identity": "A stone cistern under white glare where a cracked water seal hangs from a dry chain.",
            "inciting_event": "The cistern lock opens to the wrong faction's seal, but the water level has not changed.",
            "named_npc_or_visible_threat": "Yuna Silt (water broker)",
            "immediate_problem": "Yuna Silt knows the seal should only open for the caravan council, not for a faction mark cut this morning.",
            "specific_stakes": "If the seal is not traced before noon, the caravan council blames the wrong house and closes the public wells.",
            "first_clue_or_question": "Who cut the faction mark into the cracked water seal?",
            "player_decision": "Inspect the cracked seal, question Yuna Silt, or follow the wet footprints leaving the cistern.",
        },
        {
            "starting_location": "Glasswake Caravan Yard",
            "location_type": "caravan water yard",
            "location_identity": "A glare-bright caravan yard where glass sand has fused around a missing cistern ledger.",
            "inciting_event": "A water tally board changes while everyone is watching, moving three barrels to a caravan that never arrived.",
            "named_npc_or_visible_threat": "Marrek Voss (ledger keeper)",
            "immediate_problem": "Marrek Voss can prove the tally changed, but not who touched the board without leaving a shadow.",
            "specific_stakes": "If the false tally stands, one outbound caravan crosses the dunes without enough water to return.",
            "first_clue_or_question": "Why did the tally assign water to a caravan that never entered Glasswake?",
            "player_decision": "Secure the tally board, audit the cistern ledger, or search for the shadowless intruder.",
        },
        {
            "starting_location": "The Saltglass Well",
            "location_type": "contested desert well",
            "location_identity": "A public well rimed with saltglass where every bucket rope has been knotted in a faction pattern.",
            "inciting_event": "The first bucket comes up full of clean water and a stamped token from a supposedly empty cistern.",
            "named_npc_or_visible_threat": "Iri Qan (well guard)",
            "immediate_problem": "Iri Qan has orders to seal the well, but the token proves someone is moving water through a hidden route.",
            "specific_stakes": "If the well is sealed before the token is understood, the poorer quarter loses its only water before nightfall.",
            "first_clue_or_question": "Which hidden cistern route carried the stamped token into the public well?",
            "player_decision": "Test the token, keep the well open, or trace the knotted ropes to the faction responsible.",
        },
        {
            "starting_location": "Mirage Tax Gate",
            "location_type": "desert toll gate",
            "location_identity": "A heat-warped toll gate where water permits are punched with a seal no caravan admits using.",
            "inciting_event": "A child tries to trade a fresh water permit dated tomorrow for one mouthful from the gate barrel.",
            "named_npc_or_visible_threat": "Safa Reed (permit clerk)",
            "immediate_problem": "Safa Reed recognizes tomorrow's permit stamp as a forgery made with the real office die.",
            "specific_stakes": "If the permit die is not found, the gate shuts and every caravan behind it begins buying water at knife prices.",
            "first_clue_or_question": "Who used the real permit die to stamp tomorrow's water papers?",
            "player_decision": "Protect the child, inspect the permit die, or confront the clerk before the gate shuts.",
        },
        {
            "starting_location": "Red Dune Ration Line",
            "location_type": "desert ration line",
            "location_identity": "A wind-cut ration line where empty water jars are marked with blue wax and one jar sweats in the sun.",
            "inciting_event": "The sweating jar carries a caravan captain's mark, but the captain has been missing for three days.",
            "named_npc_or_visible_threat": "Tamar Kes (ration caller)",
            "immediate_problem": "Tamar Kes must decide whether to open the marked jar publicly or hide it before faction agents see it.",
            "specific_stakes": "If the jar is taken by a faction agent, the only proof of the missing captain's route disappears into the dunes.",
            "first_clue_or_question": "Why is the missing captain's water jar sweating while every other jar is dry?",
            "player_decision": "Open the jar, shield Tamar Kes, or follow the blue-wax mark through the ration line.",
        },
    ]
    available = [
        item for item in variants
        if item["location_type"].lower() not in recent_locs
        and item["inciting_event"].lower() not in recent_events
        and _premise_event_type(item["inciting_event"]).lower() not in recent_events
    ] or variants
    chosen = rng.choice(available)
    return {
        **seed,
        **chosen,
        "generated_by": "premise_seed",
        "memory_updates": [
            {"type": "location", "name": chosen["starting_location"], "status": "provisional"},
            {"type": "npc", "name": chosen["named_npc_or_visible_threat"].split("(")[0].strip(), "status": "provisional"},
        ],
        "freshness_consumed": {
            "location_type": chosen["location_type"],
            "event": chosen["inciting_event"],
        },
    }


def _premise_event_type(text: str) -> str:
    lower = text.lower()
    if "collapses" in lower or "blood" in lower:
        return "injured_witness"
    if "bell" in lower or "rings" in lower:
        return "failed_protection"
    if "cairn" in lower or "carved" in lower or "name" in lower:
        return "marked_victim"
    if "ledger" in lower:
        return "impossible_record"
    if "seal" in lower or "permit" in lower:
        return "forged_authority"
    if "water" in lower or "cistern" in lower or "well" in lower:
        return "water_evidence"
    return "local_disruption"


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

    desert_water = any(w in hay for w in ("desert", "dune", "glass sand", "glass desert", "caravan"))
    water_power = any(w in hay for w in ("water", "cistern", "well", "water seal", "ration", "permit"))
    if desert_water and water_power:
        return {
            "starting_location": "The Suncrack Cistern",
            "location_type": "desert cistern",
            "location_identity": "A stone cistern under white glare where a cracked water seal hangs from a dry chain.",
            "inciting_event": "The cistern lock opens to the wrong faction's seal, but the water level has not changed.",
            "named_npc_or_visible_threat": f"{_generate_npc_name(genre, rng)} (water witness)",
            "immediate_problem": "The water seal proves someone with faction access reached the cistern before the party arrived.",
            "specific_stakes": "If the seal is not traced before noon, the public wells close and one caravan leaves without enough water.",
            "first_clue_or_question": "Who cut the faction mark into the cracked water seal?",
            "player_decision": "Inspect the cracked seal, question the water witness, or follow the wet footprints leaving the cistern.",
            "memory_updates": [
                {"type": "location", "name": "The Suncrack Cistern", "status": "campaign_opening"},
            ],
            "generated_by": "premise_seed",
            "freshness_consumed": {
                "location_type": "desert cistern",
                "event": "wrong faction seal opens cistern",
            },
        }

    premise_cases = [
        (
            ("reef", "drowned", "pearl", "tide", "citadel"),
            {
                "starting_location": "The Low-Tide Reef Gate",
                "location_type": "drowned ruin",
                "location_identity": "A glass reef passage where the drowned citadel is visible only while the tide pulls back.",
                "inciting_event": "A pearl diver's marker-bell rings from inside the sealed reef gate.",
                "role": "reef witness",
                "immediate_problem": "The tide is turning, and the bell belongs to someone who vanished before dawn.",
                "specific_stakes": "If the gate floods again, the trail disappears and the missing divers are trapped below another night.",
                "first_clue_or_question": "Why is the marker-bell ringing from inside a sealed passage?",
                "player_decision": "Enter before the tide turns, question the sea-priests, or secure the reef gate and search for another route.",
                "event_key": "reef gate opens at low tide",
            },
        ),
        (
            ("ash guild", "volcano", "vote", "election", "parliament", "relic"),
            {
                "starting_location": "The Cinder Vote Hall",
                "location_type": "civic hall",
                "location_identity": "A heat-stained assembly hall where guild votes are counted beneath old volcanic reliefs.",
                "inciting_event": "A ballot token cracks open and reveals a forbidden relic seal inside.",
                "role": "guild clerk",
                "immediate_problem": "The vote cannot continue unless someone proves which guild smuggled the relic seal into the count.",
                "specific_stakes": "If the count is certified, the wrong faction gains legal power before the fraud can be exposed.",
                "first_clue_or_question": "Who had access to the ballot urn after the ash bell rang?",
                "player_decision": "Stop the count publicly, trace the token quietly, or bargain with a guild before the hall erupts.",
                "event_key": "relic seal found in ballot token",
            },
        ),
        (
            ("orbital", "orchard", "gravity fruit", "harvest", "corporate"),
            {
                "starting_location": "The Helix Orchard Gantry",
                "location_type": "orbital farm",
                "location_identity": "A curved maintenance gantry overlooking fruit rows that bend gravity around their branches.",
                "inciting_event": "A crate of gravity fruit rises against its restraints and points toward a sabotaged harvest arm.",
                "role": "harvest tech",
                "immediate_problem": "The fruit is predicting a disaster, but the inspection crew is minutes from declaring sabotage.",
                "specific_stakes": "If the harvest arm cycles again, workers below the gantry are caught in a gravity shear.",
                "first_clue_or_question": "Why did only one crate reverse gravity before the harvest arm failed?",
                "player_decision": "Shut down the harvest line, inspect the floating crate, or confront the crew hiding the maintenance logs.",
                "event_key": "gravity fruit warns of sabotage",
            },
        ),
        (
            ("bone lantern", "lanterns", "family memory", "borderlands", "raider"),
            {
                "starting_location": "The Blackwick Lantern Mile",
                "location_type": "border road",
                "location_identity": "A lonely stretch of border road where ancestral bone lanterns mark every family oath.",
                "inciting_event": "One bone lantern goes dark and speaks a stranger's memory in a child's voice.",
                "role": "lantern keeper",
                "immediate_problem": "The dark lantern has erased a family's route-marker just as riders are seen beyond the ridge.",
                "specific_stakes": "If the memory is not anchored before nightfall, the road forgets who is allowed to pass safely.",
                "first_clue_or_question": "Whose memory replaced the family oath inside the lantern?",
                "player_decision": "Relight the lantern, follow the stolen memory, or prepare the road before riders reach the mile.",
                "event_key": "bone lantern speaks wrong memory",
            },
        ),
        (
            ("clockwork", "mechanical rain", "prophetic rust", "impossible weather"),
            {
                "starting_location": "The Rustfall District Gauge",
                "location_type": "clockwork district",
                "location_identity": "A narrow municipal gauge station where rain should fall by schedule and nowhere else.",
                "inciting_event": "The rain gauge prints tomorrow's death notice in rust before the rain begins.",
                "role": "rain auditor",
                "immediate_problem": "The district is receiving weather no engine scheduled, and the notice names someone still alive.",
                "specific_stakes": "If the gauge is reset, the warning vanishes and the district accepts a false weather report.",
                "first_clue_or_question": "Who changed the rain schedule before the gauge began to rust?",
                "player_decision": "Protect the named victim, audit the rain engine, or follow the rust trail through the district.",
                "event_key": "rain gauge prints prophetic rust",
            },
        ),
        (
            ("long winter", "north march", "frozen road", "frozen roads", "silver charms", "blacken", "howls from the wilderness"),
            {
                "starting_location": "The Frostmark Road Shrine",
                "location_type": "winter road shrine",
                "location_identity": "A wind-scoured roadside shrine where blackened silver charms hang from ice-stiff cords.",
                "inciting_event": "A bloodied survivor collapses beneath the shrine and presses a forgotten symbol into the snow.",
                "role": "winter survivor",
                "immediate_problem": "The early winter is cutting off the road, and the survivor's symbol matches charms that failed overnight.",
                "specific_stakes": "If the warning is ignored, the next settlement loses its road, its trade, and the last witness before nightfall.",
                "first_clue_or_question": "Why did the old silver charms blacken before the survivor arrived?",
                "player_decision": "Aid the survivor, inspect the blackened charms, or follow the frozen tracks before new snow buries them.",
                "event_key": "winter survivor brings forgotten symbol",
            },
        ),
    ]
    for keywords, data in premise_cases:
        if any(term in hay for term in keywords):
            npc_name = _generate_npc_name(genre, rng)
            role = data["role"]
            return {
                "starting_location": data["starting_location"],
                "location_type": data["location_type"],
                "location_identity": data["location_identity"],
                "inciting_event": data["inciting_event"],
                "named_npc_or_visible_threat": f"{npc_name} ({role})",
                "immediate_problem": data["immediate_problem"],
                "specific_stakes": data["specific_stakes"],
                "first_clue_or_question": data["first_clue_or_question"],
                "player_decision": data["player_decision"],
                "memory_updates": [
                    {"type": "location", "name": data["starting_location"], "status": "campaign_opening"},
                    {"type": "npc", "name": npc_name, "role": role, "status": "provisional"},
                ],
                "generated_by": "premise_seed",
                "freshness_consumed": {
                    "location_type": data["location_type"],
                    "event": data["event_key"],
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
        "arcane observatory": "If the evidence is lost, the source of the threat becomes guesswork.",
    }
    fallback = f"By dusk, the person carrying the clearest lead will leave {location_type} and the trail will go cold."
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

    opening_anchor = (freshness_context or {}).get("opening_anchor") or {}
    if situation_type == "campaign_opening" and isinstance(opening_anchor, dict) and opening_anchor:
        opening_context = {
            "character_name": opening_anchor.get("character_name") or "",
            "arrival_reason": opening_anchor.get("arrival_reason") or "",
            "pre_scene_activity": opening_anchor.get("pre_scene_activity") or "",
            "personal_stake": opening_anchor.get("personal_stake") or "",
            "known_npc_connection": opening_anchor.get("known_npc_connection") or "",
            "party_bond": opening_anchor.get("party_bond") or "",
            "followed_complication": opening_anchor.get("followed_complication") or "",
            "fear_of_loss": opening_anchor.get("fear_of_loss") or "",
            "trust_or_distrust": opening_anchor.get("trust_or_distrust") or opening_anchor.get("known_npc_connection") or "",
            "belief_or_rumor": opening_anchor.get("belief_or_rumor") or "",
            "why_now": (
                opening_anchor.get("personal_stake")
                or opening_anchor.get("arrival_reason")
                or opening_anchor.get("belief_or_rumor")
                or ""
            ),
        }
        required_content["opening_context"] = opening_context
        required_content["opening_character_anchor"] = opening_anchor
        if not required_content.get("player_decision"):
            required_content["player_decision"] = (
                "Act on the personal lead, ask the connected witness what they know, "
                "or hold back long enough to see who else reacts."
            )

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


def ensure_content_bundle(
    situation_type: str,
    scene_director_output: dict[str, Any] | None = None,
    world_state: dict[str, Any] | None = None,
    campaign_contract: dict[str, Any] | None = None,
    previous_scene: dict[str, Any] | None = None,
    freshness_context: dict[str, Any] | None = None,
    campaign_settings: dict[str, Any] | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Build and validate a content bundle before prose generation.

    This is deterministic: if the first bundle is invalid, it retries with an
    empty director output so the fallback builders/starter seed can provide the
    required gameable fields. The returned bundle always includes
    ``content_gate_passed`` for orchestration/debug decisions.
    """
    bundle = build_content_bundle(
        situation_type=situation_type,
        scene_director_output=scene_director_output,
        world_state=world_state,
        campaign_contract=campaign_contract,
        previous_scene=previous_scene,
        freshness_context=freshness_context,
        campaign_settings=campaign_settings,
    )
    if _bundle_has_recycled_fixture(bundle):
        bundle["validated"] = False
        bundle.setdefault("validation_result", {})["valid"] = False
        bundle["validation_result"].setdefault("generic_defaults_detected", []).append(
            "recycled opening fixture detected"
        )
    attempts = 1
    while not bundle.get("validated") and attempts < max_attempts:
        attempts += 1
        bundle = build_content_bundle(
            situation_type=situation_type,
            scene_director_output={},
            world_state=world_state,
            campaign_contract=campaign_contract,
            previous_scene=previous_scene,
            freshness_context={**(freshness_context or {}), "scene_count": (freshness_context or {}).get("scene_count", 0)},
            campaign_settings=campaign_settings,
        )
        if _bundle_has_recycled_fixture(bundle):
            bundle["validated"] = False
            bundle.setdefault("validation_result", {})["valid"] = False
            bundle["validation_result"].setdefault("generic_defaults_detected", []).append(
                "recycled opening fixture detected"
            )
    bundle["content_gate_passed"] = bool(bundle.get("validated"))
    bundle["content_gate_attempts"] = attempts
    return bundle


def _bundle_has_recycled_fixture(bundle: dict[str, Any]) -> bool:
    text = str((bundle or {}).get("required_content") or {}).lower()
    return any(term in text for term in _RECYCLED_OPENING_FIXTURES)


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
