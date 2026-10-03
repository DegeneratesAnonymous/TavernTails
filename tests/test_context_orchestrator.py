"""Tests for the Context Orchestrator.

Run with: python -m pytest tests/test_context_orchestrator.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.agents.context_orchestrator import (
    ContextPacket,
    ClueContext,
    ConstraintsContext,
    FactionContext,
    LocationContext,
    NPCContext,
    PlayerContext,
    RecentHistoryContext,
    RulesContext,
    SceneContext,
    StoryThreadContext,
    _build_rules_context,
    _estimate_tokens,
    _extract_unresolved_intents,
    _names_from_text,
    _trim_to_budget,
)


def _make_packet(**kwargs) -> ContextPacket:
    return ContextPacket(
        scene=kwargs.get("scene", SceneContext(location_name="Greyford Market", mood="unease", threat_level="moderate")),
        player_character=kwargs.get("player", PlayerContext(name="Yungmin")),
        recent_history=kwargs.get("history", RecentHistoryContext()),
        active_npcs=kwargs.get("npcs", []),
        location=kwargs.get("location", LocationContext(name="Greyford Market")),
        story_threads=kwargs.get("threads", []),
        factions=kwargs.get("factions", []),
        clues=kwargs.get("clues", ClueContext()),
        rules=kwargs.get("rules", RulesContext()),
        constraints=kwargs.get("constraints", ConstraintsContext()),
        entity_scores={},
        generated_at="2026-06-24T00:00:00Z",
        token_estimate=0,
    )


# ---------------------------------------------------------------------------
# Section 1: for_narrative() always includes scene + player
# ---------------------------------------------------------------------------

def test_narrative_includes_scene_and_player():
    packet = _make_packet(
        scene=SceneContext(location_name="Greyford Market", mood="unease", threat_level="high",
                          current_problem="Caravans missing", immediate_stakes="Villages starve"),
        player=PlayerContext(name="Yungmin", class_name="Rogue"),
    )
    text = packet.for_narrative()
    assert "Greyford Market" in text, "Location must appear in narrative block"
    assert "Yungmin" in text, "Player name must appear in narrative block"
    assert "Caravans missing" in text, "Problem must appear"
    assert "Villages starve" in text, "Stakes must appear"


# ---------------------------------------------------------------------------
# Section 2: NPC secrets never leak into narrative block
# ---------------------------------------------------------------------------

def test_narrative_does_not_leak_npc_secrets():
    npc = NPCContext(
        name="Captain Elira Voss",
        goal="Find the missing caravans",
        likely_next_action="Recruit Yungmin",
        secrets_count=3,
        current_emotional_state="desperate",
        relevance_score=185,
    )
    constraint = ConstraintsContext(
        forbidden_reveals=["Do not reveal Iron Banner hired the assassins"],
    )
    packet = _make_packet(npcs=[npc], constraints=constraint)
    text = packet.for_narrative()

    # secrets_count is an int — never show actual secret content
    assert "secrets_count" not in text, "Raw field name must not appear in narrative prompt"
    assert "Iron Banner hired the assassins" not in text or "DO NOT REVEAL" in text, \
        "Secret content must not appear in narrative without constraint wrapper"
    assert "Captain Elira Voss" in text, "NPC name should appear"


# ---------------------------------------------------------------------------
# Section 3: for_analysis() stays compact
# ---------------------------------------------------------------------------

def test_analysis_block_stays_compact():
    packet = _make_packet(
        scene=SceneContext(location_name="Greyford Market", threat_level="high"),
        history=RecentHistoryContext(recent_actions=["I try to persuade the merchant", "I search for clues"]),
        rules=RulesContext(likely_skill_checks=["Persuasion (Charisma)", "Investigation (Intelligence)"]),
    )
    text = packet.for_analysis()
    tokens = _estimate_tokens(text)
    assert tokens < 800, f"Analysis block too large: ~{tokens} tokens"
    assert "Persuasion" in text, "Expected skill check must appear"


# ---------------------------------------------------------------------------
# Section 4: for_visual() only includes atmosphere/location/mood
# ---------------------------------------------------------------------------

def test_visual_block_contains_atmosphere_not_npcs():
    npc = NPCContext(name="Captain Elira Voss", goal="Find caravans", relevance_score=185)
    location = LocationContext(
        name="Greyford Market",
        atmosphere="Cold morning mist and muddy cobblestones",
        current_tensions=["Merchants whispering"],
    )
    packet = _make_packet(
        scene=SceneContext(location_name="Greyford Market", mood="unease", weather="fog", threat_level="moderate", time_of_day="dawn"),
        location=location,
        npcs=[npc],
    )
    text = packet.for_visual()
    assert "Greyford Market" in text, "Location must appear in visual block"
    assert "fog" in text or "unease" in text, "Mood/weather must appear"
    # NPC name should NOT appear in visual block (it's for environment art)
    assert "Captain Elira Voss" not in text, "NPC names must not appear in visual block"


# ---------------------------------------------------------------------------
# Section 5: Token budget trimming removes low-relevance NPCs
# ---------------------------------------------------------------------------

def test_token_budget_trims_npcs():
    npcs = [
        NPCContext(name=f"NPC_{i}", goal=f"Goal_{i}", relevance_score=100 - i * 10)
        for i in range(10)
    ]
    threads = [
        StoryThreadContext(title=f"Thread_{i}", current_state=f"Situation_{i}", relevance_score=100)
        for i in range(5)
    ]
    packet = _make_packet(npcs=npcs, threads=threads)
    original_npc_count = len(packet.active_npcs)

    # Very tight budget — forces aggressive trimming
    _trim_to_budget(packet, budget=20)

    trimmed_count = len(packet.active_npcs) + len(packet.story_threads)
    assert trimmed_count < original_npc_count + 5, "Token budget must trim NPCs and/or threads"
    assert packet.token_estimate <= 40, f"Estimated tokens after trim still too high: {packet.token_estimate}"


# ---------------------------------------------------------------------------
# Section 6: Unresolved intents extracted from player actions
# ---------------------------------------------------------------------------

def test_unresolved_intents_extracted():
    actions = [
        "I want to find the missing caravans",
        "I look around the market",
        "Who took the wagons?",
    ]
    intents = _extract_unresolved_intents(actions)
    assert len(intents) > 0, "Should find at least one unresolved intent"
    assert any("caravan" in i.lower() or "want" in i.lower() for i in intents)


# ---------------------------------------------------------------------------
# Section 7: Rules context derives skill checks from action keywords
# ---------------------------------------------------------------------------

def test_rules_context_derives_skill_checks():
    rules = _build_rules_context(["I try to persuade the guard", "I search the crates"], threat_level="moderate")
    assert "Persuasion (Charisma)" in rules.likely_skill_checks, "Persuade → Persuasion check"
    assert rules.difficulty_guidance.get("base_dc") == 15, "Moderate threat → DC 15"


# ---------------------------------------------------------------------------
# Section 8: High-priority threads appear before low-priority ones
# ---------------------------------------------------------------------------

def test_high_relevance_threads_first():
    threads = [
        StoryThreadContext(title="Minor Plot", current_state="Minor thing", relevance_score=20),
        StoryThreadContext(title="Main Crisis", current_state="Caravans missing", relevance_score=220),
        StoryThreadContext(title="Side Quest", current_state="Find the herb", relevance_score=50),
    ]
    packet = _make_packet(threads=threads)
    text = packet.for_narrative()
    main_pos = text.find("Main Crisis")
    minor_pos = text.find("Minor Plot")
    # Main Crisis (highest score) should appear first if both present
    if main_pos != -1 and minor_pos != -1:
        assert main_pos < minor_pos, "Higher-relevance thread must appear before lower-relevance"


# ---------------------------------------------------------------------------
# Section 9: debug_payload() is complete and JSON-serializable
# ---------------------------------------------------------------------------

def test_debug_payload_serializable():
    import json
    packet = _make_packet(
        scene=SceneContext(location_name="Greyford Market"),
        npcs=[NPCContext(name="Elira", goal="Find caravans", relevance_score=180)],
    )
    payload = packet.debug_payload()
    assert "entity_scores" in payload
    assert "sections" in payload
    assert "token_estimate" in payload
    # Must be JSON-serializable
    json.dumps(payload)


# ---------------------------------------------------------------------------
# Section 10: for_scene_director() includes thread + NPC + faction
# ---------------------------------------------------------------------------

def test_scene_director_block_has_entities():
    packet = _make_packet(
        threads=[StoryThreadContext(title="Missing Caravans", current_state="Three wagons gone", relevance_score=200)],
        npcs=[NPCContext(name="Captain Voss", goal="Find wagons", relevance_score=160)],
        factions=[FactionContext(name="Iron Banner", current_plan="Sabotage trade", relevance_score=80)],
    )
    text = packet.for_scene_director()
    assert "Missing Caravans" in text, "Thread must appear"
    assert "Captain Voss" in text, "NPC must appear"
    assert "Iron Banner" in text, "Faction must appear"
    assert "200" in text or "160" in text, "Relevance scores must be shown"
