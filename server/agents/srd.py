"""SRD 5.2 structured ruleset data for TavernTails session agents.

This module contains structured data derived from the Systems Reference
Document 5.2 (SRD 5.2) published by Wizards of the Coast under the
Creative Commons Attribution 4.0 International License (CC-BY-4.0).

Source:  https://www.dndbeyond.com/resources/1781-systems-reference-document-srd
License: CC-BY-4.0 — https://creativecommons.org/licenses/by/4.0/

When injecting this content into AI prompts, include the attribution string
from ``SRD_52_DATA["attribution"]`` to satisfy the CC-BY-4.0 license terms.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user

router = APIRouter(prefix="/rulesets", tags=["rulesets"])

# ---------------------------------------------------------------------------
# Attribution string (required by CC-BY-4.0)
# ---------------------------------------------------------------------------
SRD_52_ATTRIBUTION = (
    "This content includes material from the Systems Reference Document 5.2 "
    "(SRD 5.2) by Wizards of the Coast, licensed under CC-BY-4.0: "
    "https://creativecommons.org/licenses/by/4.0/"
)

# ---------------------------------------------------------------------------
# Built-in ruleset registry
# ---------------------------------------------------------------------------
RULESETS: Dict[str, Dict[str, Any]] = {
    "srd-5.2": {
        "id": "srd-5.2",
        "name": "D&D 5e SRD 5.2",
        "display": "D&D 5e — SRD 5.2 (CC-BY-4.0)",
        "description": (
            "Dungeons & Dragons 5th Edition System Reference Document 5.2, "
            "published by Wizards of the Coast under Creative Commons Attribution "
            "4.0 International. Contains 13 classes, 9 species, spells, monsters, "
            "and the full core rules."
        ),
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "publisher": "Wizards of the Coast",
        "genre": "heroic-fantasy",
        "attribution": SRD_52_ATTRIBUTION,
    },
    "pathfinder-2e": {
        "id": "pathfinder-2e",
        "name": "Pathfinder 2e",
        "display": "Pathfinder 2e (Paizo / ORC License)",
        "description": "Pathfinder Second Edition by Paizo, released under the ORC License.",
        "license": "ORC",
        "license_url": "https://paizo.com/orclicense",
        "publisher": "Paizo",
        "genre": "heroic-fantasy",
        "attribution": None,
    },
    "osr": {
        "id": "osr",
        "name": "OSR / Old-School Essentials",
        "display": "OSR / Old-School Essentials",
        "description": "Old-School Renaissance rules based on classic D&D editions.",
        "license": None,
        "license_url": None,
        "publisher": None,
        "genre": "classic-fantasy",
        "attribution": None,
    },
    "custom": {
        "id": "custom",
        "name": "Custom / Homebrew",
        "display": "Custom / Homebrew",
        "description": "Custom or homebrew ruleset. Describe your rules in the house_rules field.",
        "license": None,
        "license_url": None,
        "publisher": None,
        "genre": None,
        "attribution": None,
    },
}

# ---------------------------------------------------------------------------
# SRD 5.2 structured data (CC-BY-4.0)
# ---------------------------------------------------------------------------
SRD_52_DATA: Dict[str, Any] = {
    "attribution": SRD_52_ATTRIBUTION,
    # Core resolution mechanic
    "resolution": (
        "d20 + ability modifier (+ proficiency bonus if proficient) vs. Difficulty Class (DC). "
        "Advantage: roll 2d20, take the higher. Disadvantage: roll 2d20, take the lower."
    ),
    "proficiency_bonus": (
        "Based on total character level: "
        "+2 (levels 1–4), +3 (5–8), +4 (9–12), +5 (13–16), +6 (17–20)."
    ),
    # Six ability scores
    "ability_scores": {
        "STR": "Strength — melee attacks (non-finesse), Athletics, carrying capacity",
        "DEX": "Dexterity — ranged/finesse attacks, AC (light/medium armor), Initiative, Acrobatics, Sleight of Hand, Stealth",
        "CON": "Constitution — hit points, concentration checks",
        "INT": "Intelligence — Arcana, History, Investigation, Nature, Religion; wizard spellcasting",
        "WIS": "Wisdom — Animal Handling, Insight, Medicine, Perception, Survival; cleric/druid/ranger spellcasting",
        "CHA": "Charisma — Deception, Intimidation, Performance, Persuasion; bard/paladin/sorcerer/warlock spellcasting",
    },
    # 18 SRD skills with associated ability
    "skills": {
        "Acrobatics": "DEX",
        "Animal Handling": "WIS",
        "Arcana": "INT",
        "Athletics": "STR",
        "Deception": "CHA",
        "History": "INT",
        "Insight": "WIS",
        "Intimidation": "CHA",
        "Investigation": "INT",
        "Medicine": "WIS",
        "Nature": "INT",
        "Perception": "WIS",
        "Performance": "CHA",
        "Persuasion": "CHA",
        "Religion": "INT",
        "Sleight of Hand": "DEX",
        "Stealth": "DEX",
        "Survival": "WIS",
    },
    # 13 SRD classes with key mechanical properties
    "classes": {
        "Artificer": {
            "hit_die": "d8",
            "primary_ability": "INT",
            "saving_throws": ["CON", "INT"],
            "armor": ["light", "medium", "shields"],
            "weapons": ["simple"],
            "spellcasting": "INT (prepared, half-caster)",
            "key_features": ["Infusions", "Magical Tinkering", "The Right Tool for the Job"],
        },
        "Barbarian": {
            "hit_die": "d12",
            "primary_ability": "STR",
            "saving_throws": ["STR", "CON"],
            "armor": ["light", "medium", "shields"],
            "weapons": ["simple", "martial"],
            "spellcasting": None,
            "key_features": ["Rage", "Unarmored Defense", "Reckless Attack", "Danger Sense"],
        },
        "Bard": {
            "hit_die": "d8",
            "primary_ability": "CHA",
            "saving_throws": ["DEX", "CHA"],
            "armor": ["light"],
            "weapons": ["simple", "hand crossbow", "longsword", "rapier", "shortsword"],
            "spellcasting": "CHA (known, full-caster)",
            "key_features": ["Bardic Inspiration (d6→d12)", "Jack of All Trades", "Song of Rest"],
        },
        "Cleric": {
            "hit_die": "d8",
            "primary_ability": "WIS",
            "saving_throws": ["WIS", "CHA"],
            "armor": ["light", "medium", "shields"],
            "weapons": ["simple"],
            "spellcasting": "WIS (prepared, full-caster)",
            "key_features": ["Divine Domain", "Channel Divinity", "Turn Undead", "Divine Intervention"],
        },
        "Druid": {
            "hit_die": "d8",
            "primary_ability": "WIS",
            "saving_throws": ["INT", "WIS"],
            "armor": ["light", "medium", "shields (non-metal)"],
            "weapons": ["clubs", "daggers", "darts", "javelins", "maces", "quarterstaffs", "scimitars", "sickles", "slings", "spears"],
            "spellcasting": "WIS (prepared, full-caster)",
            "key_features": ["Wild Shape", "Druid Circle", "Timeless Body", "Beast Spells"],
        },
        "Fighter": {
            "hit_die": "d10",
            "primary_ability": "STR or DEX",
            "saving_throws": ["STR", "CON"],
            "armor": ["all armor", "shields"],
            "weapons": ["simple", "martial"],
            "spellcasting": None,
            "key_features": ["Fighting Style", "Second Wind", "Action Surge", "Extra Attack", "Indomitable"],
        },
        "Monk": {
            "hit_die": "d8",
            "primary_ability": "DEX + WIS",
            "saving_throws": ["STR", "DEX"],
            "armor": [],
            "weapons": ["simple", "shortswords"],
            "spellcasting": None,
            "key_features": ["Martial Arts", "Ki", "Unarmored Defense", "Flurry of Blows", "Stunning Strike"],
        },
        "Paladin": {
            "hit_die": "d10",
            "primary_ability": "STR + CHA",
            "saving_throws": ["WIS", "CHA"],
            "armor": ["all armor", "shields"],
            "weapons": ["simple", "martial"],
            "spellcasting": "CHA (prepared, half-caster)",
            "key_features": ["Divine Sense", "Lay on Hands", "Divine Smite", "Aura of Protection", "Sacred Oath"],
        },
        "Ranger": {
            "hit_die": "d10",
            "primary_ability": "DEX + WIS",
            "saving_throws": ["STR", "DEX"],
            "armor": ["light", "medium", "shields"],
            "weapons": ["simple", "martial"],
            "spellcasting": "WIS (known, half-caster)",
            "key_features": ["Favored Enemy", "Natural Explorer", "Extra Attack", "Feral Instinct"],
        },
        "Rogue": {
            "hit_die": "d8",
            "primary_ability": "DEX",
            "saving_throws": ["DEX", "INT"],
            "armor": ["light"],
            "weapons": ["simple", "hand crossbow", "longsword", "rapier", "shortsword"],
            "spellcasting": None,
            "key_features": ["Sneak Attack", "Thieves' Cant", "Cunning Action", "Uncanny Dodge", "Evasion", "Reliable Talent"],
        },
        "Sorcerer": {
            "hit_die": "d6",
            "primary_ability": "CHA",
            "saving_throws": ["CON", "CHA"],
            "armor": [],
            "weapons": ["daggers", "darts", "slings", "quarterstaffs", "light crossbows"],
            "spellcasting": "CHA (known, full-caster)",
            "key_features": ["Sorcerous Origin", "Font of Magic", "Sorcery Points", "Metamagic"],
        },
        "Warlock": {
            "hit_die": "d8",
            "primary_ability": "CHA",
            "saving_throws": ["WIS", "CHA"],
            "armor": ["light"],
            "weapons": ["simple"],
            "spellcasting": "CHA (known, short-rest slots, full spell progression)",
            "key_features": ["Otherworldly Patron", "Eldritch Invocations", "Pact Boon", "Mystic Arcanum"],
        },
        "Wizard": {
            "hit_die": "d6",
            "primary_ability": "INT",
            "saving_throws": ["INT", "WIS"],
            "armor": [],
            "weapons": ["daggers", "darts", "slings", "quarterstaffs", "light crossbows"],
            "spellcasting": "INT (prepared from spellbook, full-caster)",
            "key_features": ["Arcane Recovery", "Spellbook", "Arcane Tradition", "Spell Mastery"],
        },
    },
    # 9 SRD species
    "species": {
        "Dragonborn": {
            "size": "Medium", "speed": 30,
            "traits": ["Draconic Ancestry", "Breath Weapon", "Damage Resistance"],
        },
        "Dwarf": {
            "size": "Medium", "speed": 25,
            "traits": ["Darkvision", "Dwarven Resilience", "Stonecunning", "Tool Proficiency"],
        },
        "Elf": {
            "size": "Medium", "speed": 30,
            "traits": ["Darkvision", "Keen Senses (Perception proficiency)", "Fey Ancestry", "Trance"],
        },
        "Gnome": {
            "size": "Small", "speed": 25,
            "traits": ["Darkvision", "Gnome Cunning (advantage on INT/WIS/CHA saves vs magic)"],
        },
        "Half-Elf": {
            "size": "Medium", "speed": 30,
            "traits": ["Darkvision", "Fey Ancestry", "Skill Versatility (+2 skills of choice)"],
        },
        "Half-Orc": {
            "size": "Medium", "speed": 30,
            "traits": ["Darkvision", "Menacing (Intimidation proficiency)", "Relentless Endurance", "Savage Attacks"],
        },
        "Halfling": {
            "size": "Small", "speed": 25,
            "traits": ["Lucky (reroll 1s on d20 rolls)", "Brave", "Halfling Nimbleness"],
        },
        "Human": {
            "size": "Medium", "speed": 30,
            "traits": ["+1 to all six ability scores", "One extra language"],
        },
        "Tiefling": {
            "size": "Medium", "speed": 30,
            "traits": ["Darkvision", "Hellish Resistance (fire resistance)", "Infernal Legacy (thaumaturgy + spells)"],
        },
    },
    # 15 SRD conditions with brief descriptions
    "conditions": {
        "Blinded": (
            "Can't see; auto-fail sight-dependent checks. "
            "Attacks against the creature have advantage; its attack rolls have disadvantage."
        ),
        "Charmed": (
            "Can't attack or target the charmer with harmful abilities. "
            "The charmer has advantage on Charisma checks against the creature."
        ),
        "Deafened": "Can't hear; auto-fail hearing-dependent checks.",
        "Exhaustion": (
            "Cumulative levels: 1=Disadvantage on ability checks; "
            "2=Speed halved; 3=Disadvantage on attack rolls and saving throws; "
            "4=Hit point maximum halved; 5=Speed reduced to 0; 6=Death."
        ),
        "Frightened": (
            "Disadvantage on ability checks and attack rolls while source of fear is in line of sight. "
            "Can't willingly move closer to the source."
        ),
        "Grappled": (
            "Speed becomes 0. "
            "Ends if the grappler is incapacitated or the creature is forcibly moved beyond the grappler's reach."
        ),
        "Incapacitated": "Can't take actions or reactions.",
        "Invisible": (
            "Can't be seen without special sense. "
            "Has advantage on attack rolls; attack rolls against it have disadvantage."
        ),
        "Paralyzed": (
            "Incapacitated; can't move or speak. "
            "Auto-fail STR and DEX saving throws. "
            "Attack rolls against it have advantage; hits within 5 ft are critical hits."
        ),
        "Petrified": (
            "Transformed to stone; incapacitated, can't move or speak. "
            "Resistant to all damage; immune to poison and disease. "
            "Existing poison/disease effects are suspended."
        ),
        "Poisoned": "Disadvantage on attack rolls and ability checks.",
        "Prone": (
            "Can only crawl (costs 1 extra ft per ft moved) or stand up (half movement). "
            "Disadvantage on attack rolls. "
            "Melee attacks against it have advantage; ranged attacks have disadvantage."
        ),
        "Restrained": (
            "Speed becomes 0. "
            "Attack rolls against it have advantage; its attack rolls have disadvantage. "
            "Disadvantage on DEX saving throws."
        ),
        "Stunned": (
            "Incapacitated; can't move; can only speak falteringly. "
            "Auto-fail STR and DEX saving throws. Attack rolls against it have advantage."
        ),
        "Unconscious": (
            "Incapacitated; can't move or speak; drops held items; falls prone. "
            "Auto-fail STR and DEX saving throws. "
            "Attack rolls against it have advantage; hits within 5 ft are critical hits."
        ),
    },
    # Standard combat actions
    "combat_actions": {
        "Attack": "Make one melee or ranged weapon attack (more at higher levels with Extra Attack).",
        "Cast a Spell": "Cast a spell with a casting time of 1 action.",
        "Dash": "Gain extra movement equal to your speed for this turn.",
        "Disengage": "Movement this turn doesn't provoke opportunity attacks.",
        "Dodge": "Attacks against you have disadvantage (until start of your next turn); advantage on DEX saves.",
        "Help": "Grant an ally advantage on its next ability check or attack roll against a creature within 5 ft.",
        "Hide": "Make a Dexterity (Stealth) check to become hidden.",
        "Ready": "Prepare a specified action to trigger on a chosen condition before your next turn.",
        "Search": "Devote attention to finding something (Perception or Investigation check).",
        "Use an Object": "Interact with an object that requires special attention this turn.",
        "Bonus Action": "Available only when a class feature, spell, or other rule grants one (e.g. Cunning Action).",
        "Reaction": "Instantaneous response to a trigger; can happen on your or another creature's turn.",
        "Opportunity Attack": "Reaction triggered when a creature you can see leaves your reach voluntarily.",
    },
}


# ---------------------------------------------------------------------------
# Helper functions used by other server modules
# ---------------------------------------------------------------------------

def get_ruleset_context(ruleset_id: str) -> Dict[str, Any]:
    """Return a structured context dict for the given ruleset ID.

    Returns an empty dict for unknown or custom rulesets.
    For ``srd-5.2`` returns a compact subset of :data:`SRD_52_DATA` suitable
    for serialising into agent prompt context.
    """
    if ruleset_id != "srd-5.2":
        return {}
    return {
        "ruleset_id": "srd-5.2",
        "name": "D&D 5e SRD 5.2",
        "attribution": SRD_52_DATA["attribution"],
        "resolution": SRD_52_DATA["resolution"],
        "proficiency_bonus": SRD_52_DATA["proficiency_bonus"],
        "ability_scores": list(SRD_52_DATA["ability_scores"].keys()),
        "skills": SRD_52_DATA["skills"],
        "classes": list(SRD_52_DATA["classes"].keys()),
        "conditions": list(SRD_52_DATA["conditions"].keys()),
        "combat_actions": list(SRD_52_DATA["combat_actions"].keys()),
    }


def build_ruleset_prompt_context(ruleset_id: str) -> str:
    """Return a compact, agent-safe string describing the ruleset mechanics.

    The returned string is suitable for injection into LLM prompts.
    Returns an empty string for unknown or custom rulesets.
    """
    if ruleset_id != "srd-5.2":
        return ""
    data = SRD_52_DATA
    classes = ", ".join(data["classes"].keys())
    conditions = ", ".join(data["conditions"].keys())
    actions = ", ".join(k for k in data["combat_actions"] if k not in ("Bonus Action", "Reaction", "Opportunity Attack"))
    return (
        f"Ruleset: D&D 5e (SRD 5.2, CC-BY-4.0). "
        f"Resolution: {data['resolution']} "
        f"Classes: {classes}. "
        f"Conditions: {conditions}. "
        f"Standard actions: {actions}. "
        f"{data['attribution']}"
    )


# ---------------------------------------------------------------------------
# API router
# ---------------------------------------------------------------------------

@router.get("", summary="List available structured rulesets")
def list_rulesets() -> Dict[str, Any]:
    """Return all built-in structured rulesets.

    No authentication required — this is public reference data.
    """
    return {
        "rulesets": [
            {
                "id": rs["id"],
                "name": rs["name"],
                "display": rs["display"],
                "description": rs["description"],
                "license": rs.get("license"),
                "publisher": rs.get("publisher"),
            }
            for rs in RULESETS.values()
        ]
    }


@router.get("/{ruleset_id}", summary="Get structured data for a ruleset")
def get_ruleset(ruleset_id: str, current_user=Depends(get_current_user)) -> Dict[str, Any]:
    """Return full structured data for a built-in ruleset (auth required)."""
    if ruleset_id not in RULESETS:
        raise HTTPException(status_code=404, detail="Ruleset not found")
    meta = RULESETS[ruleset_id]
    data: Dict[str, Any] = SRD_52_DATA if ruleset_id == "srd-5.2" else {}
    return {"ruleset": meta, "data": data}


# ---------------------------------------------------------------------------
# Exported list of known ruleset IDs (used by frontend / campaign settings)
# ---------------------------------------------------------------------------
KNOWN_RULESET_IDS: List[str] = list(RULESETS.keys())
