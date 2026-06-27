"""Narrative Composer — plans the scene experience before prose is written.

Sits between Scene Director and Narrative Writer in the pipeline:
  Scene Director → Narrative Composer → Narrative Writer

The Composer does NOT write prose. It produces a creative brief that tells the
Writer exactly what the scene must achieve: one vivid image, one emotional
target, one unanswered question, one meaningful decision.

This separates scene planning from scene writing, which catches vague setups
before they become vague paragraphs.
"""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

try:
    from ..steward_llm import chat_complete
except Exception:
    chat_complete = None  # type: ignore


class NPCComposerProfile(BaseModel):
    name: str = ""
    role: str = ""
    visible_emotion: str = ""
    immediate_desire: str = ""
    physical_tell: str = ""
    first_line_of_dialogue: str = ""


class NarrativeComposerOutput(BaseModel):
    scene_purpose: str = ""
    dramatic_question: str = ""
    emotional_target: str = ""
    vivid_image: str = ""
    memorable_object: str = ""
    active_motion: str = ""
    primary_npc: NPCComposerProfile = Field(default_factory=NPCComposerProfile)
    specific_problem: str = ""
    specific_stakes: str = ""
    unanswered_question: str = ""
    meaningful_decision: str = ""
    environmental_storytelling: list[str] = Field(default_factory=list)
    dialogue_intent: str = ""
    ending_prompt: str = ""
    suggested_actions: list[str] = Field(default_factory=list)
    world_moves: list[str] = Field(default_factory=list)


_REQUIRED_FIELDS = {"vivid_image", "emotional_target", "unanswered_question", "meaningful_decision", "specific_stakes"}

_FALLBACK_SUGGESTED_ACTIONS = [
    "Ask what happened",
    "Investigate the scene",
    "Speak to bystanders",
    "Prepare for trouble",
]


def _deterministic_composer(sd: dict, player_name: str) -> NarrativeComposerOutput:
    """Build a scene plan from Scene Director data without an LLM call."""
    loc = sd.get("location") or {}
    npc = sd.get("primary_npc") or {}

    loc_name = loc.get("name") or "this place"
    npc_name = npc.get("name") or ""
    npc_role = npc.get("role") or "local contact"
    npc_state = npc.get("current_emotional_state") or "agitated"
    npc_wants = npc.get("what_they_want") or ""
    npc_knows = npc.get("what_they_know") or ""

    sensory = loc.get("sensory_details") or []
    conflict = sd.get("central_conflict") or ""
    inciting = sd.get("inciting_incident") or conflict
    stakes = sd.get("immediate_stakes") or ""
    clues = sd.get("player_visible_clues") or []
    possible_actions = sd.get("possible_actions") or []
    world_moves = sd.get("world_moves") or []

    vivid_image = sensory[0] if sensory else f"Every eye in {loc_name} turns toward the door."
    dramatic_question = conflict or f"What has happened at {loc_name}?"
    memorable_object = clues[0] if clues else ""
    specific_stakes = stakes or "What unfolds here will not be easily undone."
    unanswered_question = (
        f"What caused {conflict[:80]}?" if conflict
        else f"What brought this trouble to {loc_name}?"
    )
    meaningful_decision = possible_actions[0] if possible_actions else f"How does {player_name} respond?"

    suggested_actions = (possible_actions[:4] if possible_actions else _FALLBACK_SUGGESTED_ACTIONS)

    npc_profile = NPCComposerProfile(
        name=npc_name,
        role=npc_role,
        visible_emotion=npc_state,
        immediate_desire=npc_wants,
        physical_tell="",
        first_line_of_dialogue=npc_knows[:120] if npc_knows else "",
    )

    return NarrativeComposerOutput(
        scene_purpose=dramatic_question,
        dramatic_question=dramatic_question,
        emotional_target=npc_state,
        vivid_image=vivid_image,
        memorable_object=memorable_object,
        active_motion=inciting[:120] if inciting else "",
        primary_npc=npc_profile,
        specific_problem=conflict[:200] if conflict else "",
        specific_stakes=specific_stakes,
        unanswered_question=unanswered_question,
        meaningful_decision=meaningful_decision,
        environmental_storytelling=clues[:3],
        dialogue_intent=(
            f"{npc_name} must reveal: {npc_knows[:80]}"
            if npc_name and npc_knows else ""
        ),
        ending_prompt=f"What does {player_name} do?",
        suggested_actions=suggested_actions,
        world_moves=world_moves,
    )


_COMPOSER_SCHEMA = """{
  "scene_purpose": "one sentence: what this scene must accomplish",
  "dramatic_question": "the single question this scene raises",
  "emotional_target": "what the player should FEEL — dread / urgency / intrigue / tension",
  "vivid_image": "one sentence: the strongest visual moment in this scene",
  "memorable_object": "one physical object the player can interact with",
  "active_motion": "the physical action that opens the scene (strong verb required)",
  "primary_npc": {
    "name": "must be a real name, never 'a figure' or 'a stranger'",
    "role": "their function in this scene",
    "visible_emotion": "what the player can see on their face/body",
    "immediate_desire": "what they want RIGHT NOW in this scene",
    "physical_tell": "one gesture or appearance detail that reveals their state",
    "first_line_of_dialogue": "their opening line — must reveal a desire, fear, or clue"
  },
  "specific_problem": "what has gone wrong, in one concrete sentence — no abstractions",
  "specific_stakes": "who suffers, what is lost, and by when — name the person and deadline",
  "unanswered_question": "the one question the player will want answered after this scene",
  "meaningful_decision": "the concrete choice the player now faces",
  "environmental_storytelling": ["one visible detail that implies history", "another clue"],
  "dialogue_intent": "what the NPC dialogue must reveal",
  "ending_prompt": "how to close the scene — a line addressed to the player character by name",
  "suggested_actions": ["Verb + specific target 1", "Verb + specific target 2", "Verb + specific target 3", "Verb + specific target 4"],
  "world_moves": ["living-world event implying tension or consequence", "another event outside the immediate scene", "a third subtle signal"]
}"""


def compose_scene(
    scene_director_data: dict,
    player_name: str,
    scene_type: str = "opening",
) -> NarrativeComposerOutput:
    """Plan the scene experience from Scene Director output.

    Returns a NarrativeComposerOutput used by the Narrative Writer to craft prose.
    Falls back to deterministic composition if the LLM is unavailable or fails validation.
    """
    if not chat_complete:
        return _deterministic_composer(scene_director_data, player_name)

    loc = scene_director_data.get("location") or {}
    npc = scene_director_data.get("primary_npc") or {}

    system = (
        "You are the creative director for a tabletop RPG session. "
        "Your job is to plan a scene experience — not to write prose.\n\n"
        "You produce a creative brief. The prose writer reads your brief and writes the scene.\n\n"
        "REQUIRED (all must be non-empty and specific):\n"
        "  — vivid_image: the ONE image the player will remember from this scene\n"
        "  — emotional_target: what the player should feel (never 'neutral' or 'interested')\n"
        "  — unanswered_question: the ONE question this scene leaves open\n"
        "  — meaningful_decision: the concrete choice the player faces after this scene\n"
        "  — specific_stakes: name the person at risk, what they lose, and by when\n"
        "  — primary_npc.first_line_of_dialogue: their first words — must reveal desire, fear, or a clue\n"
        "  — suggested_actions: 3–4 specific actions (verb + target, not just 'investigate')\n"
        "  — world_moves: 2–4 living-world events happening outside the immediate scene\n\n"
        "RULES:\n"
        "  — NPCs must be named. Never 'a figure', 'a stranger', 'someone nearby'.\n"
        "  — Stakes must name a specific person and a concrete deadline.\n"
        "  — World moves must imply tension, opportunity, or consequence — not generic atmosphere.\n"
        "  — suggested_actions must be verb+target ('Inspect the marked object', not just 'Inspect').\n"
        "  — memorable_object must be something the player can touch, examine, or take.\n\n"
        f"Return ONLY valid JSON:\n{_COMPOSER_SCHEMA}"
    )

    ctx_lines = [
        f"Scene type: {scene_type}",
        f"Player character: {player_name}",
        f"Location: {loc.get('name') or 'unknown'}",
        f"Primary NPC: {npc.get('name') or 'UNNAMED — you must invent a name'} ({npc.get('role') or 'unknown role'})",
        f"NPC emotional state: {npc.get('current_emotional_state') or 'unknown'}",
        f"NPC wants right now: {npc.get('what_they_want') or 'unknown'}",
        f"NPC secret knowledge: {npc.get('what_they_know') or 'unknown'}",
        f"Central conflict: {scene_director_data.get('central_conflict') or 'unknown'}",
        f"Inciting incident: {scene_director_data.get('inciting_incident') or 'unknown'}",
        f"Immediate stakes: {scene_director_data.get('immediate_stakes') or 'unknown'}",
    ]
    clues = scene_director_data.get("player_visible_clues") or []
    if clues:
        ctx_lines.append(f"Visible clues for player: {'; '.join(clues[:3])}")
    sensory = loc.get("sensory_details") or []
    if sensory:
        ctx_lines.append(f"Sensory anchor details: {'; '.join(sensory[:2])}")
    possible_actions = scene_director_data.get("possible_actions") or []
    if possible_actions:
        ctx_lines.append(f"Possible player actions (refine into verb+target form): {'; '.join(possible_actions[:4])}")
    world_moves_seed = scene_director_data.get("world_moves") or []
    if world_moves_seed:
        ctx_lines.append(f"World moves seed (improve these): {'; '.join(world_moves_seed[:3])}")

    try:
        raw = chat_complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "\n".join(ctx_lines)},
            ],
            task_scope="taverntails_narrative_composer",
            max_tokens=350,
            timeout=90.0,
        )
        if raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(raw[start:end])
                missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
                if not missing:
                    npc_data = data.get("primary_npc") or {}
                    return NarrativeComposerOutput(
                        scene_purpose=str(data.get("scene_purpose") or ""),
                        dramatic_question=str(data.get("dramatic_question") or ""),
                        emotional_target=str(data.get("emotional_target") or ""),
                        vivid_image=str(data.get("vivid_image") or ""),
                        memorable_object=str(data.get("memorable_object") or ""),
                        active_motion=str(data.get("active_motion") or ""),
                        primary_npc=NPCComposerProfile(
                            name=str(npc_data.get("name") or ""),
                            role=str(npc_data.get("role") or ""),
                            visible_emotion=str(npc_data.get("visible_emotion") or ""),
                            immediate_desire=str(npc_data.get("immediate_desire") or ""),
                            physical_tell=str(npc_data.get("physical_tell") or ""),
                            first_line_of_dialogue=str(npc_data.get("first_line_of_dialogue") or ""),
                        ),
                        specific_problem=str(data.get("specific_problem") or ""),
                        specific_stakes=str(data.get("specific_stakes") or ""),
                        unanswered_question=str(data.get("unanswered_question") or ""),
                        meaningful_decision=str(data.get("meaningful_decision") or ""),
                        environmental_storytelling=[str(e) for e in (data.get("environmental_storytelling") or [])],
                        dialogue_intent=str(data.get("dialogue_intent") or ""),
                        ending_prompt=str(data.get("ending_prompt") or ""),
                        suggested_actions=[str(a) for a in (data.get("suggested_actions") or [])[:4]],
                        world_moves=[str(w) for w in (data.get("world_moves") or [])[:4]],
                    )
    except Exception:
        pass

    return _deterministic_composer(scene_director_data, player_name)
