"""Tests for system-agnostic NPC classes, abilities, and spells."""
from fastapi.testclient import TestClient

import server.main as main


def _client() -> TestClient:
    return TestClient(main.app)


def test_npc_classes_spells_roundtrip():
    """Classes, abilities, and spells are stored in the profile and returned."""
    client = _client()
    payload = {
        "name": "Zara the Arcane",
        "stats": {"initiative": 2, "hp": 40},
        "motivations": ["Seek forbidden knowledge"],
        "traits": {"faction": "Obsidian Circle"},
        "quirks": ["Speaks in riddles"],
        "classes": [
            {"name": "Wizard", "level": 7, "subclass": "School of Illusion"},
            {"name": "Scholar", "level": 2},
        ],
        "abilities": [
            {
                "name": "Arcane Recovery",
                "description": "Regain spell slots on a short rest.",
                "tags": ["passive", "magical"],
            },
        ],
        "spells": [
            {
                "name": "Fireball",
                "description": "A ball of fire that explodes in a 20-foot radius.",
                "tags": ["fire", "aoe", "attack"],
            },
            {
                "name": "Mirror Image",
                "description": "Creates three illusory duplicates.",
                "tags": ["illusion", "defensive"],
            },
        ],
    }

    resp = client.post("/npc/manage", json=payload)
    assert resp.status_code == 200, resp.text
    profile = resp.json()["npc_profile"]

    # Classes
    assert len(profile["classes"]) == 2
    assert profile["classes"][0]["name"] == "Wizard"
    assert profile["classes"][0]["level"] == 7
    assert profile["classes"][0]["subclass"] == "School of Illusion"
    assert profile["classes"][1]["name"] == "Scholar"
    assert profile["classes"][1]["level"] == 2

    # Abilities
    assert len(profile["abilities"]) == 1
    assert profile["abilities"][0]["name"] == "Arcane Recovery"
    assert "passive" in profile["abilities"][0]["tags"]

    # Spells
    assert len(profile["spells"]) == 2
    spell_names = {s["name"] for s in profile["spells"]}
    assert "Fireball" in spell_names
    assert "Mirror Image" in spell_names
    fireball = next(s for s in profile["spells"] if s["name"] == "Fireball")
    assert "fire" in fireball["tags"]
    assert "aoe" in fireball["tags"]


def test_npc_without_classes_spells_still_works():
    """Existing NPC payloads without classes/spells continue to work."""
    client = _client()
    payload = {
        "name": "Guard Bob",
        "stats": {"initiative": 1, "hp": 12},
        "motivations": ["Follow orders"],
        "traits": {},
        "quirks": [],
    }

    resp = client.post("/npc/manage", json=payload)
    assert resp.status_code == 200, resp.text
    profile = resp.json()["npc_profile"]
    assert profile["name"] == "Guard Bob"
    assert profile["classes"] == []
    assert profile["abilities"] == []
    assert profile["spells"] == []


def test_npc_classes_system_agnostic():
    """Classes work with non-D&D system names (system agnostic)."""
    client = _client()
    payload = {
        "name": "Vex",
        "stats": {},
        "motivations": [],
        "traits": {},
        "quirks": [],
        "classes": [
            {"name": "Street Samurai"},                          # Shadowrun
            {"name": "Investigator", "level": 3},               # Call of Cthulhu
            {"name": "Space Marine", "subclass": "Devastator"},  # Warhammer 40k
        ],
        "spells": [
            {"name": "Neural Hack", "tags": ["tech", "cyberpunk"]},  # non-magical ability
        ],
    }

    resp = client.post("/npc/manage", json=payload)
    assert resp.status_code == 200, resp.text
    profile = resp.json()["npc_profile"]
    class_names = [c["name"] for c in profile["classes"]]
    assert "Street Samurai" in class_names
    assert "Investigator" in class_names
    assert "Space Marine" in class_names
    assert profile["spells"][0]["name"] == "Neural Hack"
    assert "cyberpunk" in profile["spells"][0]["tags"]
