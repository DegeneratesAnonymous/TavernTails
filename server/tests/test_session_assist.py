"""Taking in a scene and acting on it: orientation, suggestions that give nothing away, recap, round status, safety."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db, steward_llm
from server.agents import session_assist as assist
from server.agents import sessions as sessions_module
from server.agents.scene_privacy import player_view
from server.agents.scene_view import build_scene_view
from server.agents.table_state import round_recap, with_table_safety
from server.auth import create_access_token

PROSE = (
    "The scent of wet ink hangs over the records room. Ada Reed leans over a desk, tracing a page that shifts under "
    "her fingers.\n\nA cart creaks somewhere in the lane outside. The patients' records rewrite themselves."
)
SCENE = {
    "id": "scene-1", "title": "Records", "location": "Grimward Asylum", "time_of_day": "day", "weather": "clear",
    "narrative_body": PROSE, "text": PROSE + "\n\nWhat does Arin do?", "player_prompt": "What does Arin do?",
    "visible_clues": ["What is behind the bricked-up ward?"],
    "scene_director_data": {
        "primary_npc": {"name": "Ada Reed (clerk)", "role": "clerk", "what_they_know": "the warden poisoned the well",
                        "what_they_want": "to sell the ledger"},
        "secondary_entities": [{"name": "Warden Corvin", "role": "warden"}],
        "hidden_pressure": "The warden's accomplice will burn the east archive tonight",
    },
    "session_storyboard": {"secret": "the sexton is the culprit"},
}


def _client() -> TestClient:
    return TestClient(main.app)


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
def table(tmp_path):
    """A session with an owner (Arin, a rogue) and a second player, a scene and a little story."""
    owner = _user("assist-owner@example.com")
    friend = _user("assist-friend@example.com")
    arin = db.create_character(owner_id=owner.id, name="Arin Quickstep", level=3, class_name="Rogue",
                               sheet={"backstory": "A courier who once carried a ledger across the border."})
    sid, meta = sessions_module.create_session_folder("Assist table", owner.email, owner_character_id=arin.id)
    folder = sessions_module.BASE / sid
    meta["members"].append({"email": friend.email, "character_id": None, "character_name": "Mox", "role": "member"})
    (folder / "meta.json").write_text(json.dumps(meta))
    (folder / "scene.json").write_text(json.dumps(SCENE))
    (folder / "story.json").write_text(json.dumps([
        {"type": "narration", "text": "Arin reached the gate at dawn. The porter let him in without a word."},
        {"type": "narration", "text": "A bell rang twice in the east wing. Nobody went to look."},
        {"type": "narration", "text": PROSE + "\n\nWhat does Arin do?"},
    ]))
    (folder / "npcs.json").write_text(json.dumps([{"name": "Ada Reed", "role": "clerk", "what_they_know": "the warden poisoned the well"}]))
    return {"sid": sid, "folder": folder, "owner": owner.email, "friend": friend.email, "client": _client()}


# --- the orientation summary ---------------------------------------------------------------------------------------

def test_scene_view_lists_only_people_the_story_has_named_and_the_open_question():
    view = build_scene_view(SCENE)
    assert view["place"] == "Grimward Asylum" and view["time_of_day"] == "day"
    names = [p["name"] for p in view["present"]]
    assert names == ["Ada Reed"]  # Warden Corvin is in the director's notes but nobody has met them
    assert view["present"][0]["role"] == "clerk" and "Ada Reed leans over a desk" in view["present"][0]["seen"]
    assert view["hook"] == "What is behind the bricked-up ward?"


def test_player_view_carries_the_summary_but_none_of_the_gm_notes():
    view = player_view(SCENE)
    assert view["scene_view"]["present"][0]["name"] == "Ada Reed"
    blob = json.dumps(view)
    assert "poisoned the well" not in blob and "sexton" not in blob and "east archive" not in blob


def test_party_route_no_longer_hands_the_table_the_npc_secrets(table):
    client = table["client"]
    got = client.get(f"/sessions/{table['sid']}/party", headers=_auth(table["friend"])).json()
    assert got["npcs"][0]["name"] == "Ada Reed"
    assert "what_they_know" not in json.dumps(got["npcs"])


# --- checking a suggestion ----------------------------------------------------------------------------------------

VISIBLE = assist.visible_text(player_view(SCENE), {"name": "Arin Quickstep", "class_name": "Rogue", "notes": "A courier."})
HIDDEN = assist.hidden_strings(SCENE)


@pytest.mark.parametrize("text, expected", [
    ("I ask Ada Reed what she has noticed about the records.", []),
    ("I look closely at the page Ada Reed is tracing.", []),
    ("Ask Ada Reed about the records.", "first person"),
    ("I ask Warden Corvin about the records.", "Warden"),
    ("I ask Ada about the well the warden poisoned.", "poisoned"),
    ("I go and burn the east archive before tonight.", "archive"),
    ("I look around and discover that the sexton is the culprit.", "sexton"),
    ("I search the records and find the truth.", "outcome"),
    ("I wait.", "Too short"),
])
def test_a_suggestion_must_use_only_what_the_player_has_seen(text, expected):
    issues = " ".join(assist.check_suggestion(text, visible=VISIBLE, hidden=HIDDEN))
    assert (expected.lower() in issues.lower()) if expected else not issues


def test_angles_rotate_and_skip_the_person_angle_when_nobody_is_present():
    view = player_view(SCENE)
    seen = {assist.pick_angle(None, view, "scene-1:a", ["x"] * n) for n in range(len(assist.ANGLES))}
    assert len(seen) == len(assist.ANGLES)
    empty = {"narrative_body": "Rain on stone.", "scene_view": {"present": []}}
    assert all(assist.pick_angle(None, empty, "s", ["x"] * n) != "person" for n in range(8))
    assert assist.pick_angle("bold", view, "s", []) == "bold"


def test_fallbacks_name_only_what_the_story_names():
    view = player_view(SCENE)
    assert assist.fallback_suggestion("person", view, {}) == "I ask Ada Reed what they have seen."
    assert "exits" in assist.fallback_suggestion("background", view, {"class_name": "Rogue"})
    for angle in assist.ANGLES:
        text = assist.fallback_suggestion(angle, view, {"class_name": "Wizard"})
        assert not assist.check_suggestion(text, visible=VISIBLE, hidden=HIDDEN), (angle, text)


# --- the suggest route ----------------------------------------------------------------------------------------------

def _suggest(table, who="owner", **body):
    return table["client"].post(f"/sessions/{table['sid']}/suggest-action", headers=_auth(table[who]), json=body)


def test_a_good_model_suggestion_is_returned(table, monkeypatch):
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: "I ask Ada Reed what she has noticed about the records.")
    body = _suggest(table).json()
    assert body["source"] == "model" and body["suggestion"].startswith("I ask Ada Reed")


def test_a_suggestion_that_leaks_is_replaced_by_a_safe_one(table, monkeypatch):
    calls = []

    def leak(messages, **kwargs):
        calls.append(messages)
        return "I ask Ada about the well the warden poisoned."

    monkeypatch.setattr(steward_llm, "chat_complete", leak)
    body = _suggest(table, angle="person").json()
    assert body["source"] == "fallback" and "poison" not in body["suggestion"].lower()
    assert len(calls) == 2 and "REJECTED" in calls[1][1]["content"]  # the model was told why and tried once more


def test_a_repeat_is_rejected_and_the_player_is_not_asked_twice_for_the_same_thing(table, monkeypatch):
    first = "I ask Ada Reed what she has noticed about the records."
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: first)
    body = _suggest(table, previous=[first]).json()
    assert body["source"] == "fallback" and body["suggestion"] != first


def test_the_model_is_never_shown_the_gm_notes(table, monkeypatch):
    seen = []
    monkeypatch.setattr(steward_llm, "chat_complete", lambda messages, **k: seen.append(json.dumps(messages)) or "I look closely at the page Ada Reed is tracing.")
    _suggest(table)
    assert seen and all(secret not in seen[0] for secret in ("poisoned", "sexton", "east archive", "Warden Corvin"))
    assert "Arin Quickstep" in seen[0] and "Rogue" in seen[0] and "courier" in seen[0]  # their own character is


def test_suggestions_need_a_ready_scene_and_a_member(table):
    (table["folder"] / "scene.json").write_text(json.dumps({"setup_pending": True, "text": "placeholder"}))
    assert _suggest(table).status_code == 409
    outsider = _user("assist-outsider@example.com")
    (table["folder"] / "scene.json").write_text(json.dumps(SCENE))
    assert table["client"].post(f"/sessions/{table['sid']}/suggest-action", headers=_auth(outsider.email), json={}).status_code in (401, 403, 404)


# --- what the character notices ----------------------------------------------------------------------------------------

def test_notice_is_made_once_per_scene_and_character_and_kept_inside_the_text(table, monkeypatch):
    calls = []
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: calls.append(1) or "You notice how Ada Reed keeps one hand flat on the page.")
    client, headers = table["client"], _auth(table["owner"])
    first = client.post(f"/sessions/{table['sid']}/notice", headers=headers).json()
    again = client.post(f"/sessions/{table['sid']}/notice", headers=headers).json()
    assert first["notice"].startswith("You notice") and again["cached"] and len(calls) == 1


def test_notice_rejects_invented_names_and_says_nothing_for_a_table_without_a_character(table, monkeypatch):
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: "You notice Governor Slade watching from the doorway.")
    assert table["client"].post(f"/sessions/{table['sid']}/notice", headers=_auth(table["owner"])).json()["notice"] == ""
    assert assist.generate_notice(player_view(SCENE), {"name": "the party"}, HIDDEN) == ""


# --- coming back ----------------------------------------------------------------------------------------------------------

def test_recap_gives_the_story_so_far_and_where_things_stand(table):
    recap = table["client"].get(f"/sessions/{table['sid']}/recap", headers=_auth(table["owner"])).json()
    assert recap["character"] == "Arin Quickstep" and recap["title"] == "Assist table"
    assert recap["previously"] == ["Arin reached the gate at dawn. The porter let him in without a word.",
                                   "A bell rang twice in the east wing. Nobody went to look."]  # not the scene on screen
    assert recap["open_question"] == "What is behind the bricked-up ward?"
    assert recap["present"][0]["name"] == "Ada Reed" and recap["last_played_at"]
    assert "poisoned" not in json.dumps(recap)


# --- the table ----------------------------------------------------------------------------------------------------------

def test_round_shows_who_has_acted_and_who_is_ready(table):
    owner = db.get_user_by_identifier(table["owner"])
    db.log_chat_message("I check the records.", session_id=table["sid"], sender_id=owner.id, sender_name="Arin", role="player")
    db.log_chat_message("The table paused.", session_id=table["sid"], sender_name="Table", role="system")
    (table["folder"] / "ready.json").write_text(json.dumps({table["owner"]: True}))
    status = table["client"].get(f"/sessions/{table['sid']}/round", headers=_auth(table["friend"])).json()
    by_name = {m["name"]: m for m in status["members"]}
    assert by_name["Arin Quickstep"]["acted"] and by_name["Arin Quickstep"]["ready"]
    assert not by_name["Mox"]["acted"] and not by_name["Mox"]["ready"]
    assert status["waiting_on"] == ["Mox"] and status["quiet"] == ["Mox"] and not status["all_ready"]
    assert status["paused"] is False and status["avoid"] == []


def test_round_recap_lists_what_the_table_did_and_rolled():
    class Msg:
        def __init__(self, who, text, role="player"):
            self.sender_name, self.message, self.role = who, text, role

    recap = round_recap([Msg("Arin", "I check the records."), Msg("Table", "paused", "system"), Msg("Mox", "I follow the cart.")],
                        [{"type": "roll", "roll": {"by": "Arin", "expression": "1d20", "total": 17}}])
    assert [a["by"] for a in recap["actions"]] == ["Arin", "Mox"]
    assert recap["rolls"] == [{"by": "Arin", "expression": "1d20", "total": 17}]


# --- safety -------------------------------------------------------------------------------------------------------------------

def _safety(table, who, **body):
    return table["client"].post(f"/sessions/{table['sid']}/table-safety", headers=_auth(table[who]), json=body)


def test_asking_the_story_to_leave_something_out_reaches_the_next_scene(table):
    assert _safety(table, "friend", kind="skip", topic="harm to children").json()["avoid"] == ["harm to children"]
    meta = json.loads((table["folder"] / "meta.json").read_text())
    contract = with_table_safety({"agent_output_contract": "Be kind.", "safety_policy": {"content_rating": "teen"}}, meta)
    assert contract["agent_output_contract"].startswith("TABLE SAFETY:") and "harm to children" in contract["agent_output_contract"]
    assert contract["safety_policy"]["table_avoid"] == ["harm to children"] and contract["safety_policy"]["content_rating"] == "teen"
    assert with_table_safety({"a": 1}, {}) == {"a": 1}
    posted = [m for m in db.list_chat_messages(session_id=table["sid"]) if m.role == "system"]
    assert any("asked the story to leave that out" in m.message for m in posted)


def test_any_player_can_pause_but_only_the_owner_can_resume_and_the_scene_waits(table):
    assert _safety(table, "friend", kind="pause").json()["paused"] is True
    assert table["client"].get(f"/sessions/{table['sid']}/round", headers=_auth(table["owner"])).json()["paused"] is True
    assert table["client"].post(f"/sessions/{table['sid']}/advance-scene", headers=_auth(table["owner"]), json={}).status_code == 409
    assert _safety(table, "friend", kind="resume").status_code == 403
    assert _safety(table, "owner", kind="resume").json()["paused"] is False
    assert _safety(table, "owner", kind="explode").status_code == 422
