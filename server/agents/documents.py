"""Session document endpoints backed by the storage abstraction.

## Document visibility & category model

Every document has two attributes that together govern access:

- **category** — *what* the document contains.  See
  :data:`~server.storage.documents.KNOWN_CATEGORIES` for the full list.
  The category drives the **default visibility** (GM categories are
  ``hidden`` by default; player and world categories are ``shared``).

- **visibility** — *who* may read the document:
  - ``"shared"`` — all session members (players + host)
  - ``"hidden"`` — host / GM only

### Recognised categories and their defaults

| Category           | Default visibility | Written by / purpose |
|--------------------|-------------------|--------------------------------------|
| ``gm_plot``        | hidden            | Storyboard Agent — storyline, arcs, secrets |
| ``gm_npc``         | hidden            | NPC Manager — full NPC stats, motivations, secrets |
| ``gm_location``    | hidden            | GM / Storyboard — full location details, traps |
| ``gm_notes``       | hidden            | GM — miscellaneous session prep notes |
| ``player_npc``     | shared            | NPC Manager — appearance + dialogue only (no stats) |
| ``player_location``| shared            | Notes Agent — shops, contacts, explored layout |
| ``player_quest_log``| shared           | Notes Agent — quests as discovered by players |
| ``player_journal`` | shared            | Players — free-text in-character notes |
| ``world_lore``     | shared            | GM / Storyboard — publicly known lore |
| ``core``           | shared            | General campaign docs (catch-all / default) |

### Player information isolation

Players **never** see ``gm_*`` documents (``visibility=hidden`` is enforced
by the API for all read/list/download operations).

When an NPC is encountered the NPC Manager Agent creates **two** documents:

1. ``gm_npc`` (hidden) — full profile with stats, motivation, secrets.
2. ``player_npc`` (shared) — player-visible card with only the information
   the party has gathered: physical appearance, dialogue, relationship status.

Quest log and player journals grow as the campaign progresses and only ever
contain information the players themselves have learned.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..storage import documents as doc_storage
from . import sessions as session_module

router = APIRouter(prefix="/documents", tags=["documents"])

store = doc_storage.get_document_store()


class DocumentCreate(BaseModel):
    """Create a new session document.

    If ``visibility`` is omitted the server infers the correct default from
    ``category`` (GM categories are hidden; player/world categories are shared).
    Callers may always explicitly override with ``"hidden"`` or ``"shared"``.

    **GM-only categories** (default ``hidden``):
    ``gm_plot``, ``gm_npc``, ``gm_location``, ``gm_notes``

    **Player-visible categories** (default ``shared``):
    ``player_npc``, ``player_location``, ``player_quest_log``,
    ``player_journal``, ``world_lore``, ``core``
    """

    name: str
    content: str = Field(default="")
    category: str = Field(
        default="core",
        description=(
            "Document category.  Determines default visibility.  "
            "One of: gm_plot, gm_npc, gm_location, gm_notes (default hidden), "
            "or player_npc, player_location, player_quest_log, player_journal, "
            "world_lore, core (default shared)."
        ),
    )
    visibility: str | None = Field(
        default=None,
        description=(
            "Override visibility: 'hidden' (host only) or 'shared' (all members). "
            "When omitted, the default for the chosen category is used."
        ),
    )
    folder: str = Field(default="", description="Folder path (e.g. 'rules/combat'). Empty = root.")


class DocumentResponse(BaseModel):
    id: str
    session_id: str
    name: str
    category: str
    visibility: str
    size: int
    created_at: str
    filename: str | None = None
    folder: str = ""


class DocumentDetail(DocumentResponse):
    content: str


class PresignRequest(BaseModel):
    filename: str
    content_type: str | None = None


class PresignResponse(BaseModel):
    url: str
    fields: dict[str, Any]


class RegisterRequest(BaseModel):
    filename: str
    name: str
    size: int
    category: str = Field(default="core")
    visibility: str | None = Field(
        default=None,
        description="Visibility override.  When omitted, defaults are inferred from category.",
    )
    folder: str = Field(default="", description="Folder path for this document.")


def _normalize_visibility(value: str | None) -> str:
    lowered = (value or "").strip().lower()
    return "hidden" if lowered == "hidden" else "shared"


def _normalize_category(value: str | None) -> str:
    lowered = (value or "").strip().lower()
    return lowered or "core"


def _resolve_visibility(category: str, visibility: str | None) -> str:
    """Return the effective visibility for a document.

    If *visibility* is explicitly provided it is always respected (after
    normalisation).  When *visibility* is ``None`` (caller omitted it), the
    default for *category* is applied — GM categories become ``"hidden"`` and
    player/world categories become ``"shared"``.
    """
    if visibility is not None:
        return _normalize_visibility(visibility)
    return doc_storage.default_visibility_for_category(category)


def _session_meta_path(session_id: str) -> Path:
    return session_module.BASE / session_id / "meta.json"


def _audit_path(session_id: str) -> Path:
    return session_module.BASE / session_id / "document_access.jsonl"


def _actor_identifier(current_user) -> str:
    return session_module._identifier_for_user(current_user)


def _load_session_meta(session_id: str) -> dict:
    meta_file = _session_meta_path(session_id)
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        return json.loads(meta_file.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail="Failed to read session meta") from err


def _is_host(meta: dict, identifier: str) -> bool:
    owner = (meta.get("owner") or "").strip().lower()
    if owner and identifier == owner:
        return True
    for member in meta.get("members", []) or []:
        if (member.get("email") or "").strip().lower() != identifier:
            continue
        role = (member.get("role") or "").strip().lower()
        if role in {"owner", "host"}:
            return True
    return False


def _ensure_session_member(session_id: str, current_user) -> tuple[dict, str, bool]:
    meta = _load_session_meta(session_id)
    identifier = _actor_identifier(current_user)
    if not session_module._user_is_member(meta, identifier):
        _audit(session_id, identifier, action="session.member_check", ok=False, detail="not_member")
        raise HTTPException(status_code=403, detail="Not authorized for this session")
    return meta, identifier, _is_host(meta, identifier)


def _audit(session_id: str, identifier: str, *, action: str, ok: bool = True, doc_id: str | None = None, visibility: str | None = None, detail: str | None = None) -> None:
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": identifier,
            "action": action,
            "ok": bool(ok),
            "doc_id": doc_id,
            "visibility": visibility,
            "detail": detail,
        }
        path = _audit_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except Exception:
        # audit failure should never block core UX
        return


def _require_host_for_hidden(session_id: str, identifier: str, is_host: bool, *, doc_id: str | None = None) -> None:
    if is_host:
        return
    _audit(session_id, identifier, action="documents.hidden_denied", ok=False, doc_id=doc_id, visibility="hidden")
    raise HTTPException(status_code=403, detail="Hidden documents require host role")


def _ensure_can_access_doc(session_id: str, identifier: str, is_host: bool, doc_visibility: str, *, doc_id: str | None = None) -> None:
    if _normalize_visibility(doc_visibility) == "hidden":
        _require_host_for_hidden(session_id, identifier, is_host, doc_id=doc_id)


@router.get("/{session_id}", response_model=list[DocumentResponse])
async def list_documents(session_id: str, current_user=Depends(get_current_user)):
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    docs = store.list_documents(session_id)
    if not is_host:
        docs = [doc for doc in docs if _normalize_visibility(getattr(doc, "visibility", "shared")) != "hidden"]
    _audit(session_id, identifier, action="documents.list", ok=True)
    return [DocumentResponse(**asdict(doc)) for doc in docs]


@router.post("/{session_id}", response_model=DocumentResponse, status_code=201)
async def create_document(session_id: str, payload: DocumentCreate, current_user=Depends(get_current_user)):
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    category = _normalize_category(payload.category)
    visibility = _resolve_visibility(category, payload.visibility)
    if visibility == "hidden":
        _require_host_for_hidden(session_id, identifier, is_host)
    saved = store.save_document(
        session_id=session_id,
        name=payload.name,
        content=payload.content,
        category=category,
        visibility=visibility,
        folder=(payload.folder or "").strip('/'),
    )
    _audit(session_id, identifier, action="documents.create", ok=True, doc_id=saved.id, visibility=visibility)
    return DocumentResponse(**asdict(saved))


@router.delete("/{session_id}/{doc_id}", response_model=dict)
async def delete_document(session_id: str, doc_id: str, current_user=Depends(get_current_user)):
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    # check visibility before delete for RBAC + audit
    metas = store.list_documents(session_id)
    target = next((m for m in metas if m.id == doc_id), None)
    if target:
        _ensure_can_access_doc(session_id, identifier, is_host, getattr(target, "visibility", "shared"), doc_id=doc_id)
    deleted = store.delete_document(session_id, doc_id)
    if not deleted:
        _audit(session_id, identifier, action="documents.delete", ok=False, doc_id=doc_id, detail="not_found")
        raise HTTPException(status_code=404, detail="Document not found")
    _audit(session_id, identifier, action="documents.delete", ok=True, doc_id=doc_id, visibility=getattr(target, "visibility", None))
    return {"ok": True}


@router.get("/{session_id}/audit")
def get_audit_log(session_id: str, current_user=Depends(get_current_user)):
    """Return the document access audit log for a session. Host-only."""
    meta, identifier, is_host = _ensure_session_member(session_id, current_user)
    if not is_host:
        _audit(session_id, identifier, action="documents.audit_denied", ok=False, detail="not_host")
        raise HTTPException(status_code=403, detail="Audit log requires host role")
    path = _audit_path(session_id)
    entries: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    _audit(session_id, identifier, action="documents.audit_read", ok=True)
    return {"session_id": session_id, "entries": entries}


# ---------------------------------------------------------------------------
# Folder management
# ---------------------------------------------------------------------------

class CreateFolderRequest(BaseModel):
    folder: str = Field(..., description="New folder path (e.g. 'rules' or 'rules/combat').")


class MoveDocumentRequest(BaseModel):
    folder: str = Field(default="", description="Destination folder (empty = root).")


def _validate_folder_path(folder: str) -> str:
    """Sanitise a supplied folder path. Raises HTTPException on invalid input."""
    clean = folder.strip('/')
    if not clean:
        return ""
    for segment in clean.split('/'):
        if not segment or segment in ('..', '.') or any(c in segment for c in ('\\', '\0', ':')):
            raise HTTPException(status_code=400, detail=f"Invalid folder path: '{folder}'")
    return clean


@router.get("/{session_id}/folders")
async def list_folders(session_id: str, current_user=Depends(get_current_user)):
    """List all folder paths for a session."""
    _, _, _ = _ensure_session_member(session_id, current_user)
    return {"folders": store.list_folders(session_id)}


@router.post("/{session_id}/folders", status_code=201)
async def create_folder(session_id: str, payload: CreateFolderRequest, current_user=Depends(get_current_user)):
    """Create an empty folder in the session document tree."""
    _, identifier, _ = _ensure_session_member(session_id, current_user)
    clean = _validate_folder_path(payload.folder)
    if not clean:
        raise HTTPException(status_code=400, detail="Folder name required")
    ok = store.create_folder(session_id, clean)
    _audit(session_id, identifier, action="documents.folder.create", ok=ok, detail=clean)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid folder path")
    return {"folder": clean}


@router.delete("/{session_id}/folders/{folder_path:path}")
async def delete_folder(session_id: str, folder_path: str, current_user=Depends(get_current_user)):
    """Delete an empty folder. Returns 400 if the folder still contains documents."""
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    if not is_host:
        raise HTTPException(status_code=403, detail="Only hosts can delete folders")
    clean = _validate_folder_path(folder_path)
    ok = store.delete_folder(session_id, clean)
    _audit(session_id, identifier, action="documents.folder.delete", ok=ok, detail=clean)
    if not ok:
        raise HTTPException(status_code=400, detail="Folder not empty or does not exist")
    return {"ok": True}


@router.patch("/{session_id}/{doc_id}/move")
async def move_document(session_id: str, doc_id: str, payload: MoveDocumentRequest, current_user=Depends(get_current_user)):
    """Move a document to a different folder. Use empty string to move to root."""
    _, identifier, _ = _ensure_session_member(session_id, current_user)
    clean = _validate_folder_path(payload.folder)
    doc = store.move_document(session_id, doc_id, clean)
    if not doc:
        _audit(session_id, identifier, action="documents.move", ok=False, doc_id=doc_id, detail="not_found")
        raise HTTPException(status_code=404, detail="Document not found")
    _audit(session_id, identifier, action="documents.move", ok=True, doc_id=doc_id, detail=f"folder:{clean}")
    return DocumentResponse(**asdict(doc))


@router.get("/{session_id}/{doc_id}", response_model=DocumentDetail)
async def get_document(session_id: str, doc_id: str, current_user=Depends(get_current_user)):
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    record = store.read_document(session_id, doc_id)
    if not record:
        _audit(session_id, identifier, action="documents.read", ok=False, doc_id=doc_id, detail="not_found")
        raise HTTPException(status_code=404, detail="Document not found")
    meta, content = record
    _ensure_can_access_doc(session_id, identifier, is_host, getattr(meta, "visibility", "shared"), doc_id=doc_id)
    _audit(session_id, identifier, action="documents.read", ok=True, doc_id=doc_id, visibility=getattr(meta, "visibility", None))
    return DocumentDetail(**asdict(meta), content=content)


@router.post("/{session_id}/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    session_id: str,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    category: str | None = Form(None),
    visibility: str | None = Form(None),
    folder: str | None = Form(None),
    current_user=Depends(get_current_user),
):
    """Upload a binary file for the session. Returns stored document metadata."""
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    normalized_category = _normalize_category(category)
    normalized_visibility = _resolve_visibility(normalized_category, visibility)
    if normalized_visibility == "hidden":
        _require_host_for_hidden(session_id, identifier, is_host)
    data = await file.read()
    display_name = name or file.filename or "uploaded"
    saved = store.save_document(
        session_id=session_id,
        name=display_name,
        content=data,
        filename=file.filename,
        category=normalized_category,
        visibility=normalized_visibility,
        folder=(folder or "").strip('/'),
    )
    _audit(session_id, identifier, action="documents.upload", ok=True, doc_id=saved.id, visibility=normalized_visibility)
    return DocumentResponse(**asdict(saved))


@router.get("/{session_id}/{doc_id}/raw")
async def get_document_raw(session_id: str, doc_id: str, current_user=Depends(get_current_user)):
    """Return the raw binary/file for a document when available.

    - For `LocalDocumentStore` this returns a FileResponse.
    - For other stores this attempts to return a JSON error or 501.
    """
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    metas = store.list_documents(session_id)
    for m in metas:
        if m.id == doc_id:
            _ensure_can_access_doc(session_id, identifier, is_host, getattr(m, "visibility", "shared"), doc_id=doc_id)
            # If S3-backed and supported, redirect to a presigned GET URL.
            if hasattr(store, 'generate_presigned_get_url'):
                try:
                    url = store.generate_presigned_get_url(session_id=session_id, filename=m.filename)
                    _audit(session_id, identifier, action="documents.raw", ok=True, doc_id=doc_id, visibility=getattr(m, "visibility", None))
                    return RedirectResponse(url=url)
                except NotImplementedError:
                    pass
                except Exception:
                    pass

            # LocalDocumentStore stores files under sessions/<session_id>/docs/<filename>
            base = session_module.BASE / session_id / 'docs'
            safe_name = Path(m.filename).name
            target = base / safe_name
            if target.exists():
                _audit(session_id, identifier, action="documents.raw", ok=True, doc_id=doc_id, visibility=getattr(m, "visibility", None))
                return FileResponse(path=str(target), filename=safe_name)
            break
    _audit(session_id, identifier, action="documents.raw", ok=False, doc_id=doc_id, detail="raw_not_found")
    raise HTTPException(status_code=404, detail='Raw file not found')


@router.post("/{session_id}/presign", response_model=PresignResponse)
async def presign_upload(session_id: str, payload: PresignRequest, current_user=Depends(get_current_user)):
    """Return a presigned POST payload for direct browser -> S3 uploads when available."""
    _, identifier, _ = _ensure_session_member(session_id, current_user)
    # only supported when store provides presign capability
    if hasattr(store, 'generate_presigned_post'):
        try:
            resp = store.generate_presigned_post(session_id=session_id, filename=payload.filename, content_type=payload.content_type)
            _audit(session_id, identifier, action="documents.presign", ok=True)
            return PresignResponse(url=resp['url'], fields=resp.get('fields', {}))
        except Exception as err:
            _audit(session_id, identifier, action="documents.presign", ok=False)
            raise HTTPException(status_code=500, detail='Failed to generate presigned upload') from err
    raise HTTPException(status_code=501, detail='Presign not supported for current storage')


@router.post("/{session_id}/register", response_model=DocumentResponse)
async def register_document(session_id: str, payload: RegisterRequest, current_user=Depends(get_current_user)):
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    category = _normalize_category(payload.category)
    visibility = _resolve_visibility(category, payload.visibility)
    if visibility == "hidden":
        _require_host_for_hidden(session_id, identifier, is_host)
    if hasattr(store, 'register_existing_object'):
        try:
            saved = store.register_existing_object(session_id=session_id, filename=payload.filename, name=payload.name, size=payload.size, category=category, visibility=visibility, folder=(payload.folder or "").strip('/'))
            _audit(session_id, identifier, action="documents.register", ok=True, doc_id=saved.id, visibility=visibility)
            return DocumentResponse(**asdict(saved))
        except Exception as err:
            _audit(session_id, identifier, action="documents.register", ok=False)
            raise HTTPException(status_code=500, detail='Failed to register uploaded file') from err
    raise HTTPException(status_code=501, detail='Register not supported for current storage')


# ---------------------------------------------------------------------------
# Document sharing with friends
# ---------------------------------------------------------------------------


@router.post("/{session_id}/{doc_id}/share")
async def share_document_with_friend(
    session_id: str,
    doc_id: str,
    friend_user_id: int = Body(..., embed=True),
    current_user=Depends(get_current_user),
):
    """Share a document with a friend user.

    * The caller must be the session host or a member.
    * The target must be a confirmed friend.
    * The document must be 'shared' visibility (hidden GM docs are not shareable).

    Sharing is recorded in the session audit log.  The actual content is not
    copied — the recipient can request access via ``GET /documents/{session_id}``
    once added to the session.  This endpoint simply validates friendship and
    notifies the friend.
    """
    from .. import db as _db

    meta, identifier, is_host = _ensure_session_member(session_id, current_user)

    docs = store.list_documents(session_id)
    doc = next((d for d in docs if d.id == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.visibility == "hidden":
        raise HTTPException(status_code=403, detail="Hidden documents cannot be shared with friends")

    if friend_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot share a document with yourself")

    friend = _db.admin_get_user(friend_user_id)
    if not friend:
        raise HTTPException(status_code=404, detail="Friend not found")

    if not _db.are_friends(current_user.id, friend_user_id):
        raise HTTPException(status_code=403, detail="You can only share documents with friends")

    # Notify the friend
    sharer_name = (current_user.profile or {}).get("name") or current_user.username or current_user.email or "Someone"
    _db.admin_send_notification(
        friend_user_id,
        title=f"📄 {sharer_name} shared a document with you",
        body=f'"{doc.name}" from session {session_id}',
    )

    _audit(session_id, identifier, action="documents.share", ok=True, doc_id=doc_id, detail=f"shared_with:{friend_user_id}")
    return {
        "shared": True,
        "doc_id": doc_id,
        "doc_name": doc.name,
        "shared_with_user_id": friend_user_id,
    }
