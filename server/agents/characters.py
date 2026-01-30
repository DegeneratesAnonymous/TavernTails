from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/characters", tags=["characters"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value).strip() or None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        v = value.strip()
        if v.isdigit():
            return int(v)
    try:
        return int(value)
    except Exception:
        return None


def _extract_character_fields(raw: Dict[str, Any]) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """Best-effort extraction from arbitrary JSON blobs.

    We intentionally keep this flexible because different exports have different shapes.
    """
    # Common direct keys
    name = _as_str(raw.get("name"))
    level = _as_int(raw.get("level"))
    class_name = _as_str(raw.get("class_name") or raw.get("class"))

    # Nested shapes (common patterns)
    if not name and isinstance(raw.get("character"), dict):
        name = _as_str(raw["character"].get("name"))
        level = level or _as_int(raw["character"].get("level"))
        class_name = class_name or _as_str(raw["character"].get("class") or raw["character"].get("class_name"))

    # If the class is an object/list, try to pull a name
    if class_name is None:
        for candidate in (raw.get("class"), raw.get("classes"), raw.get("classInfo")):
            if isinstance(candidate, dict):
                class_name = _as_str(candidate.get("name"))
                if class_name:
                    break
            if isinstance(candidate, list) and candidate:
                first = candidate[0]
                if isinstance(first, dict):
                    class_name = _as_str(first.get("name"))
                    if class_name:
                        break

    return name, level, class_name


def _serialize(character: db.Character) -> Dict[str, Any]:
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
    class_name: Optional[str] = None
    sheet: Optional[Dict[str, Any]] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    level: Optional[int] = Field(default=None, ge=1, le=20)
    class_name: Optional[str] = None
    sheet: Optional[Dict[str, Any]] = None


class CharacterImport(BaseModel):
    raw_json: str = Field(..., min_length=2, description="Raw JSON exported from a sheet/source")
    ddb_url: Optional[str] = Field(default=None, description="Optional D&D Beyond character URL")
    source: Optional[str] = Field(default="upload", description="Freeform import source label")


class CharacterImportLink(BaseModel):
    ddb_url: str = Field(..., min_length=8, description="D&D Beyond character URL")
    name: Optional[str] = Field(default=None, description="Optional display name override")


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


@router.get("/{character_id}")
def get_character(character_id: int, current_user=Depends(get_current_user)):
    character = db.get_character_for_owner(character_id=character_id, owner_id=current_user.id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"character": _serialize(character)}


@router.post("/import", status_code=201, summary="Import a character from pasted JSON")
def import_character(payload: CharacterImport, current_user=Depends(get_current_user)):
    try:
        parsed = json.loads(payload.raw_json)
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid JSON") from err
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="JSON must be an object")

    name, level, class_name = _extract_character_fields(parsed)
    if not name:
        name = "Imported Character"

    safe_level = level if isinstance(level, int) else 1
    safe_level = max(1, min(20, safe_level))

    sheet: Dict[str, Any] = {
        "import": {
            "source": payload.source or "upload",
            "imported_at": _now_iso(),
            "ddb_url": payload.ddb_url,
        },
        "raw": parsed,
    }

    character = db.create_character(
        owner_id=current_user.id,
        name=name,
        level=safe_level,
        class_name=class_name,
        sheet=sheet,
    )
    return {"character": _serialize(character)}


@router.post("/import/file", status_code=201, summary="Import a character from an uploaded JSON file")
async def import_character_file(
    file: UploadFile = File(...),
    ddb_url: Optional[str] = None,
    source: Optional[str] = "upload",
    current_user=Depends(get_current_user),
):
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    return import_character(
        CharacterImport(raw_json=text, ddb_url=ddb_url, source=source or "upload"),
        current_user=current_user,
    )


@router.post("/import/link", status_code=201, summary="Create a character from a shared DDB link (no scraping)")
def import_character_link(payload: CharacterImportLink, current_user=Depends(get_current_user)):
    url = payload.ddb_url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="DDB URL must start with http:// or https://")
    name = (payload.name or "DDB Character").strip() or "DDB Character"

    sheet: Dict[str, Any] = {
        "import": {
            "source": "ddb-link",
            "imported_at": _now_iso(),
            "ddb_url": url,
        },
        "raw": {},
    }
    character = db.create_character(owner_id=current_user.id, name=name, level=1, class_name=None, sheet=sheet)
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
