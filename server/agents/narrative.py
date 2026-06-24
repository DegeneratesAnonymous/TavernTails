"""Narrative Agent: generates narration + prompt."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..steward_llm import chat_complete
from . import sessions as sessions_agent
from .references import search_query

router = APIRouter(tags=["narrative"])


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


class NarrativeResponse(BaseModel):
    narrative: str
    prompt: str
    tone: str


STYLE_TONES = {
    "gritty realism": "Actions leave scars; wounds don't heal overnight; consequences stick.",
    "cinematic heroism": "Daring feats reward courage; there is glory to be won.",
    "balanced": "Risk and reward are real; clever play is rewarded.",
}

_FORBIDDEN_NARRATIVE = [
    "heroic fantasy adventure",
    "high fantasy",
    "mysterious threat looms",
    "choices matter",
    "outcomes stay flexible",
    "the world is dangerous",
    "paths branch ahead",
    "genre",
]


def _build_director_system(
    sd: dict,
    player: str,
    style: str,
    weather_desc: str,
    time_of_day: str,
    validator_feedback: str | None,
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
        "You are a Dungeon Master writing ONE scene of a live tabletop RPG session.",
        "You have been given a concrete scene plan. Follow it exactly.",
        "",
        "SCENE PLAN:",
        f"  Location: {loc_name}",
    ]
    if sensory:
        lines.append(f"  Sensory details: {'; '.join(sensory)}")
    if npc_name:
        lines.append(f"  Primary NPC: {npc_name} — {npc_state}")
        if npc_wants:
            lines.append(f"  They want: {npc_wants}")
        if npc_knows:
            lines.append(f"  They know: {npc_knows}")
    if secondary:
        lines.append(f"  Also present: {', '.join(secondary[:3])}")
    if inciting:
        lines.append(f"  Inciting incident: {inciting}")
    if conflict:
        lines.append(f"  Central conflict: {conflict}")
    if stakes:
        lines.append(f"  Stakes: {stakes}")
    if clues:
        lines.append(f"  Player-visible clues: {'; '.join(clues[:3])}")
    lines.append(f"  Atmosphere: {weather_desc}, {time_of_day}")
    lines.append(f"  Tone: {style} — {tone_desc}")
    lines.append("")
    lines.append("WRITING REQUIREMENTS (non-negotiable):")
    lines.append(f"  1. Open IN the scene at {loc_name} — no preamble, no setup sentence")
    lines.append("  2. Include at least one physical sensory detail (what you see, smell, or hear right now)")
    if npc_name:
        lines.append(f"  3. Name {npc_name} directly and show their emotional state through action or dialogue")
    lines.append("  4. Show the conflict through a concrete visible event or piece of evidence — not a mood")
    lines.append("  5. Write exactly 3–5 sentences of present-tense narration")
    lines.append(f"  6. End with ONE player-facing question addressed to {player} by name")
    lines.append("")
    lines.append("FORBIDDEN — never write:")
    for phrase in _FORBIDDEN_NARRATIVE:
        lines.append(f"  — \"{phrase}\"")
    lines.append("  — Do not describe the genre or campaign tone")
    lines.append("  — Do not summarize the adventure or explain the setting")
    lines.append("  — Do not say 'the party' — use the character's name")
    if validator_feedback:
        lines.append("")
        lines.append("ADDITIONAL CORRECTION REQUIRED:")
        lines.append(validator_feedback)
    lines.append("")
    lines.append('Return ONLY valid JSON — no markdown, no preamble:')
    lines.append('{"narrative": "<3-5 present-tense sentences>", "prompt": "<one question addressed to the player character by name>"}')
    return "\n".join(lines)


def _build_generic_system(player: str, style: str, weather_desc: str, time_of_day: str, validator_feedback: str | None) -> str:
    """Fallback system prompt when no Scene Director data is available."""
    tone = STYLE_TONES.get(style.lower(), STYLE_TONES["balanced"])
    lines = [
        "You are an expert Dungeon Master narrating a live tabletop RPG session.",
        "Your writing is vivid, immediate, and grounds the player in a specific moment.",
        "",
        f"Tone: {style} — {tone}",
        f"Atmosphere: {weather_desc}, {time_of_day}",
        "",
        "REQUIREMENTS:",
        "  — Begin in-scene immediately (no setup sentence)",
        "  — Name at least one specific location",
        "  — Name at least one NPC or describe a concrete visible event",
        "  — Include one physical sensory detail",
        f"  — End with a player-facing question addressed to {player} by name",
        "  — Write 3–5 sentences of present-tense narration",
        "  — Never mention dice, game mechanics, or rules",
        "  — Never describe the genre or campaign structure",
    ]
    if validator_feedback:
        lines.append("")
        lines.append("CORRECTION REQUIRED:")
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


@router.post("/narrative/generate", response_model=NarrativeResponse)
def generate_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    weather_desc = "crisp and clear" if payload.weather == "clear" else payload.weather
    player = payload.player or "the party"
    default_prompt = f"{player}: What do you do?"

    # Default narration used only when LLM is completely unavailable
    default_narration = (
        f"The scene unfolds before you. The air is {weather_desc} and the {payload.time_of_day} "
        f"light plays across {payload.scene[:80] if payload.scene else 'the surroundings'}."
    )

    if payload.scene_director_data:
        system = _build_director_system(
            payload.scene_director_data, player, payload.style,
            weather_desc, payload.time_of_day, payload.validator_feedback,
        )
        # User message: the scene plan data as a structured reminder
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
        system = _build_generic_system(player, payload.style, weather_desc, payload.time_of_day, payload.validator_feedback)
        user_content = payload.scene or ""

    text = chat_complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        task_scope="taverntails_narrative",
        max_tokens=500,
        timeout=90.0,
    )

    if text:
        narrative, prompt = _parse_narrative_response(text, default_narration, default_prompt)
        return NarrativeResponse(narrative=narrative, prompt=prompt, tone=payload.style.lower())

    return NarrativeResponse(narrative=default_narration, prompt=default_prompt, tone=payload.style.lower())


class ContinueRequest(BaseModel):
    session_id: str
    player: str | None = None


@router.post("/narrative/continue", response_model=NarrativeResponse)
def continue_narrative(payload: ContinueRequest, current_user=Depends(get_current_user)):
    """Generate the next scene for a session by summarizing recent story + PCs/NPCs.

    This is intentionally lightweight; future improvements can call the LLM with rich context.
    """
    session_id = payload.session_id
    base = Path(__file__).resolve().parents[1] / 'sessions'
    folder = base / session_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail='Session not found')

    # Ensure caller is a session member.
    campaign_ruleset = ""
    meta_file = folder / 'meta.json'
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            identifier = sessions_agent._identifier_for_user(current_user)
            if not sessions_agent._user_is_member(meta, identifier):
                raise HTTPException(status_code=403, detail='Not a member of this session')
            # Resolve campaign ruleset for SRL game-system filtering (non-fatal).
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

    # Read recent story entries
    story_file = folder / 'story.json'
    story_text = ''
    try:
        if story_file.exists():
            entries = json.loads(story_file.read_text())
            # take last few narrative entries
            last = [e for e in entries if isinstance(e, dict) and e.get('type') in ('narration','scene')]
            last = last[-6:]
            story_text = ' '.join((e.get('text') or '') for e in last).strip()
    except Exception:
        story_text = ''

    # Read NPCs and PCs to surface context
    pcs = []
    npcs = []
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

    # Attempt to surface relevant rule passages from ingested reference PDFs.
    try:
        # Build a compact query from story and characters to find matching pages
        q_parts = []
        if story_text:
            q_parts.append(story_text)
        if pc_names:
            q_parts.append(pc_names)
        if npc_names:
            q_parts.append(npc_names)
        query = " ".join(q_parts).strip()
        if query:
            hits = search_query(
                query, top_k=3,
                system_only=True,
                game_system=campaign_ruleset or None,
            )
            if hits:
                scene_desc += "\nRelevant rule passages: "
                snippets = []
                for h in hits:
                    # safe access
                    src = h.get("source_id") or "unknown"
                    page = h.get("page")
                    snip = h.get("snippet") or ""
                    snippets.append(f"[{src} p{page}] {snip}")
                scene_desc += " | ".join(snippets)
    except Exception:
        # Non-fatal: if references fail, continue without them
        pass

    player = payload.player or 'the party'
    # Reuse generate_narrative logic to produce a short scene and prompt
    req = NarrativeRequest(scene=scene_desc, player=player)
    return generate_narrative(req)


class RegenerateRequest(BaseModel):
    session_id: str
    player: str | None = None


@router.post("/narrative/regenerate", response_model=NarrativeResponse)
def regenerate_narrative(payload: RegenerateRequest, current_user=Depends(get_current_user)):
    """Regenerate the current scene from scratch, ignoring recent story history.

    Useful when a player wants a fresh take on the current situation.
    """
    session_id = payload.session_id
    base = Path(__file__).resolve().parents[1] / 'sessions'
    folder = base / session_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail='Session not found')

    # Ensure caller is a session member.
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

    # Read PCs/NPCs for context but skip story history (fresh scene)
    pcs = []
    npcs = []
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
