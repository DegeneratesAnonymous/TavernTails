"""NPC agent: summarises motivations + initiative."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional

from ..realtime import broadcaster
from ..agents import sessions as session_module
import json
from pathlib import Path

router = APIRouter(tags=["npc"])


class NPCManageRequest(BaseModel):
    name: str = Field(..., description="NPC/Enemy name")
    traits: Dict[str, Any] = Field(default_factory=dict)
    motivations: List[str] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)
    quirks: List[str] = Field(default_factory=list)
    session_id: Optional[str] = Field(default=None, description="Session to broadcast NPC cues to")


class NPCManageResponse(BaseModel):
    npc_profile: Dict[str, Any]
    initiative_hint: str


@router.post("/npc/manage", response_model=NPCManageResponse)
async def manage_npc(payload: NPCManageRequest) -> NPCManageResponse:
    initiative = payload.stats.get("initiative") or payload.stats.get("init")
    initiative_hint = f"Roll d20 + {initiative}" if initiative is not None else "Assign initiative when combat starts."
    profile = {
        "name": payload.name,
        "traits": payload.traits,
        "motivations": payload.motivations,
        "stats": payload.stats,
        "quirks": payload.quirks,
    }
    response = NPCManageResponse(npc_profile=profile, initiative_hint=initiative_hint)
    if payload.session_id:
        # persist to session npcs.json
        try:
            folder = session_module.BASE / payload.session_id
            npcs_file = folder / 'npcs.json'
            if npcs_file.exists():
                try:
                    existing = json.loads(npcs_file.read_text()) or []
                except Exception:
                    existing = []
            else:
                existing = []
            # upsert by name
            updated = [entry for entry in existing if entry.get('name') != payload.name]
            updated.append(profile)
            npcs_file.write_text(json.dumps(updated, indent=2))
        except Exception:
            # non-fatal if persistence fails
            pass

        await broadcaster.broadcast_json(payload.session_id, {
            "type": "npc.profile",
            "session_id": payload.session_id,
            "profile": profile,
            "initiative_hint": initiative_hint,
        })
    return response
