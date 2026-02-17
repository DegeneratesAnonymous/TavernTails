import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/characters", tags=["characters"])


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _build_character_import_sheet_from_json(
    raw_json: str | None = None,
    ddb_url: str | None = None,
) -> tuple[str, int, str | None, dict[str, Any]]:
    """
    Build character sheet from JSON data.
    Returns: (name, level, class_name, sheet)
    """
    # TODO: Implement JSON parsing logic
    name = "Imported Character"
    level = 1
    class_name = None
    sheet: dict[str, Any] = {
        "import": {
            "source": "json",
            "imported_at": _now_iso(),
            "raw_json": raw_json,
            "ddb_url": ddb_url,
        }
    }
    return name, level, class_name, sheet


def _build_character_import_sheet_from_pdf(
    content: bytes,
    filename: str | None = None,
    allow_name_override: bool = False,
    name_override: str | None = None,
) -> tuple[str, int, str | None, dict[str, Any]]:
    """
    Build character sheet from PDF data.
    Returns: (name, level, class_name, sheet)
    """
    # TODO: Implement PDF parsing logic
    name = name_override if allow_name_override and name_override else "PDF Import"
    level = 1
    class_name = None
    sheet: dict[str, Any] = {
        "import": {
            "source": "pdf",
            "imported_at": _now_iso(),
            "filename": filename,
        }
    }
    return name, level, class_name, sheet


def _extract_spellbook_from_text(text: str) -> list[dict[str, Any]]:
    """Extract spell entries from text."""
    # TODO: Implement spell extraction logic
    return []


def _extract_spells_from_text(text: str) -> list[str]:
    """Extract spell names from text."""
    # TODO: Implement spell name extraction logic
    return []


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


class CharacterImport(BaseModel):
    raw_json: str = Field(..., min_length=2, description="Raw JSON exported from a sheet/source")
    ddb_url: str | None = Field(default=None, description="Optional D&D Beyond character URL")
    source: str | None = Field(default="upload", description="Freeform import source label")


class CharacterImportLink(BaseModel):
    ddb_url: str = Field(..., min_length=8, description="D&D Beyond character URL")
    name: str | None = Field(default=None, description="Optional display name override")


@router.get("", summary="List characters for current user")
def list_characters(current_user=Depends(get_current_user)):
    rows = db.list_characters_for_user(current_user.id)
    return {"characters": [_serialize(row) for row in rows]}


@router.delete("/purge", summary="Delete characters for current user by name tokens")
def purge_characters(name_like: str | None = None, current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    tokens: list[str] = []
    if name_like:
        tokens = [part.strip() for part in name_like.split(',') if part.strip()]
    deleted = db.purge_characters(owner_id=current_user.id, name_tokens=tokens)
    return {"deleted": deleted}


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


@router.post("/import/preview", summary="Preview a JSON character import without creating a character")
def preview_import_character(payload: CharacterImport, current_user=Depends(get_current_user)):
    name, safe_level, class_name, sheet = _build_character_import_sheet_from_json(
        raw_json=payload.raw_json,
        ddb_url=payload.ddb_url,
        source=payload.source,
    )
    return {
        "preview": {
            "name": name,
            "level": safe_level,
            "class_name": class_name,
            "sheet": sheet,
        }
    }


@router.post("/import", status_code=201, summary="Import a character from pasted JSON")
def import_character(payload: CharacterImport, current_user=Depends(get_current_user)):
    name, safe_level, class_name, sheet = _build_character_import_sheet_from_json(
        raw_json=payload.raw_json,
        ddb_url=payload.ddb_url,
        source=payload.source,
    )

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
    ddb_url: str | None = None,
    source: str | None = "upload",
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


@router.post("/import/pdf", status_code=201, summary="Import a character from an uploaded PDF (best-effort)")
async def import_character_pdf(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    level: int | None = Form(default=None),
    class_name: str | None = Form(default=None),
    ddb_url: str | None = None,
    source: str | None = "pdf",
    current_user=Depends(get_current_user),
):
    content = await file.read()
    final_name, safe_level, final_class_name, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename=getattr(file, "filename", None),
        name_override=name,
        level_override=level,
        class_name_override=class_name,
        ddb_url=ddb_url,
        source=source,
    )

    character = db.create_character(
        owner_id=current_user.id,
        name=final_name,
        level=safe_level,
        class_name=final_class_name,
        sheet=sheet,
    )
    return {"character": _serialize(character)}


@router.post("/import/pdf/preview", summary="Preview a PDF character import without creating a character")
async def preview_import_character_pdf(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    level: int | None = Form(default=None),
    class_name: str | None = Form(default=None),
    ddb_url: str | None = None,
    source: str | None = "pdf",
    current_user=Depends(get_current_user),
):
    content = await file.read()
    final_name, safe_level, final_class_name, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename=getattr(file, "filename", None),
        name_override=name,
        level_override=level,
        class_name_override=class_name,
        ddb_url=ddb_url,
        source=source,
    )
    return {
        "preview": {
            "name": final_name,
            "level": safe_level,
            "class_name": final_class_name,
            "sheet": sheet,
        }
    }


@router.post("/import/link", status_code=201, summary="Create a character from a shared DDB link (no scraping)")
def import_character_link(payload: CharacterImportLink, current_user=Depends(get_current_user)):
    url = payload.ddb_url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="DDB URL must start with http:// or https://")
    name = (payload.name or "DDB Character").strip() or "DDB Character"

    sheet: dict[str, Any] = {
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
        updates=payload.model_dump(exclude_unset=True),
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"character": _serialize(character)}


@router.delete("/{character_id}")
def delete_character(character_id: int, current_user=Depends(get_current_user)):
    # Try owner delete first, fall back to admin delete if user is admin
    ok = db.delete_character(character_id=character_id, owner_id=current_user.id)
    if not ok and db.is_admin_user(current_user):
        ok = db.delete_character_any(character_id=character_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"ok": True}


@router.delete("/admin-delete/{character_id}")
def admin_delete_character(character_id: int, current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    ok = db.delete_character_any(character_id=character_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"ok": True}


@router.post("/{character_id}/reparse-spells")
def reparse_character_spells(character_id: int, current_user=Depends(get_current_user)):
    print(f"\n=== REPARSE SPELLS FOR CHARACTER {character_id} ===")
    # allow owners or admins to reparse
    character = db.get_character_for_owner(character_id=character_id, owner_id=current_user.id)
    if not character:
        if not db.is_admin_user(current_user):
            raise HTTPException(status_code=404, detail="Character not found")
        character = db.get_character_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

    sheet = character.sheet or {}
    raw_text = sheet.get("raw_text") or (sheet.get("raw", {}) if isinstance(sheet.get("raw"), dict) else {}).get("text") or ""
    raw_text = raw_text if isinstance(raw_text, str) else ""
    print(f"Raw text length: {len(raw_text)}")

    widget_values: dict[str, Any] = {}
    try:
        import_meta = sheet.get("import", {}) if isinstance(sheet.get("import"), dict) else {}
        pdf_widgets = import_meta.get("pdf_widgets", {}) if isinstance(import_meta.get("pdf_widgets"), dict) else {}
        widget_values = pdf_widgets.get("values", {}) if isinstance(pdf_widgets.get("values"), dict) else {}
    except Exception:
        widget_values = {}
    print(f"Widget values with 'spell': {len([k for k in widget_values.keys() if 'spell' in k.lower()])}")

    # Rebuild spellbook/spells
    spell_entries = _extract_spellbook_from_text(raw_text)
    print(f"Extracted {len(spell_entries)} spell entries from text")
    spells: list[str] = []
    if spell_entries:
        spells = [e.get("name") for e in spell_entries if isinstance(e.get("name"), str)]
        print(f"  -> {len(spells)} spell names from entries")
    else:
        # Extract from widget values, but skip metadata fields
        for k, v in widget_values.items():
            if not v:
                continue
            # Skip metadata fields (time, range, components, duration, source, etc.)
            if re.search(r"spell(time|range|comp|duration|source|save|attack|dc|hit|page|level|class|school|ritual|material)", str(k), re.I):
                continue
            if re.search(r"spell|cantrip", str(k), re.I):
                if isinstance(v, str) and ("\n" in v or "," in v):
                    parts = re.split(r"\r?\n|,", v)
                    for p in parts:
                        s = p.strip()
                        if s:
                            spells.append(s)
                else:
                    spells.append(str(v).strip())
        for s in _extract_spells_from_text(raw_text):
            if s:
                spells.append(s)

    # Clean and de-dup with aggressive filtering
    cleaned: list[str] = []
    seen: set[str] = set()
    for s in spells:
        s2 = (s or "").strip()
        if not s2:
            continue

        # Apply same aggressive filters as during extraction
        # Skip widget field names
        if re.match(r"^spell\w+\d*:?$", s2, re.I):
            continue
        # Skip generic filler words
        if re.match(r"^(additional|your|the|and|or|of|in|to|a|an)$", s2, re.I):
            continue
        # Skip empty or dash-only lines
        if re.match(r"^[—\-\s]+$", s2):
            continue
        # Skip class names
        if re.match(r"^(druid|cleric|wizard|sorcerer|bard|warlock|paladin|ranger|artificer|fighter|monk|rogue|barbarian|acolyte)$", s2, re.I):
            continue
        # Skip lines containing "/" or ","
        if "/" in s2 or "," in s2:
            continue
        # Skip distances/ranges
        if re.search(r"\d+\s*ft\.?|feet|mile", s2, re.I):
            continue
        # Skip metadata patterns
        if re.match(r"^(\d+\s*[ABR]A?|[1-9]\s*BA|[1-9]\s*A|[1-9]\s*R|action|bonus\s*action|reaction|touch|self|sight|\d+\s*ft|phb|ee|xgte|tcoe|scag|v|s|m|v/s|s/m|v/m|v/s/m|instantaneous|concentration|wis|int|cha|dex|str|con)$", s2, re.I):
            continue
        # Skip lines with colon prefix
        if re.match(r"^[A-Z]:\s*", s2):
            continue
        # Skip parenthetical notes
        if re.match(r"^\(", s2):
            continue
        # Skip pure numbers, codes, durations
        if re.match(r"^(\d+|[A-Z]{1,3}|\d+m|\d+h|\d+\s*min|\d+\s*hr)$", s2):
            continue
        # Skip page references
        if re.search(r"\b(PHB|EE|XGTE|TCOE|SCAG)\s*\d+", s2, re.I):
            continue
        # Skip common spell attributes
        if re.match(r"^(prepared|ritual|—|at\s*will|===.*===)$", s2, re.I):
            continue
        # Skip stat patterns like "CON 14", "WIS / WIS"
        if re.match(r"^[A-Z]{3}\s*\d+$", s2) or re.match(r"^[A-Z]{3}\s*/\s*[A-Z]{3}$", s2):
            continue
        # Skip asterisk annotations
        if re.match(r"^\*|.*\*$", s2):
            continue

        key = s2.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s2)
        if len(cleaned) >= 500:
            break

    sheet["spellbook"] = spell_entries
    sheet["spells"] = cleaned
    print(f"Final counts - spellbook: {len(spell_entries)}, spells: {len(cleaned)}")
    if cleaned:
        print(f"First 10 cleaned spells: {cleaned[:10]}")

    if db.is_admin_user(current_user) and (not character or character.owner_id != current_user.id):
        updated = db.update_character_any(character_id=character_id, updates={"sheet": sheet})
    else:
        updated = db.update_character(character_id=character_id, owner_id=current_user.id, updates={"sheet": sheet})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update character")
    return {"character": _serialize(updated)}
