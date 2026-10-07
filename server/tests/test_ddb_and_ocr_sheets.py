"""D&D Beyond exports are read exactly from their fields; scans are read by the model and verified."""
from __future__ import annotations

import json

from server.agents import ddb_sheet, ocr_sheet

DDB = {
    "CharacterName": "Olomar", "CLASS  LEVEL": "Wizard 5", "RACE": "Verdan", "BACKGROUND": "Urchin",
    "EXPERIENCE POINTS": "(Milestone)",
    "STR": "12", "STRmod": "+1", "INT": "19", "INTmod": "+4",
    "ST Strength": "+1", "ST Dexterity": "+2", "ST Constitution": "+1", "IntProf": "•", "ST Intelligence": "+7",
    "WisProf": "•", "ST Wisdom": "+3", "ST Charisma": "-1",
    "Acrobatics": "+2", "Animal": "+0", "ArcanaProf": "P", "Arcana": "+7", "SleightOfHandProf": "P",
    "SleightofHand": "+5", "StealthProf": "E", "Stealth": "+8",
    "Passive1": "10", "Passive2": "13", "Passive3": "14", "Init": "+2", "Total": "5d6",
    "ProficienciesLang": "=== WEAPONS ===\nSimple Weapons\n\n=== TOOLS ===\nDisguise Kit, Thieves' Tools\n\n"
                         "=== LANGUAGES ===\nCommon, Goblin, Orc",
    "Wpn Name": "Fire Bolt", "Wpn1 AtkBonus": "+7", "Wpn1 Damage": "2d10 Fire", "Wpn Notes 1": "V/S",
    "Wpn Name 2": "Unarmed Strike", "Wpn2 AtkBonus": "+4", "Wpn2 Damage": "2 Bludgeoning",
    "FeaturesTraits1": "=== WIZARD FEATURES ===\n\n* Arcane Recovery • PHB-2024 166\nYou can recover spell slots.\n\n"
                       "  | 1 / Long Rest • Special\n\n* Wizard Subclass • PHB-2024 167\n\n  | Evoker\n\n"
                       "=== VERDAN SPECIES TRAITS ===\n\n* Persuasive • AI 74\nYou have proficiency in Persuasion.\n\n"
                       "=== FEATS ===\n\n* Spell Sniper • PHB-2024 208",
    "FeaturesTraits3": "Bypass Cover. Your spells ignore Half Cover.",
    "SIZE": "Medium", "HEIGHT": "3'6", "EYES": "Yellow",
    "spellCastingAbility0": "INT", "spellSaveDC0": "15", "spellAtkBonus0": "+7", "spellCastingClass0": "Wizard",
    "spellHeader0": "=== CANTRIPS ===", "spellSlotHeader0": "(At Will)",
    "spellPrepared0": "O", "spellName0": "Fire Bolt", "spellSource0": "Wizard", "spellSaveHit0": "+7",
    "spellDuration0": "Instantaneous",
    "spellHeader1": "=== 1st LEVEL ===", "spellSlotHeader1": "4 Slots OOOO",
    "spellPrepared1": "O", "spellName1": "Unseen Servant [R]", "spellSource1": "Wizard", "spellDuration1": "1 hour",
    "spellName2": "Magic Missile", "spellSource2": "Wizard", "spellName3": "Magic Missile", "spellSource3": "Evocation Savant",
    "spellHeader2": "=== 2nd LEVEL ===", "spellSlotHeader2": "3 Slots OOO",
    "spellName4": "Invisibility", "spellSource4": "Wizard", "spellDuration4": "Concentration, up to 1 hour",
}


def test_ddb_extract_reads_proficiency_senses_and_spellcasting_exactly():
    out = ddb_sheet.extract(DDB)
    assert {k for k, v in out["saves"].items() if v["proficient"]} == {"int", "wis"}
    skills = {s["name"]: s for s in out["skills"]}
    assert len(skills) == 18 and skills["Sleight of Hand"]["modifier"] == 5 and skills["Animal Handling"]["modifier"] == 0
    assert skills["Arcana"]["proficient"] and not skills["Arcana"]["expertise"]
    assert skills["Stealth"]["proficient"] and skills["Stealth"]["expertise"]
    assert not skills["Acrobatics"]["proficient"]
    assert out["passives"] == {"perception": 10, "insight": 13, "investigation": 14}
    assert (out["initiative"], out["hit_dice"]) == (2, "5d6")
    assert out["languages"] == ["Common", "Goblin", "Orc"]
    assert out["weapon_proficiencies"] == ["Simple Weapons"] and out["tool_proficiencies"] == ["Disguise Kit", "Thieves' Tools"]
    assert (out["spellcasting_ability"], out["spell_save_dc"], out["spell_attack_bonus"]) == ("INT", 15, 7)
    assert out["spell_slots"] == {"1": 4, "2": 3}
    assert out["attacks"][0] == {"name": "Fire Bolt", "attack_bonus": "+7", "damage": "2d10 Fire", "notes": "V/S",
                                 "description": "+7 to hit, 2d10 Fire, V/S"}
    assert out["appearance_details"] == {"size": "Medium", "height": "3'6", "eyes": "Yellow"}


def test_ddb_spellbook_has_levels_rituals_concentration_and_duplicates_from_other_sources():
    out = ddb_sheet.extract(DDB)
    levels = {s["name"]: s["level"] for s in out["spellbook"]}
    assert levels == {"Fire Bolt": 0, "Unseen Servant": 1, "Magic Missile": 1, "Invisibility": 2}
    assert [s["source"] for s in out["spellbook"] if s["name"] == "Magic Missile"] == ["Wizard", "Evocation Savant"]
    assert next(s for s in out["spellbook"] if s["name"] == "Unseen Servant")["ritual"]
    assert next(s for s in out["spellbook"] if s["name"] == "Invisibility")["concentration"]
    assert out["spells"] == ["Fire Bolt", "Unseen Servant", "Magic Missile", "Invisibility"]


def test_ddb_features_are_split_by_section_with_text_and_usage():
    out = ddb_sheet.extract(DDB)
    assert [f["name"] for f in out["classFeatures"]] == ["Arcane Recovery", "Wizard Subclass"]
    assert out["classFeatures"][0]["description"] == "You can recover spell slots."
    assert out["classFeatures"][0]["usage"] == ["1 / Long Rest • Special"]
    assert out["subclass"] == "Evoker"
    assert [f["name"] for f in out["racialFeatures"]] == ["Persuasive"]
    assert [f["name"] for f in out["otherFeatures"]] == ["Spell Sniper"]
    assert "Bypass Cover" in out["otherFeatures"][0]["description"]  # the overflow column continues the last feature


def test_ddb_extract_ignores_other_pdfs():
    assert ddb_sheet.extract({"CharacterName": "Seraphine", "Race ": "Elf"}) == {}
    assert ddb_sheet.extract({}) == {}


# --- OCR ---------------------------------------------------------------------------------------------

def _tsv(words: list[tuple[int, int, str]]) -> str:
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [f"5\t1\t1\t1\t1\t{i}\t{left}\t{top}\t60\t30\t90\t{text}" for i, (left, top, text) in enumerate(words)]
    return "\n".join([header, *rows])


def test_layout_text_keeps_values_on_their_label_line_and_columns_apart():
    text = ocr_sheet.layout_text(_tsv([(100, 100, "+7"), (160, 102, "Arcana"), (700, 98, "INT"), (100, 200, "+0"), (160, 201, "Medicine")]))
    first, second = text.splitlines()
    assert first.split() == ["+7", "Arcana", "INT"] and "  " in first.strip()
    assert second.split() == ["+0", "Medicine"]


SHEET_TEXT = """\
Wizard 5                    CLASS & LEVEL
   ARMOR     Max HP
     12        27
 INITIATIVE          +2
   STRENGTH          +1 Strength
   DEXTERITY
      14
 INTELLIGENCE
      19
   +7 Arcana INT
   A  Deception CHA
 10  PASSIVE PERCEPTION
 PROFICIENCY BONUS   +7 Arcana
        (At Will)
 Fire Bolt   Wizard
 Mage Hand   Wizard
   1st LEVEL     4 Slots OOOO
 Shield      Wizard
 Unseen Servant [R]  Wizard
   nd LEVEL      3 Slots OOO
 Misty Step  Wizard
   WEAPON ATTACKS & CANTRIPS
 Fire Bolt   +7   2d10 Fire
 Unarmed Strike  +4  2 Bludgeoning
"""


def test_verify_keeps_only_values_found_beside_their_own_label():
    claimed = {
        "name": "Olomar Vance", "class_name": "Wizard", "level": 5, "hp_max": 27, "ac": 12,
        "initiative": 0, "proficiency_bonus": 7, "stats": {"str": 10, "dex": 14, "int": 19},
        "passives": {"perception": 10, "insight": 13},
        "skills": [{"name": "Arcana", "modifier": 7}, {"name": "Deception", "modifier": 0}],
    }
    kept, dropped = ocr_sheet.verify(claimed, SHEET_TEXT)
    assert kept["level"] == 5 and kept["hp_max"] == 27 and kept["ac"] == 12
    assert kept["stats"] == {"dex": 14, "int": 19}  # 10 is a different field's number; STR's own box was lost
    assert kept["passives"] == {"perception": 10}
    assert kept["skills"] == [{"name": "Arcana", "modifier": 7}]  # Deception's number is not on its line
    assert "initiative" in dropped and "proficiency_bonus" in dropped and "name" in dropped
    assert "initiative" not in kept and "proficiency_bonus" not in kept and "name" not in kept


def test_spell_levels_and_slots_come_from_table_headings_not_the_model():
    claimed = {"spells": [{"name": "Fire Bolt", "level": 9}, {"name": "Unseen Servant [R]", "level": 3},
                          {"name": "Misty Step", "level": 1}, {"name": "Unarmed Strike", "level": 1}, {"name": "Invented Spell", "level": 1}]}
    kept, _ = ocr_sheet.verify(claimed, SHEET_TEXT)
    assert kept["spells"] == [{"name": "Fire Bolt", "level": 0}, {"name": "Unseen Servant", "level": 1}, {"name": "Misty Step", "level": 2}]
    assert kept["spell_slots"] == {"1": 4, "2": 3}


def test_attack_values_must_appear_in_the_text():
    kept, _ = ocr_sheet.verify({"attacks": [{"name": "Fire Bolt", "attack_bonus": "+7", "damage": "2d10 Fire"},
                                            {"name": "Fire Bolt", "attack_bonus": "+9", "damage": "9d9 Radiant"}]}, SHEET_TEXT)
    assert kept["attacks"][0] == {"name": "Fire Bolt", "attack_bonus": "+7", "damage": "2d10 Fire"}
    assert kept["attacks"][1]["attack_bonus"] is None and kept["attacks"][1]["damage"] is None


def test_extract_retries_an_empty_reply_and_merges_pages():
    replies = iter([None, json.dumps({"level": 5}), json.dumps({"hp_max": 27})])
    calls = []

    def fake(messages, **_):
        calls.append(messages)
        return next(replies)

    page = "Wizard 5    CLASS & LEVEL\n" + ("filler line\n" * 5)
    second = "Max HP\n 27\n" + ("filler line\n" * 5)
    original = ocr_sheet.MAX_TEXT
    try:
        ocr_sheet.MAX_TEXT = len(page) + 5
        fields, _ = ocr_sheet.extract(page + "\n\n" + second, llm=fake)
    finally:
        ocr_sheet.MAX_TEXT = original
    assert len(calls) == 3  # one retry after the empty reply, then the second page
    assert fields["level"] == 5 and fields["hp_max"] == 27


def test_extract_returns_nothing_when_the_model_does():
    assert ocr_sheet.extract("some text", llm=lambda *a, **k: None) == ({}, [])
    assert ocr_sheet.extract("   ", llm=lambda *a, **k: "{}") == ({}, [])
