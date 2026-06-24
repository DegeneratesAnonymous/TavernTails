"""Tests for scene generation quality.

Run with: python -m pytest tests/test_scene_quality.py -v
"""
import sys
from pathlib import Path

# Allow imports from the server package without a full install
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.agents.scene_validator import (
    MINIMUM_SCORE,
    build_fallback_scene,
    validate_scene_quality,
)
from server.agents.scene_director import (
    SceneDirectorRequest,
    _deterministic_director,
)


# ---------------------------------------------------------------------------
# Test Case 1: Empty campaign memory — still produces concrete scene elements
# ---------------------------------------------------------------------------

def test_empty_memory_deterministic_has_required_fields():
    """Deterministic fallback must always produce a location, NPC (or marker), conflict, stakes, prompt."""
    req = SceneDirectorRequest(
        campaign_settings={"genre": "high fantasy", "tone": "gritty"},
        players=["Yungmin"],
    )
    result = _deterministic_director(req)

    assert result.location.name, "location.name must not be empty"
    assert result.central_conflict, "central_conflict must not be empty"
    assert result.inciting_incident, "inciting_incident must not be empty"
    assert result.immediate_stakes, "immediate_stakes must not be empty"
    assert result.possible_actions, "possible_actions must not be empty"
    assert "Yungmin" in result.why_player_is_involved, "player name must appear in why_player_is_involved"


# ---------------------------------------------------------------------------
# Test Case 2: Campaign memory used in scene
# ---------------------------------------------------------------------------

def test_campaign_memory_entities_used():
    """When campaign memory provides NPC + location + thread, they must appear in the director output."""
    req = SceneDirectorRequest(
        campaign_settings={"genre": "dark fantasy", "world_name": "Greyford"},
        players=["Yungmin"],
        candidate_npcs=["Captain Elira Voss"],
        candidate_npc_details=[{
            "name": "Captain Elira Voss",
            "goal": "find the missing caravans",
            "emotional_state": "desperate and road-worn",
            "next_action": "recruit Yungmin for the investigation",
        }],
        candidate_locations=["Greyford Market"],
        candidate_location_details=[{
            "name": "Greyford Market",
            "current_tension": "merchants whispering about missing winter stores",
        }],
        candidate_story_threads=["Three caravans vanished on the North Road last night"],
        open_hooks=["Missing caravans — Iron Banner mercenaries suspected"],
        candidate_factions=["Iron Banner Mercenaries"],
    )
    result = _deterministic_director(req)

    # At minimum, the primary NPC from memory must be selected
    assert result.primary_npc.name == "Captain Elira Voss", (
        f"Expected 'Captain Elira Voss' as primary NPC, got '{result.primary_npc.name}'"
    )
    assert result.location.name == "Greyford Market", (
        f"Expected 'Greyford Market' as location, got '{result.location.name}'"
    )
    # Conflict must come from the active thread / hook
    assert "caravan" in result.central_conflict.lower() or "caravan" in result.inciting_incident.lower(), (
        "Central conflict or inciting incident must reference the missing caravans thread"
    )


# ---------------------------------------------------------------------------
# Test Case 3: Generic narrative → validator scores below threshold
# ---------------------------------------------------------------------------

def test_generic_narrative_fails_validation():
    """A meta-genre narrative must score below MINIMUM_SCORE and trigger retry."""
    generic = (
        "You see a heroic fantasy adventure unfold before you. "
        "A mysterious threat looms on the horizon. "
        "The party must make choices that matter, for outcomes stay flexible in this high fantasy world. "
        "Paths branch ahead. What do you do?"
    )
    score, issues = validate_scene_quality(
        narrative_text=generic,
        location_name="Greyford",
        npc_name="Captain Elira Voss",
        player_name="Yungmin",
    )
    assert score < MINIMUM_SCORE, (
        f"Generic scene scored {score} but should be below {MINIMUM_SCORE}. Issues: {issues}"
    )
    assert issues, "Validator must report at least one issue for a generic scene"


# ---------------------------------------------------------------------------
# Test Case 4: No named entities → validator fails and fallback is used
# ---------------------------------------------------------------------------

def test_no_named_entities_fails_validation():
    """A narrative without named locations or NPCs must score below threshold."""
    no_names = (
        "The settlement is quiet in the early morning. "
        "Someone approaches you with a worried look on their face. "
        "They say something has happened. "
        "Things are tense and the situation seems dangerous. "
        "What do you do?"
    )
    score, issues = validate_scene_quality(
        narrative_text=no_names,
        location_name="Greyford Market",
        npc_name="Captain Elira Voss",
        player_name="Yungmin",
    )
    assert score < MINIMUM_SCORE, (
        f"No-names scene scored {score} but should be below {MINIMUM_SCORE}"
    )
    named_issue = any(
        "proper noun" in i.lower() or "named" in i.lower() or "NPC" in i
        for i in issues
    )
    assert named_issue, f"Validator should flag missing named entities. Issues: {issues}"


# ---------------------------------------------------------------------------
# Test Case 5: Good concrete narrative passes validation
# ---------------------------------------------------------------------------

def test_concrete_narrative_passes_validation():
    """A well-written concrete scene should score at or above MINIMUM_SCORE."""
    good_scene = (
        "Morning mist hangs over the timber roofs of Greyford Market as merchants drag open their shutters. "
        "Captain Elira Voss pushes through the crowd toward Yungmin, her blue cloak torn and dark with road mud. "
        "'Three caravans vanished on the North Road last night,' she says. "
        "'One of them carried winter stores meant for the border villages.' "
        "Behind her, a wounded scout grips a bloodied wolf-pelt charm and whispers, 'They walked like men.' "
        "What does Yungmin do?"
    )
    score, issues = validate_scene_quality(
        narrative_text=good_scene,
        location_name="Greyford Market",
        npc_name="Captain Elira Voss",
        player_name="Yungmin",
        conflict="missing caravans on the North Road",
        campaign_entities=["Captain Elira Voss", "Greyford Market", "Iron Banner Mercenaries"],
    )
    assert score >= MINIMUM_SCORE, (
        f"Good concrete scene scored only {score}/{MINIMUM_SCORE}. Issues: {issues}"
    )


# ---------------------------------------------------------------------------
# Test Case 6: Scene Director visual_prompt_elements used in image prompt
# ---------------------------------------------------------------------------

def test_image_prompt_uses_visual_elements():
    """build_image_prompt must incorporate Scene Director visual_prompt_elements."""
    from server.agents.scene_director import SceneDirectorOutput, LocationBlueprint, NPCBlueprint, build_image_prompt

    sd = SceneDirectorOutput(
        location=LocationBlueprint(
            name="Greyford Market",
            type="outdoor market",
            sensory_details=["cold morning air", "muddy cobblestones"],
        ),
        primary_npc=NPCBlueprint(
            name="Captain Elira Voss",
            role="city watch captain",
            current_emotional_state="desperate",
        ),
        visual_prompt_elements=[
            "timber rooftops",
            "morning mist",
            "wounded scout with wolf-pelt charm",
        ],
    )
    prompt = build_image_prompt(sd, style="gritty realism", weather="clear", time_of_day="dawn")

    assert "Greyford Market" in prompt, "Image prompt must include location name"
    assert "Captain Elira Voss" in prompt, "Image prompt must include primary NPC name"
    assert "timber rooftops" in prompt or "morning mist" in prompt, (
        "Image prompt must include at least one visual_prompt_element"
    )
    assert len(prompt) > 60, "Image prompt must be longer than a trivial stub"


# ---------------------------------------------------------------------------
# Test Case 7: Fallback template is always valid
# ---------------------------------------------------------------------------

def test_fallback_template_passes_validation():
    """The deterministic fallback template must always produce a passable scene."""
    fallback = build_fallback_scene(
        location_name="Greyford Market",
        npc_name="Captain Elira Voss",
        player_name="Yungmin",
        emotional_state="road-worn and pale",
        inciting_incident="Three caravans vanished on the North Road last night.",
        central_conflict="The missing winter stores threaten the border villages with starvation.",
        immediate_stakes="If no one acts, the villages will starve before the next supply run arrives.",
        sensory_detail="The smell of damp wool and smoke hangs in the cold morning air.",
    )
    score, issues = validate_scene_quality(
        narrative_text=fallback,
        location_name="Greyford Market",
        npc_name="Captain Elira Voss",
        player_name="Yungmin",
        conflict="missing caravans",
        campaign_entities=["Captain Elira Voss", "Greyford Market"],
    )
    assert score >= MINIMUM_SCORE, (
        f"Fallback template scored only {score}/{MINIMUM_SCORE}. Issues: {issues}\n\nText:\n{fallback}"
    )
