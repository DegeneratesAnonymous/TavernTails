"""Generative endpoints for player-led campaigns.

These endpoints provide GM tools for generating NPCs, locations, and loot
that factor in campaign context and details.  When OPENAI_API_KEY is set the
endpoints delegate to the configured model; otherwise they fall back to
lightweight placeholder responses so the UI stays functional without a key.
"""

import json
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..auth import get_current_user
from .srd import build_ruleset_prompt_context

router = APIRouter(prefix="/generate", tags=["generate"])


def _get_model(settings: Dict[str, Any]) -> str:
    """Return the OpenAI model to use, respecting campaign-level override."""
    return settings.get("ai_model") or os.environ.get("OPENAI_MODEL", "gpt-4o")


def _call_llm(system_prompt: str, user_content: str, settings: Dict[str, Any]) -> Dict[str, Any] | None:
    """Call the configured OpenAI model and return a parsed JSON dict, or None on failure.

    Returns None when no API key is configured or when the call / parse fails so
    callers can fall back to placeholder data transparently.
    """
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return None
    try:
        import openai

        openai.api_key = openai_key
        model = _get_model(settings)
        max_tokens = int(os.environ.get("OPENAI_MAX_TOKENS", "500"))
        temp = float(os.environ.get("OPENAI_TEMPERATURE", "0.7"))

        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=max_tokens,
            temperature=temp,
        )
        text = ""
        if resp and isinstance(resp, dict):
            choices = resp.get("choices") or []
            if choices and isinstance(choices, list):
                text = (choices[0].get("message") or {}).get("content") or ""
        if not text:
            return None
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        return None
    except Exception:
        return None


def _require_user_id(current_user) -> int:
    owner_id = getattr(current_user, 'id', None)
    if not isinstance(owner_id, int):
        raise HTTPException(status_code=401, detail='Invalid authentication credentials')
    return owner_id


class GenerateRequest(BaseModel):
    campaign_id: str
    context: Dict[str, Any] | None = None


class GenerateNPCRequest(GenerateRequest):
    npc_type: str | None = None  # e.g., "merchant", "guard", "villain"
    setting: str | None = None
    character_id: int | None = None  # optional: pull detected system + skills from this character


class GenerateLocationRequest(GenerateRequest):
    location_type: str | None = None  # e.g., "tavern", "dungeon", "forest"
    mood: str | None = None


class GenerateLootRequest(GenerateRequest):
    challenge_rating: int | None = None
    loot_type: str | None = None  # e.g., "treasure", "equipment", "magic_item"


@router.post('/npc')
def generate_npc(req: GenerateNPCRequest, current_user=Depends(get_current_user)):
    """Generate an NPC with campaign context."""
    user_id = _require_user_id(current_user)

    # Get campaign to verify ownership and check mode
    campaign = db.get_campaign_by_id(req.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if campaign.owner_id != user_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    # Get campaign settings for context
    settings = db.get_campaign_settings(req.campaign_id, user_id) or {}
    # Ownership verified above; or {} handles the "variables not yet configured" case.
    variables = db.get_campaign_variables(req.campaign_id, user_id) or {}

    # Optionally pull TTRPG system + skills from a player character sheet.
    # This lets agents tailor output to the specific ruleset in use.
    character_system: Dict[str, Any] = {}
    if req.character_id is not None:
        char = db.get_character_for_owner(character_id=req.character_id, owner_id=user_id)
        if char and char.sheet:
            detected = (char.sheet or {}).get('detected_system') or {}
            character_system = {
                # Use system-agnostic mechanic descriptors inferred from the player's
                # own sheet data.  These do not name any trademarked system, so the
                # AI can tailor output to the character's mechanics without reproducing
                # copyrighted rules text.
                'mechanic_profile': detected.get('mechanic_profile', {}),
                'system_confidence': detected.get('confidence', 0.0),
                'player_skills': [
                    s.get('name') for s in ((char.sheet or {}).get('skills') or [])
                    if isinstance(s, dict) and s.get('name')
                ],
                'player_class': char.class_name or '',
                'player_level': char.level or 1,
            }

    # Build context for generation
    ruleset_id = settings.get("ruleset", "")
    context = {
        "world_name": settings.get("world_name", ""),
        "setting_summary": settings.get("setting_summary", ""),
        "tone": settings.get("tone", ""),
        "ruleset": ruleset_id,
        "ruleset_context": build_ruleset_prompt_context(ruleset_id),
        "npc_type": req.npc_type or "generic",
        "setting": req.setting or "",
        # campaign variables
        "themes": variables.get("themes", []),
        "pacing": variables.get("pacing", "moderate"),
        "narrative_style": variables.get("narrative_style", "balanced"),
        # factions with full data (alignment, goals, members) for goal-based NPC motivations
        "factions": variables.get("factions", []),
        "npc_archetypes": variables.get("npc_archetypes", []),
        "naming_style": variables.get("naming_style", ""),
        "content_rating": variables.get("content_rating", "pg-13"),
        # system-aware context derived from the player's character sheet
        **character_system,
        **(req.context or {}),
    }

    system_prompt = (
        "You are a creative tabletop GM generating an NPC for a campaign. "
        "Using the provided campaign context, produce a JSON object with the following fields: "
        "name, description, personality, motivation, appearance, faction_affiliation. "
        "Keep it concise, evocative, and consistent with the world tone. "
        "Do not reproduce copyrighted rules text; use generic mechanic descriptors only. "
        "Return only the JSON object, no extra commentary."
    )
    user_content = json.dumps(
        {
            "world": settings.get("world_name", ""),
            "tone": settings.get("tone", ""),
            "npc_type": req.npc_type or "generic",
            "setting": req.setting or "",
            "themes": variables.get("themes", []),
            "factions": variables.get("factions", []),
            "content_rating": variables.get("content_rating", "pg-13"),
            "ruleset_context": build_ruleset_prompt_context(ruleset_id),
        }
    )

    llm_result = _call_llm(system_prompt, user_content, settings)
    npc: Dict[str, Any]
    if llm_result:
        npc = {
            "name": llm_result.get("name", f"Generated NPC ({req.npc_type or 'generic'})"),
            "description": llm_result.get("description", ""),
            "personality": llm_result.get("personality", ""),
            "motivation": llm_result.get("motivation", ""),
            "appearance": llm_result.get("appearance", ""),
            "faction_affiliation": llm_result.get("faction_affiliation", ""),
            "context": context,
            "stats": {
                "level": settings.get("starting_level", 1),
                "ruleset": ruleset_id,
            },
        }
    else:
        npc = {
            "name": f"Generated NPC ({req.npc_type or 'generic'})",
            "description": f"A {req.npc_type or 'character'} from {settings.get('world_name', 'the world')}",
            "personality": f"Fitting the {settings.get('tone', 'standard')} tone",
            "context": context,
            "stats": {
                "level": settings.get("starting_level", 1),
                # User-entered ruleset ID (e.g. "srd-5.2").
                # Mechanic behaviour for AI prompts lives in context['ruleset_context'].
                "ruleset": ruleset_id,
            },
        }

    return {"npc": npc, "campaign_id": req.campaign_id}


@router.post('/location')
def generate_location(req: GenerateLocationRequest, current_user=Depends(get_current_user)):
    """Generate a location with campaign context."""
    user_id = _require_user_id(current_user)

    # Get campaign to verify ownership and check mode
    campaign = db.get_campaign_by_id(req.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if campaign.owner_id != user_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    # Get campaign settings for context
    settings = db.get_campaign_settings(req.campaign_id, user_id) or {}
    # Ownership verified above; or {} handles the "variables not yet configured" case.
    variables = db.get_campaign_variables(req.campaign_id, user_id) or {}

    # Build context for generation
    context = {
        "world_name": settings.get("world_name", ""),
        "setting_summary": settings.get("setting_summary", ""),
        "tone": settings.get("tone", ""),
        "location_type": req.location_type or "generic",
        "mood": req.mood or "",
        # campaign variables
        "themes": variables.get("themes", []),
        "pacing": variables.get("pacing", "moderate"),
        "narrative_style": variables.get("narrative_style", "balanced"),
        "factions": variables.get("factions", []),
        "content_rating": variables.get("content_rating", "pg-13"),
        **(req.context or {}),
    }

    system_prompt = (
        "You are a creative tabletop GM generating a location for a campaign. "
        "Using the provided campaign context, produce a JSON object with the following fields: "
        "name, description, atmosphere, points_of_interest (a list of strings), "
        "rumors (a list of strings), connections_to_factions. "
        "Keep it evocative and consistent with the world tone. "
        "Do not reproduce copyrighted rules text. "
        "Return only the JSON object, no extra commentary."
    )
    user_content = json.dumps(
        {
            "world": settings.get("world_name", ""),
            "tone": settings.get("tone", ""),
            "location_type": req.location_type or "generic",
            "mood": req.mood or "",
            "themes": variables.get("themes", []),
            "factions": variables.get("factions", []),
            "content_rating": variables.get("content_rating", "pg-13"),
        }
    )

    llm_result = _call_llm(system_prompt, user_content, settings)
    location: Dict[str, Any]
    if llm_result:
        location = {
            "name": llm_result.get("name", f"Generated Location ({req.location_type or 'place'})"),
            "description": llm_result.get("description", ""),
            "atmosphere": llm_result.get("atmosphere", ""),
            "points_of_interest": llm_result.get("points_of_interest", []),
            "rumors": llm_result.get("rumors", []),
            "connections_to_factions": llm_result.get("connections_to_factions", ""),
            "mood": req.mood or settings.get("tone", ""),
            "context": context,
        }
    else:
        location = {
            "name": f"Generated Location ({req.location_type or 'place'})",
            "description": f"A {req.location_type or 'location'} in {settings.get('world_name', 'the world')}",
            "atmosphere": f"Matching the {settings.get('tone', 'standard')} tone",
            "mood": req.mood or settings.get("tone", ""),
            "context": context,
        }

    return {"location": location, "campaign_id": req.campaign_id}


@router.post('/loot')
def generate_loot(req: GenerateLootRequest, current_user=Depends(get_current_user)):
    """Generate loot/items with campaign context."""
    user_id = _require_user_id(current_user)

    # Get campaign to verify ownership and check mode
    campaign = db.get_campaign_by_id(req.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if campaign.owner_id != user_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    # Get campaign settings for context
    settings = db.get_campaign_settings(req.campaign_id, user_id) or {}
    # Ownership verified above; or {} handles the "variables not yet configured" case.
    variables = db.get_campaign_variables(req.campaign_id, user_id) or {}

    ruleset_id = settings.get("ruleset", "")
    # Build context for generation
    context = {
        "world_name": settings.get("world_name", ""),
        "setting_summary": settings.get("setting_summary", ""),
        "ruleset": ruleset_id,
        "ruleset_context": build_ruleset_prompt_context(ruleset_id),
        "starting_level": settings.get("starting_level", 1),
        "challenge_rating": req.challenge_rating or settings.get("starting_level", 1),
        "loot_type": req.loot_type or "treasure",
        # campaign variables
        "themes": variables.get("themes", []),
        "narrative_style": variables.get("narrative_style", "balanced"),
        "content_rating": variables.get("content_rating", "pg-13"),
        **(req.context or {}),
    }

    cr = req.challenge_rating or settings.get("starting_level", 1)
    system_prompt = (
        "You are a creative tabletop GM generating loot for a campaign encounter. "
        "Using the provided context, produce a JSON object with the following fields: "
        "name, description, items (a list of objects each with: name, quantity, type, rarity, description), "
        "total_value_gp. "
        f"Items should be appropriate for challenge rating {cr} and the provided ruleset. "
        "Do not reproduce copyrighted rules text; use generic item names and descriptions. "
        "Return only the JSON object, no extra commentary."
    )
    user_content = json.dumps(
        {
            "challenge_rating": cr,
            "loot_type": req.loot_type or "treasure",
            "ruleset_context": build_ruleset_prompt_context(ruleset_id),
            "themes": variables.get("themes", []),
            "content_rating": variables.get("content_rating", "pg-13"),
        }
    )

    llm_result = _call_llm(system_prompt, user_content, settings)
    loot: Dict[str, Any]
    if llm_result:
        loot = {
            "name": llm_result.get("name", f"Generated Loot ({req.loot_type or 'treasure'})"),
            "description": llm_result.get("description", ""),
            "items": llm_result.get(
                "items",
                [
                    {"name": "Gold coins", "quantity": 100, "type": "currency"},
                    {"name": "Magic item", "quantity": 1, "type": "magic"},
                ],
            ),
            "total_value_gp": llm_result.get("total_value_gp", 0),
            "context": context,
            "ruleset": ruleset_id,
        }
    else:
        loot = {
            "name": f"Generated Loot ({req.loot_type or 'treasure'})",
            "description": f"Appropriate for CR {cr}",
            "items": [
                {"name": "Gold coins", "quantity": 100, "type": "currency"},
                {"name": "Magic item", "quantity": 1, "type": "magic"},
            ],
            "context": context,
            "ruleset": ruleset_id,
        }

    return {"loot": loot, "campaign_id": req.campaign_id}
