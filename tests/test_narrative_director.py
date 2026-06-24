"""Tests for the Narrative Director and Story Validator.

Run with: python -m pytest tests/test_narrative_director.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.agents.story_state import (
    CampaignStoryState,
    CharacterHook,
    ConsequenceState,
    EmotionalState,
    ForeshadowElement,
    SceneHistoryEntry,
    StoryMetrics,
    ThreadState,
    derive_campaign_dna,
    story_dashboard_payload,
    sync_threads_from_entities,
    thread_health_score,
    update_state_after_scene,
)
from server.agents.narrative_director import (
    DirectorOutput,
    _deterministic_director,
    _find_most_neglected_thread,
    _recent_consecutive,
    _recommend_scene_type_for_variety,
    _type_count_in_recent,
)
from server.agents.story_validator import validate_story_quality


def _make_state(**kwargs) -> CampaignStoryState:
    """Build a minimal story state for testing."""
    return CampaignStoryState(
        campaign_id="test-campaign",
        scene_count=kwargs.get("scene_count", 5),
        metrics=kwargs.get("metrics", StoryMetrics()),
        emotional_state=kwargs.get("emotional_state", EmotionalState()),
        scene_history=kwargs.get("scene_history", []),
        threads=kwargs.get("threads", {}),
        character_hooks=kwargs.get("character_hooks", []),
        consequences=kwargs.get("consequences", []),
    )


def _make_history(scene_types: list[str]) -> list[SceneHistoryEntry]:
    return [
        SceneHistoryEntry(
            scene_number=i + 1,
            scene_type=t,
            scene_purpose="Advance Plot",
            tension_before=40,
            tension_after=40,
        )
        for i, t in enumerate(scene_types)
    ]


# ---------------------------------------------------------------------------
# 1. Consecutive type detection
# ---------------------------------------------------------------------------

def test_consecutive_detection_trailing():
    history = _make_history(["Social", "Combat", "Combat", "Combat"])
    count = _recent_consecutive(history, "Combat")
    assert count == 3, "Should count 3 consecutive trailing Combat scenes"


def test_consecutive_detection_stops_at_different_type():
    history = _make_history(["Combat", "Combat", "Social", "Combat"])
    count = _recent_consecutive(history, "Combat")
    assert count == 1, "Consecutive count stops at the first non-matching entry"


# ---------------------------------------------------------------------------
# 2. Variety recommendation avoids dominant type
# ---------------------------------------------------------------------------

def test_variety_avoids_dominant_type():
    history = _make_history(["Combat", "Combat", "Combat", "Combat"])
    state = _make_state(scene_history=history, metrics=StoryMetrics(tension=50))
    recommendation = _recommend_scene_type_for_variety(history, tension=50)
    assert recommendation != "Combat", "Should not recommend another Combat scene"


def test_variety_recommends_relief_at_high_tension():
    state = _make_state(metrics=StoryMetrics(tension=80))
    recommendation = _recommend_scene_type_for_variety([], tension=80)
    assert recommendation in ("Social", "Downtime", "Consequence", "Investigation"), \
        f"High tension should recommend a relief scene, got {recommendation}"


# ---------------------------------------------------------------------------
# 3. Thread health scoring
# ---------------------------------------------------------------------------

def test_thread_health_importance_matters():
    important_thread = ThreadState(title="Main Arc", importance=9, last_progressed_scene=0)
    minor_thread = ThreadState(title="Side Quest", importance=2, last_progressed_scene=0)
    high_health = thread_health_score(important_thread, current_scene=6)
    low_health = thread_health_score(minor_thread, current_scene=6)
    assert high_health > low_health, "Higher-importance threads should have higher health urgency"


def test_neglected_thread_flagged_for_attention():
    thread = ThreadState(title="Missing Caravans", importance=8, last_progressed_scene=0)
    health = thread_health_score(thread, current_scene=10)
    assert health > 70, f"Thread neglected for 10 scenes should have high health urgency ({health})"


def test_recently_progressed_thread_not_flagged():
    thread = ThreadState(title="Side Quest", importance=5, last_progressed_scene=9)
    health = thread_health_score(thread, current_scene=10)
    assert health < 70, f"Recently progressed thread should have low urgency ({health})"


# ---------------------------------------------------------------------------
# 4. Deterministic Director — recommends variety after consecutive combat
# ---------------------------------------------------------------------------

def test_director_recommends_variety_after_consecutive_combat():
    history = _make_history(["Combat", "Combat", "Combat", "Combat"])
    state = _make_state(scene_count=4, scene_history=history, metrics=StoryMetrics(tension=50))
    output = _deterministic_director(state)
    assert output.recommended_scene_type != "Combat", \
        f"Director should not recommend Combat after 4 consecutive combats, got {output.recommended_scene_type}"


# ---------------------------------------------------------------------------
# 5. High tension triggers relief recommendation
# ---------------------------------------------------------------------------

def test_high_tension_triggers_relief_recommendation():
    state = _make_state(metrics=StoryMetrics(tension=85))
    output = _deterministic_director(state)
    # Director should either recommend a reducing scene or set a lower target tension
    assert output.target_tension < 85, \
        f"High tension should lower target tension, got {output.target_tension}"


# ---------------------------------------------------------------------------
# 6. Consequence scene recommended when critical consequence is pending
# ---------------------------------------------------------------------------

def test_pending_critical_consequence_triggers_consequence_scene():
    cons = ConsequenceState(action="Insulted the Duke", scene=2, severity="critical", consequence_due=True)
    state = _make_state(scene_count=6, consequences=[cons])
    output = _deterministic_director(state)
    assert output.recommended_consequence == "Insulted the Duke", \
        "Pending critical consequence should appear in director recommendation"


# ---------------------------------------------------------------------------
# 7. Story Validator — rewards concrete scenes with named entities
# ---------------------------------------------------------------------------

def test_validator_rewards_concrete_scene():
    state = _make_state()
    state.campaign_dna.themes = ["survival", "corruption"]
    director = DirectorOutput(
        recommended_scene_type="Investigation",
        scene_purpose="Build Mystery",
        target_tension=50,
    )
    scene_text = (
        "At the Greyford Market, dawn mist clings to the cobblestones. "
        "Captain Voss stands at the entrance, desperate. Three caravans have vanished. "
        "The smell of blood hangs in the air near the eastern gate. "
        "A survival instinct kicks in — someone with power is hiding the truth. "
        "There is corruption at the heart of this city."
    )
    result = validate_story_quality(
        scene_text=scene_text,
        director=director,
        state=state,
        scene_type="Investigation",
        npc_names=["Captain Voss"],
        location_names=["Greyford Market"],
    )
    assert result.score >= 40, f"Concrete scene should score reasonably, got {result.score}"
    assert any("Concrete" in b[0] for b in result.bonuses), "Should receive Concrete Scene bonus"


# ---------------------------------------------------------------------------
# 8. Story Validator — penalizes meta narration
# ---------------------------------------------------------------------------

def test_validator_penalizes_meta_narration():
    state = _make_state()
    director = DirectorOutput(recommended_scene_type="Social", scene_purpose="Develop Character", target_tension=30)
    scene_text = (
        "Your adventure begins in a mysterious land. "
        "The story takes a turn as you discover your destiny awaits. "
        "The choices you make will matter as the paths branch ahead."
    )
    result = validate_story_quality(scene_text=scene_text, director=director, state=state)
    assert any("Meta" in p[0] for p in result.penalties), "Meta narration must be penalized"
    assert any("Generic" in p[0] for p in result.penalties), "Generic fantasy must be penalized"


# ---------------------------------------------------------------------------
# 9. Campaign DNA derived from settings
# ---------------------------------------------------------------------------

def test_campaign_dna_derived_from_settings():
    settings = {"genre": "dark political", "tone": "gritty", "setting_summary": "A corrupt city rife with war"}
    variables = {"themes": ["betrayal"]}
    dna = derive_campaign_dna(settings, variables)
    assert len(dna.themes) > 0, "Should derive at least one theme"
    assert any("corrupt" in t.lower() or t in ("survival", "corruption", "betrayal", "power") for t in dna.themes), \
        f"Expected political/dark themes, got {dna.themes}"
    assert len(dna.recurring_moods) > 0, "Should derive at least one mood"


# ---------------------------------------------------------------------------
# 10. State update after scene correctly tracks tension
# ---------------------------------------------------------------------------

def test_state_update_tracks_tension():
    state = _make_state(metrics=StoryMetrics(tension=40))
    director = DirectorOutput(target_tension=70, recommended_scene_type="Combat", scene_purpose="Escalate Conflict")
    updated = update_state_after_scene(
        state=state,
        scene_type="Combat",
        scene_purpose="Escalate Conflict",
        scene_id="test-001",
        location="Greyford Market",
        npcs_featured=["Captain Voss"],
        threads_advanced=[],
        threads_resolved=[],
        emotional_target={"fear": 60, "urgency": 70},
        director_tension_target=70,
        story_score=85,
    )
    assert updated.metrics.tension > 40, "Tension should increase after Combat scene"
    assert updated.scene_count == 6, "Scene count should increment"
    assert len(updated.scene_history) == 1, "Scene history should record the entry"
    assert updated.scene_history[0].scene_type == "Combat"


# ---------------------------------------------------------------------------
# 11. Thread sync from DB entities
# ---------------------------------------------------------------------------

def test_sync_threads_from_entities():
    state = _make_state()
    entities = [
        {"title": "Missing Caravans", "priority": 8},
        {"title": "Corrupt Noble", "priority": 6},
    ]
    updated = sync_threads_from_entities(state, entities)
    assert "Missing Caravans" in updated.threads
    assert "Corrupt Noble" in updated.threads
    assert updated.threads["Missing Caravans"].importance == 8


# ---------------------------------------------------------------------------
# 12. Dashboard payload is JSON-serializable
# ---------------------------------------------------------------------------

def test_dashboard_payload_serializable():
    import json
    state = _make_state(
        threads={"Main Arc": ThreadState(title="Main Arc", importance=9, stage="Investigation")},
    )
    payload = story_dashboard_payload(state)
    assert "metrics" in payload
    assert "threads" in payload
    json.dumps(payload)
