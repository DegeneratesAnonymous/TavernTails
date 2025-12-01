# NPC/Enemy Manager Agent
# Profiles NPCs/enemies and tracks stats


"""
NPC/Enemy Manager Agent
Profiles NPCs/enemies, tracks stats, motivations, and initiative.
"""

from fastapi import APIRouter, Body
from typing import Dict, Any

router = APIRouter()

@router.post("/npc/manage")
def manage_npc(
    name: str = Body(..., description="NPC/Enemy name"),
    traits: Dict[str, Any] = Body({}, description="Traits: goal, fear, desire, flaw, disposition"),
    motivations: list = Body([], description="Motivations: Loyal, Greedy, etc."),
    stats: Dict[str, Any] = Body({}, description="Stats: HP, AC, initiative, etc."),
    quirks: list = Body([], description="Distinct quirks for NPC/Enemy")
):
    """
    Profile an NPC/enemy and track stats, motivations, and initiative.
    """
    profile = {
        "name": name,
        "traits": traits,
        "motivations": motivations,
        "stats": stats,
        "quirks": quirks
    }
    return {"npc_profile": profile}
