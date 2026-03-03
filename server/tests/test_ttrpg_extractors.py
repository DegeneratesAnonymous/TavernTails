"""Unit tests for the 8 new TTRPG system field extractors.

Tests each extractor function directly (no HTTP overhead) using synthetic
widget key/value dicts that mirror what pypdf would produce from a real PDF.
"""

from __future__ import annotations

import pytest

from server.agents.characters import (
    _extract_alien_rpg_fields,
    _extract_coc_fields_from_widgets,
    _extract_dnd5e_fields_from_widgets,
    _extract_shadowrun_fields_from_widgets,
    _extract_sotdl_fields_from_widgets,
    _extract_starfinder_fields_from_widgets,
    _extract_wfrp_fields_from_widgets,
    _is_alien_rpg_sheet,
    _is_coc_sheet,
    _is_shadowrun_sheet,
    _is_sotdl_sheet,
    _is_wfrp_sheet,
)

# ---------------------------------------------------------------------------
# D&D 5e
# ---------------------------------------------------------------------------


class TestDnd5eExtractor:
    def _fields(self) -> dict[str, str]:
        return {
            "Race": "Half-Elf",
            "Alignment": "Chaotic Good",
            "Proficiency Bonus": "+3",
            "Initiative": "+2",
            "Inspiration": "Yes",
            "Hit Dice": "10d8",
            "Exhaustion Level": "1",
            "Death Save Successes": "2",
            "Death Save Failures": "1",
            # Saving throws
            "Str Save": "+5",
            "Str Save Prof": "True",
            "Dex Save": "+4",
            # Skills
            "Acrobatics": "+4",
            "Acrobatics Prof": "True",
            "Stealth": "+6",
            "Stealth Expertise": "True",
            # Spell slots
            "Spell Slots Total1": "4",
            "Spell Slots Total2": "3",
            "Spell Save DC": "15",
            "Spell Attack Bonus": "+7",
            # Currency
            "Gold": "150",
            "Silver": "20",
            # Class resources
            "Ki Points": "5",
            "Rage Uses": "3",
            # Equipment
            "Equipment 1": "Longsword",
            "Equipment 2": "Shield",
        }

    def test_basic_identity_fields(self):
        result = _extract_dnd5e_fields_from_widgets(self._fields())
        assert result["race"] == "Half-Elf"
        assert result["alignment"] == "Chaotic Good"
        assert result["proficiency_bonus"] == 3
        assert result["initiative"] == 2
        assert result["inspiration"] is True
        assert result["hit_dice"] == "10d8"
        assert result["exhaustion"] == 1

    def test_death_saves(self):
        result = _extract_dnd5e_fields_from_widgets(self._fields())
        assert result["death_saves"] == {"successes": 2, "failures": 1}

    def test_saving_throws(self):
        result = _extract_dnd5e_fields_from_widgets(self._fields())
        saves = result["saves"]
        assert saves["str"]["total"] == 5
        assert saves["str"]["proficient"] is True
        assert saves["dex"]["total"] == 4

    def test_skills(self):
        result = _extract_dnd5e_fields_from_widgets(self._fields())
        skills = result["skills"]
        assert skills["Acrobatics"]["modifier"] == 4
        assert skills["Acrobatics"]["proficient"] is True
        assert skills["Stealth"]["expertise"] is True

    def test_spell_slots(self):
        result = _extract_dnd5e_fields_from_widgets(self._fields())
        assert result["spell_slots"] == {"1": 4, "2": 3}
        assert result["spell_save_dc"] == 15
        assert result["spell_attack_bonus"] == 7

    def test_currency(self):
        result = _extract_dnd5e_fields_from_widgets(self._fields())
        assert result["currency"]["gp"] == 150
        assert result["currency"]["sp"] == 20

    def test_class_resources(self):
        result = _extract_dnd5e_fields_from_widgets(self._fields())
        assert result["class_resources"]["ki_points"] == 5
        assert result["class_resources"]["rage"] == 3

    def test_equipment(self):
        result = _extract_dnd5e_fields_from_widgets(self._fields())
        assert "Longsword" in result["equipment"]
        assert "Shield" in result["equipment"]

    def test_empty_fields_returns_empty(self):
        assert _extract_dnd5e_fields_from_widgets({}) == {}

    def test_none_values_ignored(self):
        fields = {"Race": "Human", "Alignment": ""}
        result = _extract_dnd5e_fields_from_widgets(fields)
        assert result["race"] == "Human"
        assert "alignment" not in result


# ---------------------------------------------------------------------------
# Call of Cthulhu
# ---------------------------------------------------------------------------


class TestCoCDetector:
    def test_detects_coc_sheet(self):
        widgets = {"POW": "60", "APP": "55", "SIZ": "50", "Sanity": "70", "Luck": "65"}
        assert _is_coc_sheet(widgets) is True

    def test_rejects_non_coc_sheet(self):
        widgets = {"Strength": "16", "Dexterity": "14", "Constitution": "12"}
        assert _is_coc_sheet(widgets) is False


class TestCoCExtractor:
    def _fields(self) -> dict[str, str]:
        return {
            "STR": "60",
            "CON": "55",
            "SIZ": "65",
            "DEX": "70",
            "APP": "50",
            "INT": "75",
            "POW": "65",
            "EDU": "80",
            "HP Max": "12",
            "HP Current": "10",
            "Magic Points": "13",
            "Sanity Current": "60",
            "Sanity Max": "65",
            "Starting Sanity": "65",
            "Luck": "55",
            "Dodge": "35",
            "Build": "+1",
            "Damage Bonus": "+1D4",
            "Move Rate": "8",
            "Age": "32",
            "Occupation": "Professor",
            "Background": "Studied at Miskatonic University",
            "Cash": "50",
            "library use": "65",
            "spot hidden": "55",
            "Weapon 1 Name": "Revolver",
            "Weapon 1 Skill": "45",
            "Weapon 1 Damage": "1D8+2",
        }

    def test_characteristics(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        chars = result["coc_characteristics"]
        assert chars["str"] == 60
        assert chars["edu"] == 80

    def test_hp(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        assert result["coc_hp"] == {"max": 12, "current": 10}

    def test_magic_points(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        assert result["coc_magic_points"] == 13

    def test_sanity(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        san = result["coc_sanity"]
        assert san["current"] == 60
        assert san["max"] == 65

    def test_luck(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        assert result["coc_luck"] == 55

    def test_derived_combat(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        assert result["coc_dodge"] == 35
        assert result["coc_build"] == "+1"
        assert result["coc_damage_bonus"] == "+1D4"
        assert result["coc_move"] == 8

    def test_occupation_and_background(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        assert result["coc_occupation"] == "Professor"
        assert "Miskatonic" in result["coc_background"]

    def test_skills(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        skills = result["coc_skills"]
        assert skills["library use"] == 65
        assert skills["spot hidden"] == 55

    def test_weapons(self):
        result = _extract_coc_fields_from_widgets(self._fields())
        weapons = result["coc_weapons"]
        assert len(weapons) == 1
        assert weapons[0]["name"] == "Revolver"
        assert weapons[0]["skill_pct"] == 45
        assert weapons[0]["damage"] == "1D8+2"

    def test_empty_returns_empty(self):
        assert _extract_coc_fields_from_widgets({}) == {}


# ---------------------------------------------------------------------------
# Starfinder
# ---------------------------------------------------------------------------


class TestStarfinderExtractor:
    def _fields(self) -> dict[str, str]:
        return {
            "Race": "Kasatha",
            "Theme": "Ace Pilot",
            "Homeworld": "Kasath",
            "Deity": "Iomedae",
            "Alignment": "Lawful Good",
            "SP Max": "20",
            "SP Current": "15",
            "RP Max": "5",
            "RP Current": "4",
            "KAC": "16",
            "EAC": "14",
            "Initiative": "+3",
            "Fortitude": "+4",
            "Reflex": "+6",
            "Will": "+2",
            "Acrobatics Total": "+7",
            "Piloting Total": "+9",
            "Feat 1": "Weapon Focus",
            "Class Feature 1": "Evasion",
            "Equipment 1": "Laser Pistol",
            "Current Bulk": "4",
            "Bulk Limit": "8",
            "Credits": "2500",
            "Cybernetics 1": "Dermal Plating",
        }

    def test_identity(self):
        result = _extract_starfinder_fields_from_widgets(self._fields())
        assert result["race"] == "Kasatha"
        assert result["starfinder_theme"] == "Ace Pilot"
        assert result["starfinder_homeworld"] == "Kasath"
        assert result["alignment"] == "Lawful Good"

    def test_stamina_and_resolve(self):
        result = _extract_starfinder_fields_from_widgets(self._fields())
        assert result["starfinder_stamina"] == {"max": 20, "current": 15}
        assert result["starfinder_resolve"] == {"max": 5, "current": 4}

    def test_armor_classes(self):
        result = _extract_starfinder_fields_from_widgets(self._fields())
        assert result["starfinder_kac"] == 16
        assert result["starfinder_eac"] == 14

    def test_saves(self):
        result = _extract_starfinder_fields_from_widgets(self._fields())
        assert result["saves"]["fort"] == 4
        assert result["saves"]["ref"] == 6
        assert result["saves"]["will"] == 2

    def test_skills(self):
        result = _extract_starfinder_fields_from_widgets(self._fields())
        assert result["skills"]["Acrobatics"]["total"] == 7
        assert result["skills"]["Piloting"]["total"] == 9

    def test_credits(self):
        result = _extract_starfinder_fields_from_widgets(self._fields())
        assert result["starfinder_credits"] == 2500

    def test_bulk(self):
        result = _extract_starfinder_fields_from_widgets(self._fields())
        assert result["bulk"] == {"current": 4, "limit": 8}

    def test_augmentations(self):
        result = _extract_starfinder_fields_from_widgets(self._fields())
        aug_names = [a["name"] for a in result["starfinder_augmentations"]]
        assert "Dermal Plating" in aug_names

    def test_empty_returns_empty(self):
        assert _extract_starfinder_fields_from_widgets({}) == {}


# ---------------------------------------------------------------------------
# Shadow of the Demon Lord
# ---------------------------------------------------------------------------


class TestSotDLDetector:
    def test_detects_sotdl(self):
        widgets = {
            "Strength": "11",
            "Agility": "10",
            "Intellect": "12",
            "Will": "13",
            "Corruption": "2",
        }
        assert _is_sotdl_sheet(widgets) is True

    def test_rejects_non_sotdl(self):
        widgets = {"Strength": "16", "Dexterity": "14"}
        assert _is_sotdl_sheet(widgets) is False


class TestSotDLExtractor:
    def _fields(self) -> dict[str, str]:
        return {
            "Strength": "11",
            "Agility": "10",
            "Intellect": "12",
            "Will": "13",
            "Health Max": "30",
            "Health Current": "22",
            "Defense": "13",
            "Healing Rate": "7",
            "Perception": "12",
            "Corruption": "3",
            "Insanity": "1",
            "Speed": "10",
            "Fortune": "2",
            "Novice Path": "Warrior",
            "Expert Path": "Fighter",
            "Race": "Human",
            "Talent 1": "Weapon Training",
            "Spell 1": "Fireball",
            "Equipment 1": "Sword",
            "Languages": "Common, Elvish",
            "Professions": "Soldier, Blacksmith",
            "Background": "Former mercenary",
        }

    def test_stats(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert result["stats"]["strength"] == 11
        assert result["stats"]["will"] == 13

    def test_hp(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert result["hp"]["max"] == 30
        assert result["hp"]["current"] == 22

    def test_defense(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert result["ac"] == 13

    def test_unique_fields(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert result["sotdl_healing_rate"] == 7
        assert result["sotdl_perception"] == 12
        assert result["sotdl_corruption"] == 3
        assert result["sotdl_insanity"] == 1
        assert result["sotdl_speed"] == 10
        assert result["sotdl_fortune_dice"] == 2

    def test_paths(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert result["sotdl_paths"]["novice"] == "Warrior"
        assert result["sotdl_paths"]["expert"] == "Fighter"

    def test_race(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert result["race"] == "Human"

    def test_talents_and_spells(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert "Weapon Training" in result["talents"]
        assert "Fireball" in result["spells"]

    def test_languages(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert "Common" in result["languages"]
        assert "Elvish" in result["languages"]

    def test_professions(self):
        result = _extract_sotdl_fields_from_widgets(self._fields())
        assert "Soldier" in result["sotdl_professions"]

    def test_empty_returns_empty(self):
        assert _extract_sotdl_fields_from_widgets({}) == {}


# ---------------------------------------------------------------------------
# Warhammer Fantasy Roleplay (WFRP 4e)
# ---------------------------------------------------------------------------


class TestWFRPDetector:
    def test_detects_wfrp(self):
        widgets = {"WS Total": "35", "BS Total": "30", "T Total": "40", "Agi Total": "45", "WP Total": "38"}
        assert _is_wfrp_sheet(widgets) is True

    def test_rejects_non_wfrp(self):
        widgets = {"Strength": "16", "Dexterity": "14"}
        assert _is_wfrp_sheet(widgets) is False


class TestWFRPExtractor:
    def _fields(self) -> dict[str, str]:
        return {
            "WS Total": "45",
            "WS Initial": "35",
            "WS Advances": "10",
            "BS Total": "30",
            "T Total": "40",
            "Agi Total": "42",
            "WP Total": "38",
            "Wounds Max": "12",
            "Wounds Current": "9",
            "Fate Points": "3",
            "Fortune Points": "2",
            "Resilience Points": "2",
            "Resolve Points": "1",
            "Corruption": "1",
            "XP Total": "1200",
            "XP Spent": "900",
            "Career Name": "Soldier",
            "Career Level": "2",
            "Career Status": "Sergeant",
            "Skill 1 Name": "Melee (Basic)",
            "Skill 1 Advances": "5",
            "Skill 1 Characteristic": "WS",
            "Talent 1": "Sturdy",
            "Armour Points": "5",
            "Trapping 1": "Plate Armor",
            "Short Term Ambition": "Survive the war",
            "Long Term Ambition": "Become a hero",
            "Species": "Human",
            "Movement": "4",
            "Gold Crowns": "10",
            "Silver Shillings": "5",
            "Spell 1": "Bolt",
        }

    def test_characteristics(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        chars = result["warhammer_characteristics"]
        assert chars["weapon_skill"]["total"] == 45
        assert chars["weapon_skill"]["initial"] == 35
        assert chars["weapon_skill"]["advances"] == 10

    def test_wounds(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        assert result["warhammer_wounds"] == {"max": 12, "current": 9}

    def test_fate_and_resilience(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        assert result["warhammer_fate"]["fate"] == 3
        assert result["warhammer_fate"]["fortune"] == 2
        assert result["warhammer_resilience"]["resilience"] == 2
        assert result["warhammer_resilience"]["resolve"] == 1

    def test_corruption_and_xp(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        assert result["warhammer_corruption"] == 1
        assert result["warhammer_experience"]["total"] == 1200
        assert result["warhammer_experience"]["spent"] == 900

    def test_career(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        assert result["warhammer_career"]["name"] == "Soldier"
        assert result["warhammer_career"]["level"] == 2
        assert result["class_name"] == "Soldier"

    def test_skills(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        skills = result["warhammer_skills"]
        assert any(s["name"] == "Melee (Basic)" for s in skills)

    def test_talents_trappings_ambitions(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        assert "Sturdy" in result["warhammer_talents"]
        assert "Plate Armor" in result["warhammer_trappings"]
        assert result["warhammer_ambitions"]["short"] == "Survive the war"
        assert result["warhammer_ambitions"]["long"] == "Become a hero"

    def test_species_and_movement(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        assert result["warhammer_species"] == "Human"
        assert result["warhammer_movement"] == 4

    def test_money(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        assert result["warhammer_money"]["gc"] == 10
        assert result["warhammer_money"]["ss"] == 5

    def test_spells(self):
        result = _extract_wfrp_fields_from_widgets(self._fields())
        assert "Bolt" in result["warhammer_spells"]

    def test_empty_returns_empty(self):
        assert _extract_wfrp_fields_from_widgets({}) == {}


# ---------------------------------------------------------------------------
# Alien RPG
# ---------------------------------------------------------------------------


class TestAlienRPGDetector:
    def test_detects_alien_rpg(self):
        widgets = {"Wits": "3", "Empathy": "2", "Comtech": "2", "Stress": "1", "Agenda": "Survive"}
        assert _is_alien_rpg_sheet(widgets) is True

    def test_rejects_non_alien(self):
        widgets = {"Strength": "16", "Dexterity": "14", "Intelligence": "12"}
        assert _is_alien_rpg_sheet(widgets) is False


class TestAlienRPGExtractor:
    def _fields(self) -> dict[str, str]:
        return {
            "Strength": "4",
            "Agility": "3",
            "Wits": "2",
            "Empathy": "3",
            "Heavy Machinery": "2",
            "Close Combat": "1",
            "Ranged Combat": "2",
            "Comtech": "3",
            "Health Max": "4",
            "Health Current": "3",
            "Stress": "2",
            "Armor Rating": "2",
            "Radiation": "1",
            "Encumbrance Current": "3",
            "Encumbrance Max": "7",
            "Pride": "My crew is my family",
            "Dark Secret": "I left someone behind",
            "Career": "Colonial Marshal",
            "Agenda": "Find the truth",
            "Buddy": "Jones",
            "Rival": "Burke",
            "Appearance": "Tall, weathered face",
            "Experience": "5",
            "Gear 1": "M41A Pulse Rifle",
            "Critical Injury 1": "Broken Arm",
        }

    def test_attributes(self):
        result = _extract_alien_rpg_fields(self._fields())
        assert result["alien_attributes"]["strength"] == 4
        assert result["alien_attributes"]["empathy"] == 3

    def test_skills(self):
        result = _extract_alien_rpg_fields(self._fields())
        assert result["alien_skills"]["comtech"] == 3
        assert result["alien_skills"]["ranged_combat"] == 2

    def test_health_and_stress(self):
        result = _extract_alien_rpg_fields(self._fields())
        assert result["alien_health"]["max"] == 4
        assert result["alien_health"]["current"] == 3
        assert result["alien_stress"]["current"] == 2

    def test_armor_and_radiation(self):
        result = _extract_alien_rpg_fields(self._fields())
        assert result["alien_armor"] == 2
        assert result["alien_radiation"] == 1

    def test_encumbrance(self):
        result = _extract_alien_rpg_fields(self._fields())
        assert result["alien_encumbrance"] == {"current": 3, "max": 7}

    def test_traits(self):
        result = _extract_alien_rpg_fields(self._fields())
        assert result["alien_pride"] == "My crew is my family"
        assert "left someone behind" in result["alien_dark_secret"]

    def test_identity(self):
        result = _extract_alien_rpg_fields(self._fields())
        assert result["career"] == "Colonial Marshal"
        assert result["agenda"] == "Find the truth"
        assert result["alien_buddy"] == "Jones"
        assert result["alien_rival"] == "Burke"

    def test_gear_and_injuries(self):
        result = _extract_alien_rpg_fields(self._fields())
        assert "M41A Pulse Rifle" in result["alien_gear"]
        assert "Broken Arm" in result["alien_critical_injuries"]

    def test_empty_returns_empty(self):
        assert _extract_alien_rpg_fields({}) == {}


# ---------------------------------------------------------------------------
# Shadowrun 6e
# ---------------------------------------------------------------------------


class TestShadowrunDetector:
    def test_detects_shadowrun(self):
        widgets = {
            "BOD": "4", "AGI": "5", "REA": "3",
            "STR": "3", "WIL": "4", "LOG": "6",
        }
        assert _is_shadowrun_sheet(widgets) is True

    def test_rejects_too_few_attributes(self):
        widgets = {"BOD": "4", "AGI": "5", "REA": "3"}
        assert _is_shadowrun_sheet(widgets) is False


class TestShadowrunExtractor:
    def _fields(self) -> dict[str, str]:
        return {
            "BOD": "4",
            "AGI": "5",
            "REA": "3",
            "STR": "3",
            "WIL": "4",
            "LOG": "6",
            "INT": "4",
            "CHA": "3",
            "EDG": "2",
            "MAG": "0",
            "Metatype": "Elf",
            "Essence": "5.5",
            "Phys Monitor Max": "10",
            "Phys Damage": "2",
            "Stun Monitor Max": "11",
            "Stun Damage": "0",
            "Skill 1 Name": "Firearms",
            "Skill 1 Rating": "6",
            "Skill 1 Specialization": "Pistols",
            "Positive Quality 1": "Ambidextrous",
            "Negative Quality 1": "Addiction (mild)",
            "Cyberware 1": "Datajack",
            "Nuyen": "15000",
            "Lifestyle": "Middle",
            "Contact 1 Name": "Fixer",
            "Contact 1 Loyalty": "3",
            "Contact 1 Connection": "4",
            "Attack": "5",
            "Sleaze": "6",
            "Data Processing": "7",
            "Firewall": "8",
            "Total Karma": "200",
            "Current Karma": "15",
            "Armor": "12",
            "Initiative Base": "7",
            "Initiative Dice": "1",
            "Knowledge Skill 2 Name": "Corporate Politics",
            "Knowledge Skill 2 Rating": "4",
            "Adept Power 1": "Killing Hands",
        }

    def test_attributes(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        attrs = result["shadowrun_attributes"]
        assert attrs["BOD"] == 4
        assert attrs["AGI"] == 5
        assert attrs["LOG"] == 6

    def test_metatype_and_essence(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        assert result["shadowrun_metatype"] == "Elf"
        assert result["shadowrun_essence"] == 5.5

    def test_condition_monitor(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        cm = result["shadowrun_condition_monitor"]
        assert cm["physical"]["max"] == 10
        assert cm["physical"]["damage"] == 2
        assert cm["stun"]["max"] == 11

    def test_skills(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        skills = result["shadowrun_skills"]
        firearm = next(s for s in skills if s["name"] == "Firearms")
        assert firearm["rating"] == 6
        assert firearm["specialization"] == "Pistols"

    def test_qualities(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        quals = result["shadowrun_qualities"]
        assert "Ambidextrous" in quals["positive"]
        assert any("Addiction" in q for q in quals["negative"])

    def test_cyberware(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        assert "Datajack" in result["shadowrun_cyberware"]

    def test_nuyen(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        assert result["shadowrun_nuyen"] == 15000

    def test_lifestyle(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        assert result["shadowrun_lifestyle"] == "Middle"

    def test_contacts(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        contacts = result["shadowrun_contacts"]
        fixer = next(c for c in contacts if c["name"] == "Fixer")
        assert fixer["loyalty"] == 3
        assert fixer["connection"] == 4

    def test_matrix(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        matrix = result["shadowrun_matrix"]
        assert matrix["attack"] == 5
        assert matrix["sleaze"] == 6
        assert matrix["data_processing"] == 7
        assert matrix["firewall"] == 8

    def test_karma(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        assert result["shadowrun_karma"]["total"] == 200
        assert result["shadowrun_karma"]["current"] == 15

    def test_initiative(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        init = result["shadowrun_initiative"]
        assert init["base"] == 7
        assert init["dice"] == 1

    def test_knowledge_skills(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        ks = result["shadowrun_knowledge_skills"]
        assert any(k["name"] == "Corporate Politics" for k in ks)

    def test_adept_powers(self):
        result = _extract_shadowrun_fields_from_widgets(self._fields())
        assert "Killing Hands" in result["shadowrun_adept_powers"]

    def test_nuyen_cap_prevents_garbage(self):
        """Values over 10M should be excluded."""
        fields = {"BOD": "4", "AGI": "5", "REA": "3", "STR": "3", "WIL": "4", "LOG": "6", "Nuyen": "99999999"}
        result = _extract_shadowrun_fields_from_widgets(fields)
        assert "shadowrun_nuyen" not in result

    def test_essence_bounds_check(self):
        """Essence outside 0–6 range should be excluded."""
        fields_valid = {"Essence": "5.5"}
        fields_zero = {"Essence": "0.0"}
        fields_over = {"Essence": "7.0"}
        assert _extract_shadowrun_fields_from_widgets(fields_valid).get("shadowrun_essence") == 5.5
        assert "shadowrun_essence" not in _extract_shadowrun_fields_from_widgets(fields_zero)
        assert "shadowrun_essence" not in _extract_shadowrun_fields_from_widgets(fields_over)

    def test_empty_returns_empty(self):
        assert _extract_shadowrun_fields_from_widgets({}) == {}
