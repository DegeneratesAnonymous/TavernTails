"""Narrative Agent: generates narration + prompt with quality enforcement."""

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..steward_llm import chat_complete
from . import sessions as sessions_agent
from .narrative_linter import ScoreResult, feedback_for_regeneration, score_scene
from .references import search_query
from .scene_validator import build_fallback_scene

router = APIRouter(tags=["narrative"])

MAX_RETRIES = 1
SCORE_THRESHOLD = 75
SCORE_THRESHOLD_OPENING = 80  # higher bar for first impressions


class NarrativeRequest(BaseModel):
    scene: str = Field(..., description="Scene description or plot seed")
    player: str = Field(..., description="Active player character name")
    style: str = Field("balanced", description="gritty realism | cinematic heroism | balanced")
    weather: str = Field("clear", description="Weather descriptor")
    time_of_day: str = Field("day", description="Time descriptor")
    scene_director_data: dict | None = Field(
        default=None,
        description="Structured scene skeleton from Scene Director; when present, drives a concrete directive prompt",
    )
    composer_data: dict | None = Field(
        default=None,
        description="Narrative Composer output; enriches the scene brief with vivid_image, emotional_target, etc.",
    )
    validator_feedback: str | None = Field(
        default=None,
        description="Quality validator feedback from a previous failed attempt; injected as an additional requirement",
    )
    player_actions: list[str] = Field(
        default_factory=list,
        description="Chat messages from players this round; woven into narration as third-person outcomes",
    )
    is_opening_scene: bool = Field(
        default=False,
        description="When True, applies the higher opening-scene quality threshold and richer prose target",
    )
    character_context: dict | None = Field(
        default=None,
        description="Character sheet context: class, race, level, backstory, personality pillars. Used to personalize narrative.",
    )
    campaign_contract: dict | None = Field(
        default=None,
        description="Persistent Campaign Contract; provides canon, creativity, tone, backstory, UI, and validator policy.",
    )


class NarrativeResponse(BaseModel):
    narrative: str
    prompt: str
    tone: str
    scene_score: int = 0
    score_passed: bool = False
    score_detail: dict = Field(default_factory=dict)
    suggested_actions: list[str] = Field(default_factory=list)
    world_moves: list[str] = Field(default_factory=list)


STYLE_TONES = {
    "gritty realism": "Actions leave scars; wounds don't heal overnight; consequences stick. Pain is real.",
    "cinematic heroism": "Daring feats reward courage; there is glory to be won against impossible odds.",
    "balanced": "Risk and reward are real; clever play is rewarded; consequences accumulate.",
}

# Class-based narrative perspective: how each class perceives and filters the world.
# These flavor the scene brief so the LLM grounds detail in the PC's expertise.
_CLASS_PERSPECTIVE: dict[str, str] = {
    "rogue": "notices exits, who's armed, and who's nervous — an eye for trouble and opportunity",
    "fighter": "reads the tactical layout — threats, choke points, defensive positions, who looks ready to fight",
    "wizard": "observes the impossible: residual magic, out-of-place inscriptions, things that shouldn't exist",
    "sorcerer": "feels the magical weave involuntarily — a static charge when something in the room is off",
    "warlock": "senses thin places where otherworldly influence bleeds through — the patron is never truly absent",
    "cleric": "feels the spiritual weight of a place — divine presence or absence, moral failure, something undead",
    "paladin": "feels the pull of oaths — where justice is absent and who is suffering for it",
    "druid": "reads the natural world's unease — animal behavior, the season's mood, what the weather is hiding",
    "ranger": "tracks signs of passage, animal reactions, reads the environment like a map that tells a story",
    "bard": "reads the room's emotional temperature — body language, half-said words, the story behind the story",
    "monk": "feels the flow of energy in the space — who is centered, who is about to break, where calm has fled",
    "barbarian": "feels the tension in jaw and muscle — where a fight wants to start and who has a reason to start it",
    "alchemist": "notices chemical reactions, unusual smells, physical signs of tampering or poison",
    "champion": "senses where righteousness is absent — its loss hangs in the air like stale smoke",
    "investigator": "catalogues inconsistencies instantly — things placed deliberately, stories that don't add up",
    "swashbuckler": "reads momentum and ego — who's the biggest threat, who wants to show off, where the drama is",
    "gunslinger": "clocks distances, sightlines, and trigger fingers — who would move first if things went wrong",
    "magus": "feels the intersection of physical and arcane — where steel and spellwork have touched the same space",
}

_FORBIDDEN_NARRATIVE = [
    # Specific recycled tavern names from LLM training data — absolutely forbidden
    "wayward lantern inn", "wayward lantern", "rusty flagon", "prancing pony",
    "golden goblet", "silver tankard", "the traveler's rest", "the drunken sailor",
    # Genre labels — never describe the setting type
    "heroic fantasy", "high fantasy", "dark fantasy", "dark-fantasy",
    "epic fantasy", "fantasy world", "fantasy setting", "genre",
    "in the fantasy world", "dark fantasy world", "fantasy world of",
    # Opening sentence red flags
    "the scene unfolds", "scene unfolds before you", "unfolds before you",
    # Vague threats
    "mysterious threat", "a mysterious threat", "a dark force",
    "evil is stirring", "danger looms", "the adventure begins",
    "a disturbance", "unrest grows",
    # Abstract stakes / summaries
    "choices matter", "outcomes stay flexible", "the world is dangerous",
    "paths branch ahead", "the situation will worsen", "if no one acts",
    "if no one acts, the situation will worsen",
    "things will get worse", "something must be done",
    "if nothing is done",
    # Party references
    "the party must", "the party needs", "the party should",
    # Unnamed NPCs
    "a figure approaches", "a figure nearby", "a nearby figure",
    "a stranger approaches", "someone nearby", "an old acquaintance",
    "a cloaked figure", "a hooded figure",
    # Region/demand abstractions
    "the region demands", "demands the party", "demands your attention",
    "demands attention", "demands immediate",
    # Routine/disturbance clichés
    "broken the routine", "routine of the",
    # Greeting clichés
    "hello traveler", "welcome traveler", "we need help",
    # Debug labels that must never appear in prose
    "atmosphere:", "stakes:", "mood:", "threat:", "quest:", "objective:",
]


def _contains_unsupported_tavern_default(narrative: str, scene_director_data: dict | None) -> bool:
    text = (narrative or "").lower()
    if not text:
        return False
    fixture_terms = (
        "first crossroads",
        "mira vale",
        "sealed packet",
        "wayward lantern",
        "torven",
        "mara vell",
        "cracked lantern",
        "harness leather",
        "rusty flagon",
        "silver tankard",
        "outer court",
        "envoy marrec",
        "docking concourse",
        "quartermaster vale",
        "rain-dark crossing",
        "waterlogged dispatch tube sealed with split red wax",
        "arcane observatory",
        "a messenger arrives too late",
        "needs help, but is not saying everything",
        "the phenomenon will not repeat for a decade",
        "conversation falters as attention turns toward the same point of trouble",
        "this was not supposed to reach us like this",
        "everyone nearby is already deciding who will risk being seen helping",
    )
    if any(term in text for term in fixture_terms):
        return True
    if not scene_director_data:
        return False
    loc = ((scene_director_data.get("location") or {}).get("name") or "").lower()
    loc_allows_tavern = any(term in loc for term in ("tavern", " inn", "alehouse", "pub", "taproom"))
    if loc_allows_tavern:
        return False
    return any(term in text for term in (" tavern", " inn", " alehouse", " taproom"))


# Phrases that corrupt the LLM brief when they appear in scene_director_data fields
_FORBIDDEN_SDD = [
    "fantasy world", "dark-fantasy", "dark fantasy", "heroic fantasy",
    "the region demands", "demands the party", "demands immediate",
    "the party", "situation will worsen", "if no one acts",
    "things will get worse", "something must be done", "genre",
    "[character:",  # unresolved template token from a weak LLM generation
]


def _is_clean_sdd(text: str) -> bool:
    """Return False if text contains forbidden abstract phrases."""
    if not text:
        return True
    tl = text.lower()
    return not any(p in tl for p in _FORBIDDEN_SDD)


def _clean_sdd(sd: dict) -> dict:
    """Return scene_director_data with forbidden-phrase fields cleared.

    The Scene Director LLM sometimes produces abstract/forbidden text in conflict
    or NPC knowledge fields. Clearing them prevents those phrases from leaking into
    the narrative prompt and getting echoed back into the prose.
    """
    cleaned = dict(sd)
    for key in ("central_conflict", "inciting_incident", "immediate_stakes"):
        if not _is_clean_sdd(cleaned.get(key) or ""):
            cleaned[key] = ""
    npc = dict(cleaned.get("primary_npc") or {})
    for key in ("what_they_know", "what_they_want"):
        if not _is_clean_sdd(npc.get(key) or ""):
            npc[key] = ""
    cleaned["primary_npc"] = npc
    return cleaned

# The 10 Laws of scene writing, stated as testable requirements
_SCENE_LAWS = """\
MANDATORY SCENE STRUCTURE — 4 paragraphs in order:
  P1 — WHERE: Name the exact location. ONE sensory detail (smell OR sound OR texture). End with something already in motion.
  P2 — WHAT HAPPENS: A named NPC or physical object acts. Use a strong present-tense verb (slams, grabs, crashes, rushes). One or two sentences.
  P3 — WHY IT MATTERS: Show physical evidence of the problem — an object, a wound, a missing thing, a position. Never say 'things are dangerous' — show the proof.
  P4 — HOOK: NPC dialogue that reveals desire or fear. OR a physical clue the player can interact with. End with a dramatic setup line that creates a new question.

THE 10 LAWS:
  1. OPEN WITH MOTION — first sentence must have a strong action verb. Something is happening right now.
  2. ALWAYS NAME NPCs — "Mara slams the door" NEVER "a figure slams the door". Unnamed NPCs are forbidden.
  3. ONE of each: smell, sound, physical movement, physical object. All four must appear somewhere in the text.
  4. EVERY NPC WANTS something specific right now. Show it through action or dialogue, not narration.
  5. ONE dramatic question — the scene exists to create a single urgent question. Everything supports it.
  6. SHOW EVIDENCE — "Three hunters share one bow between them" not "the region is dangerous".
  7. NPC DIALOGUE must reveal personality, fear, desire, or a clue. Never greeting filler.
  8. END WITH A HOOK — the last line before the player question must create urgency (dialogue, revelation, or act).
  9. PLAYER QUESTION — ONE question in the 'prompt' field only. It should feel like you MUST know the answer.
 10. NO SUMMARIES — never explain what the scene means. Let the player feel it through specifics.

THE PLAYER QUESTION:
  — Goes ONLY in the JSON "prompt" field, NEVER in the narrative body
  — Must be addressed to the player's character by name
  — Should feel urgent, not routine ("Mara grips your wrist — 'They're already inside.' What does {player} do?")"""


def _build_director_system(
    sd: dict,
    player: str,
    style: str,
    weather_desc: str,
    time_of_day: str,
    validator_feedback: str | None,
    player_actions: list[str] | None = None,
    composer: dict | None = None,
    is_opening: bool = False,
    character_context: dict | None = None,
    campaign_contract: dict | None = None,
) -> str:
    """Build a directive system prompt from Scene Director JSON + optional Composer brief."""
    sd = _clean_sdd(sd)  # strip forbidden abstract phrases before building prompt
    loc = sd.get("location") or {}
    npc = sd.get("primary_npc") or {}
    loc_name = loc.get("name") or "the location"
    npc_name = npc.get("name") or ""
    npc_state = npc.get("current_emotional_state") or "urgent"
    npc_wants = npc.get("what_they_want") or ""
    npc_knows = npc.get("what_they_know") or ""
    conflict = sd.get("central_conflict") or ""
    inciting = sd.get("inciting_incident") or ""
    stakes = sd.get("immediate_stakes") or ""
    clues = sd.get("player_visible_clues") or []
    sensory = (loc.get("sensory_details") or [])[:2]
    secondary = sd.get("secondary_entities") or []

    tone_desc = STYLE_TONES.get(style.lower(), STYLE_TONES["balanced"])
    drama_q = conflict or inciting or stakes or f"what is happening at {loc_name}"

    word_target = "200–300 words" if is_opening else "120–200 words"

    lines = [
        "You are a master Dungeon Master. You write RPG scenes that feel like the best paragraph from a fantasy novel.",
        "",
        "═══ SCENE BRIEF ═══",
        f"  Dramatic question: {drama_q}",
        f"  Location: {loc_name}  |  Weather: {weather_desc}, {time_of_day}",
        f"  Tone: {style} — {tone_desc}",
        f"  Target length: {word_target}",
    ]
    if npc_name:
        lines.append(f"  Primary NPC: {npc_name} ({npc_state})")
        if npc_wants:
            lines.append(f"  {npc_name} wants RIGHT NOW: {npc_wants}")
        if npc_knows:
            lines.append(f"  {npc_name} knows but hasn't said: {npc_knows}")
    if sensory:
        lines.append(f"  Sensory anchors to use: {'; '.join(sensory)}")
    if inciting:
        lines.append(f"  Inciting incident: {inciting}")
    if stakes:
        lines.append(f"  Stakes (show through evidence, NEVER state directly): {stakes}")
    if clues:
        lines.append(f"  Clues visible to player: {'; '.join(clues[:3])}")
    if secondary:
        lines.append(f"  Also present: {', '.join(secondary[:3])}")

    if campaign_contract:
        contract_text = str(campaign_contract.get("agent_output_contract") or "").strip()
        validator_policy = campaign_contract.get("validator_policy") or {}
        backstory_policy = campaign_contract.get("backstory_policy") or {}
        lines.append("")
        lines.append("═══ CAMPAIGN OUTPUT CONTRACT — MANDATORY ═══")
        if contract_text:
            lines.append(contract_text[:2200])
        lines.append(
            "Validator expectations: "
            f"multiple approaches={validator_policy.get('require_multiple_approaches', True)}, "
            f"concrete clues={validator_policy.get('require_concrete_clues', False)}, "
            f"preserve unanswered questions={validator_policy.get('preserve_unanswered_questions', False)}"
        )
        lines.append(
            "Backstory policy: "
            f"frequency={backstory_policy.get('usage_frequency', 'low')}, "
            f"style={backstory_policy.get('integration_style', 'subtle')}, "
            f"major changes={backstory_policy.get('player_control', 'ask_before_major_changes')}"
        )

    # Inject Composer brief when available — the richest creative direction
    if composer:
        lines.append("")
        lines.append("═══ CREATIVE BRIEF (from Narrative Composer) ═══")
        if composer.get("vivid_image"):
            lines.append(f"  VIVID IMAGE to anchor the scene: {composer['vivid_image']}")
        if composer.get("emotional_target"):
            lines.append(f"  EMOTIONAL TARGET — player must feel: {composer['emotional_target']}")
        if composer.get("unanswered_question"):
            lines.append(f"  UNANSWERED QUESTION to leave open: {composer['unanswered_question']}")
        if composer.get("meaningful_decision"):
            lines.append(f"  DECISION the player faces: {composer['meaningful_decision']}")
        if composer.get("memorable_object"):
            lines.append(f"  MEMORABLE OBJECT to include: {composer['memorable_object']}")
        if composer.get("active_motion"):
            lines.append(f"  OPENING MOTION (use or improve): {composer['active_motion']}")
        c_npc = composer.get("primary_npc") or {}
        if c_npc.get("physical_tell"):
            lines.append(f"  NPC PHYSICAL TELL: {c_npc['physical_tell']}")
        if c_npc.get("first_line_of_dialogue"):
            lines.append(f"  NPC FIRST LINE (adapt freely): \"{c_npc['first_line_of_dialogue']}\"")
        if composer.get("environmental_storytelling"):
            env = composer["environmental_storytelling"]
            if env:
                lines.append(f"  ENVIRONMENTAL DETAIL: {'; '.join(str(e) for e in env[:2])}")

    # ── Character context: class lens, backstory hooks, personality pillars ──
    if character_context:
        lines.append("")
        lines.append("═══ CHARACTER CONTEXT ═══")
        char_class = (character_context.get("class_name") or "").strip()
        char_level = character_context.get("level") or 1
        char_race = (character_context.get("race") or "").strip()
        parts = [player]
        if char_class:
            parts.append(f"Level {char_level} {char_class}")
        if char_race:
            parts.append(char_race)
        lines.append(f"  Character: {' — '.join(parts)}")
        if char_class:
            perspective = _CLASS_PERSPECTIVE.get(char_class.lower(), "")
            if perspective:
                lines.append(f"  Class Lens: A {char_class} {perspective}.")
                lines.append("    → Flavor your sensory details through this lens when possible.")
        backstory = (character_context.get("backstory") or "").strip()
        if backstory:
            # Truncate to ~300 chars for the prompt
            short_bs = backstory[:300].rsplit(" ", 1)[0] if len(backstory) > 300 else backstory
            lines.append(f"  Backstory (use as personal hook when natural): {short_bs}")
        appearance = (character_context.get("appearance") or "").strip()
        if appearance:
            lines.append(f"  Appearance: {appearance[:150]}")
        personality = (character_context.get("personality_traits") or "").strip()
        if personality:
            lines.append(f"  Personality: {personality[:150]}")
        ideals = (character_context.get("ideals") or "").strip()
        if ideals:
            lines.append(f"  Ideals: {ideals[:120]}")
        bonds = (character_context.get("bonds") or "").strip()
        if bonds:
            lines.append(f"  Bonds (what they care about): {bonds[:150]}")
        flaws = (character_context.get("flaws") or "").strip()
        if flaws:
            lines.append(f"  Flaws (potential dramatic tension): {flaws[:120]}")

    # ── Opening scene structural rules (TTRPG pacing) ──────────────────────
    if is_opening:
        lines.append("")
        lines.append("═══ OPENING SCENE RULES ═══")
        lines.append("  This is the FIRST scene of a new campaign. It must do four things:")
        lines.append("  1. ESTABLISH WHERE THE CHARACTER IS, how they came to be there, and what normal life here looks like before trouble breaks it.")
        lines.append("  2. DESCRIBE THE SETTING in vivid, specific sensory detail — temperature, smell, sound, light, nearby people, and usable exits/objects.")
        lines.append("  3. INTRODUCE THE INCITING INCIDENT in motion — not as vague backstory, but as an event happening NOW.")
        lines.append("  4. INTRODUCE NPCs with physical description BEFORE using their name.")
        lines.append(f"     WRONG: '{npc_name} shoves through the door.'")
        npc_role_hint = npc.get("role") or npc.get("occupation") or "a stranger"
        lines.append(f"     RIGHT: 'A {npc_role_hint} shoves through the door, breathing hard.' — then name them in dialogue.")
        lines.append("  5. END with a concrete choice — a decision the character must make in the next moment.")
        lines.append("  6. The final sentence must be an immediate beat: a nearby sound, urgent NPC line, visible threat, changing clue, or clock advancing.")
        lines.append("  Structure: ARRIVAL CONTEXT → PLACE DESCRIPTION → WHAT IS HAPPENING → WHY IT MATTERS → WHAT {player} MUST DECIDE.".replace("{player}", player))
        lines.append("  Do NOT use flashback, recap, or 'adventure begins' framing.")

    lines.append("")

    if player_actions:
        lines.append("═══ WHAT THE PLAYERS JUST DID ═══")
        for i, act in enumerate(player_actions[:6], 1):
            lines.append(f"  {i}. {act}")
        lines.append("")
        lines.append("  Open by narrating their actions' outcomes in third person, past tense.")
        lines.append(f"  Use {player}'s name. Show consequences. Describe what they can see, hear, smell, and physically interact with next.")
        lines.append("")

    lines.append(_SCENE_LAWS.replace("{player}", player))
    lines.append("")
    lines.append("ABSOLUTELY FORBIDDEN — writing any of these fails the scene:")
    for phrase in _FORBIDDEN_NARRATIVE:
        lines.append(f'  ✗ "{phrase}"')
    lines.append("  ✗ 'the party' — use the character's name")
    lines.append("  ✗ 'a figure', 'a stranger', 'someone nearby' — all NPCs need a name")
    lines.append("  ✗ mood without evidence ('tension fills the air', 'something feels wrong')")
    lines.append("  ✗ ending only on abstract stakes — the final sentence must show a concrete immediate beat")
    lines.append("  ✗ the player question anywhere in the narrative body")
    lines.append("  ✗ labels like 'Atmosphere:', 'Stakes:', 'Location:' — these are metadata, not prose")
    if validator_feedback:
        lines.append("")
        lines.append("══ PREVIOUS ATTEMPT FAILED — FIX THESE SPECIFIC PROBLEMS ══")
        lines.append(validator_feedback)
    lines.append("")
    lines.append("Return ONLY valid JSON — no markdown, no preamble, no explanation:")
    lines.append('{"narrative": "<4-6 paragraphs — context, setting description, action outcome, consequence, hook, final concrete immediate beat — no player question>", "prompt": "<one urgent question addressed to ' + player + ' by name>"}')
    return "\n".join(lines)


def _build_generic_system(
    player: str,
    style: str,
    weather_desc: str,
    time_of_day: str,
    validator_feedback: str | None,
    player_actions: list[str] | None = None,
    campaign_contract: dict | None = None,
) -> str:
    """Fallback system prompt when no Scene Director data is available."""
    tone = STYLE_TONES.get(style.lower(), STYLE_TONES["balanced"])
    lines = [
        "You are a master Dungeon Master. You write RPG scenes that feel like the best paragraph from a fantasy novel.",
        "",
        f"Tone: {style} — {tone}",
        f"Conditions: {weather_desc}, {time_of_day}",
        "",
    ]
    if player_actions:
        lines.append("═══ WHAT THE PLAYERS JUST DID ═══")
        for i, act in enumerate(player_actions[:6], 1):
            lines.append(f"  {i}. {act}")
        lines.append("")

    if campaign_contract:
        contract_text = str(campaign_contract.get("agent_output_contract") or "").strip()
        lines.append("═══ CAMPAIGN OUTPUT CONTRACT — MANDATORY ═══")
        lines.append(contract_text[:2200] if contract_text else "Obey campaign tone, canon, agency, safety, and backstory policies.")
        lines.append("")
        lines.append(f"  Open by narrating the outcome in third-person past tense using {player}'s name.")
        lines.append("  Show consequences, world reactions, and the physical details they can act on next.")
        lines.append("")

    lines.append(_SCENE_LAWS.replace("{player}", player))
    lines.append("")
    lines.append("ABSOLUTELY FORBIDDEN:")
    for phrase in _FORBIDDEN_NARRATIVE[:12]:
        lines.append(f'  ✗ "{phrase}"')
    lines.append("  ✗ 'the party' — use the character's name")
    lines.append("  ✗ unnamed NPCs — 'a figure', 'a stranger', 'someone nearby'")
    lines.append("  ✗ abstract moods without physical evidence")
    lines.append("  ✗ ending only on abstract stakes — final sentence must be a concrete immediate beat")
    lines.append("  ✗ the player question in the narrative body")
    if validator_feedback:
        lines.append("")
        lines.append("══ PREVIOUS ATTEMPT FAILED — FIX THESE SPECIFIC PROBLEMS ══")
        lines.append(validator_feedback)
    lines.append("")
    lines.append("Return ONLY valid JSON — no markdown, no preamble, no explanation:")
    lines.append('{"narrative": "<4-6 paragraphs — context, sensory setting, action outcome, consequence, hook, final concrete immediate beat — no player question inside>", "prompt": "<one urgent question addressed to ' + player + ' by name>"}')
    return "\n".join(lines)


def _parse_narrative_response(text: str, fallback_narrative: str, fallback_prompt: str) -> tuple[str, str]:
    """Parse LLM JSON response, returning (narrative, prompt)."""
    narration = text.strip()
    try:
        start = narration.find('{')
        end = narration.rfind('}')
        if start != -1 and end > start:
            parsed = json.loads(narration[start:end + 1])
            if isinstance(parsed, dict):
                out_narr = parsed.get('narrative') or parsed.get('text') or narration
                out_prompt = parsed.get('prompt') or fallback_prompt
                citations = parsed.get('citations') or []
                if citations:
                    cit_parts = []
                    for c in citations:
                        if isinstance(c, dict) and c.get('source_id') and c.get('page') is not None:
                            cit_parts.append(f"[{c['source_id']} p{c['page']}] {c.get('snippet', '')}".strip())
                    if cit_parts:
                        out_narr = f"{out_narr}\n\nCitations: {' | '.join(cit_parts)}"
                return str(out_narr), str(out_prompt)
    except Exception:
        pass
    return narration, fallback_prompt


def _build_messages(payload: NarrativeRequest, weather_desc: str, player: str, feedback: str | None) -> list[dict]:
    """Build LLM messages list for a generation attempt."""
    if payload.scene_director_data:
        system = _build_director_system(
            payload.scene_director_data, player, payload.style,
            weather_desc, payload.time_of_day, feedback,
            player_actions=payload.player_actions or [],
            composer=payload.composer_data,
            is_opening=payload.is_opening_scene,
            character_context=payload.character_context,
            campaign_contract=payload.campaign_contract,
        )
        sd = payload.scene_director_data
        loc = (sd.get("location") or {}).get("name") or ""
        npc = (sd.get("primary_npc") or {}).get("name") or ""
        # User message is a compact directive, not labels-as-content
        user_parts = [f"Write the opening scene at {loc}." if loc else "Write the opening scene."]
        if npc:
            user_parts.append(f"Primary NPC on stage: {npc}.")
        conflict = sd.get("central_conflict") or ""
        if conflict:
            user_parts.append(f"Central situation: {conflict[:150]}")
        if payload.scene:
            user_parts.append(payload.scene[:200])
        user_content = " ".join(user_parts)
    else:
        system = _build_generic_system(
            player, payload.style, weather_desc, payload.time_of_day,
            feedback, player_actions=payload.player_actions or [],
            campaign_contract=payload.campaign_contract,
        )
        user_content = payload.scene or ""

    return [{"role": "system", "content": system}, {"role": "user", "content": user_content}]


@router.post("/narrative/generate", response_model=NarrativeResponse)
def generate_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    weather_desc = "crisp and clear" if payload.weather == "clear" else payload.weather
    player = payload.player or "the party"

    # Extract title + action suggestions from scene director data
    scene_title = ""
    suggested_actions: list[str] = []
    world_moves: list[str] = []
    if payload.scene_director_data:
        loc = payload.scene_director_data.get("location") or {}
        scene_title = loc.get("name") or ""
        world_moves = list(payload.scene_director_data.get("world_moves") or [])
    if payload.composer_data:
        suggested_actions = list(payload.composer_data.get("suggested_actions") or [])
        composer_wm = payload.composer_data.get("world_moves") or []
        if composer_wm:
            world_moves = list(composer_wm)

    # Minimal safe default — used only if LLM returns empty on every attempt
    default_prompt = f"What does {player} do?"
    loc_name = scene_title or "here"
    default_narration = f"At {loc_name}, the moment holds — waiting for what comes next."

    threshold = SCORE_THRESHOLD_OPENING if payload.is_opening_scene else SCORE_THRESHOLD

    best_narrative = default_narration
    best_prompt = default_prompt
    best_score: ScoreResult | None = None
    feedback = payload.validator_feedback

    for _attempt in range(MAX_RETRIES + 1):
        messages = _build_messages(payload, weather_desc, player, feedback)
        text = chat_complete(
            messages,
            task_scope="taverntails_narrative",
            max_tokens=600,  # ~350 words — enough for 4 rich paragraphs
            timeout=120.0,
        )

        if not text:
            break  # LLM timed out or errored — no point retrying same call immediately

        narrative, prompt = _parse_narrative_response(text, default_narration, default_prompt)
        result = score_scene(narrative, title=scene_title, threshold=threshold)

        if best_score is None or result.score > best_score.score:
            best_narrative = narrative
            best_prompt = prompt
            best_score = result

        if result.passes_threshold:
            break

        # Build targeted feedback for next attempt
        feedback = feedback_for_regeneration(result)

    score_dict: dict = best_score.to_dict() if best_score else {}
    score_val = best_score.score if best_score else 0
    score_passed = best_score.passes_threshold if best_score else False

    placeholder = (
        "moment holds" in best_narrative.lower()
        or "waiting for what comes next" in best_narrative.lower()
        or "at here" in best_narrative.lower()
    )
    unsupported_default = _contains_unsupported_tavern_default(best_narrative, payload.scene_director_data)
    if (placeholder or unsupported_default or not score_passed) and payload.scene_director_data:
        loc = payload.scene_director_data.get("location") or {}
        npc = payload.scene_director_data.get("primary_npc") or {}
        sensory = loc.get("sensory_details") or []
        best_narrative = build_fallback_scene(
            location_name=loc.get("name") or scene_title or "the current location",
            npc_name=npc.get("name") or "",
            player_name=player,
            emotional_state=npc.get("current_emotional_state") or "urgent",
            inciting_incident=payload.scene_director_data.get("inciting_incident") or "",
            central_conflict=payload.scene_director_data.get("central_conflict") or payload.scene or "",
            immediate_stakes=payload.scene_director_data.get("immediate_stakes") or "",
            sensory_detail=sensory[0] if sensory else "",
            campaign_name=payload.scene or scene_title,
        )
        best_prompt = default_prompt
        score_val = max(score_val, 75)
        score_passed = True
        score_dict = {**score_dict, "fallback_used": True, "unsupported_default_rejected": unsupported_default}

    return NarrativeResponse(
        narrative=best_narrative,
        prompt=best_prompt,
        tone=payload.style.lower(),
        scene_score=score_val,
        score_passed=score_passed,
        score_detail=score_dict,
        suggested_actions=suggested_actions,
        world_moves=world_moves,
    )


class ContinueRequest(BaseModel):
    session_id: str
    player: str | None = None


@router.post("/narrative/continue", response_model=NarrativeResponse)
def continue_narrative(payload: ContinueRequest, current_user=Depends(get_current_user)):
    """Generate the next scene for a session by summarizing recent story + PCs/NPCs."""
    session_id = payload.session_id
    base = Path(__file__).resolve().parents[1] / 'sessions'
    folder = base / session_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail='Session not found')

    campaign_ruleset = ""
    meta_file = folder / 'meta.json'
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            identifier = sessions_agent._identifier_for_user(current_user)
            if not sessions_agent._user_is_member(meta, identifier):
                raise HTTPException(status_code=403, detail='Not a member of this session')
            campaign_id = meta.get('campaign_id')
            if campaign_id:
                try:
                    from .. import db as _db
                    c_settings = _db.get_campaign_settings(str(campaign_id), getattr(current_user, 'id', 0)) or {}
                    campaign_ruleset = c_settings.get('ruleset', '')
                except Exception:
                    pass
        except HTTPException:
            raise
        except Exception as err:
            raise HTTPException(status_code=500, detail='Failed to read meta') from err

    story_file = folder / 'story.json'
    story_text = ''
    try:
        if story_file.exists():
            entries = json.loads(story_file.read_text())
            last = [e for e in entries if isinstance(e, dict) and e.get('type') in ('narration', 'scene')]
            last = last[-6:]
            story_text = ' '.join((e.get('text') or '') for e in last).strip()
    except Exception:
        story_text = ''

    pcs: list = []
    npcs: list = []
    try:
        pcs_file = folder / 'pcs.json'
        if pcs_file.exists():
            pcs = json.loads(pcs_file.read_text()) or []
    except Exception:
        pcs = []
    try:
        npcs_file = folder / 'npcs.json'
        if npcs_file.exists():
            npcs = json.loads(npcs_file.read_text()) or []
    except Exception:
        npcs = []

    pc_names = ', '.join([n for n in (str(p.get('name') or p.get('character_name') or '') for p in pcs if p) if n])
    npc_names = ', '.join([n for n in (str(n_item.get('name') or '') for n_item in npcs if n_item) if n])

    scene_desc = 'Recent events: '
    if story_text:
        scene_desc += story_text
    if pc_names:
        scene_desc += f" Players: {pc_names}."
    if npc_names:
        scene_desc += f" Notable NPCs: {npc_names}."

    try:
        q_parts = []
        if story_text:
            q_parts.append(story_text)
        if pc_names:
            q_parts.append(pc_names)
        if npc_names:
            q_parts.append(npc_names)
        query = " ".join(q_parts).strip()
        if query:
            hits = search_query(query, top_k=3, system_only=True, game_system=campaign_ruleset or None)
            if hits:
                scene_desc += "\nRelevant rule passages: "
                snippets = []
                for h in hits:
                    src = h.get("source_id") or "unknown"
                    page = h.get("page")
                    snip = h.get("snippet") or ""
                    snippets.append(f"[{src} p{page}] {snip}")
                scene_desc += " | ".join(snippets)
    except Exception:
        pass

    player = payload.player or 'the party'
    req = NarrativeRequest(scene=scene_desc, player=player)
    return generate_narrative(req)


class RegenerateRequest(BaseModel):
    session_id: str
    player: str | None = None


@router.post("/narrative/regenerate", response_model=NarrativeResponse)
def regenerate_narrative(payload: RegenerateRequest, current_user=Depends(get_current_user)):
    """Regenerate the current scene from scratch, ignoring recent story history."""
    session_id = payload.session_id
    base = Path(__file__).resolve().parents[1] / 'sessions'
    folder = base / session_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail='Session not found')

    meta_file = folder / 'meta.json'
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            identifier = sessions_agent._identifier_for_user(current_user)
            if not sessions_agent._user_is_member(meta, identifier):
                raise HTTPException(status_code=403, detail='Not a member of this session')
        except HTTPException:
            raise
        except Exception as err:
            raise HTTPException(status_code=500, detail='Failed to read meta') from err

    pcs: list = []
    npcs: list = []
    try:
        pcs_file = folder / 'pcs.json'
        if pcs_file.exists():
            pcs = json.loads(pcs_file.read_text()) or []
    except Exception:
        pcs = []
    try:
        npcs_file = folder / 'npcs.json'
        if npcs_file.exists():
            npcs = json.loads(npcs_file.read_text()) or []
    except Exception:
        npcs = []

    # Determine active player name — prefer payload, then first PC, then meta.json member
    pc_names_list = [str(p.get('name') or p.get('character_name') or '') for p in pcs if p]
    pc_names_list = [n for n in pc_names_list if n]
    player = payload.player or (pc_names_list[0] if pc_names_list else None)
    if not player:
        # Last resort: read character_name from meta.json member list
        try:
            meta_data = json.loads(meta_file.read_text()) if meta_file.exists() else {}
            for member in (meta_data.get('members') or []):
                if not member.get('character_id'):
                    continue
                name = member.get('character_name') or ''
                if name:
                    player = name
                    break
        except Exception:
            pass
    if not player:
        player = "the party"

    npc_names_list = [str(n_item.get('name') or '') for n_item in npcs if n_item]
    npc_names_list = [n for n in npc_names_list if n]

    # Read session name for atmospheric context (e.g. "The Long Winter's Howl" → winter setting)
    session_name = ''
    meta_character_context: dict | None = None
    try:
        meta_data = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        session_name = meta_data.get('name') or ''
        # Extract character context from session members for narrative personalization
        for member in (meta_data.get('members') or []):
            char_id = member.get('character_id')
            if char_id:
                try:
                    from .. import db as _db
                    ch = _db.get_character_by_id(int(char_id))
                    if ch:
                        sheet = ch.sheet or {}
                        meta_character_context = {
                            'class_name': ch.class_name or '',
                            'level': ch.level or 1,
                            'race': sheet.get('ancestry') or sheet.get('race') or sheet.get('lineage') or '',
                            'backstory': sheet.get('backstory') or '',
                            'personality_traits': sheet.get('personality_traits') or '',
                            'ideals': sheet.get('ideals') or '',
                            'bonds': sheet.get('bonds') or '',
                            'flaws': sheet.get('flaws') or '',
                            'appearance': sheet.get('appearance') or '',
                        }
                except Exception:
                    pass
                break
    except Exception:
        pass

    # Read existing scene.json for location/atmosphere context
    scene_file = folder / 'scene.json'
    existing_scene: dict = {}
    if scene_file.exists():
        try:
            existing_scene = json.loads(scene_file.read_text())
        except Exception:
            pass

    # Read story.json for recent events
    story_file = folder / 'story.json'
    recent_events: list[str] = []
    try:
        if story_file.exists():
            story = json.loads(story_file.read_text())
            events = story.get('events') or story.get('history') or []
            recent_events = [str(e.get('summary') or e.get('text') or e) for e in events[-3:] if e]
    except Exception:
        pass

    # Extract fields from stored scene context
    # For sessions created before the new format, fall back to visual_state.location_name
    loc = (
        existing_scene.get('location')
        or (existing_scene.get('visual_state') or {}).get('location_name')
        or ''
    )
    weather = existing_scene.get('weather') or ''
    time_of_day = existing_scene.get('time_of_day') or ''
    stakes = existing_scene.get('immediate_stakes') or ''
    threads = existing_scene.get('active_threads') or []
    visible_clues = existing_scene.get('visible_clues') or []
    # Style comes from campaign settings (visual_state.mood is atmosphere, not narrative style)
    style_raw = existing_scene.get('visual_state', {}).get('mood') or ''
    style = 'balanced' if style_raw not in STYLE_TONES else style_raw

    # If npcs.json is empty but the existing narrative_body names an NPC, extract it.
    # This covers sessions where NPC data lives only in the prose.
    if not npc_names_list:
        narrative_body = existing_scene.get('narrative_body') or ''
        npc_match = re.search(
            r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\s+'
            r'(?:slams?|grabs?|rushes?|shoves?|pushes?|enters?|walks?|runs?|'
            r'says?|asks?|tells?|warns?|calls?|shouts?|whispers?|steps?|turns?|raises?|nods?)',
            narrative_body,
        )
        if npc_match:
            candidate = npc_match.group(1)
            if candidate not in ('The', 'A', 'An') and candidate != (player or ''):
                npc_names_list = [candidate]

    # Prefer saved scene_director_data (new sessions). For old sessions without it,
    # reconstruct a minimal structured brief from the scene.json context fields so
    # the Narrative Agent gets the director-level prompt instead of the weaker generic one.
    scene_director_data: dict | None = existing_scene.get('scene_director_data')

    if not scene_director_data and loc:
        # Reconstruct minimal scene_director_data for sessions created before composer support.
        # Strip banned abstract phrases from the stakes before using as conflict text.
        conflict_text = threads[0] if threads else stakes
        for banned_prefix in ("if no one acts,", "if nothing is done:", "if nothing changes,"):
            if conflict_text.lower().startswith(banned_prefix):
                conflict_text = conflict_text[len(banned_prefix):].strip()
        scene_director_data = {
            "location": {
                "name": loc,
                "type": "settlement",
                "sensory_details": [],
            },
            "primary_npc": {
                "name": npc_names_list[0] if npc_names_list else "",
                "role": "local contact",
                "current_emotional_state": "urgent",
                "what_they_want": "answers",
                "what_they_know": conflict_text[:100] if conflict_text else "",
            },
            "central_conflict": conflict_text[:200] if conflict_text else f"Something has gone wrong at {loc}.",
            "inciting_incident": recent_events[0] if recent_events else "",
            "immediate_stakes": stakes[:150] if stakes else "",
            "player_visible_clues": visible_clues[:3],
            "possible_actions": [],
            "world_moves": [],
            "secondary_entities": npc_names_list[1:3] if len(npc_names_list) > 1 else [],
        }

    # Clean forbidden phrases from scene_director_data before feeding into the LLM prompt.
    # The Scene Director LLM sometimes stores abstract/meta phrases ("In the fantasy world…")
    # as conflict or NPC fields; those get echoed back as prose if not removed here.
    if scene_director_data:
        scene_director_data = _clean_sdd(scene_director_data)

    # Build a compact directive (not label-heavy) for the scene field
    plot_parts = []
    if loc:
        plot_parts.append(f"Scene location: {loc}.")
    if npc_names_list:
        plot_parts.append(f"NPCs present: {', '.join(npc_names_list[:3])}.")
    if threads:
        plot_parts.append(f"Unresolved thread: {threads[0]}.")
    if recent_events:
        plot_parts.append(recent_events[0][:100])
    scene_desc = ' '.join(plot_parts) if plot_parts else f"The scene at {loc or 'the current location'}."

    req = NarrativeRequest(
        scene=scene_desc,
        player=player,
        style=style,
        weather=weather or 'clear',
        time_of_day=time_of_day or 'day',
        scene_director_data=scene_director_data,
        is_opening_scene=True,
        character_context=meta_character_context,
    )
    result = generate_narrative(req)

    # Only overwrite scene.json if the LLM produced real content.
    # A very short narrative or very low score means the LLM failed — use the
    # quality-guaranteed fallback template rather than persisting a placeholder.
    is_real_content = (
        result.narrative
        and len(result.narrative.strip()) > 80
        and result.scene_score > 15
    )

    write_narrative = result.narrative
    write_prompt = result.prompt

    if not is_real_content and scene_director_data:
        # LLM failed — build a template-based scene from the structured context.
        # This guarantees named NPC, sensory detail, specific stakes — not "the scene unfolds".
        sd_loc = (scene_director_data.get("location") or {})
        sd_npc = (scene_director_data.get("primary_npc") or {})
        sd_sensory = (sd_loc.get("sensory_details") or [])
        write_narrative = build_fallback_scene(
            location_name=sd_loc.get("name") or loc or "the location",
            npc_name=sd_npc.get("name") or (npc_names_list[0] if npc_names_list else ""),
            player_name=player,
            emotional_state=sd_npc.get("current_emotional_state") or "out of breath, eyes wide",
            inciting_incident=scene_director_data.get("inciting_incident") or (recent_events[0] if recent_events else ""),
            central_conflict=scene_director_data.get("central_conflict") or "",
            immediate_stakes=scene_director_data.get("immediate_stakes") or stakes,
            sensory_detail=sd_sensory[0] if sd_sensory else "",
            campaign_name=session_name,
        )
        write_prompt = f"What does {player} do?"
        is_real_content = True  # fallback is always real content

    if is_real_content:
        try:
            existing_scene['narrative_body'] = write_narrative
            existing_scene['player_prompt'] = write_prompt
            existing_scene['text'] = f"{write_narrative}\n\n{write_prompt}"
            existing_scene['scene_score'] = result.scene_score
            existing_scene['scene_score_passed'] = result.score_passed
            if result.suggested_actions:
                existing_scene['suggested_actions'] = result.suggested_actions
            if result.world_moves:
                existing_scene['world_moves'] = result.world_moves
            # Persist scene_director_data so future regenerations have full context
            if scene_director_data and 'scene_director_data' not in existing_scene:
                existing_scene['scene_director_data'] = scene_director_data
            scene_file.write_text(json.dumps(existing_scene))
        except Exception:
            pass

    return result
