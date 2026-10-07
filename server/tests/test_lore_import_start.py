"""Imported labelled lore sets where the story starts and what is wrong there."""
from __future__ import annotations

from server.agents.campaign_interpretation import _extract_named_entities
from server.agents.content_bundles import generate_starter_seed
from server.agents.generation_intent import build_opening_intent, starting_location_fact
from server.agents.opening_setup import (
    UNKNOWN_AUTHORITY,
    UNKNOWN_CONSEQUENCE,
    UNKNOWN_OBJECT,
    UNKNOWN_PROBLEM,
    UNKNOWN_URGENCY,
)

LORE = (
    "Location: Alderbrook village — a small village where every clock stopped at breakfast.\n"
    "NPC: Ada Reed — clockmaker with a stopped brass pocket watch on her workbench.\n"
    "Find the cause without frightening the neighbors."
)


def _contract(lore: str = LORE) -> dict:
    return {"player_canon": _extract_named_entities([lore])}


def test_labelled_entities_keep_the_authors_description():
    notes = {e["name"]: e["note"] for e in _extract_named_entities([LORE])}
    assert notes["Alderbrook"] == "a small village where every clock stopped at breakfast"
    assert notes["Ada Reed"].startswith("clockmaker")


def test_single_labelled_place_is_the_starting_location():
    intent = build_opening_intent({"genre": "fantasy"}, _contract())
    start = starting_location_fact(intent)
    assert start is not None and start.text == "Alderbrook"


def test_several_labelled_places_do_not_pick_a_start():
    lore = LORE + "\nLocation: Hollow Ridge — a ridge nobody climbs."
    assert starting_location_fact(build_opening_intent({}, _contract(lore))) is None


def test_opening_seed_uses_the_lore_place_npc_and_description():
    settings = {"genre": "fantasy", "creation_posture": "lore_importer"}
    seed = generate_starter_seed(settings, _contract(), seed=3)
    assert seed["starting_location"] == "Alderbrook"
    assert seed["named_npc_or_visible_threat"].startswith("Ada Reed")
    assert seed["location_identity"] == "A small village where every clock stopped at breakfast."
    assert "tower" not in seed["location_identity"].lower()


def test_unknown_placeholders_read_as_story_not_bookkeeping():
    for line in (UNKNOWN_PROBLEM, UNKNOWN_URGENCY, UNKNOWN_AUTHORITY, UNKNOWN_CONSEQUENCE, UNKNOWN_OBJECT):
        assert "established" not in line.lower()
        assert line.endswith(".") and line[0].isupper()


def test_fallback_scene_uses_the_object_the_player_named():
    from server.agents import sessions

    scene = sessions._action_response_scene(
        player_name="Mira", location_name="Ashveil Temple",
        latest_action="I inspect the sealed letter closely.", action_count=1,
    )
    text = " ".join(str(v) for v in scene.values())
    assert "sealed letter" in text.lower()
    assert "water seal" not in text.lower()
    assert not any(c[:1].islower() for c in scene.get("clues", []) if isinstance(c, str))


def test_opening_scene_does_not_invent_a_prop_the_player_never_named():
    from server.agents.opening_setup import build_opening_scene_contract

    seed = generate_starter_seed({"genre": "fantasy", "creation_posture": "lore_importer"}, _contract(), seed=2)
    scene = build_opening_scene_contract(required=seed, anchor={"character_name": "Arin"}, campaign_brief={}, player_name="Arin")
    text = scene["opening_narrative"].lower()
    for invented in ("sealed letter", "broken seal", "first sign of trouble"):
        assert invented not in text
    assert "alderbrook" in text and "ada reed" in text and "every clock stopped at breakfast" in text


def test_fallback_scene_invents_no_prop_for_a_premise_without_one():
    from server.agents.scene_validator import build_fallback_scene

    text = build_fallback_scene(
        location_name="Alderbrook", npc_name="Ada Reed", player_name="Arin", emotional_state="urgent",
        inciting_incident="Every clock stopped at breakfast", central_conflict="Nobody knows why the clocks stopped",
        immediate_stakes="The cause remains unknown and the village is uneasy", sensory_detail="Oil and old wood",
        campaign_name="Alderbrook",
    )
    for invented in ("damaged notice", "local token", "rain-gauge", "flask", "frost-stiff"):
        assert invented not in text
    assert "Ada Reed" in text
