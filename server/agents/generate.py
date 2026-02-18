"""Generative endpoints for player-led campaigns.

These endpoints provide GM tools for generating NPCs, locations, and loot
that factor in campaign context and details.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/generate", tags=["generate"])


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

    # Build context for generation
    context = {
        'world_name': settings.get('world_name', ''),
        'setting_summary': settings.get('setting_summary', ''),
        'tone': settings.get('tone', ''),
        'ruleset': settings.get('ruleset', '5e'),
        'npc_type': req.npc_type or 'generic',
        'setting': req.setting or '',
        **(req.context or {}),
    }

    # TODO: Integrate with LLM to generate NPC based on context
    # For now, return a placeholder structure
    npc = {
        'name': f"Generated NPC ({req.npc_type or 'generic'})",
        'description': f"A {req.npc_type or 'character'} from {settings.get('world_name', 'the world')}",
        'personality': f"Fitting the {settings.get('tone', 'standard')} tone",
        'context': context,
        'stats': {
            'level': settings.get('starting_level', 1),
            'ruleset': settings.get('ruleset', '5e'),
        },
    }

    return {'npc': npc, 'campaign_id': req.campaign_id}


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

    # Build context for generation
    context = {
        'world_name': settings.get('world_name', ''),
        'setting_summary': settings.get('setting_summary', ''),
        'tone': settings.get('tone', ''),
        'location_type': req.location_type or 'generic',
        'mood': req.mood or '',
        **(req.context or {}),
    }

    # TODO: Integrate with LLM to generate location based on context
    # For now, return a placeholder structure
    location = {
        'name': f"Generated Location ({req.location_type or 'place'})",
        'description': f"A {req.location_type or 'location'} in {settings.get('world_name', 'the world')}",
        'atmosphere': f"Matching the {settings.get('tone', 'standard')} tone",
        'mood': req.mood or settings.get('tone', ''),
        'context': context,
    }

    return {'location': location, 'campaign_id': req.campaign_id}


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

    # Build context for generation
    context = {
        'world_name': settings.get('world_name', ''),
        'setting_summary': settings.get('setting_summary', ''),
        'ruleset': settings.get('ruleset', '5e'),
        'starting_level': settings.get('starting_level', 1),
        'challenge_rating': req.challenge_rating or settings.get('starting_level', 1),
        'loot_type': req.loot_type or 'treasure',
        **(req.context or {}),
    }

    # TODO: Integrate with LLM to generate loot based on context
    # For now, return a placeholder structure
    loot = {
        'name': f"Generated Loot ({req.loot_type or 'treasure'})",
        'description': f"Appropriate for CR {req.challenge_rating or settings.get('starting_level', 1)}",
        'items': [
            {'name': 'Gold coins', 'quantity': 100, 'type': 'currency'},
            {'name': 'Magic item', 'quantity': 1, 'type': 'magic'},
        ],
        'context': context,
        'ruleset': settings.get('ruleset', '5e'),
    }

    return {'loot': loot, 'campaign_id': req.campaign_id}
