from server.agents.arc_planner import plan_arc
from server.agents.campaign_interpretation import build_full_contract_package
from server.agents.content_bundles import ensure_content_bundle
from server.agents.player_intent_parser import parse_player_intent
from server.agents.scene import RollRecommendation, SceneAnalysisResponse, check_roll_consistency
from server.agents.scene_director import _contact_from_text, _location_from_text
from server.agents.scene_beat_selector import select_scene_beat_plan


def test_campaign_creation_produces_scale_and_story_shape_profiles():
    package = build_full_contract_package(
        campaign_id="camp-scale",
        campaign_name="The Bell Road",
        description="A standard mystery campaign about vanished bells.",
        settings={"genre": "mystery", "tone": "slow-burn"},
        variables={},
    )

    assert package["campaign_scale_profile"]["campaign_length"] == "standard"
    assert package["story_shape_profile"]["primary_story_model"] == "mystery_web"
    assert package["campaign_contract"]["campaign_scale_profile"]


def test_one_shot_uses_tight_planning_and_low_thread_budget():
    package = build_full_contract_package(
        campaign_id="one",
        campaign_name="One Night at the Gate",
        description="A one-shot single session dungeon mystery.",
        settings={"campaign_length": "one_shot"},
        variables={},
    )
    scale = package["campaign_scale_profile"]
    arc = plan_arc({
        "campaign_contract": package["campaign_contract"],
        "campaign_scale_profile": scale,
        "story_shape_profile": package["story_shape_profile"],
        "campaign_storyboard": {"central_question": "Who opened the gate?"},
        "active_threads": ["Gate opened", "Guard missing", "Old debt", "Strange lights"],
    })

    assert scale["planning_horizon"] == "current_session"
    assert scale["max_open_threads"] <= 3
    assert arc.arc_type == "one_shot"
    assert arc.required_payoffs


def test_endless_does_not_force_final_resolution():
    package = build_full_contract_package(
        campaign_id="endless",
        campaign_name="Open Frontier",
        description="An endless west marches living world sandbox.",
        settings={"campaign_length": "endless"},
        variables={},
    )
    arc = plan_arc({
        "campaign_contract": package["campaign_contract"],
        "campaign_scale_profile": package["campaign_scale_profile"],
        "story_shape_profile": package["story_shape_profile"],
        "campaign_storyboard": {"central_question": "What lies past the home base?"},
        "active_threads": [{"title": "Old trail", "retirement_candidate": True}],
    })

    assert arc.arc_type == "emergent"
    assert "avoid final campaign resolution" in arc.arc_goal.lower()
    assert arc.threads_to_retire == ["Old trail"]


def test_hero_cycle_stages_do_not_force_player_choices():
    package = build_full_contract_package(
        campaign_id="hero",
        campaign_name="Threshold",
        description="A heroic saga.",
        settings={"primary_story_model": "hero_cycle"},
        variables={},
    )
    shape = package["story_shape_profile"]

    assert shape["primary_story_model"] == "hero_cycle"
    assert "player decisions" in shape["stage_do_not_force"]
    assert "never force" in shape["model_notes"].lower()


def test_mystery_web_requires_clue_redundancy():
    package = build_full_contract_package(
        campaign_id="mystery",
        campaign_name="Clue Web",
        description="A mystery of secret ledgers and hidden heirs.",
        settings={},
        variables={},
    )
    arc = plan_arc({
        "campaign_contract": package["campaign_contract"],
        "campaign_scale_profile": package["campaign_scale_profile"],
        "story_shape_profile": package["story_shape_profile"],
        "campaign_storyboard": {"central_question": "Who hid the ledger?"},
    })

    assert package["story_shape_profile"]["primary_story_model"] == "mystery_web"
    assert any("redundant clue" in payoff for payoff in arc.optional_payoffs)


def test_faction_fronts_requires_clocks():
    package = build_full_contract_package(
        campaign_id="fronts",
        campaign_name="Court Fronts",
        description="Political factions fight over the throne.",
        settings={"primary_story_model": "faction_fronts"},
        variables={},
    )
    arc = plan_arc({
        "campaign_contract": package["campaign_contract"],
        "campaign_scale_profile": package["campaign_scale_profile"],
        "story_shape_profile": package["story_shape_profile"],
        "campaign_storyboard": {"central_question": "Which faction takes the court?"},
    })

    assert arc.clocks_to_advance


def test_deterministic_director_avoids_hardcoded_court_defaults():
    premise = "A political campaign about nobles, a fallen throne, and factions circling the crown."

    location = _location_from_text(premise, "fantasy")
    contact = _contact_from_text(premise, "fantasy")

    assert location != "The Outer Court"
    assert contact != "Envoy Marrec"
    assert "court" not in location.lower() or location.lower() != "the outer court"


def test_player_intent_can_override_planned_beat():
    beat = select_scene_beat_plan({
        "session_storyboard": {
            "session_id": "s",
            "campaign_id": "c",
            "candidate_beats": [{"beat_type": "social_pressure", "thread": "The witness lies"}],
        },
        "campaign_storyboard": {
            "campaign_id": "c",
            "central_question": "Who lied?",
            "open_threads": ["The witness lies"],
        },
        "arc_plan": {"do_not_force": []},
        "player_intent": parse_player_intent(["I search the room for clues"]).model_dump(),
    })

    assert beat["scene_type"] == "investigation"
    assert "player action" in beat["selection_reason"]


def test_ignored_hook_is_not_immediately_forced_again():
    beat = select_scene_beat_plan({
        "session_storyboard": {
            "session_id": "s",
            "campaign_id": "c",
            "candidate_beats": [
                {"beat_type": "npc_request", "hook": "meet patron"},
                {"beat_type": "discovery", "thread": "Bell clue"},
            ],
            "do_not_force": ["npc_request"],
        },
        "campaign_storyboard": {
            "campaign_id": "c",
            "central_question": "Why bells?",
            "open_threads": ["Bell clue"],
            "do_not_force": ["npc_request"],
        },
        "arc_plan": {"do_not_force": ["npc_request"]},
    })

    assert beat["scene_type"] != "conversation"


def test_opening_scene_uses_content_bundle_before_prose():
    bundle = ensure_content_bundle(
        situation_type="campaign_opening",
        scene_director_output={},
        campaign_settings={"genre": "fantasy"},
        freshness_context={"scene_count": 0},
    )

    assert bundle["content_gate_passed"] is True
    assert bundle["required_content"]["starting_location"]


def test_content_gate_rejects_recycled_first_crossroads_fixture():
    bundle = ensure_content_bundle(
        situation_type="campaign_opening",
        scene_director_output={
            "location": {"name": "The First Crossroads", "type": "crossroads"},
            "primary_npc": {"name": "Mira Vale"},
            "inciting_incident": "Mira Vale clutches a sealed packet.",
            "central_conflict": "Something has gone very wrong at The First Crossroads.",
            "immediate_stakes": "The sealed packet will be lost by nightfall.",
            "player_visible_clues": ["sealed packet"],
            "possible_actions": ["Open the packet"],
        },
        campaign_settings={"genre": "fantasy", "setting_summary": "A crystal desert under glass storms."},
        freshness_context={"scene_count": 0},
    )

    text = str(bundle["required_content"]).lower()
    assert bundle["content_gate_passed"] is True
    assert "first crossroads" not in text
    assert "mira vale" not in text
    assert "sealed packet" not in text


def test_advance_scene_gate_reports_invalid_bundle():
    bundle = ensure_content_bundle(
        situation_type="combat_setup",
        scene_director_output={"location": {"name": "Empty Field"}},
        world_state={"active_enemies": []},
        max_attempts=1,
    )

    assert bundle["content_gate_passed"] is False
    assert bundle["validation_result"]["missing_required_fields"]


def test_pending_rolls_come_from_content_bundle_consistency():
    bundle = {
        "required_content": {
            "possible_checks": ["Persuasion", "Insight"],
        }
    }
    analysis = SceneAnalysisResponse(
        dice_rolls=[RollRecommendation(type="d20", skill="Persuasion", reason="Talk")],
        prompts=[],
    )
    result = check_roll_consistency(bundle, analysis)

    assert result["valid"] is True
    assert "Insight" in result["supported_but_not_implied"]


def test_scene_analysis_flags_roll_mismatch():
    bundle = {"required_content": {"possible_checks": ["Persuasion"]}}
    analysis = SceneAnalysisResponse(
        dice_rolls=[RollRecommendation(type="d20", skill="Athletics", reason="Climb")],
        prompts=[],
    )
    result = check_roll_consistency(bundle, analysis)

    assert result["valid"] is False
    assert result["unsupported_implied_checks"] == ["Athletics"]
