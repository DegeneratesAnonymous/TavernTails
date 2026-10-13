"""Worlds a player has built and saved, to start campaigns from.

A campaign takes a copy of the world's narrative when it is created, so editing or deleting a saved world never
changes a campaign that is already running.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/worlds", tags=["saved-worlds"])


class WorldBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    narrative: str = Field(default="", max_length=6000)
    context: dict[str, Any] = Field(default_factory=dict)
    answers: dict[str, Any] = Field(default_factory=dict)


def _view(world: db.SavedWorld, *, full: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": world.id, "name": world.name, "version": world.version,
        "updated_at": world.updated_at.isoformat() if world.updated_at else None,
        "preview": (world.narrative or "")[:220],
    }
    if full:
        out.update({"narrative": world.narrative, "context": world.context, "answers": world.answers})
    return out


@router.get("")
def list_worlds(current_user=Depends(get_current_user)):
    return {"worlds": [_view(w, full=False) for w in db.list_saved_worlds(current_user.id)]}


@router.post("", status_code=201)
def create_world(body: WorldBody, current_user=Depends(get_current_user)):
    world = db.create_saved_world(current_user.id, body.name, body.narrative.strip(), body.context, body.answers)
    if world is None:
        raise HTTPException(status_code=409, detail=f"You can keep up to {db.MAX_SAVED_WORLDS} saved worlds. Delete one first.")
    return {"world": _view(world, full=True)}


@router.get("/{world_id}")
def get_world(world_id: str, current_user=Depends(get_current_user)):
    world = db.get_saved_world(world_id, current_user.id)
    if not world:
        raise HTTPException(status_code=404, detail="World not found")
    return {"world": _view(world, full=True)}


@router.put("/{world_id}")
def update_world(world_id: str, body: WorldBody, current_user=Depends(get_current_user)):
    world = db.update_saved_world(world_id, current_user.id, {
        "name": body.name, "narrative": body.narrative.strip(), "context": body.context, "answers": body.answers,
    })
    if not world:
        raise HTTPException(status_code=404, detail="World not found")
    return {"world": _view(world, full=True)}


@router.delete("/{world_id}")
def delete_world(world_id: str, current_user=Depends(get_current_user)):
    if not db.delete_saved_world(world_id, current_user.id):
        raise HTTPException(status_code=404, detail="World not found")
    return {"ok": True}
