"""Backstory threads (the B plot) braided into the campaign's hidden truth (the A plot)."""
from __future__ import annotations

import json

from sqlmodel import Session, select

from server import db
from server.agents import sessions as sessions_module
from server.agents import thread_weaver as tw
from server.agents.context_orchestrator import orchestrate

TRUTH = {
    "thread_name": "The Burning Granaries", "visible_problem": "Grain stores keep catching fire.",
    "hidden_truth": "The Salt Court is burning its own granaries to raise the price of grain.",
    "who_benefits": "Salt Court", "first_clue": "Oil on the sill", "stakes": "The city starves by winter",
}
FACTIONS = [{"name": "Salt Court", "wants": "control of the grain", "plan": "raise prices", "if_ignored": "famine"}]
NPCS = [{"name": "Hale Orrin", "role": "magistrate", "wants": "quiet", "secret": "", "knows": "", "faction": "Salt Court"}]


def _thread(**kw):
    base = {
        "character_id": 1, "name": "Mira", "backstory": "", "allies": [], "rivals": [], "patron": "",
        "goals": [{"term": "long", "text": "find who burned the granary", "because": "my street went hungry", "but": ""}],
        "link": {"kind": "faction", "name": "Salt Court"},
    }
    base.update(kw)
    return base


def _user(email):
    existing = db.get_user_by_identifier(email)
    if existing:
        return existing
    user = db.create_user(email=email, password="secret", username=email.split("@")[0], profile={"name": email.split("@")[0]})
    db.verify_user(email, user.verification_token)
    return db.get_user_by_identifier(email)


def test_a_good_draft_is_used():
    reply = json.dumps({"threads": [{
        "character": "Mira", "connection": "The Salt Court's fires are the ones Mira is hunting.",
        "complication": "Each new fire makes her street hungrier.", "beat": "A fire breaks out beside Hale Orrin's office.",
    }]})
    out = tw.weave([_thread()], TRUTH, FACTIONS, NPCS, "Saltmere", call=lambda *a, **k: reply)
    assert out[1]["source"] == "model" and "Salt Court" in out[1]["connection"]


def test_a_draft_with_an_invented_name_is_replaced_by_a_plain_sentence():
    reply = json.dumps({"threads": [{
        "character": "Mira", "connection": "The Salt Court hired Captain Vorrel to burn it.",
        "complication": "More fires.", "beat": "Meet Captain Vorrel.",
    }]})
    out = tw.weave([_thread()], TRUTH, FACTIONS, NPCS, "Saltmere", call=lambda *a, **k: reply)
    assert out[1]["source"] == "template"
    assert "Vorrel" not in json.dumps(out)
    assert "find who burned the granary" in out[1]["connection"]


def test_a_draft_that_touches_nothing_in_the_world_is_replaced():
    reply = json.dumps({"threads": [{"character": "Mira", "connection": "She thinks about her goal a lot.", "complication": "Time passes.", "beat": "She walks."}]})
    assert tw.weave([_thread()], TRUTH, FACTIONS, NPCS, "Saltmere", call=lambda *a, **k: reply)[1]["source"] == "template"


def test_a_failing_model_still_gives_every_character_a_thread():
    def boom(*a, **k):
        raise RuntimeError("down")

    out = tw.weave([_thread(), _thread(character_id=2, name="Tam")], TRUTH, FACTIONS, NPCS, call=boom)
    assert set(out) == {1, 2} and all(v["source"] == "template" for v in out.values())


def test_fallback_without_a_skeleton_uses_the_players_link():
    out = tw.weave([_thread(link={"kind": "place", "name": "Ashen Market"})], None, [], [])
    assert "Ashen Market" in out[1]["connection"]


def test_block_lists_goals_ties_and_link_for_the_table():
    block = tw.thread_block(_thread(allies=["Tam"], rivals=["a magistrate"], patron="the guild"))
    assert "[Character thread: Mira]" in block and "Long goal: find who burned the granary because my street went hungry" in block
    assert "Allies: Tam" in block and "Rivals: a magistrate" in block and "Patron: the guild" in block
    assert "Salt Court" in block


def test_campaign_only_backstory_overrides_the_sheet():
    owner = _user("weaver-owner@example.com")
    mira = db.create_character(owner_id=owner.id, name="Mira", level=1, class_name="Rogue", sheet={"goals": [{"term": "long", "text": "sheet goal"}]})
    camp = db.create_campaign(owner_id=owner.id, name="Saltmere")
    db.set_campaign_metadata_keys(camp.id, owner.id, {"player_backstories": [
        {"character_id": str(mira.id), "backstory": "x", "goals": [{"term": "long", "text": "campaign goal"}], "link": {"kind": "faction", "name": "Salt Court"}},
    ]})
    threads = tw.character_threads(db.get_campaign_by_id(camp.id), [{"character_id": mira.id}, {"character_id": mira.id}, {"character_id": None}])
    assert len(threads) == 1 and threads[0]["goals"][0]["text"] == "campaign goal" and threads[0]["link"]["name"] == "Salt Court"


def test_a_character_with_no_story_has_no_thread():
    owner = _user("weaver-owner2@example.com")
    plain = db.create_character(owner_id=owner.id, name="Plain", level=1, class_name="Fighter", sheet={"backstory": "Just a backstory."})
    camp = db.create_campaign(owner_id=owner.id, name="Plain")
    assert tw.character_threads(db.get_campaign_by_id(camp.id), [{"character_id": plain.id}]) == []


def test_rows_are_written_once_updated_on_change_and_offered_to_the_scene_writers():
    owner = _user("weaver-owner3@example.com")
    mira = db.create_character(owner_id=owner.id, name="Mira", level=1, class_name="Rogue", sheet={
        "goals": [{"term": "long", "text": "find who burned the granary", "because": "", "but": ""}],
        "backstory_link": {"kind": "place", "name": "Ashen Market"},
    })
    camp = db.create_campaign(owner_id=owner.id, name="Saltmere")
    members = [{"character_id": mira.id}]
    calls = []

    def count(*a, **k):
        calls.append(1)
        return None

    tw.ensure_threads(db.get_campaign_by_id(camp.id), members, call=count)
    rows = tw.b_plot_rows(camp.id)
    assert len(rows) == 1 and rows[0].visibility == "gm_only" and rows[0].data["plot"] == "B"
    assert rows[0].data["current_situation"] == "Mira wants to find who burned the granary."
    first_signature = rows[0].data["signature"]
    tw.ensure_threads(db.get_campaign_by_id(camp.id), members, call=count)
    assert tw.b_plot_rows(camp.id)[0].data["signature"] == first_signature  # nothing changed, nothing rewritten
    db.update_character(mira.id, owner.id, {"sheet_patch": {"goals": [{"term": "long", "text": "clear the market's name"}]}})
    tw.ensure_threads(db.get_campaign_by_id(camp.id), members, call=count)
    changed = tw.b_plot_rows(camp.id)
    assert len(changed) == 1 and changed[0].data["signature"] != first_signature
    assert "clear the market's name" in changed[0].data["current_situation"]
    packet = orchestrate(campaign_id=str(camp.id), player_name="Mira", player_actions=[], use_cache=False)
    assert any("Mira" in t.title for t in packet.story_threads)
    with Session(db.engine) as s:
        assert len(s.exec(select(db.CampaignEntity).where(db.CampaignEntity.campaign_id == camp.id)).all()) == 1


def test_opening_goals_are_the_seated_characters_own_shortest_first():
    threads = [_thread(goals=[{"term": "long", "text": "L"}, {"term": "short", "text": "S"}, {"term": "mid", "text": "M"}])]
    assert sessions_module._opening_goals(threads, "Mira") == ["S", "M"]
    assert sessions_module._opening_goals(threads, "Someone Else") == []


# ---- braiding ----------------------------------------------------------------

def _two_threads(tmp_path):
    from server.agents import braid  # noqa: F401  (imported by the tests below)

    owner = _user("braid-owner@example.com")
    chars = [
        db.create_character(owner_id=owner.id, name=name, level=1, class_name="Rogue", sheet={
            "goals": [{"term": "long", "text": goal}], "backstory_link": {"kind": "story", "name": ""},
        })
        for name, goal in (("Mira", "find who burned the granary"), ("Tam", "repay the ferry debt"))
    ]
    camp = db.create_campaign(owner_id=owner.id, name="Braid")
    tw.ensure_threads(db.get_campaign_by_id(camp.id), [{"character_id": c.id} for c in chars], call=lambda *a, **k: None)
    (tmp_path / "meta.json").write_text(json.dumps({"members": [{"character_id": c.id} for c in chars]}))
    return camp, chars


def test_a_thread_beat_comes_at_most_one_scene_in_three_and_characters_take_turns(tmp_path):
    from server.agents import braid

    camp, _ = _two_threads(tmp_path)
    seen = []
    for _scene in range(8):
        beat = braid.next_b_beat(tmp_path, str(camp.id))
        seen.append(beat["character"] if beat else None)
        text = f"{beat['character']} chased the {beat['goal']} lead." if beat else "The market stirred."
        braid.record_scene(tmp_path, text, beat)
    assert seen == [None, None, "Mira", None, None, "Tam", None, None]


def test_a_scene_that_ignored_the_request_does_not_reset_the_count(tmp_path):
    from server.agents import braid

    camp, _ = _two_threads(tmp_path)
    for _ in range(2):
        braid.record_scene(tmp_path, "The market stirred.", None)
    beat = braid.next_b_beat(tmp_path, str(camp.id))
    assert beat is not None
    braid.record_scene(tmp_path, "The market stirred.", beat)  # never mentions the character
    again = braid.next_b_beat(tmp_path, str(camp.id))
    assert again is not None and again["character"] == beat["character"]  # asked again, same character


def test_no_threads_means_no_thread_beats(tmp_path):
    from server.agents import braid

    owner = _user("braid-owner2@example.com")
    camp = db.create_campaign(owner_id=owner.id, name="NoThreads")
    for _ in range(5):
        braid.record_scene(tmp_path, "Text.", None)
    assert braid.next_b_beat(tmp_path, str(camp.id)) is None


# ---- the opening questions use what the player already wrote ------------------

STORY = _thread(
    goals=[{"term": "long", "text": "bring the Court to account", "because": "they let my street starve", "but": "the witness left town"},
           {"term": "short", "text": "find who burned the granary", "because": "", "but": ""}],
    allies=["Tam, a ferryman"], rivals=["a magistrate who wants me quiet"], patron="the Reed Guild",
)


def _question(questionnaire, qid):
    return next(q for q in questionnaire["questions"] if q["id"] == qid)


def test_the_players_own_story_is_offered_first_in_their_own_words():
    from server.agents.opening_setup import generate_questionnaire

    out = generate_questionnaire(session_id="s", character={"id": "1", "name": "Mira"}, story=STORY)
    arrival = _question(out, "arrival_reason")["options"]
    assert arrival[0]["id"] == "backstory" and arrival[0]["value"] == "I came to find who burned the granary"
    assert _question(out, "personal_stake")["options"][0]["value"] == "It matters because they let my street starve"
    assert _question(out, "followed_complication")["options"][0]["value"] == "a magistrate who wants me quiet is close behind me"
    assert _question(out, "fear_of_loss")["options"][0]["value"] == "I could not bear to lose Tam, a ferryman"
    assert _question(out, "npc_connection")["options"][0]["value"] == "the Reed Guild backs me"
    assert _question(out, "arrival_reason")["options"][-1]["id"] == "ai_choose"  # canned choices are still there


def test_without_a_written_story_the_questions_are_unchanged():
    from server.agents.opening_setup import generate_questionnaire

    for kwargs in ({}, {"story": None}, {"story": _thread(goals=[], link=None)}):
        out = generate_questionnaire(session_id="s", character={"id": "1", "name": "Mira"}, **kwargs)
        assert all(o["id"] != "backstory" for q in out["questions"] for o in q["options"])


def test_a_party_is_not_asked_to_speak_for_one_member():
    from server.agents.opening_setup import generate_questionnaire

    out = generate_questionnaire(session_id="s", character={"id": "1", "name": "Mira"}, story=STORY, party_mode=True)
    assert all(o["id"] != "backstory" for q in out["questions"] for o in q["options"])


def test_a_backstory_answer_is_the_players_own_in_the_anchor():
    from server.agents.opening_setup import answers_to_anchor, generate_questionnaire

    q = generate_questionnaire(session_id="s", character={"id": "1", "name": "Mira"}, story=STORY)
    anchor = answers_to_anchor(session_id="s", character={"id": "1", "name": "Mira"}, questionnaire=q,
                               answers=[{"question_id": "arrival_reason", "option_id": "backstory"}])
    assert anchor["arrival_reason"] == "I came to find who burned the granary"
    assert anchor["field_sources"]["arrival_reason"] == "player"
    assert anchor["field_sources"]["personal_stake"] == "default"  # unanswered questions are not credited to the player


def test_a_failed_campaign_setup_is_reported_not_swallowed(monkeypatch):
    from fastapi.testclient import TestClient

    import server.main as main
    from server.agents import campaigns
    from server.auth import create_access_token

    owner = _user("warn-owner@example.com")

    def boom(*a, **k):
        raise RuntimeError("contract failed")

    monkeypatch.setattr(campaigns, "_contract_package_for_campaign", boom)
    res = TestClient(main.app).post("/campaigns", json={"name": "Warn", "owner_role": "dm", "create_session": False},
                                    headers={"Authorization": f"Bearer {create_access_token(owner.email)}"})
    assert res.status_code == 201 and res.json()["warnings"]
    assert db.get_campaign_by_id(res.json()["campaign"]["id"]).metadata_json.get("setup_incomplete") is True


def test_a_session_only_brings_in_its_own_characters(tmp_path):
    from server.agents import braid

    camp, chars = _two_threads(tmp_path)
    (tmp_path / "meta.json").write_text(json.dumps({"members": [{"character_id": chars[0].id}]}))
    for _ in range(2):
        braid.record_scene(tmp_path, "The market stirred.", None)
    assert braid.next_b_beat(tmp_path, str(camp.id))["character"] == "Mira"
    braid.record_scene(tmp_path, "Mira chased the find who burned the granary lead.", braid.next_b_beat(tmp_path, str(camp.id)))
    for _ in range(2):
        braid.record_scene(tmp_path, "The market stirred.", None)
    assert braid.next_b_beat(tmp_path, str(camp.id))["character"] == "Mira"  # Tam is not seated here


def test_two_characters_with_the_same_name_keep_their_own_drafts():
    threads = [_thread(character_id=1), _thread(character_id=2, goals=[{"term": "long", "text": "repay the ferry debt"}])]
    reply = json.dumps({"threads": [
        {"id": 1, "character": "Mira", "connection": "The Salt Court's fires are what Mira hunts.", "complication": "Fires spread.", "beat": "A fire near Hale Orrin."},
        {"id": 2, "character": "Mira", "connection": "Hale Orrin holds the ferry debt Mira owes.", "complication": "The debt grows.", "beat": "Hale Orrin calls it in."},
    ]})
    out = tw.weave(threads, TRUTH, FACTIONS, NPCS, "Saltmere", call=lambda *a, **k: reply)
    assert "Salt Court" in out[1]["connection"] and "ferry debt" in out[2]["connection"]


def test_finishing_a_goal_updates_the_stored_thread_at_once(tmp_path):
    from server.agents import braid

    camp, chars = _two_threads(tmp_path)
    tw.refresh_after_goal_change(camp.id, chars[0].id, [{"term": "long", "text": "find who burned the granary", "status": "done"}])
    assert [r.name for r in tw.b_plot_rows(camp.id)] == ["Tam's story"]  # Mira has nothing left to pursue
    tw.refresh_after_goal_change(camp.id, chars[1].id, [{"term": "long", "text": "repay the ferry debt", "status": "done"}, {"term": "mid", "text": "buy a boat"}])
    row = tw.b_plot_rows(camp.id)[0]
    assert row.data["current_situation"] == "Tam wants to buy a boat." and row.data["signature"] == ""
    assert braid is not None


def test_a_short_name_is_not_found_inside_other_words(tmp_path):
    from server.agents import braid

    beat = {"character": "Al", "goal": "find the granary arsonist", "beat": "a fire near the granary"}
    assert not braid.touched("The salt hall smelled of smoke near the granary arsonist's lamp.", beat)
    assert braid.touched("Al found the granary arsonist's lamp.", beat)


def test_a_blank_campaign_field_is_a_choice_not_a_gap(tmp_path):
    owner = _user("weaver-owner4@example.com")
    mira = db.create_character(owner_id=owner.id, name="Mira", level=1, class_name="Rogue", sheet={
        "goals": [{"term": "long", "text": "sheet goal"}], "rivals": ["Sheet Rival"], "patron": "Sheet Patron",
    })
    camp = db.create_campaign(owner_id=owner.id, name="Saltmere")
    db.set_campaign_metadata_keys(camp.id, owner.id, {"player_backstories": [
        {"character_id": str(mira.id), "backstory": "x", "goals": [{"term": "long", "text": "campaign goal"}], "rivals": [], "patron": "", "allies": [], "link": None},
    ]})
    thread = tw.character_threads(db.get_campaign_by_id(camp.id), [{"character_id": mira.id}])[0]
    assert thread["rivals"] == [] and thread["patron"] == "" and thread["goals"][0]["text"] == "campaign goal"


def test_changing_the_active_goal_replaces_everything_derived_from_the_old_one(tmp_path):
    camp, chars = _two_threads(tmp_path)
    before = tw.b_plot_rows(camp.id)[0].data
    assert "granary" in before["next_recommended_dm_move"] or "ferry" in before["next_recommended_dm_move"]
    old_goal = before["primary_goal"]
    tw.refresh_after_goal_change(camp.id, int(before["character_id"]), [
        {"term": "long", "text": old_goal, "status": "done"}, {"term": "mid", "text": "buy a boat"},
    ])
    after = next(r for r in tw.b_plot_rows(camp.id) if r.data["character_id"] == before["character_id"]).data
    assert old_goal not in " ".join(str(after[k]) for k in ("next_recommended_dm_move", "gm_notes", "stakes", "story_engine", "current_situation"))
    assert "buy a boat" in after["next_recommended_dm_move"]


def test_an_opening_may_not_say_the_characters_goal_is_already_done():
    from server.agents.scene_weaver import _resolves_goal

    goals = ["find who burned the granary"]
    assert _resolves_goal("Mira has already found who burned the granary.", goals)
    assert _resolves_goal("At last Mira solved who burned the granary.", goals)
    assert not _resolves_goal("Mira wants to find who burned the granary, and asks around.", goals)
    assert not _resolves_goal("The granary stood finally empty.", goals)
