"""Tests for entity_schemas and entity-lookup / association endpoints."""
import json

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import sessions as sessions_module
from server.agents.entity_schemas import (
    AttitudeRank,
    EntityAssociation,
    GMLocationDocument,
    GMNPCDocument,
    GMQuestDocument,
    PlayerEntityCard,
    QuestStage,
    SessionNoteEntry,
)
from server.auth import create_access_token


def _client():
    return TestClient(main.app)


def _ensure_user(email: str) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(email=email, password="secret", username=email.split("@")[0], profile={"name": email.split("@")[0], "email": email})
    db.verify_user(email, user.verification_token)


# ---------------------------------------------------------------------------
# Schema unit tests
# ---------------------------------------------------------------------------


def test_gm_npc_document_minimal():
    """GMNPCDocument requires only name; all other fields have defaults."""
    npc = GMNPCDocument(name="Warlord Vrak")
    assert npc.name == "Warlord Vrak"
    assert npc.factions == []
    assert npc.motivations == []
    assert npc.attitude == []
    assert npc.secrets == []
    assert npc.classes == []
    assert npc.gear == []
    assert npc.appearance == ""
    assert npc.backstory == ""
    assert npc.linked_locations == []
    assert npc.linked_quests == []


def test_gm_npc_document_full():
    """GMNPCDocument serialises and round-trips all canonical fields."""
    npc = GMNPCDocument(
        name="Warlord Vrak",
        factions=["The Iron Fist", "Shadow Council"],
        motivations=["conquer the northern provinces", "avenge his fallen brother"],
        personality="Cold, calculating, speaks in measured tones. Never raises his voice.",
        attitude=[
            AttitudeRank(target="party", rank="hostile", notes="they killed his lieutenant"),
            AttitudeRank(target="The Iron Fist", rank="love"),
        ],
        secrets=["actually a reformed paladin", "the Shadow Council controls him"],
        classes=[{"name": "Fighter", "level": 10}, {"name": "Warlord", "level": 5}],
        gear=["Vorpal greatsword", "Black plate armour", "Signet ring of The Iron Fist"],
        appearance="Tall, heavily scarred across the left cheek. Always in black armour.",
        backstory="Born in the slums of Dur'Khal, rose through brutal combat.",
        linked_locations=["The Black Keep", "Iron Fist Fortress"],
        linked_quests=["Siege of Shadows", "The Traitor's Price"],
    )
    data = npc.model_dump()
    assert data["name"] == "Warlord Vrak"
    assert len(data["factions"]) == 2
    assert len(data["attitude"]) == 2
    assert data["attitude"][0]["rank"] == "hostile"
    assert data["attitude"][1]["rank"] == "love"
    # Round-trip
    npc2 = GMNPCDocument(**data)
    assert npc2.name == npc.name
    assert npc2.attitude[0].rank == "hostile"


def test_gm_location_document():
    """GMLocationDocument captures all fields needed to recall a location."""
    loc = GMLocationDocument(
        name="The Black Keep",
        location_type="stronghold",
        region="Northern Wastes",
        description="A massive obsidian fortress atop a frozen peak.",
        hidden_areas=["Sub-level dungeon", "Secret treasury"],
        traps_hazards=["Portcullis trap at main gate"],
        true_history="Built by the dwarves of Dur'Khal 400 years ago.",
        secrets=["Contains a portal to the Shadow Realm"],
        known_to_players="A dark keep visible on the horizon.",
        notable_shops=["Armorer (ground floor)"],
        contacts=["Warlord Vrak"],
        linked_npcs=["Warlord Vrak"],
        linked_quests=["Siege of Shadows"],
        connected_locations=["Iron Fist Fortress", "Frozen Pass"],
    )
    data = loc.model_dump()
    assert data["name"] == "The Black Keep"
    assert "Sub-level dungeon" in data["hidden_areas"]
    assert data["linked_npcs"] == ["Warlord Vrak"]


def test_gm_quest_document():
    """GMQuestDocument captures all fields needed to recall a quest."""
    quest = GMQuestDocument(
        title="Siege of Shadows",
        giver="Council of Five",
        quest_type="main",
        objective="Defeat Warlord Vrak and end the siege of Dur'Khal.",
        stakes="If the party fails, Dur'Khal falls within the week.",
        secrets=["Warlord Vrak is secretly working against the Shadow Council"],
        stages=[
            QuestStage(title="Infiltrate the Keep", description="Get past the outer wall.", completed=True),
            QuestStage(title="Confront Vrak", description="Reach the throne room."),
        ],
        complications=["An ally may betray the party", "The keep contains civilians"],
        rewards=["500gp", "Deed to the Frozen Pass"],
        linked_npcs=["Warlord Vrak", "Council Elder Mira"],
        linked_locations=["The Black Keep"],
    )
    data = quest.model_dump()
    assert data["title"] == "Siege of Shadows"
    assert data["stages"][0]["completed"] is True
    assert data["stages"][1]["completed"] is False
    assert "Warlord Vrak" in data["linked_npcs"]


def test_session_note_entry():
    """SessionNoteEntry answers What/Where/Why/When/What-changed/What-stayed-same."""
    note = SessionNoteEntry(
        what="The party defeated the keep's outer guard.",
        where="The Black Keep — outer courtyard",
        why="Guard alerted by a tripped alarm rune.",
        when="Start of scene 4, after the long rest.",
        what_changed=["Outer courtyard is now clear", "Party alerted the keep"],
        what_stayed_same=["Warlord Vrak is unaware", "The inner gate remains locked"],
        linked_entities=["Warlord Vrak", "The Black Keep"],
    )
    assert note.what.startswith("The party")
    assert len(note.what_changed) == 2
    assert len(note.what_stayed_same) == 2
    assert "Warlord Vrak" in note.linked_entities


def test_entity_association():
    """EntityAssociation links two entities with a typed relationship."""
    assoc = EntityAssociation(
        entity_a="Warlord Vrak",
        entity_a_type="npc",
        entity_b="The Black Keep",
        entity_b_type="location",
        relationship="Warlord Vrak commands The Black Keep",
    )
    data = assoc.model_dump()
    assert data["entity_a_type"] == "npc"
    assert data["entity_b_type"] == "location"


def test_player_entity_card():
    """PlayerEntityCard contains only player-safe info."""
    card = PlayerEntityCard(
        name="Warlord Vrak",
        entity_type="npc",
        summary="Tall figure in black armour. Spoke in cold, measured tones.",
        appearance="Tall, scarred on the left cheek.",
        relationship_notes="Attacked the party on sight.",
        attitude_toward_party="hostile",
        known_associations=["Seen at The Black Keep"],
    )
    # Confirm no GM-secret fields exist on the card
    data = card.model_dump()
    assert "backstory" not in data
    assert "secrets" not in data
    assert "motivations" not in data
    assert data["attitude_toward_party"] == "hostile"


# ---------------------------------------------------------------------------
# API integration tests — associations + entity-lookup endpoint
# ---------------------------------------------------------------------------


def _make_session(owner: str) -> str:
    sid, _ = sessions_module.create_session_folder(f"Entity Test {owner}", owner)
    return sid


def test_add_and_list_associations():
    """POST /sessions/{id}/entities/associate and GET /sessions/{id}/entities/associations."""
    client = _client()
    owner = "entity-assoc-owner@example.com"
    _ensure_user(owner)
    sid = _make_session(owner)
    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    # Create an NPC ↔ Location association
    resp = client.post(
        f"/sessions/{sid}/entities/associate",
        headers=headers,
        json={
            "entity_a": "Warlord Vrak",
            "entity_a_type": "npc",
            "entity_b": "The Black Keep",
            "entity_b_type": "location",
            "relationship": "Warlord Vrak commands The Black Keep",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["association"]["entity_a"] == "Warlord Vrak"

    # List should include it
    resp = client.get(f"/sessions/{sid}/entities/associations", headers=headers)
    assert resp.status_code == 200, resp.text
    assocs = resp.json()["associations"]
    assert len(assocs) == 1
    assert assocs[0]["entity_b"] == "The Black Keep"


def test_association_upsert():
    """Posting the same pair twice replaces rather than duplicates."""
    client = _client()
    owner = "entity-upsert-owner@example.com"
    _ensure_user(owner)
    sid = _make_session(owner)
    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    base = {
        "entity_a": "Mira",
        "entity_a_type": "npc",
        "entity_b": "Council Hall",
        "entity_b_type": "location",
        "relationship": "first version",
    }
    client.post(f"/sessions/{sid}/entities/associate", headers=headers, json=base)
    base["relationship"] = "updated version"
    client.post(f"/sessions/{sid}/entities/associate", headers=headers, json=base)

    resp = client.get(f"/sessions/{sid}/entities/associations", headers=headers)
    assocs = resp.json()["associations"]
    assert len(assocs) == 1
    assert assocs[0]["relationship"] == "updated version"


def test_entity_card_lookup_from_npcs_json():
    """GET /sessions/{id}/entity/{name} resolves an NPC from npcs.json using the canonical schema."""
    client = _client()
    owner = "entity-lookup-owner@example.com"
    _ensure_user(owner)
    sid = _make_session(owner)
    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed npcs.json with the canonical schema produced by the updated manage_npc endpoint
    # (appearance is a top-level field, personality replaces the old quirks-as-personality pattern).
    npcs_path = sessions_module.BASE / sid / "npcs.json"
    npcs_path.write_text(json.dumps([{
        "name": "Warlord Vrak",
        "appearance": "Tall figure in black armour, scarred face.",
        "personality": "Cold and calculating.",
        "factions": ["The Iron Fist"],
        "motivations": ["conquer the north"],
        "secrets": ["actually a reformed paladin"],
        "stats": {},
        "quirks": ["Speaks in riddles"],
        "classes": [],
        "abilities": [],
        "spells": [],
        "gear": [],
        "backstory": "Born in the slums of Dur'Khal.",
        "traits": {},
    }]))

    resp = client.get(f"/sessions/{sid}/entity/Warlord Vrak", headers=headers)
    assert resp.status_code == 200, resp.text
    card = resp.json()
    assert card["name"] == "Warlord Vrak"
    assert card["entity_type"] == "npc"
    # Must NOT expose GM-only fields
    assert "motivations" not in card
    assert "secrets" not in card
    assert "backstory" not in card
    # Appearance comes from the canonical top-level field → always in card['appearance']
    assert "black armour" in card["appearance"]


def test_entity_card_lookup_from_npcs_json_legacy_traits_compat():
    """GET /sessions/{id}/entity/{name} falls back to traits['appearance'] for older profiles."""
    client = _client()
    owner = "entity-legacy-owner@example.com"
    _ensure_user(owner)
    sid = _make_session(owner)
    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed with the OLD schema shape (appearance buried in traits dict, no top-level appearance)
    npcs_path = sessions_module.BASE / sid / "npcs.json"
    npcs_path.write_text(json.dumps([{
        "name": "Old NPC",
        "traits": {"appearance": "Weathered and grey."},
        "motivations": ["survive"],
        "stats": {},
        "quirks": [],
        "classes": [],
        "abilities": [],
        "spells": [],
    }]))

    resp = client.get(f"/sessions/{sid}/entity/Old NPC", headers=headers)
    assert resp.status_code == 200, resp.text
    card = resp.json()
    assert card["entity_type"] == "npc"
    # Appearance comes from the traits fallback → still lands in card['appearance']
    assert "Weathered" in card["appearance"]


def test_entity_card_lookup_from_player_document():
    """GET /sessions/{id}/entity/{name} resolves a location from player_location docs."""
    client = _client()
    owner = "entity-loc-owner@example.com"
    _ensure_user(owner)
    sid = _make_session(owner)
    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    # Create a player_location document via the documents API
    doc_resp = client.post(
        f"/documents/{sid}",
        headers=headers,
        json={
            "name": "The Black Keep",
            "content": "A dark fortress on a frozen peak. The outer courtyard has been cleared.",
            "category": "player_location",
        },
    )
    assert doc_resp.status_code == 201, doc_resp.text

    resp = client.get(f"/sessions/{sid}/entity/The Black Keep", headers=headers)
    assert resp.status_code == 200, resp.text
    card = resp.json()
    assert card["entity_type"] == "location"
    assert "frozen peak" in card["summary"]


def test_entity_card_not_found():
    """GET /sessions/{id}/entity/{name} returns 404 for unknown entities."""
    client = _client()
    owner = "entity-notfound-owner@example.com"
    _ensure_user(owner)
    sid = _make_session(owner)
    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/sessions/{sid}/entity/UnknownEntity", headers=headers)
    assert resp.status_code == 404, resp.text


def test_entity_lookup_non_member_forbidden():
    """Non-members receive 403 from all entity endpoints."""
    client = _client()
    owner = "entity-rbac-owner@example.com"
    stranger = "entity-rbac-stranger@example.com"
    _ensure_user(owner)
    _ensure_user(stranger)
    sid = _make_session(owner)
    stranger_token = create_access_token(stranger)
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}

    assert client.get(f"/sessions/{sid}/entity/SomeName", headers=stranger_headers).status_code == 403
    assert client.get(f"/sessions/{sid}/entities/associations", headers=stranger_headers).status_code == 403
    assert client.post(
        f"/sessions/{sid}/entities/associate",
        headers=stranger_headers,
        json={"entity_a": "A", "entity_a_type": "npc", "entity_b": "B", "entity_b_type": "location"},
    ).status_code == 403


# ---------------------------------------------------------------------------
# Session init creates associations.json
# ---------------------------------------------------------------------------


def test_session_init_creates_associations_file():
    """create_session_folder must initialize associations.json as an empty list."""
    sid, _ = sessions_module.create_session_folder("Assoc Init Test", "assoc-init-owner@example.com")
    assoc_path = sessions_module.BASE / sid / "associations.json"
    assert assoc_path.exists(), "associations.json was not created during session init"
    assert json.loads(assoc_path.read_text()) == []


# ---------------------------------------------------------------------------
# NPCManageRequest canonical field alignment
# ---------------------------------------------------------------------------


def test_manage_npc_canonical_fields_stored_in_profile():
    """POST /npc/manage persists all canonical GMNPCDocument fields at the top level."""
    client = _client()
    resp = client.post("/npc/manage", json={
        "name": "Elder Mirra",
        "factions": ["Council of Five"],
        "motivations": ["protect the city"],
        "personality": "Warm but firm. Never breaks eye contact.",
        "attitude": [{"target": "party", "rank": "like", "notes": "grateful for past help"}],
        "secrets": ["knows the location of the lost vault"],
        "gear": ["Staff of Verdancy", "Council signet ring"],
        "appearance": "Elderly woman with silver-streaked hair and keen amber eyes.",
        "backstory": "Former adventurer who retired to city council after the Great War.",
        "quirks": ["Always speaks in a whisper when stressed"],
        "classes": [{"name": "Wizard", "level": 8}],
        "stats": {"initiative": 2},
    })
    assert resp.status_code == 200, resp.text
    profile = resp.json()["npc_profile"]

    # Canonical fields at top level
    assert profile["factions"] == ["Council of Five"]
    assert profile["personality"] == "Warm but firm. Never breaks eye contact."
    assert profile["secrets"] == ["knows the location of the lost vault"]
    assert profile["gear"] == ["Staff of Verdancy", "Council signet ring"]
    assert profile["appearance"] == "Elderly woman with silver-streaked hair and keen amber eyes."
    assert profile["backstory"] == "Former adventurer who retired to city council after the Great War."

    # Attitude is serialised
    assert len(profile["attitude"]) == 1
    assert profile["attitude"][0]["rank"] == "like"
    assert profile["attitude"][0]["target"] == "party"

    # Backward-compat fields still present
    assert "quirks" in profile
    assert "classes" in profile


def test_manage_npc_appearance_top_level_wins_over_traits():
    """When both top-level 'appearance' and traits['appearance'] are supplied,
    the top-level field wins."""
    client = _client()
    resp = client.post("/npc/manage", json={
        "name": "Dual Appearance NPC",
        "appearance": "Canonical appearance text.",
        "traits": {"appearance": "Old traits bag appearance."},
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["npc_profile"]["appearance"] == "Canonical appearance text."


def test_manage_npc_traits_appearance_fallback():
    """When top-level 'appearance' is empty, traits['appearance'] is used as fallback."""
    client = _client()
    resp = client.post("/npc/manage", json={
        "name": "Legacy NPC",
        "traits": {"appearance": "Fallback from traits."},
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["npc_profile"]["appearance"] == "Fallback from traits."
