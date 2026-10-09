from __future__ import annotations

import json

from server.agents import premise_seed
from server.agents import sessions as sessions_module
from server.tests.test_opening_setup import _auth, _client, _create_campaign_session

PREMISE = {"setting_summary": "A toll crossing on the old river road where a merchant caravan vanished two nights ago. "
                              "I want the opening to begin at dawn when its lead wagon rolls in empty.", "genre": "fantasy"}

GOOD = {
    "starting_location": "Old River Road Toll Crossing", "location_type": "toll crossing",
    "location_identity": "A weathered stone bridge with a wooden tollhouse beside the old river road.",
    "inciting_event": "The lead wagon of a merchant caravan rolls in empty at dawn.",
    "named_npc_or_visible_threat": "Eldrin Voss (toll collector)",
    "immediate_problem": "The wagon is empty and its driver is missing.",
    "specific_stakes": "If the caravan is not found, trade on the road stops.",
    "first_clue_or_question": "What happened to the driver?",
    "player_decision": "Search the wagon, question Eldrin, or follow the ruts.",
}


def _complete(payload):
    return lambda *a, **k: payload if isinstance(payload, str) or payload is None else json.dumps(payload)


def test_extracts_a_seed_from_the_players_premise_in_the_shape_the_opening_uses():
    seed = premise_seed.extract_premise_seed(PREMISE, {}, complete=_complete(GOOD))
    assert seed["starting_location"] == "Old River Road Toll Crossing"
    assert seed["generated_by"] == "premise_seed" and seed["seed_mode"] == "premise_model"
    assert seed["memory_updates"][1] == {"type": "npc", "name": "Eldrin Voss", "status": "campaign_opening"}
    assert "toll crossing" in seed["premise_anchor"]


def test_tolerates_model_wrapping_and_adds_a_role_when_missing():
    wrapped = "<think>planning</think>Here you go:\n```json\n" + json.dumps({**GOOD, "named_npc_or_visible_threat": "Eldrin Voss"}) + "\n```"
    seed = premise_seed.extract_premise_seed(PREMISE, {}, complete=_complete(wrapped))
    assert seed["named_npc_or_visible_threat"] == "Eldrin Voss (local contact)"


def test_rejects_answers_that_ignore_the_premise_or_are_incomplete():
    ungrounded = {**GOOD, "starting_location": "Coldwater Temple", "location_identity": "A temple of the old gods.",
                  "inciting_event": "A prophecy is read aloud."}
    assert premise_seed.extract_premise_seed(PREMISE, {}, complete=_complete(ungrounded)) is None
    assert premise_seed.extract_premise_seed(PREMISE, {}, complete=_complete({**GOOD, "player_decision": ""})) is None
    assert premise_seed.extract_premise_seed(PREMISE, {}, complete=_complete("not json at all")) is None
    assert premise_seed.extract_premise_seed(PREMISE, {}, complete=_complete(None)) is None


def test_skips_the_call_for_a_premise_too_thin_to_read_and_survives_a_failing_model():
    calls: list[int] = []
    thin = {"setting_summary": "A dark forest", "genre": "fantasy"}
    assert premise_seed.extract_premise_seed(thin, {}, complete=lambda *a, **k: calls.append(1)) is None
    assert calls == []

    def boom(*a, **k):
        raise TimeoutError("model busy")

    assert premise_seed.extract_premise_seed(PREMISE, {}, complete=boom) is None


def test_the_opening_questionnaire_uses_the_players_premise(monkeypatch):
    monkeypatch.setattr(sessions_module, "extract_premise_seed", lambda *a, **k: premise_seed.extract_premise_seed(PREMISE, {}, complete=_complete(GOOD)))
    client = _client()
    email = "premise-seed@example.com"
    session_id, _ = _create_campaign_session(client, email, "Premise Scout")
    brief = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email)).json()["questionnaire"]["campaign_brief"]
    assert brief["location_name"] == "Old River Road Toll Crossing"
    meta = json.loads((sessions_module.BASE / session_id / "meta.json").read_text())
    assert meta["opening_setup"]["seed"]["starting_location"] == "Old River Road Toll Crossing"


def test_a_failed_extraction_keeps_the_pool_seed(monkeypatch):
    monkeypatch.setattr(sessions_module, "extract_premise_seed", lambda *a, **k: None)
    client = _client()
    email = "premise-seed-fallback@example.com"
    session_id, _ = _create_campaign_session(client, email, "Fallback Scout")
    response = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email))
    assert response.status_code == 200 and response.json()["questionnaire"]["campaign_brief"]["location_name"]
