"""TTRPG system detection from character sheet data.

Analyses skill names, class names, stat labels, and raw text to infer
which TTRPG system a character sheet belongs to.  The result is stored on
the character sheet so generative agents can tailor output without needing
explicit user configuration.

Design goals:
- System-agnostic: no single system is assumed as "default".
- Best-effort: returns the best guess plus a confidence score and evidence
  list so the UI / agents can handle uncertainty gracefully.
- Extensible: add new systems by appending to SYSTEM_SIGNATURES below.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# System signatures
# Each system entry has:
#   "classes"  - set of class/role names used in this system
#   "skills"   - set of skill names used in this system
#   "stats"    - set of primary ability/stat names
#   "keywords" - freeform strings found in raw text that strongly indicate
#                this system (e.g. publisher name, rulebook title)
# Matches are case-insensitive.  Scoring is additive: each matching
# class/skill/stat contributes 2 pts, each keyword match contributes 3 pts.
# ---------------------------------------------------------------------------
SYSTEM_SIGNATURES: List[Dict[str, Any]] = [
    {
        "name": "D&D 5e",
        "publisher": "Wizards of the Coast",
        # Mechanical fingerprint inferred purely from observable character-sheet evidence
        # (resolution die, stat structure, resource tracks, genre).  These descriptors
        # are system-agnostic and do not reproduce any copyrighted rules text.
        "mechanic_profile": {
            "resolution": "d20-check",
            "stat_model": "six-ability-scores-with-modifiers",
            "resources": ["hit-points", "spell-slots", "hit-dice"],
            "key_mechanics": ["proficiency-bonus", "advantage-disadvantage", "saving-throws", "action-bonus-action-reaction"],
            "genre": "heroic-fantasy",
        },
        "classes": {
            "artificer", "barbarian", "bard", "cleric", "druid", "fighter",
            "monk", "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard",
        },
        "skills": {
            "acrobatics", "animal handling", "arcana", "athletics",
            "deception", "history", "insight", "intimidation",
            "investigation", "medicine", "nature", "perception",
            "performance", "persuasion", "religion", "sleight of hand",
            "stealth", "survival",
        },
        "stats": {"str", "dex", "con", "int", "wis", "cha",
                  "strength", "dexterity", "constitution", "intelligence",
                  "wisdom", "charisma"},
        # Widget keys that appear on D&D 5e official/D&D Beyond character sheets.
        # Proficiency Bonus, Death Saves, Hit Dice, and Inspiration are D&D 5e–specific
        # field labels that do not appear on Pathfinder sheets.
        "widget_signals": {
            "positive": {
                "proficiency bonus", "profbonus",
                "death saves", "death save",
                "hit dice", "inspiration",
                "spell slots total", "slotstotal",
                "animal handling", "sleight of hand",
            },
            "negative": {
                "ancestry", "heritage", "proficiency rank",
                "focus points", "class dc", "bulk",
                "bab", "base attack bonus", "cmb", "cmd",
                "control", "daring", "fitness", "reason",
            },
        },
        "keywords": {
            "d&d", "dnd", "dungeons & dragons", "dungeons and dragons",
            "5e", "5th edition", "d&d beyond", "dndbeyond",
            "player's handbook", "phb", "tasha's", "xanathar",
            "sword coast", "forgotten realms",
        },
    },
    {
        "name": "Pathfinder 2e",
        "publisher": "Paizo",
        "mechanic_profile": {
            "resolution": "d20-check",
            "stat_model": "six-ability-scores-with-modifiers",
            "resources": ["hit-points", "spell-slots", "focus-points"],
            "key_mechanics": ["proficiency-ranks", "three-action-economy", "degrees-of-success", "reactions"],
            "genre": "heroic-fantasy",
        },
        "classes": {
            "alchemist", "barbarian", "bard", "champion", "cleric", "druid",
            "fighter", "investigator", "magus", "monk", "oracle", "psychic",
            "ranger", "rogue", "sorcerer", "summoner", "swashbuckler",
            "thaumaturge", "witch", "wizard",
            # Remaster classes
            "animist", "exemplar", "commander", "guardian",
        },
        "skills": {
            "acrobatics", "arcana", "athletics", "crafting", "deception",
            "diplomacy", "intimidation", "lore", "medicine", "nature",
            "occultism", "performance", "religion", "society", "stealth",
            "survival", "thievery",
        },
        "stats": {"str", "dex", "con", "int", "wis", "cha",
                  "strength", "dexterity", "constitution", "intelligence",
                  "wisdom", "charisma"},
        # Widget keys that appear on official PF2e character sheets but not PF1e.
        # Used by infer_ttrpg_system when widget_keys are supplied in the sheet dict.
        "widget_signals": {
            "positive": {
                "proficiency rank", "ancestry", "heritage",
                "focus points", "focus max", "class dc", "bulk",
            },
            "negative": {"bab", "base attack bonus", "cmb", "cmd", "spells per day"},
        },
        "keywords": {
            "pathfinder", "pf2e", "pf2", "paizo", "pathfinder 2",
            "pathfinder second edition", "age of ashes", "abomination vaults",
            "core rulebook", "player core", "pzo",
            # Pathfinder-specific sheet terminology
            "ancestry", "heritage", "focus points", "class dc",
        },
    },
    {
        "name": "Pathfinder 1e",
        "publisher": "Paizo",
        "mechanic_profile": {
            "resolution": "d20-check",
            "stat_model": "six-ability-scores-with-modifiers",
            "resources": ["hit-points", "spell-slots", "daily-abilities"],
            "key_mechanics": ["base-attack-bonus", "cmb-cmd", "feat-chains", "skill-ranks-per-level"],
            "genre": "heroic-fantasy",
        },
        "classes": {
            "alchemist", "barbarian", "bard", "cavalier", "cleric",
            "druid", "fighter", "gunslinger", "inquisitor", "magus",
            "monk", "ninja", "oracle", "paladin", "ranger", "rogue",
            "samurai", "sorcerer", "summoner", "witch", "wizard",
        },
        "skills": {
            "acrobatics", "appraise", "bluff", "climb", "craft",
            "diplomacy", "disable device", "disguise", "escape artist",
            "fly", "handle animal", "heal", "intimidate", "knowledge",
            "linguistics", "perception", "perform", "profession", "ride",
            "sense motive", "sleight of hand", "spellcraft", "stealth",
            "survival", "swim", "use magic device",
        },
        "stats": {"str", "dex", "con", "int", "wis", "cha",
                  "strength", "dexterity", "constitution", "intelligence",
                  "wisdom", "charisma"},
        "keywords": {
            "pathfinder 1e", "pathfinder 1", "pathfinder first edition",
            "pathfinder rpg",
            # PF1e-specific sheet terminology (these appear in widget key lines)
            "base attack bonus", "bab", "cmb", "cmd",
        },
        # Widget keys that appear on official PF1e character sheets but not PF2e.
        "widget_signals": {
            "positive": {
                "bab", "base attack bonus", "cmb", "cmd",
                "spells per day", "combat maneuver bonus", "combat maneuver defense",
            },
            "negative": {"proficiency rank", "ancestry", "heritage", "focus points"},
        },
    },
    {
        "name": "Starfinder",
        "publisher": "Paizo",
        "mechanic_profile": {
            "resolution": "d20-check",
            "stat_model": "six-ability-scores-with-modifiers",
            "resources": ["hit-points", "stamina-points", "resolve-points", "spell-slots"],
            "key_mechanics": ["bulk-encumbrance", "eac-kac-armor-class", "starship-combat", "tech-items"],
            "genre": "science-fantasy",
        },
        "classes": {
            "biohacker", "envoy", "evolutionist", "mechanic", "mystic",
            "nanocyte", "operative", "precog", "solarian", "soldier",
            "technomancer", "vanguard", "witchwarper",
        },
        "skills": {
            "acrobatics", "athletics", "bluff", "computers", "culture",
            "diplomacy", "disguise", "engineering", "intimidate", "life science",
            "medicine", "mysticism", "perception", "physical science",
            "piloting", "profession", "sense motive", "sleight of hand",
            "social", "stealth", "survival",
        },
        "stats": {"str", "dex", "con", "int", "wis", "cha",
                  "strength", "dexterity", "constitution", "intelligence",
                  "wisdom", "charisma"},
        "keywords": {
            "starfinder", "sfrd", "pact worlds", "drift", "eox",
            "armada", "starship", "absalom station",
        },
        # Widget keys that appear on Starfinder character sheets but not on PF or D&D sheets.
        "widget_signals": {
            "positive": {
                "stamina points", "sp max", "sp current", "resolve points",
                "rp max", "rp current", "eac", "kac", "theme",
                "drift", "racial hp",
            },
            "negative": {
                "proficiency rank", "ancestry", "heritage", "focus points",
                "bab", "base attack bonus", "cmb", "cmd",
            },
        },
    },
    {
        "name": "Call of Cthulhu",
        "publisher": "Chaosium",
        "mechanic_profile": {
            "resolution": "percentile-skill-check",
            "stat_model": "eight-attributes-percentile-range",
            "resources": ["hit-points", "magic-points", "sanity", "luck"],
            "key_mechanics": ["skill-improvement-on-success", "sanity-loss", "push-roll", "occupation-skills"],
            "genre": "investigative-horror",
        },
        "classes": {
            "accountant", "artist", "author", "clergyman", "criminal",
            "dilettante", "doctor of medicine", "engineer", "entertainer",
            "farmer", "federal agent", "hobo", "investigator", "journalist",
            "lawyer", "librarian", "military officer", "missionary", "nurse",
            "occultist", "parapsychologist", "police detective",
            "private investigator", "professor", "soldier", "spy",
            "street tough", "tribal shaman",
        },
        "skills": {
            "accounting", "anthropology", "appraise", "archaeology",
            "art/craft", "charm", "climb", "computer use", "credit rating",
            "cthulhu mythos", "disguise", "dodge", "drive auto",
            "electrical repair", "fast talk", "fighting", "first aid",
            "history", "hypnosis", "intimidate", "jump", "language",
            "law", "library use", "listen", "locksmith",
            "mechanical repair", "medicine", "natural world", "navigate",
            "occult", "operate heavy machinery", "persuade", "photography",
            "pilot", "psychology", "psychoanalysis", "ride", "science",
            "sleight of hand", "spot hidden", "stealth", "swim",
            "throw", "track",
        },
        "stats": {
            "str", "dex", "con", "int", "pow", "app", "edu", "siz",
            "strength", "dexterity", "constitution", "intelligence",
            "power", "appearance", "education", "size",
            "sanity", "luck", "hit points", "magic points",
        },
        # Widget keys that appear on CoC sheets but not on D&D/PF sheets.
        "widget_signals": {
            "positive": {
                "sanity points", "magic points", "luck", "cthulhu mythos",
                "pow", "app", "siz", "edu", "investigator name",
            },
            "negative": {"proficiency bonus", "spell slots", "ki points"},
        },
        "keywords": {
            "call of cthulhu", "coc", "cthulhu", "investigator",
            "keeper", "chaosium", "sanity", "cosmic horror",
            "lovecraft", "7th edition",
        },
    },
    {
        "name": "Star Trek Adventures",
        "publisher": "Modiphius Entertainment",
        "mechanic_profile": {
            "resolution": "2d20-check",
            "stat_model": "six-attributes-plus-six-disciplines",
            "resources": ["stress", "determination", "momentum"],
            "key_mechanics": ["momentum-pool", "complication-threat", "talents", "values"],
            "genre": "science-fiction",
        },
        "classes": {
            "command", "conn", "engineering", "medical", "operations",
            "science", "security", "tactical",
        },
        "skills": {
            "command", "conn", "engineering", "medical", "science", "security",
        },
        "stats": {
            "control", "daring", "fitness", "insight",
            "presence", "reason",
            "engineering", "medicine", "science",
            "conn", "command", "security",
        },
        "keywords": {
            "star trek", "sta", "star trek adventures", "modiphius",
            "starfleet", "federation", "klingon", "vulcan", "romulan",
            "starship", "uss", "united federation of planets",
        },
    },
    {
        "name": "Shadow of the Demon Lord",
        "publisher": "Schwalb Entertainment",
        "mechanic_profile": {
            "resolution": "d20-check",
            "stat_model": "four-attributes-with-modifiers",
            "resources": ["health", "insanity", "corruption"],
            "key_mechanics": ["boons-banes", "traditions", "path-levels", "fortune"],
            "genre": "dark-fantasy",
        },
        "classes": {
            "warrior", "priest", "rogue", "magician",
        },
        "skills": set(),
        "stats": {"strength", "agility", "intellect", "will"},
        "keywords": {
            "shadow of the demon lord", "sotdl", "schwalb",
            "demon lord", "tradition",
        },
    },
    {
        "name": "Warhammer Fantasy Roleplay",
        "publisher": "Cubicle 7",
        "mechanic_profile": {
            "resolution": "percentile-skill-check",
            "stat_model": "ten-characteristics-percentile-range",
            "resources": ["wounds", "fate-fortune", "corruption", "resilience"],
            "key_mechanics": ["career-advances", "talents", "opposed-checks", "critical-wounds"],
            "genre": "dark-fantasy",
        },
        "classes": {
            "apprentice wizard", "burgher", "cavalryman", "courtier",
            "entertainer", "innkeeper", "investigator", "knight",
            "mercenary", "physician", "rat catcher", "scholar", "scout",
            "soldier", "thief", "warrior priest", "wizard",
        },
        "skills": {
            "animal care", "bribery", "channelling", "charm",
            "charm animal", "climb", "consume alcohol", "cool",
            "dodge", "drive", "endurance", "entertain",
            "evaluate", "gamble", "gossip", "haggle", "heal",
            "intimidate", "intuition", "leadership", "lore",
            "melee", "navigation", "outdoor survival", "perception",
            "ranged", "ride", "row", "sail", "stealth",
            "swim", "trade", "track",
        },
        "stats": {
            "ws", "bs", "s", "t", "i", "ag", "dex", "int", "wp", "fel",
            "weapon skill", "ballistic skill", "strength", "toughness",
            "initiative", "agility", "dexterity", "intelligence",
            "willpower", "fellowship",
        },
        "keywords": {
            "warhammer", "wfrp", "cubicle 7", "altdorf", "reikland",
            "sigmar", "old world", "chaos",
        },
    },
    {
        "name": "Alien RPG",
        "publisher": "Free League Publishing",
        "mechanic_profile": {
            "resolution": "dice-pool-d6",
            "stat_model": "four-attributes-with-skill-ratings",
            "resources": ["health", "stress", "ammo"],
            "key_mechanics": ["stress-dice", "push-rolls", "panic-check", "critical-injuries"],
            "genre": "science-fiction-horror",
        },
        "classes": {
            "colonial marine", "company agent", "kid", "medic",
            "officer", "pilot", "roughneck", "scientist",
        },
        "skills": {
            "close combat", "command", "comtech", "heavy machinery",
            "manipulation", "medical aid", "mobility", "observation",
            "piloting", "ranged combat", "stamina", "survival",
        },
        "stats": {
            "strength", "agility", "wits", "empathy",
        },
        "keywords": {
            "alien rpg", "alien", "free league", "xenomorph",
            "weyland-yutani", "nostromo",
        },
    },
    {
        "name": "Shadowrun",
        "publisher": "Catalyst Game Labs",
        "mechanic_profile": {
            "resolution": "dice-pool-d6",
            "stat_model": "nine-attributes-with-dice-ratings",
            "resources": ["physical-condition-monitor", "stun-condition-monitor", "essence", "edge"],
            "key_mechanics": ["threshold-hits", "glitch-critical-glitch", "initiative-passes", "matrix-actions"],
            "genre": "cyberpunk-fantasy",
        },
        "classes": {
            "adept", "decker", "face", "gunslinger", "mage", "rigger",
            "samurai", "shaman", "smuggler", "soldier", "spy",
            "street samurai", "street shaman", "technomancer",
        },
        "skills": {
            "archery", "automatics", "blades", "clubs", "computer",
            "con", "cybercombat", "demolitions", "disguise",
            "electronics", "etiquette", "forgery", "gunnery",
            "gymnastics", "hacking", "hardware", "heavy weapons",
            "impersonation", "intimidation", "locksmith",
            "longarms", "medicine", "navigation", "negotiation",
            "palming", "perception", "pilot", "pistols", "running",
            "shotguns", "sneaking", "software", "spellcasting",
            "summoning", "survival", "swimming", "unarmed combat",
        },
        "stats": {
            "body", "agility", "reaction", "strength", "willpower",
            "logic", "intuition", "charisma", "edge", "magic",
            "resonance", "essence",
        },
        "keywords": {
            "shadowrun", "sixth world", "nuyen", "matrix",
            "sprawl", "corp", "megacorp", "awakened", "otaku",
        },
    },
]

# Build a lowercase lookup index for fast matching
_SYSTEMS_BY_NAME: Dict[str, Dict[str, Any]] = {s["name"]: s for s in SYSTEM_SIGNATURES}


def _norm(text: str) -> str:
    """Lowercase and strip for comparison."""
    return (text or "").lower().strip()


def _score_system(sig: Dict[str, Any], sheet: Dict[str, Any]) -> tuple[int, List[str]]:
    """Return (score, evidence_list) for a single system signature vs a sheet."""
    score = 0
    evidence: List[str] = []

    # ---- Class name matching -----------------------------------------------
    class_name = _norm(sheet.get("class_name") or "")
    for cls_part in re.split(r"[/,|]+", class_name):
        cls_part = cls_part.strip()
        if cls_part and cls_part in sig["classes"]:
            score += 2
            evidence.append(f"class:{cls_part}")

    # Also check multiclass list
    for mc_entry in sheet.get("multiclass") or []:
        mc_cls = _norm(mc_entry.get("class_name") or mc_entry.get("name") or "")
        if mc_cls and mc_cls in sig["classes"]:
            score += 2
            evidence.append(f"multiclass:{mc_cls}")

    # ---- Skill name matching -----------------------------------------------
    skill_names = _collect_skill_names(sheet)
    for sname in skill_names:
        sname_norm = _norm(sname)
        if sname_norm in sig["skills"]:
            score += 2
            evidence.append(f"skill:{sname_norm}")

    # ---- Stat key matching -------------------------------------------------
    stats = sheet.get("stats") or {}
    if isinstance(stats, dict):
        for stat_key in stats:
            sk = _norm(stat_key)
            if sk in sig["stats"]:
                score += 1
                evidence.append(f"stat:{sk}")

    # ---- Keyword matching in raw text / import metadata --------------------
    searchable = _collect_raw_text(sheet)
    for kw in sig["keywords"]:
        pattern = re.escape(kw)
        if re.search(rf"\b{pattern}\b", searchable, re.IGNORECASE):
            score += 3
            evidence.append(f"keyword:{kw}")

    # ---- Widget key signals (PDF form field names for PF edition disambiguation) ----
    widget_keys = sheet.get("widget_keys") or []
    if widget_keys and sig.get("widget_signals"):
        def _normalize_widget_key(s: str) -> str:
            return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()

        normed_wkeys = {_normalize_widget_key(k) for k in widget_keys if k}
        positive_signals = sig["widget_signals"].get("positive", set())
        negative_signals = sig["widget_signals"].get("negative", set())

        for signal in positive_signals:
            norm_sig = _normalize_widget_key(signal)
            for nk in normed_wkeys:
                if norm_sig == nk or norm_sig in nk:
                    score += 4
                    evidence.append(f"widget_signal:{norm_sig}")
                    break

        for signal in negative_signals:
            norm_sig = _normalize_widget_key(signal)
            for nk in normed_wkeys:
                if norm_sig == nk or norm_sig in nk:
                    score -= 2
                    evidence.append(f"widget_antisignal:{norm_sig}")
                    break

    return score, evidence


def _collect_skill_names(sheet: Dict[str, Any]) -> List[str]:
    """Extract skill names from a sheet regardless of import format."""
    names: List[str] = []
    skills = sheet.get("skills") or []
    if isinstance(skills, list):
        for entry in skills:
            if isinstance(entry, dict):
                n = entry.get("name") or entry.get("skill") or ""
                if n:
                    names.append(str(n))
            elif isinstance(entry, str):
                names.append(entry)
    return names


def _collect_raw_text(sheet: Dict[str, Any]) -> str:
    """Collect all freeform text from a sheet for keyword scanning."""
    parts: List[str] = []

    raw_text = sheet.get("raw_text") or ""
    if isinstance(raw_text, str):
        parts.append(raw_text[:10000])

    # Import metadata sometimes has the source URL / label
    imp = sheet.get("import") or {}
    if isinstance(imp, dict):
        for field in ("source", "ddb_url", "filename"):
            v = imp.get(field) or ""
            if v:
                parts.append(str(v))

    # Raw embedded JSON
    raw_embedded = sheet.get("raw") or {}
    if isinstance(raw_embedded, dict):
        # Only stringify top-level string values to keep it fast
        for v in raw_embedded.values():
            if isinstance(v, str):
                parts.append(v[:500])

    return " ".join(parts)


def infer_ttrpg_system(sheet: Dict[str, Any]) -> Dict[str, Any]:
    """Analyse a character sheet and return the best-guess TTRPG system.

    Returns a dict with::

        {
          "system_name":     str,   # detected system name, or "Unknown"
          "publisher":       str,   # publisher name, or ""
          "confidence":      float, # 0.0 – 1.0 relative confidence
          "evidence":        list,  # list of signals that fired
          "all_scores":      dict,  # {system_name: score} for debugging/UI
          "mechanic_profile": dict, # system-agnostic mechanical descriptors
                                    # safe to pass to AI without naming the system
        }

    The caller should store this on the character sheet so agents can use it.
    ``mechanic_profile`` describes observable mechanics (resolution die, stat model,
    resource tracks, genre) inferred from the player's own sheet data — not from any
    copyrighted rules text — so agents can tailor output without referencing a
    trademarked system name.
    """
    if not isinstance(sheet, dict):
        return _unknown_result()

    scored: List[tuple[int, str, List[str]]] = []
    for sig in SYSTEM_SIGNATURES:
        s, ev = _score_system(sig, sheet)
        scored.append((s, sig["name"], ev))

    scored.sort(key=lambda t: t[0], reverse=True)

    top_score, top_name, top_evidence = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0

    if top_score == 0:
        return _unknown_result()

    # Confidence: ratio of top score vs (top + second), capped at 1.0.
    # Using the sum of top two scores keeps the value relative to how much
    # stronger the winner is than its closest rival.
    max_score = max(top_score + second_score, 1)
    confidence = round(min(1.0, top_score / max_score), 3)

    matched_sig = next(
        (sig for sig in SYSTEM_SIGNATURES if sig["name"] == top_name),
        None,
    )
    publisher = matched_sig["publisher"] if matched_sig else ""
    mechanic_profile = matched_sig.get("mechanic_profile", {}) if matched_sig else {}

    return {
        "system_name": top_name,
        "publisher": publisher,
        "confidence": confidence,
        "evidence": top_evidence,
        "all_scores": {name: s for s, name, _ in scored},
        "mechanic_profile": mechanic_profile,
    }


def describe_mechanic_profile(sheet: Dict[str, Any]) -> str:
    """Return a concise, AI-safe plain-text description of the mechanical
    patterns observed on *sheet*, without naming any trademarked system.

    Example output::

        "d20-check resolution · six-ability-scores-with-modifiers stats · \
heroic-fantasy genre · key mechanics: proficiency-bonus, advantage-disadvantage"

    This string can be injected into LLM prompts so the model can tailor
    output to the character's mechanics without reproducing copyrighted rules.
    """
    result = infer_ttrpg_system(sheet)
    profile = result.get("mechanic_profile") or {}
    if not profile:
        return ""

    parts: List[str] = []
    if profile.get("resolution"):
        parts.append(f"{profile['resolution']} resolution")
    if profile.get("stat_model"):
        parts.append(f"{profile['stat_model']} stats")
    if profile.get("genre"):
        parts.append(f"{profile['genre']} genre")
    key_mechs = profile.get("key_mechanics") or []
    if key_mechs:
        parts.append("key mechanics: " + ", ".join(key_mechs))
    resources = profile.get("resources") or []
    if resources:
        parts.append("resources: " + ", ".join(resources))
    return " · ".join(parts)


def _unknown_result() -> Dict[str, Any]:
    return {
        "system_name": "Unknown",
        "publisher": "",
        "confidence": 0.0,
        "evidence": [],
        "all_scores": {sig["name"]: 0 for sig in SYSTEM_SIGNATURES},
        "mechanic_profile": {},
    }


def list_ttrpg_systems() -> List[Dict[str, str]]:
    """Return a list of all known TTRPG systems with name and publisher.

    Intended for use in UI dropdowns so players can manually specify which
    game system a PDF was created for.  Displaying these names in a
    selection list is purely referential (like a file-format selector) and
    does not reproduce any copyrighted rules content.
    """
    return [{"name": sig["name"], "publisher": sig["publisher"]} for sig in SYSTEM_SIGNATURES]


def override_ttrpg_system(detected: Dict[str, Any], system_name: str) -> Dict[str, Any]:
    """Return a copy of *detected* with system fields overridden by *system_name*.

    If *system_name* is not in the known registry the original dict is returned
    unchanged.  Confidence is set to 1.0 and ``"user-selected"`` is prepended
    to the evidence list so downstream code can tell it was a manual choice.
    """
    sig = _SYSTEMS_BY_NAME.get(system_name)
    if sig is None:
        return detected
    overridden = dict(detected)
    overridden["system_name"] = sig["name"]
    overridden["publisher"] = sig["publisher"]
    overridden["mechanic_profile"] = sig.get("mechanic_profile", {})
    overridden["confidence"] = 1.0
    overridden["evidence"] = ["user-selected"] + list(overridden.get("evidence") or [])
    return overridden
