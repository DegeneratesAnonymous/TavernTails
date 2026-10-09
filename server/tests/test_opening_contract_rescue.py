"""A model-written opening is kept when it fails only style checks; the template is the last resort."""
from __future__ import annotations

from server.agents import sessions

BRIEF_SENTENCE = "Old River Road Toll Crossing is a weathered stone bridge with a small wooden toll booth."
MODEL_PROSE = (
    f"Brother Anselm reaches the bridge as the fog lifts. {BRIEF_SENTENCE} "
    "A wagon creaks in with its driver slumped, and Eldrin Voss waves it to a stop before the barrier."
)


def _scene(fallback_used: bool = False) -> dict:
    return {
        "narrative_body": MODEL_PROSE, "text": MODEL_PROSE + "\n\nWhat does Brother Anselm do?",
        "player_prompt": "What does Brother Anselm do?", "choices": [{"id": "a", "label": "Search the wagon"}],
        "generation_debug": {"fallback_used": fallback_used},
    }


def _validation(**failed):
    checks = dict.fromkeys(("mentions_character", "mentions_location", "sensory_detail", "concrete_npc_object", "personal_hook", "pressure_timer", "three_grounded_options", "no_forbidden", "no_brief_repetition", "no_internal_language", "well_formed", "claims_supported"), True)
    checks.update(dict.fromkeys(failed, False))
    return {"valid": not failed, "issues": [f"{n} failed" for n in failed], "checks": checks,
            "repeated_brief_sentences": [BRIEF_SENTENCE] if "no_brief_repetition" in failed else [],
            "unsupported_claims": [], "internal_language": [], "malformed_sentences": []}


def _apply(monkeypatch, results, scene):
    queue = list(results)
    monkeypatch.setattr(sessions, "validate_opening_scene_contract", lambda **k: queue.pop(0) if len(queue) > 1 else queue[0])
    return sessions._apply_concrete_opening_scene_contract(
        scene, required={"starting_location": "Old River Road Toll Crossing"}, opening_anchor={},
        campaign_brief={"location_name": "Old River Road Toll Crossing"}, player_name="Brother Anselm", time_of_day="day",
    )


def test_copied_brief_sentence_is_trimmed_and_the_model_prose_survives(monkeypatch):
    result, validation = _apply(monkeypatch, [_validation(no_brief_repetition=True), _validation()], _scene())
    assert BRIEF_SENTENCE not in result["narrative_body"]
    assert "Eldrin Voss waves it to a stop" in result["narrative_body"]
    assert result["generation_debug"]["fallback_used"] is False and result["generation_debug"]["brief_repetition_removed"]
    assert validation["valid"] and "repair_applied" not in validation


def test_missing_personal_hook_or_timer_alone_does_not_discard_model_prose(monkeypatch):
    result, validation = _apply(monkeypatch, [_validation(personal_hook=True, pressure_timer=True)], _scene())
    assert result["narrative_body"] == MODEL_PROSE
    assert result["generation_debug"]["fallback_used"] is False
    assert validation["valid"] and validation["optional_unestablished_checks"] == ["personal_hook", "pressure_timer"]


def test_a_real_failure_still_falls_back_to_the_template(monkeypatch):
    result, validation = _apply(monkeypatch, [_validation(mentions_location=True), _validation()], _scene())
    assert result["generation_debug"]["fallback_used"] is True
    assert result["generation_debug"]["fallback_reason"] == "opening_contract_repair"
    assert result["narrative_body"] != MODEL_PROSE and validation["repair_applied"]


def test_a_scene_that_was_already_a_fallback_is_never_rescued(monkeypatch):
    result, _ = _apply(monkeypatch, [_validation(personal_hook=True), _validation()], _scene(fallback_used=True))
    assert result["generation_debug"]["fallback_reason"] == "opening_contract_repair"


def test_trimming_refuses_to_gut_a_mostly_copied_draft():
    gutted = {"narrative_body": BRIEF_SENTENCE + " Yes.", "player_prompt": "", "generation_debug": {"fallback_used": False}}
    assert sessions._strip_repeated_brief_sentences(gutted, [BRIEF_SENTENCE]) is gutted


def test_a_draft_missing_the_named_person_is_completed_not_replaced(monkeypatch):
    contract = {"named_npcs": ["Elias Vane"], "key_objects_or_clues": ["fresh footprints"],
                "pressure_or_timer": "Before the tide turns, the tower floods.", "personal_hook": ""}
    monkeypatch.setattr(sessions, "build_opening_scene_contract", lambda **k: contract)
    result, validation = _apply(monkeypatch, [_validation(concrete_npc_object=True), _validation()], _scene())
    assert result["generation_debug"]["fallback_used"] is False
    assert result["generation_debug"]["contract_sentences_added"] == ["concrete_npc_object"]
    assert MODEL_PROSE in result["narrative_body"] and "Elias Vane is close enough to see all of it." in result["narrative_body"]
    assert validation["valid"]


def test_completion_that_still_fails_a_hard_check_falls_back(monkeypatch):
    contract = {"named_npcs": ["Elias Vane"], "pressure_or_timer": "", "personal_hook": ""}
    monkeypatch.setattr(sessions, "build_opening_scene_contract", lambda **k: contract)
    result, _ = _apply(monkeypatch, [_validation(concrete_npc_object=True), _validation(mentions_location=True), _validation()], _scene())
    assert result["generation_debug"]["fallback_reason"] == "opening_contract_repair"
