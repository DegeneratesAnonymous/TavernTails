"""Player journeys through real routes, including the no-provider path."""
import json
import os
import re

import pytest
from fastapi.testclient import TestClient

from server import db, main, steward_llm
from server.agents import narrative, scene_director, sessions
from server.agents.content_bundles import generate_starter_seed
from server.agents.scene_qa import apply_targeted_scene_repairs, run_scene_qa
from server.auth import create_access_token

PREMISE = (
    "At Alderbrook village, every clock stopped at breakfast. "
    "Clockmaker Ada Reed has a stopped brass pocket watch on her workbench. "
    "Find the cause without frightening the neighbors."
)


def _clock_campaign(email):
    user = db.get_user_by_identifier(email)
    if not user:
        user = db.create_user(email=email, username=email.split("@")[0], password="secret", profile={})
    if not user.verified:
        db.verify_user(email, user.verification_token or "")
    client = TestClient(main.app)
    client.headers["Authorization"] = f"Bearer {create_access_token(email)}"
    created = client.post("/campaigns", json={
        "name": "QA Clock Mystery", "description": PREMISE, "create_session": True,
        "preferences": {"genre": "mystery", "tone": "cozy", "setting_summary": PREMISE},
    })
    assert created.status_code == 201, created.text
    sid = created.json()["campaign"]["sessions"][0]["id"]
    assert client.post(f"/sessions/{sid}/opening-setup/skip").status_code == 200
    return client, sid


def test_authored_brief_survives_random_seed_choices():
    for seed in range(10):
        result = generate_starter_seed({"setting_summary": PREMISE}, seed=seed)
        assert result["starting_location"] == "Alderbrook village"
        assert result["named_npc_or_visible_threat"] == "Ada Reed"
        assert "every clock stopped at breakfast" in result["inciting_event"]
        assert result["approved_object"] == "stopped brass pocket watch"


def test_repairs_do_not_turn_clue_sentences_into_movable_objects():
    scene = {
        "location": "Alderbrook", "narrative_body": "Ada Reed waits at the workbench.",
        "player_prompt": "What do you do?", "visible_clues": ["The first answer is rehearsed."],
        "immediate_stakes": "",
    }
    qa = run_scene_qa(scene=scene)
    assert qa["truth_table"]["approved_stakes"] == ""
    qa["repair_targets"] = ["continuity", "specificity", "clue_presentation"]
    qa["truth_table"]["approved_clue"] = "The first answer is rehearsed."
    result = apply_targeted_scene_repairs(scene, qa, recent_player_actions=["I ask Ada when she wound the watch."])
    assert "chosen to I" not in result["text"]
    assert "is moved" not in result["text"]
    assert result["text"].count("The first answer is rehearsed.") == 1


def test_ordinary_camp_does_not_invent_a_slave_army():
    result = sessions._action_response_scene(
        player_name="Aria", location_name="Summer Camp",
        latest_action="I inspect the picnic table.", action_count=1,
    )
    assert result["title"] != "Breaking Camp"
    assert "army" not in result["narrative"]
    assert "escapees" not in result["narrative"]


def test_no_provider_campaign_and_multiple_rounds(monkeypatch):
    # Explicitly disable completions: the global structural stub would conceal
    # the actual fallback behavior this journey is intended to exercise.
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: None)
    monkeypatch.setattr(narrative, "chat_complete", lambda *a, **k: None)
    director_requests = []
    original_director = scene_director.direct_scene

    def capture_director(request):
        director_requests.append(request)
        return original_director(request)

    monkeypatch.setattr(scene_director, "direct_scene", capture_director)
    client, sid = _clock_campaign("playthrough-quality@example.com")
    opening = client.post(f"/sessions/{sid}/start", json={})
    assert opening.status_code == 200, opening.text
    assert "Alderbrook" in opening.json()["scene"]["text"]
    assert "Ada Reed" in opening.json()["scene"]["text"]
    assert "pocket watch" in opening.json()["scene"]["text"]

    def advance(action):
        message = client.post("/chat", json={"session_id": sid, "message": action, "role": "player"})
        assert message.status_code == 201
        response = client.post(f"/sessions/{sid}/advance-scene", json={})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["scene"]["last_resolved_message_id"] == message.json()["id"]
        return data

    rested = advance("I take a long rest.")
    assert rested["simulation_debug"]["time_resolver"]["elapsed_minutes"] == 480
    asked = advance("I ask Ada Reed when she last wound the watch.")
    assert director_requests[-1].is_opening_scene is False
    assert director_requests[-1].player_actions == ["I ask Ada Reed when she last wound the watch."]
    assert asked["simulation_debug"]["time_resolver"]["elapsed_minutes"] == 5
    assert "chosen to I" not in asked["scene"]["text"]
    assert ". is moved" not in asked["scene"]["text"]
    # Reloading and advancing without new chat must not repeat the long rest.
    persisted = json.loads((sessions.BASE / sid / "scene.json").read_text())
    assert persisted["last_resolved_message_id"] == asked["scene"]["last_resolved_message_id"]
    # Migration of an existing save must retain the history watermark even
    # when its first advance has no new messages.
    del persisted["last_resolved_message_id"]
    (sessions.BASE / sid / "scene.json").write_text(json.dumps(persisted))
    idle = client.post(f"/sessions/{sid}/advance-scene", json={})
    assert idle.status_code == 200
    assert idle.json()["simulation_debug"]["time_resolver"]["elapsed_minutes"] != 480
    assert idle.json()["scene"]["last_resolved_message_id"] == asked["scene"]["last_resolved_message_id"]
    after_reload = advance("I ask Ada Reed about breakfast.")
    assert after_reload["simulation_debug"]["time_resolver"]["elapsed_minutes"] == 5
    # An async party may post more than 20 messages between scenes. None of
    # that new input should disappear behind the previous fixed history limit.
    pending_actions = ["I search the workbench."] + [f"I wait quietly, turn {i}." for i in range(25)]
    for action in pending_actions:
        assert client.post("/chat", json={"session_id": sid, "message": action}).status_code == 201
    crowded = client.post(f"/sessions/{sid}/advance-scene", json={})
    assert crowded.status_code == 200, crowded.text
    assert director_requests[-1].player_actions == pending_actions
    assert crowded.json()["simulation_debug"]["time_resolver"]["elapsed_minutes"] == 20


@pytest.mark.llm
def test_live_clock_mystery_resolves_specific_actions(tmp_path):
    """Opt-in release check: requires a real provider and saves reviewable prose."""
    assert any(os.environ.get(key) for key in ("STEWARD_HOST", "OLLAMA_HOST", "OPENAI_API_KEY")), (
        "Configure a real AI provider before running the live playthrough."
    )
    client, sid = _clock_campaign("live-playthrough-quality@example.com")
    transcript = []
    opening = client.post(f"/sessions/{sid}/start", json={})
    assert opening.status_code == 200, opening.text
    transcript.append({"action": None, "response": opening.json()})
    for action, target in (
        ("I inspect the brass pocket watch on Ada Reed's workbench.", "watch"),
        ("I ask Ada Reed when she last wound the watch.", "Ada Reed"),
        ("I leave the workshop and go to the village square.", "square"),
    ):
        assert client.post("/chat", json={"session_id": sid, "message": action}).status_code == 201
        response = client.post(f"/sessions/{sid}/advance-scene", json={})
        assert response.status_code == 200, response.text
        data = response.json()
        transcript.append({"action": action, "response": data})
        (tmp_path / "live-playthrough.json").write_text(json.dumps(transcript, indent=2))
        body = data["scene"].get("narrative_body") or data["scene"]["text"]
        assert re.search(rf"\b{re.escape(target)}\b", body, re.I), body  # whole word: "watching" is not "watch"
        assert body != transcript[-2]["response"]["scene"].get("narrative_body"), body
        assert "moment holds" not in body.lower()
        assert "chosen to I" not in body
        assert ". is moved" not in body
        assert not data["simulation_debug"]["scene_validator"]["fallback_used"], "Fallback is not live-model validation"
        assert data["scene"]["scene_director_data"]["source"] == "llm"
    # The full transcript still needs a human review for actual answers,
    # fair consequences and sensible clues; keyword checks cannot prove prose quality.


def test_fallback_scene_keeps_the_campaigns_established_object():
    from server.agents.scene_validator import build_fallback_scene

    kwargs = {
        "location_name": "Alderbrook village", "npc_name": "Ada Reed", "player_name": "Ren",
        "emotional_state": "shaken", "inciting_incident": "Every clock stopped at breakfast",
        "central_conflict": "The clocks stopped", "immediate_stakes": "The village loses its sense of time",
        "campaign_name": "Winter clocks",
    }
    plain = build_fallback_scene(**kwargs)
    kept = build_fallback_scene(**kwargs, approved_object="stopped brass pocket watch")
    assert "stopped brass pocket watch" in kept.lower()
    assert "frost-stiff packet" in plain  # the keyword-table prop the campaign never asked for
    assert "frost-stiff packet" not in kept
    # A full clue sentence is never substituted for an object name.
    sentence = build_fallback_scene(**kwargs, approved_object="Ada found the watch. It is stopped.")
    assert "Ada found the watch" not in sentence
