"""Scene Director Agent — converts storyboard raw material into a concrete playable scene skeleton.

Sits between the Storyboard Agent and the Narrative Agent. Its job is to ensure
every opening scene has a specific location, a named NPC, a concrete conflict,
and a clear reason the player character is involved — before the Narrative Agent
writes a single word of prose.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

try:
    from ..steward_llm import chat_complete
except Exception:
    chat_complete = None  # type: ignore

# Phrases that indicate the scene is meta/generic rather than concrete.
FORBIDDEN_GENERIC = [
    "heroic fantasy adventure",
    "high fantasy",
    "mysterious threat looms",
    "choices matter",
    "outcomes stay flexible",
    "the world is dangerous",
    "an urgent request appears",
    "the stakes are personal",
    "adventure awaits",
    "paths branch ahead",
]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SceneDirectorRequest(BaseModel):
    campaign_settings: dict[str, Any] = Field(default_factory=dict)
    campaign_variables: dict[str, Any] = Field(default_factory=dict)
    players: list[str] = Field(default_factory=list)
    plot_seed: str = Field(default="")
    candidate_npcs: list[str] = Field(default_factory=list)
    candidate_npc_details: list[dict[str, Any]] = Field(default_factory=list)
    candidate_locations: list[str] = Field(default_factory=list)
    candidate_location_details: list[dict[str, Any]] = Field(default_factory=list)
    candidate_factions: list[str] = Field(default_factory=list)
    candidate_story_threads: list[str] = Field(default_factory=list)
    candidate_thread_details: list[dict[str, Any]] = Field(default_factory=list)
    open_hooks: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    world_context_block: str = Field(default="")
    # Narrative Director guidance — overrides default pacing choices
    director_guidance: dict[str, Any] | None = None


class LocationBlueprint(BaseModel):
    name: str = ""
    type: str = ""
    sensory_details: list[str] = Field(default_factory=list)


class NPCBlueprint(BaseModel):
    name: str = ""
    role: str = ""
    current_emotional_state: str = ""
    what_they_want: str = ""
    what_they_know: str = ""


class SceneDirectorOutput(BaseModel):
    scene_title: str = ""
    scene_type: str = "opening"
    location: LocationBlueprint = Field(default_factory=LocationBlueprint)
    primary_npc: NPCBlueprint = Field(default_factory=NPCBlueprint)
    secondary_entities: list[str] = Field(default_factory=list)
    central_conflict: str = ""
    inciting_incident: str = ""
    why_player_is_involved: str = ""
    immediate_stakes: str = ""
    hidden_pressure: str = ""
    player_visible_clues: list[str] = Field(default_factory=list)
    possible_actions: list[str] = Field(default_factory=list)
    visual_prompt_elements: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    source: str = "llm"  # "llm" | "deterministic"


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

def _deterministic_director(req: SceneDirectorRequest) -> SceneDirectorOutput:
    """Build a best-effort scene skeleton from available structured data without LLM."""
    player_name = req.players[0] if req.players else "the party"
    genre = req.campaign_settings.get("genre", "fantasy")
    tone = (req.campaign_settings.get("tone")
            or req.campaign_variables.get("narrative_style")
            or "gritty")

    loc_name = req.candidate_locations[0] if req.candidate_locations else "The Wayward Lantern Inn"
    npc_name = req.candidate_npcs[0] if req.candidate_npcs else ""

    # Prefer active thread over hook over plot seed for conflict text
    thread = req.candidate_story_threads[0] if req.candidate_story_threads else ""
    hook = req.open_hooks[0] if req.open_hooks else ""
    recent = req.recent_events[0] if req.recent_events else ""
    conflict_source = thread or hook or recent or (req.plot_seed[:150] if req.plot_seed else "")
    conflict = conflict_source or f"Something urgent has drawn attention in {loc_name}."
    inciting = hook or thread or f"A disturbance has broken the routine of {loc_name}."

    # NPC detail from campaign memory if available
    npc_detail = {}
    if req.candidate_npc_details:
        npc_detail = req.candidate_npc_details[0]
    emotional_state = npc_detail.get("emotional_state") or "visibly shaken"
    npc_goal = npc_detail.get("goal") or "find help immediately"
    npc_knows = npc_detail.get("next_action") or conflict_source[:80] or "something terrible has happened"

    loc_detail = {}
    if req.candidate_location_details:
        loc_detail = req.candidate_location_details[0]
    tension = loc_detail.get("current_tension") or ""
    sensory = [
        "The air carries the smell of hearth smoke and damp stone.",
        "Voices drop to a murmur as you enter.",
    ]
    if tension:
        sensory.append(tension[:80])

    visual_elements = [
        f"{genre} illustration style",
        f"{loc_name}, {tone} atmosphere",
        "grounded cinematic composition",
    ]
    if npc_name:
        role = npc_detail.get("faction") or "local figure"
        visual_elements.append(f"{npc_name} — {role}")
    if req.campaign_settings.get("world_name"):
        visual_elements.append(req.campaign_settings["world_name"])

    return SceneDirectorOutput(
        scene_title=f"Opening — {loc_name}",
        scene_type="opening",
        location=LocationBlueprint(name=loc_name, type="settlement", sensory_details=sensory),
        primary_npc=NPCBlueprint(
            name=npc_name,
            role=npc_detail.get("faction") or "local contact",
            current_emotional_state=emotional_state,
            what_they_want=npc_goal,
            what_they_know=npc_knows,
        ),
        secondary_entities=req.candidate_npcs[1:3],
        central_conflict=conflict[:250],
        inciting_incident=inciting[:200],
        why_player_is_involved=f"{player_name} is already here and cannot ignore what unfolds.",
        immediate_stakes="If no one acts, the situation will worsen within hours.",
        visual_prompt_elements=visual_elements,
        possible_actions=[
            "Approach and ask what happened",
            "Investigate the area for clues",
            "Speak to bystanders",
            "Prepare for a potential confrontation",
        ],
        source="deterministic",
    )


# ---------------------------------------------------------------------------
# LLM-backed director
# ---------------------------------------------------------------------------

_SCHEMA = (
    '{"scene_title":"","scene_type":"opening",'
    '"location":{"name":"","type":"","sensory_details":[]},'
    '"primary_npc":{"name":"","role":"","current_emotional_state":"","what_they_want":"","what_they_know":""},'
    '"secondary_entities":[],"central_conflict":"","inciting_incident":"","why_player_is_involved":"",'
    '"immediate_stakes":"","hidden_pressure":"","player_visible_clues":[],'
    '"possible_actions":[],"visual_prompt_elements":[],"continuity_notes":[]}'
)


def direct_scene(req: SceneDirectorRequest) -> SceneDirectorOutput:
    """Call the LLM to produce a concrete scene skeleton; falls back to deterministic output."""
    if not chat_complete:
        return _deterministic_director(req)

    player_name = req.players[0] if req.players else "the party"
    genre = req.campaign_settings.get("genre", "fantasy")

    ctx: list[str] = []
    if req.campaign_settings.get("world_name"):
        ctx.append(f"World: {req.campaign_settings['world_name']}")
    if genre:
        ctx.append(f"Genre: {genre}")
    if req.campaign_settings.get("setting_summary"):
        ctx.append(f"Setting: {req.campaign_settings['setting_summary'][:200]}")
    ctx.append(f"Player character: {player_name}")
    if req.plot_seed:
        ctx.append(f"Plot seed: {req.plot_seed[:300]}")

    # Structured memory — most valuable content goes first
    if req.candidate_story_threads:
        ctx.append("ACTIVE STORY THREADS (use these first):\n"
                   + "\n".join(f"  • {t}" for t in req.candidate_story_threads[:3]))
    if req.open_hooks:
        ctx.append("OPEN HOOKS (unresolved player-facing situations):\n"
                   + "\n".join(f"  • {h}" for h in req.open_hooks[:3]))
    if req.recent_events:
        ctx.append("RECENT WORLD EVENTS:\n"
                   + "\n".join(f"  • {e}" for e in req.recent_events[:3]))
    if req.candidate_npc_details:
        npc_lines = []
        for n in req.candidate_npc_details[:4]:
            line = f"  • {n.get('name', '?')}"
            if n.get("goal"):
                line += f" — wants: {n['goal'][:60]}"
            if n.get("emotional_state"):
                line += f" — currently: {n['emotional_state'][:40]}"
            if n.get("next_action"):
                line += f" — next: {n['next_action'][:60]}"
            npc_lines.append(line)
        ctx.append("KNOWN NPCs:\n" + "\n".join(npc_lines))
    elif req.candidate_npcs:
        ctx.append(f"Known NPC names: {', '.join(req.candidate_npcs[:5])}")

    if req.candidate_location_details:
        loc_lines = []
        for loc in req.candidate_location_details[:3]:
            line = f"  • {loc.get('name', '?')}"
            if loc.get("current_tension"):
                line += f" — tension: {loc['current_tension'][:60]}"
            if loc.get("threat"):
                line += f" — threat: {loc['threat'][:60]}"
            loc_lines.append(line)
        ctx.append("KNOWN LOCATIONS:\n" + "\n".join(loc_lines))
    elif req.candidate_locations:
        ctx.append(f"Known locations: {', '.join(req.candidate_locations[:4])}")

    if req.candidate_factions:
        ctx.append(f"Active factions: {', '.join(req.candidate_factions[:3])}")
    if req.world_context_block:
        ctx.append(req.world_context_block[:500])

    # Inject Narrative Director guidance if provided
    if req.director_guidance:
        dg = req.director_guidance
        director_lines = []
        if dg.get("recommended_scene_type"):
            director_lines.append(f"SCENE TYPE: {dg['recommended_scene_type']}")
        if dg.get("scene_purpose"):
            director_lines.append(f"SCENE PURPOSE: {dg['scene_purpose']}")
        if dg.get("threads_to_advance"):
            director_lines.append(f"ADVANCE THESE THREADS: {', '.join(dg['threads_to_advance'])}")
        if dg.get("spotlight_target"):
            director_lines.append(f"SPOTLIGHT PLAYER/NPC: {dg['spotlight_target']}")
        if dg.get("recommended_consequence"):
            director_lines.append(f"TRIGGER THIS CONSEQUENCE: {dg['recommended_consequence']}")
        if dg.get("recommended_reveal"):
            director_lines.append(f"REVEAL: {dg['recommended_reveal']}")
        if dg.get("recommended_complication"):
            director_lines.append(f"COMPLICATION: {dg['recommended_complication']}")
        if dg.get("next_story_beat"):
            director_lines.append(f"TARGET STORY BEAT: {dg['next_story_beat']}")
        if dg.get("mystery_guidance"):
            director_lines.append(f"MYSTERY GUIDANCE: {dg['mystery_guidance']}")
        if director_lines:
            ctx.append("NARRATIVE DIRECTOR GUIDANCE (mandatory):\n" + "\n".join(f"  — {item}" for item in director_lines))

    system = (
        "You are a tabletop RPG Scene Director. Your job: convert campaign context into ONE concrete, "
        "immediately playable opening scene. Every field must be specific and grounded.\n\n"
        "REQUIREMENTS (non-negotiable):\n"
        f"  — location.name: a SPECIFIC named place from the context (or invent one that fits {genre})\n"
        f"  — primary_npc.name: a SPECIFIC named character — not 'a stranger' or 'a mysterious figure'\n"
        "  — central_conflict: a visible, immediate situation — not a vague mood\n"
        "  — inciting_incident: what physically happens in the opening moments\n"
        f"  — why_player_is_involved: personal, professional, or accidental reason {player_name} cannot ignore this\n"
        "  — immediate_stakes: WHO suffers, WHAT is lost, BY WHEN — specific consequences\n"
        "  — sensory_details: what you see, hear, or smell RIGHT NOW — physical and grounded\n"
        "  — visual_prompt_elements: 3–5 items for image generation (location + NPC + mood + key visual)\n\n"
        "CONTENT PRIORITY ORDER:\n"
        "  1. Active story threads  2. Open hooks  3. NPC goals  4. Faction plans  5. Location tensions  6. Invent only if nothing else exists\n\n"
        "FORBIDDEN — never write:\n"
        + "\n".join(f"  — \"{p}\"" for p in FORBIDDEN_GENERIC)
        + "\n\nReturn ONLY valid JSON — no markdown fences, no preamble, no commentary:\n"
        + _SCHEMA
    )

    try:
        raw = chat_complete(
            [{"role": "system", "content": system},
             {"role": "user", "content": "\n".join(ctx)}],
            task_scope="taverntails_scene_director",
            max_tokens=700,
            timeout=120.0,
        )
        if raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(raw[start:end])
                loc = data.get("location") or {}
                npc = data.get("primary_npc") or {}
                return SceneDirectorOutput(
                    scene_title=str(data.get("scene_title") or ""),
                    scene_type=str(data.get("scene_type") or "opening"),
                    location=LocationBlueprint(
                        name=str(loc.get("name") or ""),
                        type=str(loc.get("type") or ""),
                        sensory_details=[str(s) for s in (loc.get("sensory_details") or [])],
                    ),
                    primary_npc=NPCBlueprint(
                        name=str(npc.get("name") or ""),
                        role=str(npc.get("role") or ""),
                        current_emotional_state=str(npc.get("current_emotional_state") or ""),
                        what_they_want=str(npc.get("what_they_want") or ""),
                        what_they_know=str(npc.get("what_they_know") or ""),
                    ),
                    secondary_entities=[str(e) for e in (data.get("secondary_entities") or [])],
                    central_conflict=str(data.get("central_conflict") or ""),
                    inciting_incident=str(data.get("inciting_incident") or ""),
                    why_player_is_involved=str(data.get("why_player_is_involved") or ""),
                    immediate_stakes=str(data.get("immediate_stakes") or ""),
                    hidden_pressure=str(data.get("hidden_pressure") or ""),
                    player_visible_clues=[str(c) for c in (data.get("player_visible_clues") or [])],
                    possible_actions=[str(a) for a in (data.get("possible_actions") or [])],
                    visual_prompt_elements=[str(v) for v in (data.get("visual_prompt_elements") or [])],
                    continuity_notes=[str(n) for n in (data.get("continuity_notes") or [])],
                    source="llm",
                )
    except Exception:
        pass

    return _deterministic_director(req)


def build_image_prompt(sd: SceneDirectorOutput, style: str = "realistic", weather: str = "clear", time_of_day: str = "day") -> str:
    """Build a structured image generation prompt from Scene Director output."""
    parts: list[str] = []

    genre_map = {"gritty": "dark gritty fantasy", "heroic": "heroic fantasy", "horror": "dark horror fantasy"}
    style_label = genre_map.get(style, "dark heroic fantasy illustration")
    parts.append(style_label)

    time_map = {"dawn": "early morning golden light", "day": "daylight", "dusk": "golden hour dusk", "night": "night torchlight"}
    weather_map = {"rain": "rain-soaked", "clear": "clear", "fog": "misty fog", "storm": "stormy"}
    parts.append(f"{weather_map.get(weather, 'clear')} {time_map.get(time_of_day, 'daylight')}")

    if sd.location.name:
        loc_desc = sd.location.name
        if sd.location.type:
            loc_desc += f", {sd.location.type}"
        if sd.location.sensory_details:
            loc_desc += f", {sd.location.sensory_details[0]}"
        parts.append(loc_desc)

    if sd.primary_npc.name:
        npc_desc = sd.primary_npc.name
        if sd.primary_npc.role:
            npc_desc += f" ({sd.primary_npc.role})"
        if sd.primary_npc.current_emotional_state:
            npc_desc += f", {sd.primary_npc.current_emotional_state}"
        parts.append(npc_desc)

    for element in sd.visual_prompt_elements[:4]:
        if element not in " ".join(parts):
            parts.append(element)

    parts.append("grounded cinematic composition, detailed, dramatic lighting")

    return ". ".join(p.rstrip(".") for p in parts if p)
