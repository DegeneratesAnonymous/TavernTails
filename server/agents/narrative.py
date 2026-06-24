"""Narrative Agent: generates narration + prompt with quality enforcement."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..steward_llm import chat_complete
from . import sessions as sessions_agent
from .narrative_linter import ScoreResult, feedback_for_regeneration, score_scene
from .references import search_query

router = APIRouter(tags=["narrative"])

MAX_RETRIES = 2
SCORE_THRESHOLD = 75


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
    validator_feedback: str | None = Field(
        default=None,
        description="Quality validator feedback from a previous failed attempt; injected as an additional requirement",
    )
    player_actions: list[str] = Field(
        default_factory=list,
        description="Chat messages from players this round; woven into narration as third-person outcomes",
    )


class NarrativeResponse(BaseModel):
    narrative: str
    prompt: str
    tone: str
    scene_score: int = 0
    score_passed: bool = False
    score_detail: dict = Field(default_factory=dict)


STYLE_TONES = {
    "gritty realism": "Actions leave scars; wounds don't heal overnight; consequences stick. Pain is real.",
    "cinematic heroism": "Daring feats reward courage; there is glory to be won against impossible odds.",
    "balanced": "Risk and reward are real; clever play is rewarded; consequences accumulate.",
}

_FORBIDDEN_NARRATIVE = [
    "heroic fantasy",
    "high fantasy",
    "dark fantasy",
    "dark-fantasy",
    "epic fantasy",
    "fantasy world",
    "mysterious threat",
    "choices matter",
    "outcomes stay flexible",
    "the world is dangerous",
    "paths branch ahead",
    "genre",
    "the party must",
    "a dark force",
    "evil is stirring",
    "danger looms",
    "the adventure begins",
    "a disturbance",
    "unrest grows",
    "an old acquaintance",
]

_WRITING_PRINCIPLES = [
    "Write from INSIDE the scene — open mid-action, not with setup",
    "First sentence must place the reader in a specific physical location with sensory grounding",
    "Show NPCs acting, not waiting — they are doing something when the players arrive",
    "Concrete visible events over mood — 'Dara slams the ledger shut' beats 'tension fills the air'",
    "Named characters only — never 'a figure', 'a stranger', or 'someone nearby'",
    "Specific stakes with a clock — 'by dusk' or 'before the guard rotation' beats 'things will get worse'",
    "One strong question at the end, addressed to the player by name — never repeated or doubled",
    "3–5 sentences total — trim every word that doesn't earn its place",
]


def _build_director_system(
    sd: dict,
    player: str,
    style: str,
    weather_desc: str,
    time_of_day: str,
    validator_feedback: str | None,
    player_actions: list[str] | None = None,
) -> str:
    """Build a directive system prompt from Scene Director JSON."""
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

    lines = [
        "You are a master Dungeon Master writing ONE scene of a live tabletop RPG session.",
        "You write like a Sly Flourish keynote — immediate, grounded, never vague.",
        "You follow The Alexandrian's Three Clue Rule: any important fact has three ways to discover it.",
        "",
        "SCENE PLAN — follow exactly:",
        f"  Location: {loc_name}",
    ]
    if sensory:
        lines.append(f"  Sensory details to use: {'; '.join(sensory)}")
    if npc_name:
        lines.append(f"  Primary NPC: {npc_name} — current state: {npc_state}")
        if npc_wants:
            lines.append(f"  {npc_name} wants: {npc_wants}")
        if npc_knows:
            lines.append(f"  {npc_name} knows: {npc_knows}")
    if secondary:
        lines.append(f"  Also present: {', '.join(secondary[:3])}")
    if inciting:
        lines.append(f"  Inciting incident: {inciting}")
    if conflict:
        lines.append(f"  Central conflict: {conflict}")
    if stakes:
        lines.append(f"  Immediate stakes: {stakes}")
    if clues:
        lines.append(f"  Player-visible clues: {'; '.join(clues[:3])}")
    lines.append(f"  Atmosphere: {weather_desc}, {time_of_day}")
    lines.append(f"  Tone: {style} — {tone_desc}")
    lines.append("")

    if player_actions:
        lines.append("WHAT THE PLAYERS DID (this round):")
        for i, act in enumerate(player_actions[:6], 1):
            lines.append(f"  {i}. {act}")
        lines.append("")
        lines.append("NARRATIVE WEAVING — required:")
        lines.append(f"  — Open with the outcome of the players' actions in third person, past tense")
        lines.append(f"  — Use {player}'s name when describing what they did")
        lines.append("  — Show the world's reaction: NPC responses, environmental changes, consequences")
        lines.append("  — Then transition naturally into the new situation at the scene location")
        lines.append("  — Never invent actions the players didn't take")
        lines.append("")

    lines.append("WRITING REQUIREMENTS — non-negotiable:")
    for i, principle in enumerate(_WRITING_PRINCIPLES, 1):
        lines.append(f"  {i}. {principle}")
    lines.append("")
    if npc_name:
        lines.append(f"  → {npc_name} must appear by name and be shown doing something specific")
        lines.append(f"  → Use the scene's sensory details: {'; '.join(sensory) if sensory else 'invent two concrete ones'}")
    lines.append(f"  → End with one direct question to {player}")
    lines.append("")
    lines.append("FORBIDDEN — never write:")
    for phrase in _FORBIDDEN_NARRATIVE:
        lines.append(f'  — "{phrase}"')
    lines.append("  — abstract moods without physical evidence ('tension fills the air')")
    lines.append("  — genre labels or campaign descriptions")
    lines.append(f"  — 'the party' — use {player}'s name")
    lines.append("  — duplicate player-facing questions")
    if validator_feedback:
        lines.append("")
        lines.append("PREVIOUS ATTEMPT FAILED — CORRECTIONS REQUIRED:")
        lines.append(validator_feedback)
    lines.append("")
    lines.append('Return ONLY valid JSON — no markdown, no preamble, no explanation:')
    lines.append('{"narrative": "<3-5 present-tense sentences>", "prompt": "<one question addressed to the player character by name>"}')
    return "\n".join(lines)


def _build_generic_system(
    player: str,
    style: str,
    weather_desc: str,
    time_of_day: str,
    validator_feedback: str | None,
    player_actions: list[str] | None = None,
) -> str:
    """Fallback system prompt when no Scene Director data is available."""
    tone = STYLE_TONES.get(style.lower(), STYLE_TONES["balanced"])
    lines = [
        "You are a master Dungeon Master narrating a live tabletop RPG session.",
        "Your writing is immediate, concrete, and grounds the player in a specific physical moment.",
        "You never use genre labels, abstract moods, or setup sentences.",
        "",
        f"Tone: {style} — {tone}",
        f"Atmosphere: {weather_desc}, {time_of_day}",
        "",
    ]
    if player_actions:
        lines.append("WHAT THE PLAYERS DID (this round):")
        for i, act in enumerate(player_actions[:6], 1):
            lines.append(f"  {i}. {act}")
        lines.append("")
        lines.append("NARRATIVE WEAVING — required:")
        lines.append(f"  — Open with the third-person past-tense outcome of those actions, using {player}'s name")
        lines.append("  — Show consequences and world reactions before introducing the new situation")
        lines.append("")

    lines.append("REQUIREMENTS:")
    for principle in _WRITING_PRINCIPLES:
        lines.append(f"  — {principle}")
    lines.append("")
    lines.append("FORBIDDEN:")
    for phrase in _FORBIDDEN_NARRATIVE[:8]:
        lines.append(f'  — "{phrase}"')
    lines.append("  — abstract mood statements without physical evidence")
    lines.append("  — genre descriptions or campaign framing")
    lines.append(f"  — 'the party' — use {player}'s name")
    if validator_feedback:
        lines.append("")
        lines.append("PREVIOUS ATTEMPT FAILED — CORRECTIONS REQUIRED:")
        lines.append(validator_feedback)
    lines.append("")
    lines.append('Return ONLY valid JSON — no markdown, no preamble:')
    lines.append('{"narrative": "<3-5 present-tense sentences>", "prompt": "<one question addressed to the player by name>"}')
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
        )
        sd = payload.scene_director_data
        loc = (sd.get("location") or {}).get("name") or ""
        npc = (sd.get("primary_npc") or {}).get("name") or ""
        user_content = "\n".join(filter(None, [
            f"Location: {loc}",
            f"NPC: {npc}" if npc else "",
            f"Conflict: {sd.get('central_conflict', '')[:150]}",
            f"Inciting: {sd.get('inciting_incident', '')[:150]}",
            f"Stakes: {sd.get('immediate_stakes', '')[:100]}",
            f"Player: {player}",
            payload.scene[:200] if payload.scene else "",
        ]))
    else:
        system = _build_generic_system(
            player, payload.style, weather_desc, payload.time_of_day,
            feedback, player_actions=payload.player_actions or [],
        )
        user_content = payload.scene or ""

    return [{"role": "system", "content": system}, {"role": "user", "content": user_content}]


@router.post("/narrative/generate", response_model=NarrativeResponse)
def generate_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    weather_desc = "crisp and clear" if payload.weather == "clear" else payload.weather
    player = payload.player or "the party"
    default_prompt = f"{player}: What do you do?"

    default_narration = (
        f"The scene unfolds before you. The air is {weather_desc} and the {payload.time_of_day} "
        f"light plays across {payload.scene[:80] if payload.scene else 'the surroundings'}."
    )

    # Extract title for linting (use location name if available)
    scene_title = ""
    if payload.scene_director_data:
        loc = payload.scene_director_data.get("location") or {}
        scene_title = loc.get("name") or ""

    best_narrative = default_narration
    best_prompt = default_prompt
    best_score: ScoreResult | None = None
    feedback = payload.validator_feedback

    for attempt in range(MAX_RETRIES + 1):
        messages = _build_messages(payload, weather_desc, player, feedback)
        text = chat_complete(
            messages,
            task_scope="taverntails_narrative",
            max_tokens=500,
            timeout=90.0,
        )

        if not text:
            break

        narrative, prompt = _parse_narrative_response(text, default_narration, default_prompt)
        result = score_scene(narrative, title=scene_title, threshold=SCORE_THRESHOLD)

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

    return NarrativeResponse(
        narrative=best_narrative,
        prompt=best_prompt,
        tone=payload.style.lower(),
        scene_score=score_val,
        score_passed=score_passed,
        score_detail=score_dict,
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

    pc_names = ', '.join([n for n in (str(p.get('name') or p.get('character_name') or '') for p in pcs if p) if n])
    npc_names = ', '.join([n for n in (str(n_item.get('name') or '') for n_item in npcs if n_item) if n])

    scene_desc = 'The scene opens anew.'
    if pc_names:
        scene_desc += f" Players: {pc_names}."
    if npc_names:
        scene_desc += f" Notable NPCs: {npc_names}."

    player = payload.player or 'the party'
    req = NarrativeRequest(scene=scene_desc, player=player)
    return generate_narrative(req)
