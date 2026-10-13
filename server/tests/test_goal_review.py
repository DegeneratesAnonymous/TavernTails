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
    mira = type("C", (), {"id": 1, "name": "Mira", "sheet": {"goals": [{"term": "long", "text": "find who burned the granary"}]}})()
    story = "Mira found the oil-stained sill behind the Ashen Market and knew the granary fire was no accident."
    good = {"updates": [{"id": 1, "goal": "find who burned the granary", "status": "progressed", "evidence": "found the oil-stained sill behind the Ashen Market"}]}
    assert len(gr.suggest_updates([mira], story, call=lambda *a, **k: json.dumps(good))) == 1
    invented_quote = {"updates": [{**good["updates"][0], "evidence": "confronted the magistrate in the square"}]}
    assert gr.suggest_updates([mira], story, call=lambda *a, **k: json.dumps(invented_quote)) == []
    invented_goal = {"updates": [{**good["updates"][0], "goal": "become king"}]}
    assert gr.suggest_updates([mira], story, call=lambda *a, **k: json.dumps(invented_goal)) == []
    bad_status = {"updates": [{**good["updates"][0], "status": "achieved forever"}]}
    assert gr.suggest_updates([mira], story, call=lambda *a, **k: json.dumps(bad_status)) == []
    assert gr.suggest_updates([mira], story, call=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))) is None  # a failed review is not "nothing moved"


def test_review_route_marks_whose_goal_it_is_and_resets_the_count(table, monkeypatch):
    reply = json.dumps({"updates": [
        {"id": table["mira"].id, "goal": "find who burned the granary", "status": "progressed", "evidence": "knew the granary fire was no accident"},
        {"id": table["tam"].id, "goal": "repay the ferry debt", "status": "done", "evidence": "paid the last coin of the ferry debt"},
    ]})
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: reply)
    c = _client()
    res = c.post(f"/sessions/{table['sid']}/goals/review", headers=_auth(table["owner"].email)).json()["suggestions"]
    assert {(s["character"], s["you"]) for s in res} == {("Mira", True), ("Tam", False)}
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


def test_goals_kept_for_one_campaign_are_the_goals_in_effect(table):
    camp = db.create_campaign(owner_id=table["owner"].id, name="Saltmere")
    meta = json.loads((table["folder"] / "meta.json").read_text())
    meta["campaign_id"] = camp.id
    (table["folder"] / "meta.json").write_text(json.dumps(meta))
    db.set_campaign_metadata_keys(camp.id, table["owner"].id, {"player_backstories": [
        {"character_id": str(table["mira"].id), "backstory": "x", "goals": [{"term": "long", "text": "burn the ledger"}]},
    ]})
    c = _client()
    h = _auth(table["owner"].email)
    mira = next(x for x in c.get(f"/sessions/{table['sid']}/goals", headers=h).json()["characters"] if x["name"] == "Mira")
    assert [g["text"] for g in mira["goals"]] == ["burn the ledger"]  # not the sheet's goals
    done = c.post(f"/sessions/{table['sid']}/goals/apply", json={"character_id": table["mira"].id, "goal_id": gr.goal_id("burn the ledger"), "status": "done"}, headers=h)
    assert done.status_code == 200
    assert db.get_campaign_by_id(camp.id).metadata_json["player_backstories"][0]["goals"][0]["status"] == "done"
    assert all(g.get("status", "active") == "active" for g in db.get_character_by_id(table["mira"].id).sheet["goals"])  # the sheet is untouched


def test_a_suggestion_names_its_character_by_id_so_a_shared_name_is_not_confused():
    one = type("C", (), {"id": 1, "name": "Mira", "sheet": {"goals": [{"term": "long", "text": "find the arsonist"}]}})()
    two = type("C", (), {"id": 2, "name": "Mira", "sheet": {"goals": [{"term": "long", "text": "repay the debt"}]}})()
    story = "Mira found the arsonist's lamp behind the granary, and the debt was paid in full at dawn."
    reply = json.dumps({"updates": [{"id": 1, "goal": "find the arsonist", "status": "progressed", "evidence": "found the arsonist's lamp behind the granary"}]})
    found = gr.suggest_updates([one, two], story, call=lambda *a, **k: reply)
    assert [(s["character_id"], s["goal"]) for s in found] == [(1, "find the arsonist")]
    by_name = json.dumps({"updates": [{"character": "Mira", "goal": "repay the debt", "status": "done", "evidence": "the debt was paid in full at dawn"}]})
    assert gr.suggest_updates([one, two], story, call=lambda *a, **k: by_name) == []  # an ambiguous name is not a match


def test_the_same_goal_words_under_two_horizons_are_two_goals():
    from server.agents import lifepath

    goals = lifepath._clean_goals([{"term": "long", "text": "Survive the siege"}, {"term": "short", "text": "Survive the siege"}])
    assert len({g["id"] for g in goals}) == 2


def test_a_failed_review_is_an_error_and_does_not_mark_the_story_reviewed(table, monkeypatch):
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: None)
    c = _client()
    h = _auth(table["owner"].email)
    assert c.post(f"/sessions/{table['sid']}/goals/review", headers=h).status_code == 502
    assert c.get(f"/sessions/{table['sid']}/goals", headers=h).json()["scenes_since_review"] == 2
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: json.dumps({"updates": []}))
    assert c.post(f"/sessions/{table['sid']}/goals/review", headers=h).json() == {"suggestions": [], "more": False}
    assert c.get(f"/sessions/{table['sid']}/goals", headers=h).json()["scenes_since_review"] == 0


def test_a_review_reads_only_scenes_added_since_the_last_one(table, monkeypatch):
    seen: list[str] = []

    def fake(messages, **kw):
        seen.append(messages[-1]["content"])
        return json.dumps({"updates": []})

    monkeypatch.setattr(steward_llm, "chat_complete", fake)
    c = _client()
    h = _auth(table["owner"].email)
    assert c.post(f"/sessions/{table['sid']}/goals/review", headers=h).status_code == 200
    assert "oil-stained sill" in seen[0] and "ferry debt" in seen[0]
    assert c.post(f"/sessions/{table['sid']}/goals/review", headers=h).json() == {"suggestions": [], "more": False}
    assert len(seen) == 1  # nothing new, so the model is not asked again
    story = json.loads((table["folder"] / "story.json").read_text())
    story.append({"type": "narration", "text": "Dawn came up over the quiet harbour."})
    (table["folder"] / "story.json").write_text(json.dumps(story))
    assert c.post(f"/sessions/{table['sid']}/goals/review", headers=h).status_code == 200
    assert "Dawn came up" in seen[1] and "oil-stained sill" not in seen[1]


def _sugg(table, who, goal, evidence):
    return {"id": table[who].id, "goal": goal, "status": "progressed", "evidence": evidence}


def test_suggestions_are_kept_for_the_whole_table_until_acted_on(table, monkeypatch):
    reply = json.dumps({"updates": [_sugg(table, "tam", "repay the ferry debt", "paid the last coin of the ferry debt")]})
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: reply)
    c = _client()
    c.post(f"/sessions/{table['sid']}/goals/review", headers=_auth(table["owner"].email))
    # Tam's player sees the suggestion about their own goal even though someone else did the checking.
    seen = c.get(f"/sessions/{table['sid']}/goals", headers=_auth(table["friend"].email)).json()["suggestions"]
    assert [(s["character"], s["you"]) for s in seen] == [("Tam", True)]
    assert c.get(f"/sessions/{table['sid']}/goals", headers=_auth(table["owner"].email)).json()["suggestions"][0]["you"] is False
    # Only their own player can dismiss it; applying the change also clears it.
    body = {"character_id": table["tam"].id, "goal_id": seen[0]["goal_id"]}
    assert c.post(f"/sessions/{table['sid']}/goals/dismiss", json=body, headers=_auth(table["owner"].email)).status_code == 403
    assert c.post(f"/sessions/{table['sid']}/goals/dismiss", json=body, headers=_auth(table["friend"].email)).json() == {"suggestions": []}


def test_the_review_cursor_moves_only_past_scenes_the_model_was_shown(table, monkeypatch):
    story = [{"type": "narration", "text": f"Scene {i}. " + "word " * 5} for i in range(12)]
    (table["folder"] / "story.json").write_text(json.dumps(story))
    shown: list[str] = []
    monkeypatch.setattr(steward_llm, "chat_complete", lambda m, **k: shown.append(m[-1]["content"]) or json.dumps({"updates": []}))
    c = _client()
    h = _auth(table["owner"].email)
    first = c.post(f"/sessions/{table['sid']}/goals/review", headers=h).json()
    assert first["more"] is True and "Scene 0." in shown[0] and "Scene 7." in shown[0] and "Scene 8." not in shown[0]
    second = c.post(f"/sessions/{table['sid']}/goals/review", headers=h).json()
    assert second["more"] is False and "Scene 8." in shown[1] and "Scene 11." in shown[1] and "Scene 0." not in shown[1]


def test_reopening_a_goal_respects_the_active_limit(table):
    c = _client()
    h = _auth(table["owner"].email)
    mira = table["mira"]
    goals = [{"term": "mid", "text": f"active goal {i}"} for i in range(6)] + [{"term": "long", "text": "an old goal", "status": "done"}]
    db.update_character(mira.id, table["owner"].id, {"sheet_patch": {"goals": goals}})
    res = c.post(f"/sessions/{table['sid']}/goals/apply", json={"character_id": mira.id, "goal_id": gr.goal_id("an old goal"), "status": "active"}, headers=h)
    assert res.status_code == 409
