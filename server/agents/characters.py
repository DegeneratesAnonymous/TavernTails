from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/characters", tags=["characters"])


def _serialize(character: db.Character) -> dict[str, Any]:
    return {
        "id": character.id,
        "name": character.name,
        "level": character.level,
        "class_name": character.class_name,
        "sheet": character.sheet or {},
    }


class CharacterCreate(BaseModel):
    name: str
    level: int = Field(default=1, ge=1, le=20)
    class_name: str | None = None
    sheet: dict[str, Any] | None = None


class CharacterUpdate(BaseModel):
    name: str | None = None
    level: int | None = Field(default=None, ge=1, le=20)
    class_name: str | None = None
    sheet: dict[str, Any] | None = None


@router.get("", summary="List characters for current user")
def list_characters(current_user=Depends(get_current_user)):
    rows = db.list_characters_for_user(current_user.id)
    return {"characters": [_serialize(row) for row in rows]}


@router.post("", status_code=201)
def create_character(payload: CharacterCreate, current_user=Depends(get_current_user)):
    character = db.create_character(
        owner_id=current_user.id,
        name=payload.name,
        level=payload.level,
        class_name=payload.class_name,
        sheet=payload.sheet,
    )
    return {"character": _serialize(character)}


@router.put("/{character_id}")
def update_character(character_id: int, payload: CharacterUpdate, current_user=Depends(get_current_user)):
    character = db.update_character(
        character_id=character_id,
        owner_id=current_user.id,
        updates=payload.dict(exclude_unset=True),
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"character": _serialize(character)}


@router.delete("/{character_id}")
def delete_character(character_id: int, current_user=Depends(get_current_user)):
    ok = db.delete_character(character_id=character_id, owner_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"ok": True}
