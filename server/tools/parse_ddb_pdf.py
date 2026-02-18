"""
D&D Beyond character importer.

Primary path: import_from_ddb(url_or_id) — fetches live data from the DDB character service API.
Legacy path:  parse_ddb_pdf(path) — extracts character ID from the PDF filename then calls import_from_ddb.
"""
from __future__ import annotations

import math
import re
import urllib.request
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ParsedAbility:
    score: int = 10
    modifier: int = 0
    save_proficient: bool = False


@dataclass
class ParsedSkill:
    name: str = ""
    modifier: int = 0
    proficient: bool = False
    expertise: bool = False


@dataclass
class ParsedAttack:
    name: str = ""
    attack_bonus: int = 0
    damage: str = ""
    damage_type: str = ""
    properties: str = ""


@dataclass
class ParsedEquipment:
    name: str = ""
    quantity: int = 1
    weight: float = 0.0
    equipped: bool = False
    attuned: bool = False


@dataclass
class ParsedFeature:
    name: str = ""
    source: str = ""
    description: str = ""


@dataclass
class ParsedCharacterSheet:
    name: str = ""
    player_name: str = ""
    class_name: str = ""
    level: int = 1
    subclass: Optional[str] = None
    species: str = ""
    background: str = ""
    experience_points: int = 0
    initiative: int = 0
    armor_class: int = 10
    hp_max: int = 0
    hp_current: int = 0
    hp_temp: int = 0
    hit_dice: str = ""
    death_save_successes: int = 0
    death_save_failures: int = 0
    proficiency_bonus: int = 2
    ability_save_dc: Optional[int] = None
    heroic_inspiration: bool = False
    speed_walking: int = 30
    speed_flying: int = 0
    speed_swimming: int = 0
    speed_climbing: int = 0
    speed_burrowing: int = 0
    passive_perception: int = 10
    passive_insight: int = 10
    passive_investigation: int = 10
    abilities: dict = field(default_factory=dict)
    skills: list = field(default_factory=list)
    attacks: list = field(default_factory=list)
    equipment: list = field(default_factory=list)
    carrying_weight: float = 0.0
    carrying_capacity: float = 0.0
    features_and_traits: list = field(default_factory=list)
    languages: list = field(default_factory=list)
    tool_proficiencies: list = field(default_factory=list)
    armor_proficiencies: list = field(default_factory=list)
    weapon_proficiencies: list = field(default_factory=list)
    currencies: dict = field(default_factory=dict)
    multiclass: list = field(default_factory=list)
    story: dict = field(default_factory=dict)
    ddb_character_id: Optional[str] = None
    ddb_url: Optional[str] = None
    raw_additional_features: str = ""
    raw_additional_equipment: str = ""
    parse_warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_STAT_ID_MAP: Dict[int, str] = {1: "str", 2: "dex", 3: "con", 4: "int", 5: "wis", 6: "cha"}

_SKILL_ABILITY_MAP: Dict[str, str] = {
    "Acrobatics": "dex",
    "Animal Handling": "wis",
    "Arcana": "int",
    "Athletics": "str",
    "Deception": "cha",
    "History": "int",
    "Insight": "wis",
    "Intimidation": "cha",
    "Investigation": "int",
    "Medicine": "wis",
    "Nature": "int",
    "Perception": "wis",
    "Performance": "cha",
    "Persuasion": "cha",
    "Religion": "int",
    "Sleight of Hand": "dex",
    "Stealth": "dex",
    "Survival": "wis",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _modifier(score: int) -> int:
    return math.floor((score - 10) / 2)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fetch_ddb(character_id: str) -> Dict[str, Any]:
    url = f"https://character-service.dndbeyond.com/character/v5/character/{character_id}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (TavernTAIls/1.0)",
            "Accept": "application/json",
            "x-requested-with": "XMLHttpRequest",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read())
    except Exception as exc:
        raise RuntimeError(f"DDB API request failed: {exc}") from exc

    if not payload.get("success"):
        raise RuntimeError(f"DDB API returned success=false: {payload.get('message', 'unknown error')}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("DDB API response missing 'data' key")

    return data


# ---------------------------------------------------------------------------
# Field builders
# ---------------------------------------------------------------------------

def _build_abilities(data: Dict[str, Any]) -> Dict[str, ParsedAbility]:
    stats = {s["id"]: (s.get("value") or 10) for s in (data.get("stats") or []) if s.get("id")}
    bonus_stats = {s["id"]: (s.get("value") or 0) for s in (data.get("bonusStats") or []) if s.get("id")}
    override_stats = {s["id"]: s.get("value") for s in (data.get("overrideStats") or []) if s.get("id")}

    racial_bonuses: Dict[str, int] = {}
    for mod in (data.get("modifiers", {}).get("race", [])
                + data.get("modifiers", {}).get("feat", [])
                + data.get("modifiers", {}).get("background", [])):
        st = mod.get("subType", "")
        val = mod.get("value") or 0
        for ability in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"):
            if st == f"{ability}-score":
                short = ability[:3]
                racial_bonuses[short] = racial_bonuses.get(short, 0) + val

    abilities: Dict[str, ParsedAbility] = {}
    for stat_id, short in _STAT_ID_MAP.items():
        base = stats.get(stat_id, 10)
        bonus = bonus_stats.get(stat_id, 0) or 0
        override = override_stats.get(stat_id)
        racial = racial_bonuses.get(short, 0)
        score = override if override is not None else (base + (bonus or 0) + racial)
        abilities[short] = ParsedAbility(score=score, modifier=_modifier(score))

    return abilities


def _build_proficiency_bonus(total_level: int) -> int:
    return math.ceil(total_level / 4) + 1


def _build_classes(data: Dict[str, Any]) -> tuple[str, int, Optional[str], list, str]:
    classes = data.get("classes") or []
    if not classes:
        return "Unknown", 1, None, [], "1d8"

    names: list[str] = []
    total_level = 0
    subclass: Optional[str] = None
    multiclass: list[dict] = []
    primary_hit_die = "1d8"

    for cls in classes:
        definition = cls.get("definition") or {}
        subclass_def = cls.get("subclassDefinition")
        cname = definition.get("name") or "Unknown"
        clevel = cls.get("level") or 1
        hit_die = definition.get("hitDice") or 8
        is_starting = cls.get("isStartingClass", False)

        names.append(f"{cname} {clevel}")
        total_level += clevel
        multiclass.append({"class_name": cname, "level": clevel})

        if is_starting:
            primary_hit_die = f"1d{hit_die}"

        if subclass_def and subclass is None:
            subclass = subclass_def.get("name") or subclass_def.get("fullName")

    return " / ".join(names), total_level, subclass, multiclass, primary_hit_die


def _build_skills(
    data: Dict[str, Any],
    abilities: Dict[str, ParsedAbility],
    prof_bonus: int,
) -> List[ParsedSkill]:
    skill_prof: Dict[str, str] = {}

    all_mods: list = []
    for source in ("class", "race", "feat", "background", "item"):
        all_mods.extend(data.get("modifiers", {}).get(source, []))

    for mod in all_mods:
        if mod.get("type") not in ("proficiency", "expertise", "half-proficiency"):
            continue
        st = mod.get("subType", "") or ""
        skill_name_clean = st.replace("-", " ").title()
        if skill_name_clean in _SKILL_ABILITY_MAP:
            existing = skill_prof.get(skill_name_clean.lower())
            new_val = ("expertise" if mod["type"] == "expertise"
                       else ("half" if mod["type"] == "half-proficiency" else "proficient"))
            if existing != "expertise":
                skill_prof[skill_name_clean.lower()] = new_val

    skills: list[ParsedSkill] = []
    for skill_name, ability_key in _SKILL_ABILITY_MAP.items():
        ability = abilities.get(ability_key)
        base_mod = ability.modifier if ability else 0
        prof_state = skill_prof.get(skill_name.lower(), "none")

        if prof_state == "expertise":
            total_mod = base_mod + prof_bonus * 2
        elif prof_state == "proficient":
            total_mod = base_mod + prof_bonus
        elif prof_state == "half":
            total_mod = base_mod + math.floor(prof_bonus / 2)
        else:
            total_mod = base_mod

        skills.append(ParsedSkill(
            name=skill_name,
            modifier=total_mod,
            proficient=prof_state in ("proficient", "expertise"),
            expertise=prof_state == "expertise",
        ))

    return skills


def _build_features(data: Dict[str, Any], classes: list, total_level: int) -> List[ParsedFeature]:
    features: list[ParsedFeature] = []
    seen: set[str] = set()

    def _add(name: str, source: str, desc: str) -> None:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            features.append(ParsedFeature(name=name, source=source, description=_strip_html(desc)))

    for cls_entry in classes:
        definition = cls_entry.get("definition") or {}
        cls_name = definition.get("name") or "Unknown"
        cls_level = cls_entry.get("level") or 1
        subclass_def = cls_entry.get("subclassDefinition")
        subclass_name = subclass_def.get("name") if subclass_def else None

        for feat in definition.get("classFeatures") or []:
            feat_level = feat.get("requiredLevel") or feat.get("level") or 1
            if feat_level > cls_level:
                continue
            feat_name = feat.get("name") or ""
            if feat_name:
                _add(feat_name, cls_name, feat.get("description") or "")

        if subclass_def:
            for feat in subclass_def.get("classFeatures") or []:
                feat_level = feat.get("requiredLevel") or feat.get("level") or 1
                if feat_level > cls_level:
                    continue
                feat_name = feat.get("name") or ""
                if feat_name:
                    _add(feat_name, subclass_name or cls_name, feat.get("description") or "")

    bg = data.get("background") or {}
    bg_def = bg.get("definition") or {}
    bg_name = bg_def.get("name") or "Background"
    for feat in bg_def.get("featureItems") or []:
        feat_name = feat.get("name") or ""
        if feat_name:
            _add(feat_name, bg_name, feat.get("description") or "")

    race = data.get("race") or {}
    race_name = race.get("fullName") or race.get("baseRaceName") or "Species"
    for trait in race.get("racialTraits") or []:
        td = trait.get("definition") or {}
        feat_name = td.get("name") or ""
        if feat_name:
            _add(feat_name, race_name, td.get("description") or "")

    for feat_entry in data.get("feats") or []:
        feat_def = feat_entry.get("definition") or {}
        feat_name = feat_def.get("name") or ""
        if feat_name:
            _add(feat_name, "Feat", feat_def.get("description") or "")

    return features


def _build_equipment(data: Dict[str, Any]) -> List[ParsedEquipment]:
    items: list[ParsedEquipment] = []
    for inv in data.get("inventory") or []:
        defn = inv.get("definition") or {}
        items.append(ParsedEquipment(
            name=defn.get("name") or "Unknown Item",
            quantity=inv.get("quantity") or 1,
            weight=float(defn.get("weight") or 0.0),
            equipped=bool(inv.get("equipped")),
            attuned=bool(inv.get("isAttuned")),
        ))
    return items


def _build_languages(data: Dict[str, Any]) -> List[str]:
    languages: list[str] = []
    seen: set[str] = set()
    all_mods: list = []
    for source in ("race", "background", "class", "feat"):
        all_mods.extend(data.get("modifiers", {}).get(source, []))
    for mod in all_mods:
        if mod.get("type") == "language":
            lang = (mod.get("subType") or "").replace("-", " ").title()
            if lang and lang.lower() not in seen:
                seen.add(lang.lower())
                languages.append(lang)
    return sorted(languages)


def _build_proficiencies(data: Dict[str, Any]) -> tuple[list, list, list]:
    armor: list[str] = []
    weapons: list[str] = []
    tools: list[str] = []
    seen_a: set[str] = set()
    seen_w: set[str] = set()
    seen_t: set[str] = set()

    all_mods: list = []
    for source in ("race", "background", "class", "feat"):
        all_mods.extend(data.get("modifiers", {}).get(source, []))

    for mod in all_mods:
        if mod.get("type") != "proficiency":
            continue
        st = (mod.get("subType") or "").lower()
        friendly = st.replace("-", " ").title()

        if any(k in st for k in ("light-armor", "medium-armor", "heavy-armor", "shields", "armor")):
            if st not in seen_a:
                seen_a.add(st)
                armor.append(friendly)
        elif any(k in st for k in ("simple-weapons", "martial-weapons", "firearms", "weapon")):
            if st not in seen_w:
                seen_w.add(st)
                weapons.append(friendly)
        elif any(k in st for k in ("tools", "kit", "instrument", "vehicle")):
            if st not in seen_t:
                seen_t.add(st)
                tools.append(friendly)

    return sorted(armor), sorted(weapons), sorted(tools)


def _build_ac(data: Dict[str, Any], abilities: Dict[str, ParsedAbility]) -> int:
    override = data.get("overrideArmorClass")
    if override is not None:
        return int(override)
    dex_mod = abilities.get("dex", ParsedAbility()).modifier
    return 10 + dex_mod


def _build_speed(data: Dict[str, Any]) -> Dict[str, int]:
    override = data.get("overrideSpeed")
    if override is not None:
        return {"walk": int(override)}

    race = data.get("race") or {}
    speed_val = (race.get("weightSpeeds") or {}).get("normal", {}).get("walk") or 30
    speeds: Dict[str, int] = {"walk": int(speed_val)}

    for mod in data.get("modifiers", {}).get("race", []):
        if mod.get("type") == "set" and mod.get("subType") == "speed":
            speeds["walk"] = mod.get("value") or speeds["walk"]
        if mod.get("type") == "bonus" and "speed" in (mod.get("subType") or ""):
            speeds["walk"] = speeds.get("walk", 30) + (mod.get("value") or 0)
        if mod.get("subType") == "innate-speed-flying":
            speeds["fly"] = mod.get("value") or 0
        if mod.get("subType") == "innate-speed-swimming":
            speeds["swim"] = mod.get("value") or 0
        if mod.get("subType") == "innate-speed-climbing":
            speeds["climb"] = mod.get("value") or 0

    return speeds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def import_from_ddb(url_or_id: str) -> ParsedCharacterSheet:
    """
    Fetch a character from D&D Beyond and return a fully populated ParsedCharacterSheet.

    Args:
        url_or_id: A DDB character URL (https://www.dndbeyond.com/characters/12345678)
                   or just the numeric character ID.

    Returns:
        ParsedCharacterSheet with all fields populated from the DDB API.

    Raises:
        ValueError: if url_or_id contains no recognisable character ID.
        RuntimeError: if the DDB API call fails or returns an error.
    """
    url_or_id = url_or_id.strip()
    m = re.search(r"(\d{5,12})", url_or_id)
    if not m:
        raise ValueError(f"Could not extract a character ID from: {url_or_id!r}")
    character_id = m.group(1)

    data = _fetch_ddb(character_id)

    sheet = ParsedCharacterSheet()
    sheet.ddb_character_id = character_id
    sheet.ddb_url = f"https://www.dndbeyond.com/characters/{character_id}"

    sheet.name = data.get("name") or "Unknown"
    sheet.player_name = data.get("username") or ""
    sheet.experience_points = data.get("currentXp") or 0

    class_name, total_level, subclass, multiclass, hit_dice = _build_classes(data)
    sheet.class_name = class_name
    sheet.level = total_level
    sheet.subclass = subclass
    sheet.multiclass = multiclass
    sheet.hit_dice = hit_dice

    race = data.get("race") or {}
    sheet.species = race.get("fullName") or race.get("baseRaceName") or ""

    bg = data.get("background") or {}
    bg_def = bg.get("definition") or {}
    sheet.background = bg_def.get("name") or ""

    sheet.abilities = _build_abilities(data)
    sheet.proficiency_bonus = _build_proficiency_bonus(total_level)

    sheet.hp_max = data.get("baseHitPoints") or 0
    override_hp = data.get("overrideHitPoints")
    if override_hp is not None:
        sheet.hp_max = int(override_hp)
    sheet.hp_max += int(data.get("bonusHitPoints") or 0)
    sheet.hp_current = sheet.hp_max

    sheet.armor_class = _build_ac(data, sheet.abilities)
    dex_mod = sheet.abilities.get("dex", ParsedAbility()).modifier
    sheet.initiative = dex_mod + int(data.get("initiativeBonus") or 0)

    speeds = _build_speed(data)
    sheet.speed_walking = speeds.get("walk", 30)
    sheet.speed_flying = speeds.get("fly", 0)
    sheet.speed_swimming = speeds.get("swim", 0)
    sheet.speed_climbing = speeds.get("climb", 0)
    sheet.speed_burrowing = speeds.get("burrow", 0)

    classes_raw = data.get("classes") or []
    sheet.skills = _build_skills(data, sheet.abilities, sheet.proficiency_bonus)

    perception_skill = next((s for s in sheet.skills if s.name == "Perception"), None)
    insight_skill = next((s for s in sheet.skills if s.name == "Insight"), None)
    investigation_skill = next((s for s in sheet.skills if s.name == "Investigation"), None)
    sheet.passive_perception = 10 + (perception_skill.modifier if perception_skill
                                     else sheet.abilities.get("wis", ParsedAbility()).modifier)
    sheet.passive_insight = 10 + (insight_skill.modifier if insight_skill
                                  else sheet.abilities.get("wis", ParsedAbility()).modifier)
    sheet.passive_investigation = 10 + (investigation_skill.modifier if investigation_skill
                                        else sheet.abilities.get("int", ParsedAbility()).modifier)

    # Spellcasting save DC
    for mod in (data.get("modifiers") or {}).get("class", []):
        if mod.get("type") == "set" and mod.get("subType") == "spellcasting-ability":
            val = mod.get("value")
            if val:
                sa_key = _STAT_ID_MAP.get(val)
                if sa_key:
                    sa_mod = sheet.abilities.get(sa_key, ParsedAbility()).modifier
                    sheet.ability_save_dc = 8 + sheet.proficiency_bonus + sa_mod
                    break

    sheet.features_and_traits = _build_features(data, classes_raw, total_level)
    sheet.equipment = _build_equipment(data)
    sheet.languages = _build_languages(data)
    sheet.armor_proficiencies, sheet.weapon_proficiencies, sheet.tool_proficiencies = _build_proficiencies(data)

    currencies = data.get("currencies") or {}
    sheet.currencies = {
        "cp": currencies.get("cp", 0),
        "sp": currencies.get("sp", 0),
        "ep": currencies.get("ep", 0),
        "gp": currencies.get("gp", 0),
        "pp": currencies.get("pp", 0),
    }

    notes = data.get("notes") or {}
    sheet.story = {
        "backstory": data.get("backstory") or notes.get("backstory") or "",
        "personality_traits": notes.get("personalityTraits") or "",
        "ideals": notes.get("ideals") or "",
        "bonds": notes.get("bonds") or "",
        "flaws": notes.get("flaws") or "",
        "appearance": notes.get("appearance") or "",
    }

    sheet.heroic_inspiration = bool(data.get("inspiration") or data.get("heroicInspiration"))

    if not sheet.name or sheet.name == "Unknown":
        sheet.parse_warnings.append("Character name not found in API response")
    if sheet.hp_max == 0:
        sheet.parse_warnings.append("HP max is 0 — may need manual correction")
    if not sheet.abilities:
        sheet.parse_warnings.append("No ability scores found")

    return sheet


def parse_ddb_pdf(path: "str | Path") -> ParsedCharacterSheet:
    """
    Legacy entry point: extract a DDB character ID from a PDF filename and call import_from_ddb.

    The DDB PDF export filename typically contains the character ID, e.g.:
        spaceman_wil_91460971.pdf  ->  character ID 91460971

    Raises:
        FileNotFoundError: if the path does not exist.
        RuntimeError: if no numeric ID can be found in the filename, or the API call fails.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    m = re.search(r"(\d{5,12})", path.stem)
    if not m:
        raise RuntimeError(
            f"Could not find a DDB character ID in filename: {path.name!r}. "
            "Expected a filename like 'sheet_91460971.pdf'."
        )

    return import_from_ddb(m.group(1))

