"""NPC agent: summarises motivations + initiative."""

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..agents import sessions as session_module
from ..realtime import broadcaster

router = APIRouter(tags=["npc"])


class NPCClassEntry(BaseModel):
    """A system-agnostic class/role entry for an NPC.

    Works for any TTRPG: D&D fighter, Pathfinder alchemist,
    Shadowrun street samurai, Call of Cthulhu investigator, etc.
    """

    name: str = Field(..., description="Class or role name, e.g. 'Fighter', 'Street Samurai', 'Alchemist'")
    level: int | None = Field(default=None, description="Optional level/tier within this class")
    subclass: str | None = Field(default=None, description="Optional subclass, archetype, or specialization")


class NPCAbility(BaseModel):
    """A system-agnostic active or passive ability for an NPC."""

    name: str = Field(..., description="Ability name, e.g. 'Multiattack', 'Evasion', 'Battle Cry'")
    description: str = Field(default="", description="What the ability does")
    tags: list[str] = Field(default_factory=list, description="Optional tags, e.g. ['combat', 'passive', 'aoe']")


class NPCSpell(BaseModel):
    """A system-agnostic spell or magical power for an NPC."""

    name: str = Field(..., description="Spell name, e.g. 'Fireball', 'Mind Control', 'Healing Touch'")
    description: str = Field(default="", description="What the spell does")
    tags: list[str] = Field(default_factory=list, description="Optional tags, e.g. ['fire', 'aoe', 'healing']")


class NPCManageRequest(BaseModel):
    name: str = Field(..., description="NPC/Enemy name")
    traits: dict[str, Any] = Field(default_factory=dict)
    motivations: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    quirks: list[str] = Field(default_factory=list)
    classes: list[NPCClassEntry] = Field(
        default_factory=list,
        description="System-agnostic class/role entries. Works across any TTRPG.",
    )
    abilities: list[NPCAbility] = Field(
        default_factory=list,
        description="Active or passive abilities/powers, free-form for any system.",
    )
    spells: list[NPCSpell] = Field(
        default_factory=list,
        description="Spells or magical powers, free-form for any system.",
    )
    session_id: str | None = Field(default=None, description="Session to broadcast NPC cues to")


class NPCManageResponse(BaseModel):
    npc_profile: dict[str, Any]
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
        "classes": [c.model_dump(exclude_none=True) for c in payload.classes],
        "abilities": [a.model_dump(exclude_none=True) for a in payload.abilities],
        "spells": [s.model_dump(exclude_none=True) for s in payload.spells],
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
