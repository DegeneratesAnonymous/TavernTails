from server.agents.scene_qa import (
    apply_targeted_scene_repairs,
    build_scene_truth_table,
    classify_opening_shape,
    run_scene_qa,
    score_specificity,
    validate_player_action_continuity,
)
from server.agents.scene_beat_selector import select_scene_beat_plan
from server.scripts.scene_quality_regression import run_quality_regression


def _bundle():
    return {
        "required_content": {
            "starting_location": "The Frostmark Road Shrine",
            "location_type": "winter road shrine",
            "location_identity": "A wind-scoured roadside shrine where blackened silver charms hang from ice-stiff cords.",
            "inciting_event": "A bloodied survivor collapses beneath the shrine and presses a forgotten symbol into the snow.",
            "named_npc_or_visible_threat": "Hadwin Crowe (winter survivor)",
            "immediate_problem": "The early winter is cutting off the road, and the survivor's symbol matches charms that failed overnight.",
            "specific_stakes": "If ignored, the next settlement loses its road, trade, and last witness before nightfall.",
            "first_clue_or_question": "Why did the old silver charms blacken before the survivor arrived?",
            "player_decision": "Aid the survivor, inspect the blackened charms, or follow the frozen tracks.",
        }
    }


def _scene(text: str | None = None):
    narrative = text or (
        "The Frostmark Road Shrine is no place for comfort. Blackened silver charms hang from ice-stiff cords.\n\n"
        "A bloodied survivor named Hadwin Crowe presses a forgotten symbol into the snow.\n\n"
        "The clue is clear: why did the old silver charms blacken before the survivor arrived? "
        "If ignored, the next settlement loses its road, trade, and last witness before nightfall."
    )
    return {
        "title": "Opening — The Frostmark Road Shrine",
        "narrative_body": narrative,
        "player_prompt": "What does the party do?",
        "text": f"{narrative}\n\nWhat does the party do?",
        "choices": [{"id": "inspect", "label": "Inspect the blackened charms"}],
        "suggested_actions": ["Inspect the blackened charms", "Aid Hadwin Crowe"],
        "world_moves": ["The next settlement loses its road before nightfall."],
        "location": "The Frostmark Road Shrine",
        "visible_clues": ["Why did the old silver charms blacken before the survivor arrived?"],
        "immediate_stakes": "If ignored, the next settlement loses its road, trade, and last witness before nightfall.",
        "scene_director_data": {
            "location": {"name": "The Frostmark Road Shrine", "type": "winter road shrine"},
            "primary_npc": {"name": "Hadwin Crowe", "role": "winter survivor"},
            "central_conflict": "The winter road is closing.",
            "inciting_incident": "A bloodied survivor collapses beneath the shrine.",
            "immediate_stakes": "If ignored, the next settlement loses its road, trade, and last witness before nightfall.",
            "player_visible_clues": ["Why did the old silver charms blacken before the survivor arrived?"],
            "possible_actions": ["Inspect the blackened charms", "Aid Hadwin Crowe", "Follow the frozen tracks"],
        },
    }


def test_specificity_scoring_rewards_campaign_details_and_penalizes_generic_language():
    truth = build_scene_truth_table(scene=_scene(), content_bundle=_bundle())
    good_score, good_failures = score_specificity(_scene()["text"], truth, {
        "recurring_symbols": ["blackened silver"],
        "sensory_palette": ["cold iron"],
        "preferred_concrete_nouns": ["charm", "shrine"],
    })
    bad_score, bad_failures = score_specificity(
        "Something dangerous is happening. Someone needs help before things will get worse.",
        truth,
        {},
    )

    assert good_score > bad_score
    assert good_score >= 70
    assert any("Generic language" in failure for failure in bad_failures)
    assert not any("Generic language" in failure for failure in good_failures)


def test_scene_qa_fails_generic_scene_and_repair_adds_truth_table_content():
    generic = _scene("Something dangerous is happening at a place. Someone needs help and things will get worse.")
    qa = run_scene_qa(
        scene=generic,
        campaign_contract={"campaign_pitch": "Frozen roads and blackened silver charms."},
        scene_beat_plan={"scene_type": "campaign_opening", "gm_move": "reveal_clue", "primary_scene_purpose": "seed_thread"},
        content_bundle=_bundle(),
    )

    assert qa["pass"] is False
    assert "location_identity" in qa["repair_targets"]
    repaired = apply_targeted_scene_repairs(generic, qa, player_name="the party")
    repaired_text = repaired["text"].lower()
    assert "the frostmark road shrine" in repaired_text
    assert "blackened" in repaired_text
    assert "next settlement loses its road" in repaired_text


def test_opening_shape_detects_noun_swapped_messenger_packet_pattern():
    bad = _scene(
        "At the Docking Concourse, Quartermaster Vale arrives visibly shaken with a sealed dispatch tube. "
        "Something went wrong and she needs help but is not saying everything."
    )
    shape = classify_opening_shape(bad, {"required_content": {"inciting_event": "A messenger arrives too late.", "named_npc_or_visible_threat": "Quartermaster Vale", "specific_stakes": "hidden information urgency"}})

    assert shape["opening_shape"] == "named_npc_arrives_with_object_and_warning"
    assert shape["inciting_event_type"] == "late_message"
    assert shape["object_type"] == "sealed_message"


def test_continuity_validator_requires_response_to_player_action():
    bad = _scene("Mira looks around nervously and asks for help.")
    score, failures, repairs = validate_player_action_continuity(
        recent_player_actions=["I inspect the packet seal."],
        current_scene=_scene(),
        new_scene=bad,
        content_bundle=_bundle(),
    )

    assert score < 75
    assert failures
    assert "continuity" in repairs


def test_scene_beat_plan_includes_gm_move_and_primary_purpose():
    beat = select_scene_beat_plan({
        "session_storyboard": {
            "session_id": "s",
            "campaign_id": "c",
            "candidate_beats": [{"beat_type": "mystery_clue", "thread": "Blackened charms"}],
        },
        "campaign_storyboard": {
            "campaign_id": "c",
            "central_question": "Why did charms blacken?",
            "open_threads": ["Blackened charms"],
        },
        "player_intent": {"declared_actions": ["I inspect the shrine"], "requested_mode": "investigation"},
    })

    assert beat["gm_move"] == "reveal_clue"
    assert beat["primary_scene_purpose"] == "reveal_clue"


def test_regression_harness_reports_required_quality_fields():
    report = run_quality_regression(runs_per_seed=1)

    assert len(report) == 9
    for item in report:
        assert item["campaign_seed"]
        assert item["runs"] == 1
        assert item["average_quality_score"] >= 70
        assert isinstance(item["freshness_failures"], list)
        assert isinstance(item["specificity_failures"], list)
        assert isinstance(item["continuity_failures"], list)
        assert isinstance(item["repeated_shapes"], list)
        assert item["stale_data_leaks"] == []
