import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from server import main, steward_llm
from server.agents import narrative, scene_director, sessions
from server.agents.action_resolution import continuation_issues, resolution_issues
from server.agents.content_bundles import build_content_bundle
from server.agents.generation_intent import build_opening_intent, definite, established_object
from server.agents.narrative_linter import ScoreResult
from server.tests.test_playthrough_quality import PREMISE, _clock_campaign


def test_authored_object_is_canon_in_model_bundle_and_carried_forward():
    settings = {"setting_summary": PREMISE}
    intent = build_opening_intent(settings)
    obj = next(f for f in intent.facts() if f.kind == "object")
    assert obj.provenance == "user"
    assert obj.source == "settings.setting_summary"
    output = {"location": {"name": "Alderbrook village"}, "primary_npc": {"name": "Ada Reed"},
              "player_visible_clues": ["a sealed letter"]}
    opening = build_content_bundle("campaign_opening", output, campaign_settings=settings)
    assert opening["required_content"]["approved_object"] == "stopped brass pocket watch"
    continuation = build_content_bundle("travel", output, previous_scene={"content_bundle": opening})
    assert continuation["required_content"]["approved_object"] == "stopped brass pocket watch"


@pytest.mark.parametrize("text", [
    "Ada Reed has no watch on the bench.",
    "If Ada Reed has a pocket watch on the bench, inspect it.",
    "Ada Reed does not have a pocket watch on the bench.",
    "Ada Reed has a watch. It is on the bench.",
])
def test_denied_or_hypothetical_possession_is_not_canon(text):
    assert not established_object(build_opening_intent({"setting_summary": text}))


@pytest.mark.parametrize(("phrase", "expected"), [
    ("A small gear inside the pocket watch", "a small gear inside the pocket watch"),
    ("An unmarked gear", "an unmarked gear"),
    ("The brass watch", "the brass watch"),
    ("a Silver Court badge", "a Silver Court badge"),
    ("Ada Reed's watch", "Ada Reed's watch"),
])
def test_inline_object_determiners_preserve_proper_names(phrase, expected):
    assert definite(phrase) == expected


def test_director_rejects_question_without_reply_and_preserves_npc(monkeypatch):
    monkeypatch.setattr(scene_director, "chat_complete", lambda *a, **k: json.dumps({
        "location": {"name": "Elsewhere"}, "primary_npc": {"name": "Milo Thorne"},
        "player_visible_clues": ["a broken pocket watch"],
    }))
    out = scene_director.direct_scene(scene_director.SceneDirectorRequest(
        is_opening_scene=False, player_actions=["I ask Ada when she wound the watch."],
        campaign_settings={"setting_summary": PREMISE},
        previous_scene={"location": "Ada Reed's Workshop", "primary_npc": {"name": "Ada Reed"}},
    ))
    assert out.location.name == "Ada Reed's Workshop"
    assert out.primary_npc.name == "Ada Reed"
    assert out.player_visible_clues == ["stopped brass pocket watch"]
    assert out.action_resolutions[0]["status"] == "cannot_answer"
    assert out.generation_debug["fallback_reason"] == "missing_question_resolution"


def test_posture_is_not_reply_and_unwritten_reply_fails_check():
    actions = ["I ask Ada when she wound the watch."]
    assert resolution_issues(actions, [])
    assert resolution_issues(actions, [{"action_index": 0, "status": "answered", "reply": "Ada Reed glances away nervously."}])
    resolution = [{"action_index": 0, "status": "answered", "reply": "I wound it at breakfast."}]
    assert continuation_issues("Ada Reed looks away.", actions, resolution,
                               known_names=["Ada Reed"], allow_new_names=False)
    assert not continuation_issues('Ada Reed says, "I wound it at breakfast."', actions, resolution,
                                   known_names=["Ada Reed"], allow_new_names=False)
    assert continuation_issues("Milo Thorne arrives.", [], [], known_names=["Ada Reed"], allow_new_names=False)
    assert not continuation_issues("Milo Thorne arrives.", [], [], known_names=["Ada Reed"], allow_new_names=True)


def test_opening_contract_keeps_grounded_model_prose_without_invented_hook(monkeypatch):
    from server.agents.content_bundles import generate_starter_seed
    from server.agents.generation_intent import intent_from_opening
    required = generate_starter_seed({"setting_summary": PREMISE}, seed=0)
    body = (
        "At Alderbrook village, the cold air carries no ticking. Ada Reed stands at her workbench beside "
        "the stopped brass pocket watch. Every clock stopped at breakfast; you can compare the watch "
        "with the other clocks before disturbing anything."
    )
    scene = {"location": "Alderbrook village", "narrative_body": body, "text": body,
             "generation_debug": {"fallback_used": False},
             "choices": [{"label": t} for t in ["Inspect the watch", "Question Ada Reed", "Compare the clocks"]]}
    intent = intent_from_opening(required=required, settings={"setting_summary": PREMISE}, player_name="the party")
    result, _ = sessions._apply_concrete_opening_scene_contract(
        scene, required=required, opening_anchor={}, campaign_brief={}, player_name="the party",
        time_of_day="day", source_intent=intent,
    )
    assert result["narrative_body"] == body
    assert not result["generation_debug"]["fallback_used"]


def test_start_route_keeps_valid_writer_prose_instead_of_premise_template(monkeypatch):
    body = (
        "At Alderbrook village, the cold air carries no ticking. The party stands beside Ada Reed's workbench "
        "and the stopped brass pocket watch. Every clock stopped at breakfast. Ada Reed sets the watch "
        "under a lamp so its brass surface catches the light. The party can compare it with the other clocks "
        "before disturbing anything."
    )
    monkeypatch.setattr(narrative, "generate_narrative", lambda *a, **k: narrative.NarrativeResponse(
        narrative=body, prompt="What does the party do?", tone="cozy", scene_score=100,
        score_passed=True, score_detail={"fallback_used": False},
    ))
    client, sid = _clock_campaign("model-opening-followup@example.com")
    response = client.post(f"/sessions/{sid}/start", json={})
    assert response.status_code == 200, response.text
    data = response.json()
    assert "cold air carries no ticking" in data["scene"]["narrative_body"]
    assert "sealed letter" not in data["scene"]["narrative_body"]
    assert not data["scene_debug"]["fallback_used"]


def test_model_writer_retries_a_non_answer_even_if_prose_score_passes(monkeypatch):
    monkeypatch.setattr(narrative, "chat_complete", lambda *a, **k: json.dumps({
        "narrative": "Ada Reed glances at the brass pocket watch and turns away.", "prompt": "What next?",
    }))
    # The semantic action check must reject this independently of prose score.
    monkeypatch.setattr(narrative, "score_scene", lambda *a, **k: ScoreResult(score=100, passes_threshold=True))
    result = narrative.generate_narrative(narrative.NarrativeRequest(
        scene="Clock mystery", player="Aria", player_actions=["I ask Ada when she wound the watch."],
        known_names=["Ada Reed", "Aria"], approved_object="brass pocket watch",
        scene_director_data={"location": {"name": "Workshop"}, "primary_npc": {"name": "Ada Reed"},
                             "action_resolutions": [{"action_index": 0, "status": "answered", "reply": "I wound it at breakfast."}]},
    ))
    assert result.score_detail["fallback_used"]
    assert result.score_detail["fallback_reason"] == "action_or_fact_check_failed"
    assert result.score_detail["attempts"] == 2


def test_real_routes_report_fallback_and_resolve_question_and_movement(monkeypatch):
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: None)
    monkeypatch.setattr(narrative, "chat_complete", lambda *a, **k: None)
    assert main.app
    client, sid = _clock_campaign("followup-quality@example.com")
    start = client.post(f"/sessions/{sid}/start", json={}).json()
    assert start["scene_debug"]["fallback_used"]
    assert "sealed letter" not in start["scene"]["narrative_body"]
    def advance(action):
        assert client.post("/chat", json={"session_id": sid, "message": action}).status_code == 201
        result = client.post(f"/sessions/{sid}/advance-scene", json={})
        assert result.status_code == 200, result.text
        return result.json()
    asked = advance("I ask Ada Reed when she last wound the watch.")
    assert "I can't give you a reliable answer" in asked["scene"]["narrative_body"]
    assert "I don't have enough information" in asked["scene"]["narrative_body"]
    assert asked["simulation_debug"]["scene_validator"]["fallback_used"]
    moved = advance("I leave the workshop and go to the village square.")
    assert moved["scene"]["location"] == "village square"
    assert "reaches village square" in moved["scene"]["narrative_body"]
    assert moved["scene"]["content_bundle"]["required_content"]["approved_object"] == "stopped brass pocket watch"
    assert "Milo Thorne" not in moved["scene"]["narrative_body"]
    assert "broken pocket watch" not in moved["scene"]["narrative_body"]


def test_local_inference_gate_queues_calls_and_releases_on_error(monkeypatch):
    from importlib import reload
    real_chat_complete = reload(steward_llm).chat_complete
    monkeypatch.setenv("OLLAMA_HOST", "http://local-model.invalid")
    monkeypatch.delenv("TAVERNTAILS_LLM_MAX_CONCURRENCY", raising=False)
    entered, release, second = Event(), Event(), Event()
    calls = []
    def complete(messages, **kwargs):
        calls.append(messages[0]["content"])
        if len(calls) == 1:
            entered.set()
            assert release.wait(2)
            raise RuntimeError("provider error")
        second.set()
        return "ok"
    monkeypatch.setattr(steward_llm, "_chat_complete", complete)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(real_chat_complete, [{"content": "first"}])
        assert entered.wait(2)
        later = pool.submit(real_chat_complete, [{"content": "second"}])
        assert not second.wait(.05)
        release.set()
        with pytest.raises(RuntimeError):
            first.result()
        assert later.result() == "ok"
    assert calls == ["first", "second"]


def test_writer_may_shorten_the_established_object_but_not_swap_it():
    from server.agents.narrative import mentions_object

    obj = "stopped brass pocket watch"
    assert mentions_object("Ada turns the watch over in her palm.", obj)
    assert mentions_object("The brass pocket watch ticks once.", obj)
    assert mentions_object("The stopped brass pocket watch rests there.", obj)
    assert not mentions_object("A sealed letter lies on the bench.", obj)
    assert not mentions_object("Ada is watching the door.", obj)


def test_grounded_draft_missing_only_the_problem_cue_is_kept():
    from server.agents.narrative import soft_shortfall_only
    from server.agents.narrative_linter import score_scene

    text = (
        "The brass pocket watch lies open on Ada Reed's workbench at Alderbrook village, its casing "
        "smeared with a faint residue. The air smells of old wood and oil. Ada slams her palm on the "
        "bench and the watch jumps."
    )
    result = score_scene(text, title="Alderbrook village")
    assert result.failed_checks == ["No immediate concrete problem"] or not soft_shortfall_only(result)
    result.failed_checks = ["No immediate concrete problem"]
    result.banned_phrases_found = []
    result.has_location = result.has_named_npc = result.has_visible_event = result.has_sensory_detail = True
    result.score = 61
    assert soft_shortfall_only(result)
    result.banned_phrases_found = ["something is wrong"]
    assert not soft_shortfall_only(result)
    result.banned_phrases_found = []
    result.has_named_npc = False
    assert not soft_shortfall_only(result)


def test_continuation_schema_asks_for_action_resolutions_but_opening_does_not():
    import json

    from server.agents.scene_director import _CONTINUATION_SCHEMA, _SCHEMA

    assert "action_resolutions" in json.loads(_CONTINUATION_SCHEMA)
    assert "action_resolutions" not in json.loads(_SCHEMA)
