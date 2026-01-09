"""Session document endpoints backed by the storage abstraction.

MVP requirements:
- Session members can access shared documents.
- Only session hosts can access documents with visibility=hidden.
- Sensitive document access is audited to a per-session jsonl file.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..storage import documents as doc_storage
from . import sessions as session_module

router = APIRouter(prefix="/documents", tags=["documents"])

store = doc_storage.get_document_store()


class DocumentCreate(BaseModel):
    name: str
    content: str = Field(default="")
    category: str = Field(default="core")
    visibility: str = Field(default="shared")


class DocumentResponse(BaseModel):
    id: str
    session_id: str
    name: str
    category: str
    visibility: str
    size: int
    created_at: str
    filename: str | None = None


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
    visibility: str = Field(default="shared")


def _normalize_visibility(value: Optional[str]) -> str:
    lowered = (value or "").strip().lower()
    return "hidden" if lowered == "hidden" else "shared"


def _normalize_category(value: Optional[str]) -> str:
    lowered = (value or "").strip().lower()
    return lowered or "core"


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


def _ensure_session_member(session_id: str, current_user) -> Tuple[dict, str, bool]:
    meta = _load_session_meta(session_id)
    identifier = _actor_identifier(current_user)
    if not session_module._user_is_member(meta, identifier):
        _audit(session_id, identifier, action="session.member_check", ok=False, detail="not_member")
        raise HTTPException(status_code=403, detail="Not authorized for this session")
    return meta, identifier, _is_host(meta, identifier)


def _audit(session_id: str, identifier: str, *, action: str, ok: bool = True, doc_id: Optional[str] = None, visibility: Optional[str] = None, detail: Optional[str] = None) -> None:
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


def _require_host_for_hidden(session_id: str, identifier: str, is_host: bool, *, doc_id: Optional[str] = None) -> None:
    if is_host:
        return
    _audit(session_id, identifier, action="documents.hidden_denied", ok=False, doc_id=doc_id, visibility="hidden")
    raise HTTPException(status_code=403, detail="Hidden documents require host role")


def _ensure_can_access_doc(session_id: str, identifier: str, is_host: bool, doc_visibility: str, *, doc_id: Optional[str] = None) -> None:
    if _normalize_visibility(doc_visibility) == "hidden":
        _require_host_for_hidden(session_id, identifier, is_host, doc_id=doc_id)


@router.get("/{session_id}", response_model=List[DocumentResponse])
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
    visibility = _normalize_visibility(payload.visibility)
    category = _normalize_category(payload.category)
    if visibility == "hidden":
        _require_host_for_hidden(session_id, identifier, is_host)
    saved = store.save_document(
        session_id=session_id,
        name=payload.name,
        content=payload.content,
        category=category,
        visibility=visibility,
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
    current_user=Depends(get_current_user),
):
    """Upload a binary file for the session. Returns stored document metadata."""
    _, identifier, is_host = _ensure_session_member(session_id, current_user)
    normalized_visibility = _normalize_visibility(visibility)
    normalized_category = _normalize_category(category)
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
    # If local store, map to session folder
    # LocalDocumentStore stores files under sessions/<session_id>/docs/<filename>
    base = session_module.BASE / session_id / 'docs'
    metas = store.list_documents(session_id)
    for m in metas:
        if m.id == doc_id:
            _ensure_can_access_doc(session_id, identifier, is_host, getattr(m, "visibility", "shared"), doc_id=doc_id)
            target = base / m.filename
            if target.exists():
                _audit(session_id, identifier, action="documents.raw", ok=True, doc_id=doc_id, visibility=getattr(m, "visibility", None))
                return FileResponse(path=str(target), filename=m.filename)
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
    visibility = _normalize_visibility(payload.visibility)
    category = _normalize_category(payload.category)
    if visibility == "hidden":
        _require_host_for_hidden(session_id, identifier, is_host)
    if hasattr(store, 'register_existing_object'):
        try:
            saved = store.register_existing_object(session_id=session_id, filename=payload.filename, name=payload.name, size=payload.size, category=category, visibility=visibility)
            _audit(session_id, identifier, action="documents.register", ok=True, doc_id=saved.id, visibility=visibility)
            return DocumentResponse(**asdict(saved))
        except Exception as err:
            _audit(session_id, identifier, action="documents.register", ok=False)
            raise HTTPException(status_code=500, detail='Failed to register uploaded file') from err
    raise HTTPException(status_code=501, detail='Register not supported for current storage')
