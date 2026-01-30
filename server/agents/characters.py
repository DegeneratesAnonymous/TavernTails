from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/characters", tags=["characters"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _guess_character_name_from_filename(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    base = filename.strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not base:
        return None

    base = re.sub(r"\.(pdf|json|txt)$", "", base, flags=re.IGNORECASE)
    # Many exports include an ID suffix like spaceman_wil_91460971.pdf
    base = re.sub(r"(?:[_-]?\d{4,})$", "", base)
    base = base.replace("_", " ").replace("-", " ")
    base = re.sub(r"\s+", " ", base).strip()
    if not base:
        return None

    # Keep it simple/deterministic.
    titled = base.title()
    return titled.strip() or None


def _extract_fields_from_text(text: str) -> tuple[Optional[str], Optional[int], Optional[str]]:
    cleaned = (text or "").replace("\r", "\n")
    lines = [ln.strip() for ln in cleaned.split("\n") if ln and ln.strip()]

    name: Optional[str] = None
    # Avoid accidentally using template headings as the character name.
    bad_name_fragments = (
        "CHARACTER NAME",
        "CLASS & LEVEL",
        "CLASS AND LEVEL",
        "PLAYER NAME",
        "SPECIES",
        "BACKGROUND",
        "EXPERIENCE POINTS",
        "FEATURES & TRAITS",
        "ADDITIONAL FEATURES",
        "EQUIPMENT",
        "SPELLCASTING",
        "TM &",
        "ALL RIGHTS RESERVED",
        "WIZARDS OF THE COAST",
        "D&D BEYOND",
    )
    for ln in lines[:30]:
        if len(ln) < 2 or len(ln) > 80:
            continue
        upper = ln.upper()
        if any(frag in upper for frag in bad_name_fragments):
            continue
        # Needs at least one letter.
        if not re.search(r"[A-Za-z]", ln):
            continue
        name = ln
        break

    level: Optional[int] = None
    m = re.search(r"\bLevel\s*(\d{1,2})\b", cleaned, flags=re.IGNORECASE)
    if m:
        level = _as_int(m.group(1))

    class_name: Optional[str] = None
    # Try common label patterns.
    m2 = re.search(r"\bClass\b[^\n]*\n?\s*([A-Za-z][A-Za-z\s]{2,40})\b", cleaned, flags=re.IGNORECASE)
    if m2:
        class_name = _as_str(m2.group(1))

    # Fallback: scan for known 5e classes.
    if class_name is None:
        candidates = [
            "Artificer",
            "Barbarian",
            "Bard",
            "Cleric",
            "Druid",
            "Fighter",
            "Monk",
            "Paladin",
            "Ranger",
            "Rogue",
            "Sorcerer",
            "Warlock",
            "Wizard",
        ]
        for cname in candidates:
            if re.search(rf"\b{re.escape(cname)}\b", cleaned, flags=re.IGNORECASE):
                class_name = cname
                break

    return name, level, class_name


def _read_pdf_text(content: bytes) -> str:
    """Best-effort PDF text extraction.

    For testability and robustness, if PDF parsing fails we fall back to decoding bytes
    as UTF-8 text. This lets users upload text-only exports or malformed PDFs without
    blowing up the import flow.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(__import__("io").BytesIO(content))
        parts: list[str] = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        text = "\n".join(parts)
        if text and text.strip():
            return text
    except Exception:
        pass

    try:
        return content.decode("utf-8")
    except Exception:
        return content.decode("utf-8", errors="ignore")


def _read_pdf_widget_values(content: bytes) -> Dict[str, str]:
    """Extract PDF widget values (interactive form fields).

    D&D Beyond PDF exports commonly store filled values as widget annotations on pages.
    Many PDF text extractors won't include these values in `extract_text()` output.
    """
    try:
        from pypdf import PdfReader
    except Exception:
        return {}

    try:
        reader = PdfReader(__import__("io").BytesIO(content))
    except Exception:
        return {}

    fields: Dict[str, str] = {}

    for page in reader.pages:
        try:
            annots = page.get("/Annots")
        except Exception:
            annots = None
        if not annots:
            continue

        try:
            annot_refs = list(annots)
        except Exception:
            continue

        for ref in annot_refs:
            try:
                annot = ref.get_object()
            except Exception:
                continue
            try:
                subtype = str(annot.get("/Subtype") or "")
            except Exception:
                subtype = ""
            if subtype != "/Widget":
                continue

            try:
                key = _as_str(annot.get("/T"))
                value = _as_str(annot.get("/V"))
            except Exception:
                continue
            if not key or value is None:
                continue
            # Keep the first occurrence; DDB PDFs can repeat widgets across pages.
            fields.setdefault(key, value)

    return fields


def _extract_fields_from_pdf_widgets(fields: Dict[str, str]) -> tuple[Optional[str], Optional[int], Optional[str]]:
    if not fields:
        return None, None, None

    name = fields.get("CharacterName") or fields.get("CHARACTER NAME")

    # Find a key that looks like it contains both Class and Level.
    class_level_value: Optional[str] = None
    for k, v in fields.items():
        up = k.upper()
        if "CLASS" in up and "LEVEL" in up and v.strip():
            class_level_value = v
            break

    class_name: Optional[str] = None
    level: Optional[int] = None

    if class_level_value:
        candidates = [
            "Artificer",
            "Barbarian",
            "Bard",
            "Cleric",
            "Druid",
            "Fighter",
            "Monk",
            "Paladin",
            "Ranger",
            "Rogue",
            "Sorcerer",
            "Warlock",
            "Wizard",
        ]

        pairs = re.findall(r"\b([A-Za-z][A-Za-z ]{2,40}?)\s+(\d{1,2})\b", class_level_value)
        found_classes: list[str] = []
        total_level = 0
        for cname_raw, lvl_raw in pairs:
            cname = _as_str(cname_raw)
            lvl = _as_int(lvl_raw)
            if not cname or not isinstance(lvl, int):
                continue
            # Only accept known 5e class names to avoid picking up random labels.
            if not any(cname.lower() == c.lower() for c in candidates):
                continue
            if cname not in found_classes:
                found_classes.append(cname)
            total_level += lvl

        if found_classes:
            class_name = " / ".join(found_classes[:3])
        if total_level > 0:
            level = total_level

        if class_name is None:
            # Last resort: if the value includes a known class name, capture it.
            for cname in candidates:
                if re.search(rf"\b{re.escape(cname)}\b", class_level_value, flags=re.IGNORECASE):
                    class_name = cname
                    break

    return name, level, class_name


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
    def _class_name_from_classes_list(classes: Any) -> Optional[str]:
        if not isinstance(classes, list) or not classes:
            return None
        names: list[str] = []
        for item in classes:
            if not isinstance(item, dict):
                continue
            cname = _as_str(item.get("name") or item.get("class") or item.get("class_name"))
            if cname:
                names.append(cname)
        if not names:
            return None
        if len(names) == 1:
            return names[0]
        return " / ".join(names[:3])

    def _level_from_classes_list(classes: Any) -> Optional[int]:
        if not isinstance(classes, list) or not classes:
            return None
        total = 0
        found_any = False
        for item in classes:
            if not isinstance(item, dict):
                continue
            lvl = _as_int(item.get("level"))
            if isinstance(lvl, int):
                total += lvl
                found_any = True
        return total if found_any else None

    name: Optional[str] = None
    level: Optional[int] = None
    class_name: Optional[str] = None

    # Search likely roots in order: top-level, then common nesting wrappers.
    roots: list[Dict[str, Any]] = [raw]
    for key in ("character", "data"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            roots.append(nested)

    for root in roots:
        name = name or _as_str(root.get("name"))
        level = level or _as_int(root.get("level") or root.get("characterLevel"))
        class_name = class_name or _as_str(root.get("class_name") or root.get("class"))

        classes = root.get("classes")
        if class_name is None:
            class_name = _class_name_from_classes_list(classes)
        if level is None:
            level = _level_from_classes_list(classes)

        # If the class is an object (common in some exports), try to pull its name.
        if class_name is None:
            cls_obj = root.get("class")
            if isinstance(cls_obj, dict):
                class_name = _as_str(cls_obj.get("name"))

        # Alternative shapes.
        if class_name is None:
            class_info = root.get("classInfo")
            if isinstance(class_info, dict):
                class_name = _as_str(class_info.get("name"))

        if name and level is not None:
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


@router.post("/import/pdf", status_code=201, summary="Import a character from an uploaded PDF (best-effort)")
async def import_character_pdf(
    file: UploadFile = File(...),
    name: Optional[str] = Form(default=None),
    level: Optional[int] = Form(default=None),
    class_name: Optional[str] = Form(default=None),
    ddb_url: Optional[str] = None,
    source: Optional[str] = "pdf",
    current_user=Depends(get_current_user),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    widget_values = _read_pdf_widget_values(content)
    widget_name, widget_level, widget_class_name = _extract_fields_from_pdf_widgets(widget_values)

    text = _read_pdf_text(content)
    # Combine extracted page text + widget key/value lines for better downstream parsing.
    widget_lines = "\n".join([f"{k}: {v}" for k, v in list(widget_values.items())[:600]])
    combined_text = (text or "") + ("\n\n" + widget_lines if widget_lines else "")
    extracted_name, extracted_level, extracted_class_name = _extract_fields_from_text(combined_text)

    # Prefer widget-derived values over regex-from-text values.
    if widget_name:
        extracted_name = widget_name
    if isinstance(widget_level, int):
        extracted_level = widget_level
    if widget_class_name:
        extracted_class_name = widget_class_name

    final_name = _as_str(name) or extracted_name or _guess_character_name_from_filename(getattr(file, "filename", None))
    if not final_name:
        final_name = "Imported Character"

    final_level = level if isinstance(level, int) else extracted_level
    final_class_name = _as_str(class_name) or extracted_class_name

    safe_level = final_level if isinstance(final_level, int) else 1
    safe_level = max(1, min(20, safe_level))

    sheet: Dict[str, Any] = {
        "import": {
            "source": source or "pdf",
            "imported_at": _now_iso(),
            "ddb_url": ddb_url,
            "filename": getattr(file, "filename", None),
            "overrides": {
                "name": _as_str(name),
                "level": level if isinstance(level, int) else None,
                "class_name": _as_str(class_name),
            },
            "extracted": {
                "name": extracted_name,
                "level": extracted_level,
                "class_name": extracted_class_name,
            },
            "raw_text_len": len(text or ""),
            "pdf_widgets": {
                "count": len(widget_values),
                "valued_sample": {k: widget_values[k] for k in list(widget_values.keys())[:30]},
            },
        },
        # Store extracted text for future parsing improvements (avoid storing large binaries in DB).
        "raw_text": (combined_text or "")[:50000],
    }

    character = db.create_character(
        owner_id=current_user.id,
        name=final_name,
        level=safe_level,
        class_name=final_class_name,
        sheet=sheet,
    )
    return {"character": _serialize(character)}


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
