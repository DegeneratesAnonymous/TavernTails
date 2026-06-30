"""Scene Director Agent — converts storyboard raw material into a concrete playable scene skeleton.

Sits between the Storyboard Agent and the Narrative Agent. Its job is to ensure
every opening scene has a specific location, a named NPC, a concrete conflict,
and a clear reason the player character is involved — before the Narrative Agent
writes a single word of prose.
"""
from __future__ import annotations

import json
import hashlib
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
    campaign_contract: dict[str, Any] | None = None


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
    threads_to_advance: list[str] = Field(default_factory=list)
    world_moves: list[str] = Field(default_factory=list)
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
    world_name = str(req.campaign_settings.get("world_name") or "").strip()
    setting_summary = str(req.campaign_settings.get("setting_summary") or "").strip()
    contract = req.campaign_contract or {}
    campaign_pitch = str(contract.get("campaign_pitch") or "").strip()
    campaign_name = str(contract.get("campaign_name") or "").strip()

    location_candidates = [
        loc for loc in req.candidate_locations
        if not (_is_tavernish(loc) and not _campaign_allows_tavern(req))
    ]
    loc_name = location_candidates[0] if location_candidates else (
        world_name
        or _location_from_text(setting_summary or campaign_pitch or campaign_name, genre)
    )
    npc_name = req.candidate_npcs[0] if req.candidate_npcs else _contact_from_text(setting_summary or campaign_pitch or campaign_name, genre)

    # Prefer active thread over hook over plot seed for conflict text
    thread = _first_story_signal(req.candidate_story_threads)
    hook = _first_story_signal(req.open_hooks)
    recent = _first_story_signal(req.recent_events)
    conflict_source = thread or hook or recent or (req.plot_seed[:180] if req.plot_seed else "") or campaign_pitch or setting_summary
    conflict = conflict_source or f"A pressure point in {loc_name} has become impossible to ignore."

    # Derive a concrete inciting incident — never vague "disturbance" language
    if hook:
        inciting = hook
    elif thread:
        inciting = f"{thread} has reached a breaking point."
    elif recent:
        inciting = recent
    else:
        inciting = _inciting_from_context(loc_name, campaign_name or setting_summary, genre)

    # NPC detail from campaign memory if available
    npc_detail = {}
    if req.candidate_npc_details:
        npc_detail = req.candidate_npc_details[0]
    emotional_state = npc_detail.get("emotional_state") or "focused and wary"
    npc_goal = npc_detail.get("goal") or _npc_goal_from_context(loc_name, conflict_source)
    npc_knows = npc_detail.get("next_action") or conflict_source[:80] or "what happened — and who is responsible"

    loc_detail = {}
    if req.candidate_location_details:
        loc_detail = req.candidate_location_details[0]
    tension = loc_detail.get("current_tension") or ""
    sensory = _sensory_from_context(loc_name, campaign_name or setting_summary, genre, tone)
    if tension:
        sensory.append(tension[:80])

    # Specific stakes — name who suffers and by when
    if req.candidate_story_threads:
        stakes_who = npc_name or "the people involved"
        stakes = f"{stakes_who} cannot wait past tonight — what happens next will set what comes after."
    else:
        stakes = f"Every delay gives the forces moving through {loc_name} more time to shape what happens next."

    # World moves — living-world events happening outside the immediate scene
    world_moves: list[str] = []
    if req.candidate_story_threads:
        world_moves.append(f"{req.candidate_story_threads[0]} is still unresolved.")
    if req.recent_events:
        world_moves.append(req.recent_events[0])
    if loc_detail.get("current_tension"):
        world_moves.append(loc_detail["current_tension"][:80])
    if req.open_hooks and len(req.open_hooks) > 1:
        world_moves.append(req.open_hooks[1])
    # Fallback world moves that imply tension without being generic
    if not world_moves:
        world_moves = [
            f"Rumors are already changing how people move through {loc_name}.",
            "Someone with a stake in this moment is acting elsewhere right now.",
        ]

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
        why_player_is_involved=f"{player_name} is here and cannot ignore what is unfolding in front of them.",
        immediate_stakes=stakes,
        visual_prompt_elements=visual_elements,
        possible_actions=[
            f"Ask {npc_name} what they know",
            "Study the most obvious sign of trouble",
            "Watch who reacts strangely",
            "Look for a safer angle before acting",
        ],
        world_moves=world_moves[:4],
        source="deterministic",
    )


def _location_from_text(text: str, genre: str) -> str:
    hay = (text or "").lower()
    cleaned = " ".join((text or "").replace("—", " ").replace("-", " ").split())
    proper_words = [
        word.strip(".,:;!?()[]{}'\"")
        for word in cleaned.split()
        if word[:1].isupper()
    ]
    if len(proper_words) >= 2:
        return " ".join(proper_words[:3])
    if any(w in hay for w in ("ship", "station", "star", "void", "orbit", "alien")):
        return _varied_name(text, ["Kestrel", "Vesper", "Helion", "Morrow", "Cinder"], ["Dock", "Relay", "Berth", "Concourse"])
    if any(w in hay for w in ("court", "crown", "throne", "noble", "palace")):
        return _varied_name(text, ["Ashen", "Gilded", "Wolfshead", "Pearl", "Blackglass"], ["Petition Hall", "Gallery", "Gate", "Antechamber"])
    if any(w in hay for w in ("academy", "wizard", "arcane", "ritual", "spell")):
        return _varied_name(text, ["Vellum", "Starfall", "Candle", "Orrery", "Glass"], ["Archive", "Atrium", "Gate", "Scriptorium"])
    if any(w in hay for w in ("forest", "wild", "woods", "grove")):
        return _varied_name(text, ["Briar", "Greybough", "Moonfen", "Hollow", "Redleaf"], ["Edge", "Camp", "Track", "Grove"])
    if any(w in hay for w in ("ruin", "tomb", "crypt", "catacomb")):
        return _varied_name(text, ["Sunken", "Bone", "Ash", "Hollow", "Salt"], ["Threshold", "Vault", "Steps", "Reliquary"])
    if any(w in hay for w in ("city", "street", "guild", "market")):
        return _varied_name(text, ["Copper", "Lantern", "Grey", "Barrow", "Bell"], ["Market", "Ward", "Street", "Exchange"])
    if any(w in (genre or "").lower() for w in ("horror", "mystery")):
        return _varied_name(text or genre, ["Rain", "Pale", "Mourning", "Black", "Drowned"], ["Crossing", "Lane", "House", "Bridge"])
    return _varied_name(text or genre or "opening", ["Dawn", "Iron", "Thorn", "Cinder", "Hearth"], ["Ground", "Road", "Hollow", "Post"])


def _contact_from_text(text: str, genre: str) -> str:
    hay = (text or "").lower()
    if any(w in hay for w in ("academy", "wizard", "arcane", "ritual")):
        return _varied_person(text, ["Binder", "Adjunct", "Curator"], ["Ilyen", "Maelis", "Corven", "Tamsin", "Orris"])
    if any(w in hay for w in ("court", "crown", "throne", "noble")):
        return _varied_person(text, ["Factor", "Chamberlain", "Herald"], ["Odran", "Velis", "Kael", "Sovra", "Edrin"])
    if any(w in hay for w in ("ship", "station", "star", "alien")):
        return _varied_person(text, ["Quartermaster", "Pilot", "Dockhand"], ["Vale", "Rook", "Iven", "Sol", "Nara"])
    if any(w in hay for w in ("forest", "wild", "woods")):
        return _varied_person(text, ["Ranger", "Guide", "Warden"], ["Elian", "Mara", "Tovin", "Bran", "Selka"])
    if "horror" in (genre or "").lower():
        return _varied_person(text or genre, ["Keeper", "Witness", "Caretaker"], ["Rook", "Hale", "Maren", "Iosef", "Anya"])
    return _varied_person(text or genre or "contact", ["Witness", "Factor", "Guide"], ["Lio", "Tamsin", "Corren", "Edda", "Neris"])


def _stable_index(seed: str, modulo: int, *, salt: str = "") -> int:
    if modulo <= 0:
        return 0
    digest = hashlib.sha1(f"{salt}|{seed}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


def _varied_name(seed: str, prefixes: list[str], suffixes: list[str]) -> str:
    prefix = prefixes[_stable_index(seed, len(prefixes), salt="location-prefix")]
    suffix = suffixes[_stable_index(seed, len(suffixes), salt="location-suffix")]
    return f"The {prefix} {suffix}"


def _varied_person(seed: str, roles: list[str], names: list[str]) -> str:
    role = roles[_stable_index(seed, len(roles), salt="person-role")]
    name = names[_stable_index(seed, len(names), salt="person-name")]
    return f"{role} {name}"


def _first_story_signal(values: list[str]) -> str:
    for value in values or []:
        text = str(value or "").strip()
        if text and not _is_contract_heading_signal(text):
            return text
    return ""


def _is_contract_heading_signal(value: str) -> bool:
    normalized = value.strip().strip("[]").strip().lower().rstrip(":")
    if not normalized:
        return True
    if normalized in {
        "campaign contract",
        "campaign output contract",
        "agent output contract",
        "requirements",
        "contract",
    }:
        return True
    return normalized.startswith(("campaign output contract", "requirements for "))


def _npc_goal_from_context(location: str, conflict_source: str) -> str:
    if conflict_source:
        return "get the truth of the danger in front of them"
    if location:
        return f"protect what still matters at {location}"
    return "understand what changed before someone else pays for it"


def _inciting_from_context(location: str, text: str, genre: str) -> str:
    hay = (text or "").lower()
    if any(w in hay for w in ("mystery", "missing", "vanished", "secret")):
        return f"At {location}, a missing piece of the truth has just surfaced in public view."
    if any(w in hay for w in ("war", "siege", "battle", "invasion")):
        return f"At {location}, the first visible consequence of the coming conflict arrives ahead of the soldiers."
    if any(w in hay for w in ("survival", "winter", "storm", "scarcity")):
        return f"At {location}, supplies, weather, and fear collide at the worst possible hour."
    if "horror" in (genre or "").lower():
        return f"At {location}, something ordinary behaves in a way no one can explain."
    return f"At {location}, a local problem becomes urgent enough that waiting is no longer neutral."


def _sensory_from_context(location: str, text: str, genre: str, tone: str) -> list[str]:
    hay = " ".join([text or "", genre or "", tone or ""]).lower()
    if any(w in hay for w in ("winter", "frost", "snow", "ice")):
        return ["Cold air scrapes across exposed skin.", f"Frost has gathered along the edges of {location}."]
    if any(w in hay for w in ("storm", "rain", "sea", "flood")):
        return ["Rain ticks against every hard surface.", f"The ground around {location} shines with wet reflections."]
    if any(w in hay for w in ("desert", "ash", "sun", "sand")):
        return ["Dry grit catches in the throat.", f"Heat presses the color out of {location}."]
    if any(w in hay for w in ("horror", "grim", "dark")):
        return ["The air feels too still.", f"Every sound in {location} seems to arrive a heartbeat late."]
    return ["The air is tense with held breath.", f"Small details around {location} suddenly feel important."]


def _campaign_allows_tavern(req: SceneDirectorRequest) -> bool:
    contract = req.campaign_contract or {}
    hay = " ".join([
        str(req.campaign_settings.get("world_name") or ""),
        str(req.campaign_settings.get("setting_summary") or ""),
        str(req.campaign_settings.get("starting_location") or ""),
        str(req.campaign_variables.get("starting_location") or ""),
        str(contract.get("campaign_name") or ""),
        str(contract.get("campaign_pitch") or ""),
        str((contract.get("campaign_dna") or {}).get("starting_promise") or ""),
        str(req.plot_seed or ""),
    ]).lower()
    return any(w in hay for w in ("tavern", " inn", "inn ", "alehouse", "pub", "taproom"))


def _is_tavernish(value: str) -> bool:
    lowered = (value or "").lower()
    return any(w in lowered for w in ("tavern", " inn", "alehouse", "flagon", "tankard", "taproom", "wayward", "lantern inn"))


def _guard_against_unsupported_tavern(req: SceneDirectorRequest, out: SceneDirectorOutput) -> SceneDirectorOutput:
    loc = out.location.name or ""
    if not _is_tavernish(loc) or _campaign_allows_tavern(req):
        return out
    guarded = _deterministic_director(SceneDirectorRequest(
        campaign_settings=req.campaign_settings,
        campaign_variables=req.campaign_variables,
        players=req.players,
        plot_seed=req.plot_seed,
        candidate_npcs=req.candidate_npcs,
        candidate_npc_details=req.candidate_npc_details,
        candidate_locations=[],
        candidate_location_details=[],
        candidate_factions=req.candidate_factions,
        candidate_story_threads=req.candidate_story_threads,
        candidate_thread_details=req.candidate_thread_details,
        open_hooks=req.open_hooks,
        recent_events=req.recent_events,
        world_context_block=req.world_context_block,
        director_guidance=req.director_guidance,
        campaign_contract=req.campaign_contract,
    ))
    guarded.source = "deterministic_guard"
    return guarded


# ---------------------------------------------------------------------------
# LLM-backed director
# ---------------------------------------------------------------------------

_SCHEMA = (
    '{"scene_title":"","scene_type":"opening",'
    '"location":{"name":"","type":"","sensory_details":[]},'
    '"primary_npc":{"name":"","role":"","current_emotional_state":"","what_they_want":"","what_they_know":""},'
    '"secondary_entities":[],"central_conflict":"","inciting_incident":"","why_player_is_involved":"",'
    '"immediate_stakes":"","hidden_pressure":"","player_visible_clues":[],'
    '"possible_actions":[],"visual_prompt_elements":[],"continuity_notes":[],'
    '"world_moves":["living-world event 1","living-world event 2","living-world event 3"]}'
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
    if req.campaign_contract:
        contract_text = str(req.campaign_contract.get("agent_output_contract") or "").strip()
        canon = req.campaign_contract.get("canon_policy") or {}
        creativity = req.campaign_contract.get("ai_creativity_policy") or {}
        ui_policy = req.campaign_contract.get("ui_policy") or {}
        if contract_text:
            ctx.append("CAMPAIGN CONTRACT (mandatory operating agreement):\n" + contract_text[:1600])
        ctx.append(
            "CONTRACT POLICIES:\n"
            f"  — Canon mode: {canon.get('mode', 'guided_canon')} / major invention: {canon.get('major_invention', 'ask_first')}\n"
            f"  — AI creativity: {creativity.get('level', 'balanced')} / new elements per scene: {creativity.get('new_elements_per_scene', 2)}\n"
            f"  — UI emphasis: {', '.join((ui_policy.get('primary_widgets') or [])[:6])}"
        )

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

        # Hard opening constraints — pre-generated seed that must be used exactly
        opening_lines = []
        if dg.get("required_opening_location"):
            opening_lines.append(f"REQUIRED LOCATION (use this exactly): {dg['required_opening_location']}")
        if dg.get("required_opening_npc"):
            opening_lines.append(f"REQUIRED NPC (use this exactly): {dg['required_opening_npc']}")
        if dg.get("required_opening_event"):
            opening_lines.append(f"REQUIRED INCITING EVENT (use this exactly): {dg['required_opening_event']}")
        if dg.get("required_opening_stakes"):
            opening_lines.append(f"REQUIRED STAKES (use this exactly): {dg['required_opening_stakes']}")
        if dg.get("required_opening_decision"):
            opening_lines.append(f"REQUIRED PLAYER DECISION (use this exactly): {dg['required_opening_decision']}")
        if dg.get("required_opening_location_context"):
            opening_lines.append(f"REQUIRED SETTING CONTEXT: {dg['required_opening_location_context']}")
        if opening_lines:
            ctx.append(
                "OPENING SCENE CONSTRAINTS (mandatory — do not substitute, override, or ignore these):\n"
                + "\n".join(f"  — {item}" for item in opening_lines)
            )

        if director_lines:
            ctx.append("NARRATIVE DIRECTOR GUIDANCE (mandatory):\n" + "\n".join(f"  — {item}" for item in director_lines))

    system = (
        "You are a tabletop RPG Scene Director. Your job: convert campaign context into ONE concrete, "
        "immediately playable opening scene. Every field must be specific and grounded.\n\n"
        "REQUIREMENTS (non-negotiable):\n"
        f"  — location.name: use the REQUIRED LOCATION from the opening constraints if provided; otherwise a SPECIFIC named place that fits {genre} — NEVER a tavern, inn, alehouse, or pub unless the campaign explicitly demands it\n"
        f"  — primary_npc.name: use the REQUIRED NPC from the opening constraints if provided; otherwise a SPECIFIC named character — not 'a stranger' or 'a mysterious figure'\n"
        "  — central_conflict: a visible, immediate situation — not a vague mood\n"
        "  — inciting_incident: what physically happens in the opening moments — a strong verb required\n"
        f"  — why_player_is_involved: personal, professional, or accidental reason {player_name} cannot ignore this\n"
        "  — immediate_stakes: WHO suffers, WHAT is lost, BY WHEN — name the person and the deadline\n"
        "  — sensory_details: what you see, hear, or smell RIGHT NOW — physical and grounded\n"
        "  — visual_prompt_elements: 3–5 items for image generation (location + NPC + mood + key visual)\n"
        "  — world_moves: 2–4 living-world events happening OUTSIDE the immediate scene — "
        "subtle signals of a world in motion (not generic atmosphere, not duplicates of the main conflict)\n\n"
        "CONTENT PRIORITY ORDER:\n"
        "  1. Active story threads  2. Open hooks  3. NPC goals  4. Faction plans  5. Location tensions  6. Invent only if nothing else exists\n\n"
        "CAMPAIGN CONTRACT RULES:\n"
        "  — Obey the campaign contract if provided. It outranks generic genre assumptions.\n"
        "  — For strict canon, do not invent major factions, gods, cities, cosmology, or history; use provisional minor entities only.\n"
        "  — For mystery campaigns, preserve unanswered questions and create concrete clues.\n"
        "  — For high-agency campaigns, include multiple plausible approaches.\n\n"
        "FORBIDDEN — never write:\n"
        + "\n".join(f"  — \"{p}\"" for p in FORBIDDEN_GENERIC)
        + "\n  — 'if no one acts' or 'the situation will worsen' — stakes must be concrete, not conditional warnings"
        + "\n  — 'a disturbance' — name the specific event"
        + "\n  — tavern or inn as the default invented location when no tavern context exists"
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
                output = SceneDirectorOutput(
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
                    world_moves=[str(w) for w in (data.get("world_moves") or [])],
                    source="llm",
                )
                return _guard_against_unsupported_tavern(req, output)
    except Exception:
        pass

    return _guard_against_unsupported_tavern(req, _deterministic_director(req))


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
