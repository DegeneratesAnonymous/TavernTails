# Notes Agent
# Logs session notes and provides recaps


"""
Notes Agent
Logs session notes, recaps, and provides notes on request.
"""

from fastapi import APIRouter, Body
from typing import List, Dict, Any

router = APIRouter()

@router.post("/notes/log")
def log_note(
    location: str = Body(..., description="Location of event"),
    npcs: List[str] = Body([], description="NPCs involved"),
    items: List[str] = Body([], description="Items, lore, or quests"),
    objectives: List[str] = Body([], description="Objectives and unresolved threads"),
    rolls: List[str] = Body([], description="Key rolls and outcomes")
):
    """
    Log a session note and provide recap on request.
    """
    note = {
        "location": location,
        "npcs": npcs,
        "items": items,
        "objectives": objectives,
        "rolls": rolls
    }
    return {"notes": [note]}
