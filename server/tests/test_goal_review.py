"""Goals during play: shared with the table, suggested from the story with a real quote, changed only by their player."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db, steward_llm
from server.agents import goal_review as gr
from server.agents import sessions as sessions_module
from server.auth import create_access_token

STORY = [
    {"type": "narration", "text": "Mira found the oil-stained sill behind the Ashen Market and knew the granary fire was no accident."},
    {"type": "narration", "text": "Tam paid the last coin of the ferry debt and watched the boat slip away."},
]


def _user(email):
    existing = db.get_user_by_identifier(email)
    if existing:
        return existing
    user = db.create_user(email=email, password="secret", username=email.split("@")[0], profile={"name": email.split("@")[0]})
    db.verify_user(email, user.verification_token)
    return db.get_user_by_identifier(email)


def _auth(email):
    return {"Authorization": f"Bearer {create_access_token(email)}"}


@pytest.fixture()
def table():
    owner, friend = _user("goals-owner@example.com"), _user("goals-friend@example.com")
    mira = db.create_character(owner_id=owner.id, name="Mira", level=1, class_name="Rogue", sheet={
        "goals": [{"term": "long", "text": "find who burned the granary"}, {"term": "short", "text": "ask around the market"}],
    })
    tam = db.create_character(owner_id=friend.id, name="Tam", level=1, class_name="Bard", sheet={
        "goals": [{"term": "long", "text": "repay the ferry debt"}],
    })
    sid, meta = sessions_module.create_session_folder("Goals table", owner.email, owner_character_id=mira.id)
    folder = sessions_module.BASE / sid
    meta["members"].append({"email": friend.email, "character_id": tam.id, "character_name": "Tam", "role": "member"})
    (folder / "meta.json").write_text(json.dumps(meta))
    (folder / "story.json").write_text(json.dumps(STORY))
    return {"sid": sid, "owner": owner, "friend": friend, "mira": mira, "tam": tam, "folder": folder}


def _client():
    return TestClient(main.app)


def test_goals_are_shared_with_the_table_and_marked_as_yours(table):
    res = _client().get(f"/sessions/{table['sid']}/goals", headers=_auth(table["owner"].email))
    body = res.json()
    by_name = {c["name"]: c for c in body["characters"]}
    assert by_name["Mira"]["you"] is True and by_name["Tam"]["you"] is False
    assert {g["text"] for g in by_name["Tam"]["goals"]} == {"repay the ferry debt"}
    assert all(g["status"] == "active" and g["id"] for g in by_name["Mira"]["goals"])
    assert body["scenes_since_review"] == 2


def test_only_members_can_see_goals(table):
    stranger = _user("goals-stranger@example.com")
    assert _client().get(f"/sessions/{table['sid']}/goals", headers=_auth(stranger.email)).status_code == 403


def test_suggestions_need_a_real_quote_and_a_real_goal():
    mira = type("C", (), {"name": "Mira", "sheet": {"goals": [{"term": "long", "text": "find who burned the granary"}]}})()
    story = "Mira found the oil-stained sill behind the Ashen Market and knew the granary fire was no accident."
    good = {"updates": [{"character": "Mira", "goal": "find who burned the granary", "status": "progressed", "evidence": "found the oil-stained sill behind the Ashen Market"}]}
    assert len(gr.suggest_updates([mira], story, call=lambda *a, **k: json.dumps(good))) == 1
    invented_quote = {"updates": [{**good["updates"][0], "evidence": "confronted the magistrate in the square"}]}
    assert gr.suggest_updates([mira], story, call=lambda *a, **k: json.dumps(invented_quote)) == []
    invented_goal = {"updates": [{**good["updates"][0], "goal": "become king"}]}
    assert gr.suggest_updates([mira], story, call=lambda *a, **k: json.dumps(invented_goal)) == []
    bad_status = {"updates": [{**good["updates"][0], "status": "achieved forever"}]}
    assert gr.suggest_updates([mira], story, call=lambda *a, **k: json.dumps(bad_status)) == []
    assert gr.suggest_updates([mira], story, call=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))) == []


def test_review_route_marks_whose_goal_it_is_and_resets_the_count(table, monkeypatch):
    reply = json.dumps({"updates": [
        {"character": "Mira", "goal": "find who burned the granary", "status": "progressed", "evidence": "knew the granary fire was no accident"},
        {"character": "Tam", "goal": "repay the ferry debt", "status": "done", "evidence": "paid the last coin of the ferry debt"},
    ]})
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: reply)
    c = _client()
    res = c.post(f"/sessions/{table['sid']}/goals/review", headers=_auth(table["owner"].email)).json()["suggestions"]
    assert {(s["character"], s["you"]) for s in res} == {("mira", True), ("tam", False)}
    assert c.get(f"/sessions/{table['sid']}/goals", headers=_auth(table["owner"].email)).json()["scenes_since_review"] == 0


def test_only_the_characters_player_can_change_a_goal(table):
    c = _client()
    tam_goal = db.get_character_by_id(table["tam"].id).sheet["goals"][0]
    body = {"character_id": table["tam"].id, "goal_id": gr.goal_id(tam_goal["text"]), "status": "done"}
    assert c.post(f"/sessions/{table['sid']}/goals/apply", json=body, headers=_auth(table["owner"].email)).status_code == 403
    ok = c.post(f"/sessions/{table['sid']}/goals/apply", json=body, headers=_auth(table["friend"].email))
    assert ok.status_code == 200 and ok.json()["goals"][0]["status"] == "done"
    assert db.get_character_by_id(table["tam"].id).sheet["goals"][0]["status"] == "done"


def test_unknown_goal_and_unseated_character_are_refused(table):
    c = _client()
    h = _auth(table["owner"].email)
    assert c.post(f"/sessions/{table['sid']}/goals/apply", json={"character_id": table["mira"].id, "goal_id": "nope", "status": "done"}, headers=h).status_code == 404
    other = db.create_character(owner_id=table["owner"].id, name="Elsewhere", level=1, class_name="Monk", sheet={})
    assert c.post(f"/sessions/{table['sid']}/goals/apply", json={"character_id": other.id, "goal_id": "x", "status": "done"}, headers=h).status_code == 404


def test_finished_goals_leave_the_scene_threads_and_new_ones_can_be_added(table):
    from server.agents import thread_weaver as tw

    c = _client()
    h = _auth(table["owner"].email)
    long_id = gr.goal_id("find who burned the granary")
    c.post(f"/sessions/{table['sid']}/goals/apply", json={"character_id": table["mira"].id, "goal_id": long_id, "status": "done", "note": "It was the Court."}, headers=h)
    threads = tw.character_threads(None, [{"character_id": table["mira"].id}])
    assert [g["text"] for g in threads[0]["goals"]] == ["ask around the market"]
    added = c.post(f"/sessions/{table['sid']}/goals/add", json={"character_id": table["mira"].id, "term": "long", "text": "bring the Court to account", "because": "they let the street starve"}, headers=h)
    assert added.status_code == 200 and added.json()["goals"][-1]["text"] == "bring the Court to account"
    assert c.post(f"/sessions/{table['sid']}/goals/add", json={"character_id": table["mira"].id, "text": "bring the Court to account"}, headers=h).status_code == 409


def test_a_campaigns_own_copy_of_the_goals_is_kept_in_step(table):
    camp = db.create_campaign(owner_id=table["owner"].id, name="Saltmere")
    meta = json.loads((table["folder"] / "meta.json").read_text())
    meta["campaign_id"] = camp.id
    (table["folder"] / "meta.json").write_text(json.dumps(meta))
    db.set_campaign_metadata_keys(camp.id, table["owner"].id, {"player_backstories": [
        {"character_id": str(table["mira"].id), "backstory": "x", "goals": [{"term": "long", "text": "find who burned the granary"}]},
    ]})
    long_id = gr.goal_id("find who burned the granary")
    res = _client().post(f"/sessions/{table['sid']}/goals/apply", json={"character_id": table["mira"].id, "goal_id": long_id, "status": "done"}, headers=_auth(table["owner"].email))
    assert res.status_code == 200
    kept = db.get_campaign_by_id(camp.id).metadata_json["player_backstories"][0]["goals"][0]
    assert kept["status"] == "done"


def test_too_many_active_goals_is_refused(table):
    c = _client()
    h = _auth(table["owner"].email)
    codes = [c.post(f"/sessions/{table['sid']}/goals/add", json={"character_id": table["mira"].id, "text": f"goal number {i}"}, headers=h).status_code for i in range(6)]
    assert codes[-1] == 409 and codes.count(200) == 4  # two goals already, six active at most
