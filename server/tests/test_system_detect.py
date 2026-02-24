"""Tests for TTRPG system detection from character sheet data."""
from server.agents.system_detect import SYSTEM_SIGNATURES, describe_mechanic_profile, infer_ttrpg_system

_KNOWN_SYSTEM_NAMES = {s["name"] for s in SYSTEM_SIGNATURES} | {"Unknown"}


def test_detect_dnd5e_from_class_name():
    sheet = {"class_name": "Wizard", "stats": {"str": 10, "dex": 14, "wis": 16}}
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "D&D 5e"
    assert result["confidence"] > 0


def test_detect_dnd5e_from_skills():
    sheet = {
        "class_name": "Fighter",
        "skills": [
            {"name": "Acrobatics", "modifier": 3},
            {"name": "Intimidation", "modifier": 2},
            {"name": "Perception", "modifier": 1},
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "D&D 5e"
    assert result["confidence"] > 0
    assert any("skill:acrobatics" in e for e in result["evidence"])


def test_detect_dnd5e_from_keyword_in_raw_text():
    sheet = {
        "class_name": "Paladin",
        "raw_text": "Adventurers League 5e character exported from D&D Beyond",
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "D&D 5e"
    assert any("keyword" in e for e in result["evidence"])


def test_detect_pathfinder2e_from_class_name():
    sheet = {"class_name": "Investigator"}
    result = infer_ttrpg_system(sheet)
    # Investigator is exclusively PF2e (not in D&D 5e)
    assert result["system_name"] == "Pathfinder 2e"


def test_detect_pathfinder2e_from_keywords():
    sheet = {
        "class_name": "Alchemist",
        "raw_text": "Pathfinder 2e character sheet — Age of Ashes campaign",
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Pathfinder 2e"


def test_detect_starfinder_from_class():
    sheet = {"class_name": "Operative"}
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Starfinder"


def test_detect_starfinder_from_skills():
    sheet = {
        "class_name": "Mechanic",
        "skills": [
            {"name": "Computers", "modifier": 8},
            {"name": "Engineering", "modifier": 6},
            {"name": "Piloting", "modifier": 5},
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Starfinder"


def test_detect_call_of_cthulhu_from_stats():
    sheet = {
        "class_name": "Private Investigator",
        "stats": {"str": 50, "dex": 60, "pow": 55, "edu": 75, "app": 60},
        "raw_text": "Call of Cthulhu 7th Edition investigator sheet",
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Call of Cthulhu"


def test_detect_star_trek_adventures():
    sheet = {
        "class_name": "Science",
        "stats": {"control": 9, "daring": 8, "fitness": 7, "insight": 10, "presence": 8, "reason": 11},
        "raw_text": "Star Trek Adventures — USS Pegasus crew manifest",
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Star Trek Adventures"


def test_detect_shadowrun_from_class_and_stats():
    sheet = {
        "class_name": "Street Samurai",
        "stats": {"body": 6, "agility": 8, "reaction": 5, "strength": 4, "logic": 3, "essence": 3.5},
        "raw_text": "Shadowrun 6th World — Sixth Edition runner sheet",
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Shadowrun"


def test_unknown_returns_gracefully():
    sheet = {"class_name": "Hero", "stats": {"power": 10}}
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] in _KNOWN_SYSTEM_NAMES
    assert "confidence" in result
    assert "evidence" in result
    assert "all_scores" in result


def test_all_scores_always_present():
    result = infer_ttrpg_system({})
    assert isinstance(result["all_scores"], dict)
    assert "D&D 5e" in result["all_scores"]


def test_detect_from_multiclass():
    sheet = {
        "class_name": "Fighter / Wizard",
        "multiclass": [
            {"class_name": "Fighter", "level": 5},
            {"class_name": "Wizard", "level": 2},
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "D&D 5e"


def test_detect_from_import_ddb_url():
    sheet = {
        "class_name": "Ranger",
        "import": {"source": "ddb-api", "ddb_url": "https://www.dndbeyond.com/characters/12345"},
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "D&D 5e"
    assert any("keyword:dndbeyond" in e or "keyword:d&d beyond" in e for e in result["evidence"])


# ---------------------------------------------------------------------------
# mechanic_profile tests — ensure AI-safe mechanical descriptors are returned
# without any trademarked system name needing to be inspected.
# ---------------------------------------------------------------------------

def test_every_signature_has_mechanic_profile():
    """All system signatures must declare a mechanic_profile."""
    for sig in SYSTEM_SIGNATURES:
        assert "mechanic_profile" in sig, f"{sig['name']} missing mechanic_profile"
        profile = sig["mechanic_profile"]
        assert "resolution" in profile, f"{sig['name']} mechanic_profile missing 'resolution'"
        assert "genre" in profile, f"{sig['name']} mechanic_profile missing 'genre'"


def test_infer_returns_mechanic_profile():
    """infer_ttrpg_system always includes a mechanic_profile key."""
    sheet = {"class_name": "Wizard", "stats": {"str": 10, "dex": 14, "wis": 16}}
    result = infer_ttrpg_system(sheet)
    assert "mechanic_profile" in result
    profile = result["mechanic_profile"]
    assert isinstance(profile, dict)
    assert profile.get("resolution") == "d20-check"
    assert profile.get("genre") == "heroic-fantasy"


def test_unknown_result_has_empty_mechanic_profile():
    """Unknown detection returns an empty mechanic_profile, not absent."""
    result = infer_ttrpg_system({})
    assert "mechanic_profile" in result
    assert result["mechanic_profile"] == {}


def test_mechanic_profile_does_not_contain_system_name():
    """mechanic_profile must not contain any trademarked system name."""
    trademarked = {s["name"].lower() for s in SYSTEM_SIGNATURES}
    for sig in SYSTEM_SIGNATURES:
        profile = sig.get("mechanic_profile", {})
        profile_text = " ".join(
            " ".join(v) if isinstance(v, list) else str(v)
            for v in profile.values()
            if isinstance(v, (str, list))
        )
        for tm in trademarked:
            assert tm not in profile_text.lower(), (
                f"{sig['name']} mechanic_profile contains trademarked name '{tm}'"
            )


def test_coc_mechanic_profile_uses_percentile():
    """Call of Cthulhu should report percentile resolution, not d20."""
    sheet = {
        "class_name": "Private Investigator",
        "stats": {"str": 50, "dex": 60, "pow": 55, "edu": 75},
        "raw_text": "Call of Cthulhu 7th Edition investigator sheet",
    }
    result = infer_ttrpg_system(sheet)
    assert result["mechanic_profile"].get("resolution") == "percentile-skill-check"


def test_shadowrun_mechanic_profile_uses_dice_pool():
    """Shadowrun should report dice-pool resolution."""
    sheet = {
        "class_name": "Street Samurai",
        "stats": {"body": 6, "agility": 8, "essence": 3.5},
        "raw_text": "Shadowrun 6th World runner sheet",
    }
    result = infer_ttrpg_system(sheet)
    assert result["mechanic_profile"].get("resolution") == "dice-pool-d6"


def test_describe_mechanic_profile_no_system_name():
    """describe_mechanic_profile output must not contain any trademarked name."""
    trademarked = {s["name"].lower() for s in SYSTEM_SIGNATURES}
    sheet = {"class_name": "Wizard", "stats": {"str": 10, "wis": 16}}
    description = describe_mechanic_profile(sheet)
    assert description  # non-empty for a detected sheet
    for tm in trademarked:
        assert tm not in description.lower(), f"description contains trademarked name '{tm}'"


def test_describe_mechanic_profile_empty_sheet():
    """describe_mechanic_profile returns empty string for an undetectable sheet."""
    description = describe_mechanic_profile({})
    assert description == ""


def test_describe_mechanic_profile_contains_resolution():
    """describe_mechanic_profile includes the resolution mechanism."""
    sheet = {"class_name": "Rogue", "stats": {"str": 10, "dex": 18, "cha": 14}}
    description = describe_mechanic_profile(sheet)
    assert "d20-check" in description
