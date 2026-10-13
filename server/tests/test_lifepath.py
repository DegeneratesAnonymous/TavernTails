"""Life-path builders: checked narratives, applying a backstory to a character, keeping it for one campaign."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db, steward_llm
from server.agents import lifepath
from server.auth import create_access_token

ENTRIES = [
    lifepath.Entry(stage="roots", answer="Raised in the Ashen Market", clause="was raised in the Ashen Market"),
    lifepath.Entry(stage="event", answer="Lost a mentor to the Salt Court", clause="lost a mentor to the Salt Court"),
    lifepath.Entry(stage="goals", answer="Find who burned the granary", clause="wants to find who burned the granary", source="typed"),
]
CONTEXT = lifepath.WorldContext(
    world_name="Saltmere", conflict="The granaries are burning and the Salt Court blames the market",
    factions=["Salt Court"], places=["Ashen Market"],
)


def _req(**kw) -> lifepath.NarrativeRequest:
    base = {
        "kind": "character", "name": "Mira", "entries": ENTRIES, "context": CONTEXT,
        "link": lifepath.Link(kind="faction", name="Salt Court"),
    }
    base.update(kw)
    return lifepath.NarrativeRequest(**base)


GOOD = (
    "Mira was raised in the Ashen Market, where everyone knew the price of grain.\n\n"
    "She lost a mentor to the Salt Court, and has not forgiven them. Now she wants to find who burned the granary."
)


def test_good_draft_passes():
    assert lifepath.check_narrative(GOOD, _req()) == []


def test_invented_name_is_caught():
    issues = lifepath.check_narrative(GOOD.replace("a mentor", "her mentor Old Brannock"), _req())
    assert any("Brannock" in i for i in issues)


def test_sentence_start_word_is_not_a_name():
    assert lifepath.invented_names("Years later, Mira left. Then she returned.", "Mira") == []


def test_question_and_missing_link_are_caught():
    issues = lifepath.check_narrative(GOOD.replace("the Salt Court", "them") + " Who knows?", _req())
    assert any("question" in i for i in issues)
    assert any("Salt Court" in i for i in issues)


def test_story_link_needs_no_mention():
    req = _req(link=lifepath.Link(kind="story"))
    assert lifepath.check_narrative(GOOD.replace("the Salt Court", "them"), req) == []


def test_draft_that_ignores_the_choices_is_caught():
    bland = "Mira is a person with a past.\n\nShe lives in the world and does things, as people do. It is all quite ordinary."
    assert any("choices" in i for i in lifepath.check_narrative(bland, _req(link=lifepath.Link(kind="story"))))


def test_template_is_used_when_model_fails_and_states_the_link():
    def boom(*a, **k):
        raise RuntimeError("down")

    out = lifepath.write_narrative(_req(), call=boom)
    assert out["source"] == "template"
    assert "Mira was raised in the Ashen Market" in out["narrative"]
    assert "Salt Court" in out["narrative"]
    assert lifepath.check_narrative(out["narrative"], _req()) == []


def test_bad_draft_is_retried_with_feedback_then_accepted():
    seen = []

    def fake(messages, **kw):
        seen.append(messages[-1]["content"])
        return "Who is Mira?" if len(seen) == 1 else GOOD

    out = lifepath.write_narrative(_req(), call=fake)
    assert out["source"] == "model" and out["narrative"] == GOOD
    assert "Do not ask questions" in seen[1]


def test_two_bad_drafts_fall_back_to_template():
    out = lifepath.write_narrative(_req(), call=lambda *a, **k: "Who is Mira?")
    assert out["source"] == "template" and out["issues"]


def test_first_person_typed_answer_becomes_third_person_in_template():
    entries = [lifepath.Entry(stage="goals", answer="I want to clear my name", source="typed")]
    text = lifepath.build_template(_req(entries=entries, link=None))
    assert "I want" not in text and "my name" not in text


# ---- applying to a character ------------------------------------------------

def test_add_keeps_existing_and_merges_lines():
    sheet = {"backstory": "Old tale.", "bonds": "My sister", "alignment": "Neutral", "stats": {"str": 10}}
    payload = lifepath.BackstoryPayload(
        backstory="New tale.", label="Saltmere", bonds="My sister\nThe market", alignment="Chaotic Good",
        allies=["Tam"], goals=[{"term": "long", "text": "Clear the market's name"}],
    )
    new, changes = lifepath.apply_backstory(sheet, payload, "add")
    assert new["backstory"] == "Old tale.\n\nSaltmere\nNew tale."
    assert new["bonds"] == "My sister\nThe market"
    assert new["alignment"] == "Neutral"  # add never replaces a filled field
    assert new["allies"] == ["Tam"] and new["goals"][0]["term"] == "long"
    assert new["stats"] == {"str": 10} and "backstory_history" not in new
    assert {c["field"] for c in changes} >= {"backstory", "bonds", "allies", "goals"}


def test_overwrite_replaces_and_can_be_undone():
    sheet = {"backstory": "Old tale.", "flaws": "Proud", "stats": {"str": 10}}
    payload = lifepath.BackstoryPayload(backstory="New tale.", flaws="Reckless")
    new, _ = lifepath.apply_backstory(sheet, payload, "overwrite")
    assert new["backstory"] == "New tale." and new["flaws"] == "Reckless"
    assert new["backstory_history"][-1]["values"]["backstory"] == "Old tale."
    restored = lifepath.undo_backstory(new)
    assert restored["backstory"] == "Old tale." and restored["flaws"] == "Proud"
    assert restored["backstory_history"] == [] and restored["stats"] == {"str": 10}


def test_overwrite_undo_removes_fields_that_were_new():
    new, _ = lifepath.apply_backstory({}, lifepath.BackstoryPayload(backstory="Tale.", alignment="Lawful Good"), "overwrite")
    restored = lifepath.undo_backstory(new)
    assert "backstory" not in restored and "alignment" not in restored


def test_nothing_to_undo():
    assert lifepath.undo_backstory({"backstory": "x"}) is None


def test_never_touches_mechanics():
    sheet = {"stats": {"str": 15}, "skills": ["stealth"], "languages": ["Common"], "hp": {"max": 9}}
    new, _ = lifepath.apply_backstory(sheet, lifepath.BackstoryPayload(backstory="Tale.", flaws="Proud"), "overwrite")
    for key in ("stats", "skills", "languages", "hp"):
        assert new[key] == sheet[key]


# ---- routes -------------------------------------------------------------------

def _user(email: str) -> db.User:
    existing = db.get_user_by_identifier(email)
    if existing:
        return existing
    user = db.create_user(email=email, password="secret", username=email.split("@")[0], profile={"name": email.split("@")[0]})
    db.verify_user(email, user.verification_token)
    return db.get_user_by_identifier(email)


def _auth(email: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(email)}"}


@pytest.fixture()
def owner():
    return _user("lifepath-owner@example.com")


def test_narrative_route_uses_template_without_a_model(monkeypatch, owner):
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: None)
    res = TestClient(main.app).post("/lifepath/narrative", json=_req().model_dump(), headers=_auth(owner.email))
    assert res.status_code == 200 and res.json()["source"] == "template"


def test_apply_route_previews_then_commits_and_undoes(owner):
    arin = db.create_character(owner_id=owner.id, name="Arin", level=1, class_name="Rogue", sheet={"backstory": "Old."})
    client = TestClient(main.app)
    body = {"mode": "overwrite", "backstory": {"backstory": "New."}, "commit": False}
    url = f"/lifepath/characters/{arin.id}/apply"
    res = client.post(url, json=body, headers=_auth(owner.email))
    assert res.json()["committed"] is False
    assert db.get_character_for_owner(arin.id, owner.id).sheet["backstory"] == "Old."
    body["commit"] = True
    assert client.post(url, json=body, headers=_auth(owner.email)).json()["committed"] is True
    assert db.get_character_for_owner(arin.id, owner.id).sheet["backstory"] == "New."
    assert client.post(f"/lifepath/characters/{arin.id}/undo", headers=_auth(owner.email)).status_code == 200
    assert db.get_character_for_owner(arin.id, owner.id).sheet["backstory"] == "Old."


def test_apply_route_refuses_someone_elses_character(owner):
    other = _user("lifepath-other@example.com")
    theirs = db.create_character(owner_id=other.id, name="Zed", level=1, class_name="Bard", sheet={})
    res = TestClient(main.app).post(
        f"/lifepath/characters/{theirs.id}/apply", json={"mode": "add", "backstory": {"backstory": "x"}, "commit": True},
        headers=_auth(owner.email),
    )
    assert res.status_code == 404


def test_campaign_only_keeps_the_sheet_untouched(owner):
    arin = db.create_character(owner_id=owner.id, name="Arin", level=1, class_name="Rogue", sheet={"backstory": "Old."})
    camp = db.create_campaign(owner_id=owner.id, name="Saltmere")
    res = TestClient(main.app).post(
        f"/lifepath/campaigns/{camp.id}/characters/{arin.id}", json={"backstory": "Campaign tale.", "goals": [{"text": "Find the arsonist"}]},
        headers=_auth(owner.email),
    )
    assert res.status_code == 200
    meta = db.get_campaign_by_id(camp.id).metadata_json
    assert meta["player_backstories"][0]["backstory"] == "Campaign tale."
    assert meta["player_backstories"][0]["goals"][0]["text"] == "Find the arsonist"
    assert db.get_character_for_owner(arin.id, owner.id).sheet["backstory"] == "Old."


# ---- saved worlds ------------------------------------------------------------

def test_saved_worlds_are_private_and_editable(owner):
    other = _user("lifepath-other2@example.com")
    client = TestClient(main.app)
    body = {"name": "Saltmere", "narrative": "A harbour under a salt court.", "context": {"world_name": "Saltmere"}, "answers": {"tone": {"picked": ["grim"]}}}
    made = client.post("/worlds", json=body, headers=_auth(owner.email))
    assert made.status_code == 201
    wid = made.json()["world"]["id"]
    assert client.get(f"/worlds/{wid}", headers=_auth(owner.email)).json()["world"]["answers"] == body["answers"]
    assert client.get(f"/worlds/{wid}", headers=_auth(other.email)).status_code == 404
    assert client.delete(f"/worlds/{wid}", headers=_auth(other.email)).status_code == 404
    body["narrative"] = "Changed."
    updated = client.put(f"/worlds/{wid}", json=body, headers=_auth(owner.email)).json()["world"]
    assert updated["narrative"] == "Changed." and updated["version"] == 2
    listed = client.get("/worlds", headers=_auth(owner.email)).json()["worlds"]
    assert any(w["id"] == wid and "narrative" not in w for w in listed)
    assert client.delete(f"/worlds/{wid}", headers=_auth(owner.email)).status_code == 200
    assert client.get(f"/worlds/{wid}", headers=_auth(owner.email)).status_code == 404


def test_saved_world_limit(monkeypatch):
    user = _user("lifepath-limit@example.com")
    monkeypatch.setattr(db, "MAX_SAVED_WORLDS", 1)
    client = TestClient(main.app)
    assert client.post("/worlds", json={"name": "One"}, headers=_auth(user.email)).status_code == 201
    assert client.post("/worlds", json={"name": "Two"}, headers=_auth(user.email)).status_code == 409
    for w in client.get("/worlds", headers=_auth(user.email)).json()["worlds"]:
        client.delete(f"/worlds/{w['id']}", headers=_auth(user.email))


def test_possessives_are_checked_by_name():
    assert lifepath.invented_names("She works beside Hale Orrin's office.", "Hale Orrin") == []
    assert lifepath.invented_names("She works beside Hale Orrin's office.", "Mira") == ["Hale", "Orrin"]


def test_invented_relatives_are_caught_unless_the_player_said_them():
    assert lifepath.invented_kin("She was raised by her grandmother.", "was raised by a grandparent") == ["grandmother"]
    assert lifepath.invented_kin("She was raised by her grandmother.", "my grandmother raised me") == []
    issues = lifepath.check_narrative(GOOD.replace("Mira was raised", "Her father taught her. Mira was raised"), _req())
    assert any("father" in i for i in issues)


def test_campaign_only_keeps_every_field_the_character_sheet_would_have_had(owner):
    arin = db.create_character(owner_id=owner.id, name="Arin", level=1, class_name="Rogue", sheet={})
    camp = db.create_campaign(owner_id=owner.id, name="Saltmere")
    res = TestClient(main.app).post(
        f"/lifepath/campaigns/{camp.id}/characters/{arin.id}",
        json={"backstory": "Tale.", "bonds": "My family", "flaws": "Proud\nReckless", "ideals": "Justice", "alignment": "Chaotic Good",
              "personality_traits": "Dry humour", "lifepath": {"label": "Saltmere"}},
        headers=_auth(owner.email),
    )
    assert res.status_code == 200
    entry = db.get_campaign_by_id(camp.id).metadata_json["player_backstories"][0]
    assert entry["fields"]["flaws"] == "Proud\nReckless" and entry["fields"]["alignment"] == "Chaotic Good"
    assert "Flaws: Proud; Reckless" in entry["backstory"] and entry["backstory"].startswith("Tale.")
    assert entry["lifepath"] == {"label": "Saltmere"}


def test_a_name_may_not_be_assembled_from_two_supplied_names():
    supplied = "Hale Orrin and Maren Vey"
    assert lifepath.invented_names("She met Hale Vey at the dock.", supplied) == ["Hale Vey"]
    assert lifepath.invented_names("She met Hale Orrin and Maren Vey at the dock.", supplied) == []
    assert lifepath.invented_names("She trusted Hale.", supplied) == []  # a short reference to a supplied name


def test_an_answer_in_another_script_must_appear_in_the_draft():
    entry = lifepath.Entry(stage="places", answer="灰の市場", clause="")
    req = _req(entries=[entry], link=lifepath.Link(kind="story"))
    assert any("choices" in i for i in lifepath.check_narrative("Mira grew up far from here.\n\nShe left young and never came back, and nothing more is known about it at all.", req))
    assert not any("choices" in i for i in lifepath.check_narrative("Mira grew up in 灰の市場 and left young, never looking back at all.\n\nShe returned only once.", req))


def test_first_person_words_inside_a_fallback_clause_are_made_third_person():
    entries = [lifepath.Entry(stage="goals", answer="x", clause="wants to find them because my sister vanished", source="typed")]
    text = lifepath.build_template(_req(entries=entries, link=None))
    assert "my sister" not in text and "their sister vanished" in text


def test_saving_two_characters_backstories_keeps_both(owner):
    a = db.create_character(owner_id=owner.id, name="A", level=1, class_name="Rogue", sheet={})
    b = db.create_character(owner_id=owner.id, name="B", level=1, class_name="Bard", sheet={})
    camp = db.create_campaign(owner_id=owner.id, name="Two")
    client = TestClient(main.app)
    for who, text in ((a, "A's tale."), (b, "B's tale.")):
        assert client.post(f"/lifepath/campaigns/{camp.id}/characters/{who.id}", json={"backstory": text}, headers=_auth(owner.email)).status_code == 200
    kept = db.get_campaign_by_id(camp.id).metadata_json["player_backstories"]
    assert sorted(e["character_name"] for e in kept) == ["A", "B"]
    client.post(f"/lifepath/campaigns/{camp.id}/characters/{a.id}", json={"backstory": "A again."}, headers=_auth(owner.email))
    kept = db.get_campaign_by_id(camp.id).metadata_json["player_backstories"]
    assert len(kept) == 2 and next(e for e in kept if e["character_name"] == "A")["backstory"] == "A again."


def test_the_players_own_note_is_never_lost_from_a_draft():
    req = _req(freeform="The bell in the tower never rang again")
    out = lifepath.write_narrative(req, call=lambda *a, **k: GOOD)
    assert out["source"] == "model" and "bell in the tower" in out["narrative"]
    mentioned = GOOD + "\n\nThe bell in the tower never rang again."
    assert lifepath.write_narrative(req, call=lambda *a, **k: mentioned)["narrative"] == mentioned  # not added twice
