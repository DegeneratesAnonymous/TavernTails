"""The narrative scorer ranks concrete prose above thin prose."""
from __future__ import annotations

from server.agents import sessions  # noqa: F401  (import order: sessions before narrative)
from server.agents.narrative import score_scene

RICH = (
    "The ancient library smells of dust and forgotten magic. Moonlight filters through stained glass, "
    "casting spectral patterns across towering bookshelves. Archivist Venn grips the locked iron chest on "
    "the central table and whispers that the key was stolen before dusk. Someone upstairs has just slammed "
    "a door, and the lamps gutter as the party hears footsteps coming down. If the chest is opened before "
    "the thief is found, the guild will blame the party."
)
THIN = "You are in a room. Something happens. It is quiet."


def test_rich_scene_outscores_thin_scene():
    assert score_scene(RICH, title="Library", threshold=75).score > score_scene(THIN, title="Library", threshold=75).score


GROUP = (
    "Ada Reed's workshop smells of oil and cold brass. The party edges past the workbench as Ada sets down "
    "a stopped pocket watch and hisses that someone has broken in before dawn. Rain runs down the window, "
    "and a boot print is still wet on the floorboards beside the door."
)


def test_addressing_the_group_as_the_party_is_not_meta_narration():
    result = score_scene(GROUP, title="Workshop", threshold=75)
    assert "the party" not in result.banned_phrases_found


def test_real_meta_narration_is_still_penalised():
    result = score_scene(GROUP + " The players decide what the campaign needs next.", title="Workshop", threshold=75)
    assert {"the players", "the campaign"} <= set(result.banned_phrases_found)


def test_a_draft_is_scored_with_its_player_prompt(monkeypatch):
    """The prompt comes back beside the prose; leaving it out capped good openings below the opening bar."""
    from server.agents import narrative as narrative_module

    body = ("Ada Reed's workshop smells of oil and cold brass. Ada slams the broken watch on the bench and hisses that "
            "someone stole the key before dawn. Rain runs down the window, and unless the party acts before the bell, "
            "the thief walks free.")
    seen = []
    monkeypatch.setattr(narrative_module, "chat_complete", lambda *a, **k: f"{body}\n\nWhat does Arin do?")
    real = narrative_module.score_scene
    monkeypatch.setattr(narrative_module, "score_scene", lambda text, **kw: seen.append(text) or real(text, **kw))
    narrative_module.generate_narrative(narrative_module.NarrativeRequest(scene="clock mystery", player="Arin", is_opening_scene=True))
    assert seen and "What does Arin do?" in seen[0]
    assert seen[0].lower().count("what does arin do") == 1


def test_naming_the_place_keeps_proper_names_and_lowers_common_openers():
    from server.agents.narrative import name_place_in_opening

    assert name_place_in_opening("The crisp air smells of bread.", "Alderbrook village") == \
        "In Alderbrook village, the crisp air smells of bread."
    assert name_place_in_opening("Ada Reed stumbles in.", "Alderbrook village") == \
        "In Alderbrook village, Ada Reed stumbles in."
    assert name_place_in_opening("", "Alderbrook village") == ""
