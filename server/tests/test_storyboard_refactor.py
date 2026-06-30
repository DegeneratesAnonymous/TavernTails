from server.agents.storyboard import (
    CampaignStoryboard,
    PacingPatternState,
    SceneBeatSelectionInput,
    beat_type_library,
    create_campaign_storyboard,
    generate_plot,
    generate_session_storyboard,
    select_scene_beat,
    update_storyboards_after_scene,
    StoryboardPlotRequest,
)
from server.agents.content_bundles import build_content_bundle


def _campaign() -> CampaignStoryboard:
    return create_campaign_storyboard(
        campaign_id="camp-1",
        campaign_premise="A slow-burn mystery about missing bells and a river cult.",
        central_question="Who is stealing the drowned bells?",
        major_threat="The River Choir",
        major_factions=["River Choir", "Bridge Wardens"],
        open_threads=["The drowned bells are disappearing"],
        backstory_hooks_available=["Mira's lost sibling heard the bells"],
    )


def test_session_storyboard_generates_candidate_beats():
    session = generate_session_storyboard("s-1", _campaign(), {"pacing_profile": "slow-burn"})

    assert session.session_goal
    assert session.desired_tension_curve
    assert session.candidate_beats
    assert any(beat["beat_type"] in {"mystery_clue", "investigation"} for beat in session.candidate_beats)


def test_plot_hooks_ignore_campaign_contract_headings():
    plot = generate_plot(StoryboardPlotRequest(
        campaign_id="contract-heading",
        campaign_name="Salt, Steel, and Sorcery",
        campaign_premise="A grim frontier campaign where mercenary survivors owe a debt to a dangerous house.",
        campaign_docs=[
            "[Campaign Contract]\n"
            "CAMPAIGN OUTPUT CONTRACT\n"
            "Requirements:\n"
            "A noble patron has disappeared near a salt road guarded by rival soldiers."
        ],
    ))

    storyboard = plot["campaign_storyboard"] if isinstance(plot, dict) else plot.campaign_storyboard
    hooks = [hook.lower() for hook in storyboard["open_threads"]]
    assert not any(hook in {"campaign contract", "campaign output contract", "requirements"} for hook in hooks)
    assert any("noble patron" in hook or "salt road" in hook for hook in hooks)


def test_scene_beat_selector_avoids_repeated_scene_types():
    campaign = _campaign()
    session = generate_session_storyboard("s-1", campaign)
    session.candidate_beats = [
        {"beat_type": "mystery_clue", "thread": campaign.open_threads[0]},
        {"beat_type": "social_pressure", "thread": campaign.open_threads[0]},
    ]

    result = select_scene_beat(SceneBeatSelectionInput(
        session_storyboard=session,
        campaign_storyboard=campaign,
        recent_scene_types=["investigation", "investigation", "investigation"],
        recent_patterns=PacingPatternState(recent_scene_types=["investigation", "investigation"]),
    ))

    assert result.beat_type_chosen != "mystery_clue"
    assert result.rejected_candidate_beats


def test_beat_selector_respects_player_action():
    campaign = _campaign()
    session = generate_session_storyboard("s-1", campaign)

    result = select_scene_beat(SceneBeatSelectionInput(
        session_storyboard=session,
        campaign_storyboard=campaign,
        player_actions=["I search the bell tower for clues"],
    ))

    assert result.beat_type_chosen == "investigation"
    assert "player action" in result.beat_selection_reason


def test_beat_selector_does_not_force_ignored_hooks():
    campaign = _campaign()
    session = generate_session_storyboard("s-1", campaign)
    session.candidate_beats = [
        {"beat_type": "npc_request", "hook": "meet the patron"},
        {"beat_type": "discovery", "thread": campaign.open_threads[0]},
    ]
    campaign.do_not_force.append("npc_request")

    result = select_scene_beat(SceneBeatSelectionInput(
        session_storyboard=session,
        campaign_storyboard=campaign,
    ))

    assert result.beat_type_chosen != "npc_request"
    assert any(r["reason"] == "listed in do_not_force" for r in result.rejected_candidate_beats)


def test_campaign_opening_avoids_tavern_inn_defaults_unless_requested():
    response = generate_plot(StoryboardPlotRequest(
        session_id="s-1",
        players=["Yungmin"],
        campaign_settings={"genre": "fantasy", "setting_summary": "A mountain pass under siege"},
        campaign_variables={},
        campaign_docs=[],
    ))

    text = " ".join([
        response.plot,
        str(response.campaign_storyboard),
        str(response.session_storyboard),
    ]).lower()
    assert "tavern" not in text
    assert " inn" not in text


def test_mystery_campaign_preserves_unanswered_questions():
    campaign = _campaign()
    session = generate_session_storyboard("s-1", campaign, {"pacing_profile": "slow-burn mystery"})
    result = select_scene_beat(SceneBeatSelectionInput(
        session_storyboard=session,
        campaign_storyboard=campaign,
    ))

    plan = result.selected_plan
    assert plan.required_content_bundle == "InvestigationBundle"
    assert "do not reveal mysteries before earned clues" in plan.must_not_include
    assert campaign.central_question


def test_combat_beat_requests_combat_bundle():
    library = beat_type_library()
    assert library["combat_threat"].required_content_bundle == "CombatBundle"
    assert library["combat_threat"].preferred_situation_contract == "combat_setup"


def test_interrogation_beat_requests_dialogue_bundle():
    library = beat_type_library()
    assert library["social_pressure"].required_content_bundle == "DialogueBundle"
    assert library["npc_conflict"].required_content_bundle == "DialogueBundle"


def test_investigation_beat_requests_investigation_bundle():
    library = beat_type_library()
    assert library["mystery_clue"].required_content_bundle == "InvestigationBundle"
    assert library["investigation"].required_content_bundle == "InvestigationBundle"


def test_backstory_callback_respects_backstory_policy():
    campaign = _campaign()
    session = generate_session_storyboard("s-1", campaign)
    session.candidate_beats = [
        {"beat_type": "backstory_callback", "thread": "Mira's lost sibling heard the bells"},
        {"beat_type": "discovery", "thread": campaign.open_threads[0]},
    ]

    result = select_scene_beat(SceneBeatSelectionInput(
        session_storyboard=session,
        campaign_storyboard=campaign,
        backstory_spotlight_tracker={"policy": "disabled"},
    ))

    assert result.beat_type_chosen != "backstory_callback"


def test_update_storyboards_records_ignored_hook_as_do_not_force():
    campaign = _campaign()
    session = generate_session_storyboard("s-1", campaign)
    plan = select_scene_beat(SceneBeatSelectionInput(
        session_storyboard=session,
        campaign_storyboard=campaign,
    )).selected_plan

    updated_campaign, updated_session = update_storyboards_after_scene(
        campaign,
        session,
        plan,
        player_intent="The player avoids the patron and follows the bells.",
        ignored_hooks=["meet the patron"],
        unresolved_questions=["Why do the bells ring underwater?"],
    )

    assert "meet the patron" in updated_campaign.do_not_force
    assert "meet the patron" in updated_session.do_not_force
    assert "Why do the bells ring underwater?" in updated_campaign.open_threads
    assert updated_campaign.active_clocks


def test_content_bundle_mapping_supports_new_bundle_names():
    threat = build_content_bundle("resource_pressure")
    backstory = build_content_bundle("backstory_callback")

    assert threat["bundle_type"] == "ThreatBundle"
    assert backstory["bundle_type"] == "BackstoryHookBundle"
