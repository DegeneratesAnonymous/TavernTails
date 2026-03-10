import datetime
import html as _html_stdlib
import json
import logging
import math
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from pypdf import PdfReader

from .. import db as _db
from ..auth import get_current_user

logger = logging.getLogger("taverntails.references")

router = APIRouter(prefix="/references", tags=["references"])

# Supported file extensions and their MIME types accepted for reference upload
SUPPORTED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".csv", ".json",
    ".html", ".htm",
    ".docx", ".doc",
    ".xlsx", ".xls",
}


class ReferenceMeta(BaseModel):
    title: str
    filename: str
    pages: int
    system_ref: bool = False  # admin/agent-only; never visible to players
    game_system: str = "global"  # e.g. "D&D 5e", "Pathfinder 2e", or "global" for cross-system docs
    size_bytes: int = 0
    created_at: str = ""  # ISO 8601 UTC timestamp
    folder: str = ""  # logical folder path; empty = root


class ReferenceListItem(BaseModel):
    id: str
    meta: ReferenceMeta


class FolderListResponse(BaseModel):
    folders: list[str]


class FolderItem(BaseModel):
    folder: str


class MoveRefRequest(BaseModel):
    folder: str = ""


class PatchRefMetaRequest(BaseModel):
    game_system: str | None = None
    title: str | None = None
    system_ref: bool | None = None


class ReferenceSearchResult(BaseModel):
    source_id: str
    page: int | None = None
    snippet: str | None = None
    score: float


class ReferenceSearchResponse(BaseModel):
    query: str
    results: list[ReferenceSearchResult]


class ReferenceUploadResponse(BaseModel):
    ok: bool
    id: str
    meta: ReferenceMeta


class ReferenceReindexResponse(BaseModel):
    ok: bool
    id: str
    embeddings: int


def _storage_root() -> Path:
    root = Path(__file__).resolve().parents[1] / "storage" / "references"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _folders_file() -> Path:
    return _storage_root() / "folders.json"


def _load_ref_folders() -> list[str]:
    f = _folders_file()
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_ref_folders(folders: list[str]) -> None:
    _folders_file().write_text(json.dumps(sorted(set(folders))), encoding="utf-8")


def _validate_ref_folder_path(folder: str) -> str:
    """Sanitise a folder path: strip outer slashes, block traversal attacks."""
    clean = folder.strip("/")
    if not clean:
        return ""
    for seg in clean.split("/"):
        if seg in ("", ".", "..") or "\\" in seg or "\x00" in seg or ":" in seg:
            raise HTTPException(status_code=400, detail=f"Invalid folder segment: {seg!r}")
    return clean


def _save_uploaded_file(dest: Path, upload: UploadFile):
    with open(dest, "wb") as f:
        f.write(upload.file.read())


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML-to-text converter using stdlib only."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip = False
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        return _html_stdlib.unescape("".join(self._parts))


def _extract_pages_text(file_path: Path) -> list[str]:
    """Extract text from a document file into a list of page/chunk strings.

    Supports PDF, plain text (.txt, .md, .csv, .json), HTML (.html, .htm),
    Word documents (.docx), and Excel spreadsheets (.xlsx).
    For non-paged formats the entire content is returned as a single chunk.
    """
    suffix = file_path.suffix.lower()

    # ── PDF ────────────────────────────────────────────────────────────────
    if suffix == ".pdf":
        try:
            reader = PdfReader(str(file_path))
            pages: list[str] = []
            for page in reader.pages:
                text = page.extract_text() or ""
                pages.append(text)
            return pages
        except Exception:
            logger.exception("Failed to extract PDF text from %s", file_path.name)
            return []

    # ── Plain text / Markdown / CSV / JSON ────────────────────────────────
    if suffix in {".txt", ".md", ".csv", ".json"}:
        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
            # chunk at ~3000 chars to keep passage size reasonable
            chunk_size = 3000
            chunks = [raw[i : i + chunk_size] for i in range(0, len(raw), chunk_size)] or [""]
            return chunks
        except Exception:
            logger.exception("Failed to read text file %s", file_path.name)
            return []

    # ── HTML ───────────────────────────────────────────────────────────────
    if suffix in {".html", ".htm"}:
        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
            extractor = _HTMLTextExtractor()
            extractor.feed(raw)
            text = extractor.get_text()
            chunk_size = 3000
            chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]
            return chunks
        except Exception:
            logger.exception("Failed to extract HTML text from %s", file_path.name)
            return []

    # ── Word documents (.docx) ─────────────────────────────────────────────
    if suffix in {".docx", ".doc"}:
        try:
            import docx  # python-docx

            doc = docx.Document(str(file_path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            # group paragraphs into page-sized chunks
            chunk_size = 3000
            docx_chunks: list[str] = []
            current = ""
            for para in paragraphs:
                if len(current) + len(para) + 1 > chunk_size and current:
                    docx_chunks.append(current)
                    current = para
                else:
                    current = (current + "\n" + para).strip() if current else para
            if current:
                docx_chunks.append(current)
            return docx_chunks or [""]
        except Exception:
            logger.exception("Failed to extract Word text from %s", file_path.name)
            return []

    # ── Excel spreadsheets (.xlsx / .xls) ────────────────────────────────
    if suffix in {".xlsx", ".xls"}:
        try:
            import openpyxl

            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
            excel_chunks: list[str] = []
            for sheet in wb.worksheets:
                rows_text: list[str] = []
                for row in sheet.iter_rows(values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    rows_text.append("\t".join(cells))
                sheet_text = f"[Sheet: {sheet.title}]\n" + "\n".join(rows_text)
                chunk_size = 3000
                for i in range(0, len(sheet_text), chunk_size):
                    excel_chunks.append(sheet_text[i : i + chunk_size])
            wb.close()
            return excel_chunks or [""]
        except Exception:
            logger.exception("Failed to extract Excel text from %s", file_path.name)
            return []

    # ── Fallback: try reading as UTF-8 text ───────────────────────────────
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        return [raw[:3000]] if raw.strip() else []
    except Exception:
        logger.exception("Failed to read file %s as text", file_path.name)
        return []


def _cosine_score(a: list[float], b: list[float]) -> float:
    # Avoid numpy dependency; compute cosine similarity manually
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / ((na**0.5) * (nb**0.5))


def _make_snippet(text: str, max_len: int = 400) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rsplit(" ", 1)[0] + "…"


@router.post("/upload", response_model=ReferenceUploadResponse)
async def upload_reference(
    file: UploadFile = File(...),
    title: str = Form(None),
    system_ref: bool = Form(False),
    game_system: str = Form("global"),
    folder: str = Form(""),
    current_user=Depends(get_current_user),
):
    """Upload a reference document for AI lookup.

    Supported formats: PDF, Word (.docx), Excel (.xlsx), HTML (.html/.htm),
    plain text (.txt), Markdown (.md), CSV (.csv), and JSON (.json).
    Text is extracted and optionally embedded for semantic search if
    OPENAI_API_KEY is set.

    Set ``system_ref=true`` to mark this document as system-level reference
    data (e.g. rulebooks, monster manuals).  System references are:
    - Only uploadable by admins.
    - Never listed or searchable by players.
    - Never returned verbatim to any endpoint (snippets are suppressed).
    - Accessible only to AI agents building GM context internally.
    """
    if system_ref and not _db.is_admin_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admins may upload system reference documents.",
        )
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{suffix}'. "
                "Accepted: PDF, Word (.docx), Excel (.xlsx), HTML, "
                "plain text (.txt/.md/.csv), JSON."
            ),
        )
    root = _storage_root()
    safe_name = (title or Path(filename).stem).strip().replace(" ", "_")
    dest_dir = root / f"{safe_name}"
    if dest_dir.exists():
        # create a new unique folder
        i = 1
        while (root / f"{safe_name}_{i}").exists():
            i += 1
        dest_dir = root / f"{safe_name}_{i}"
    dest_dir.mkdir(parents=True)
    dest_file = dest_dir / filename
    _save_uploaded_file(dest_file, file)

    pages = _extract_pages_text(dest_file)

    # prepare pages JSON
    pages_json = []
    for idx, text in enumerate(pages):
        pages_json.append({"page": idx + 1, "text": text, "snippet": _make_snippet(text)})

    size_bytes = dest_file.stat().st_size if dest_file.exists() else 0
    created_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    clean_folder = _validate_ref_folder_path(folder or "")
    meta = {
        "title": title or filename,
        "filename": filename,
        "pages": len(pages),
        "system_ref": bool(system_ref),
        "game_system": game_system or "global",
        "size_bytes": size_bytes,
        "created_at": created_at,
        "folder": clean_folder,
    }
    # Register the folder so it appears in the folder list
    if clean_folder:
        existing_folders = _load_ref_folders()
        if clean_folder not in existing_folders:
            existing_folders.append(clean_folder)
            _write_ref_folders(existing_folders)
    (dest_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (dest_dir / "pages.json").write_text(json.dumps(pages_json, ensure_ascii=False), encoding="utf-8")

    # Try to build embeddings if OPENAI_API_KEY is present
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            import openai

            openai.api_key = openai_key
            embeddings: list[list[float] | None] = []
            for page in pages_json:
                text = page["text"] or ""
                if not text.strip():
                    embeddings.append(None)
                    continue
                # create embedding
                resp = openai.Embedding.create(model="text-embedding-3-small", input=text)
                vect = resp["data"][0]["embedding"]
                embeddings.append(vect)
            (dest_dir / "embeddings.json").write_text(json.dumps(embeddings), encoding="utf-8")
        except Exception:
            logger.exception("Failed to create embeddings; saving pages without vectors")

    return {"ok": True, "id": dest_dir.name, "meta": meta}


@router.get("/list", response_model=list[ReferenceListItem])
async def list_references(current_user=Depends(get_current_user)):
    root = _storage_root()
    is_admin = _db.is_admin_user(current_user)
    out: list[ReferenceListItem] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        meta_path = directory / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {"title": directory.name, "filename": "", "pages": 0, "system_ref": False}
        else:
            meta = {"title": directory.name, "filename": "", "pages": 0, "system_ref": False}
        # Back-fill size_bytes / created_at for documents uploaded before these fields existed.
        if not meta.get("size_bytes"):
            for f in directory.iterdir():
                if f.suffix.lower() not in (".json",):
                    meta["size_bytes"] = f.stat().st_size
                    break
        if not meta.get("created_at"):
            ts = directory.stat().st_mtime
            meta["created_at"] = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")
        # System references are never listed to non-admin users.
        if meta.get("system_ref") and not is_admin:
            continue
        out.append({"id": directory.name, "meta": meta})
    return out


@router.get("/folders", response_model=FolderListResponse)
async def list_ref_folders(current_user=Depends(get_current_user)):
    """Return the list of all known reference folders."""
    return {"folders": _load_ref_folders()}


@router.post("/folders", status_code=201, response_model=FolderItem)
async def create_ref_folder(
    body: FolderItem,
    current_user=Depends(get_current_user),
):
    """Create a new logical folder for organising references. Admin only."""
    if not _db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required.")
    clean = _validate_ref_folder_path(body.folder)
    if not clean:
        raise HTTPException(status_code=400, detail="Folder name required.")
    folders = _load_ref_folders()
    if clean not in folders:
        folders.append(clean)
        _write_ref_folders(folders)
    return {"folder": clean}


@router.delete("/folders/{folder_path:path}")
async def delete_ref_folder(
    folder_path: str,
    current_user=Depends(get_current_user),
):
    """Delete a folder. Fails if any reference is still assigned to it. Admin only."""
    if not _db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required.")
    clean = _validate_ref_folder_path(folder_path)
    root = _storage_root()
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        meta_path = directory / "metadata.json"
        if meta_path.exists():
            try:
                ref_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                ref_folder = ref_meta.get("folder", "")
                if ref_folder == clean or ref_folder.startswith(clean + "/"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Folder '{clean}' is not empty — move or delete its references first.",
                    )
            except HTTPException:
                raise
            except Exception:
                pass
    _write_ref_folders([f for f in _load_ref_folders() if f != clean])
    return {"ok": True}


@router.patch("/{ref_id}/move", response_model=ReferenceListItem)
async def move_reference(
    ref_id: str,
    body: MoveRefRequest,
    current_user=Depends(get_current_user),
):
    """Move a reference to a different logical folder. Admin only."""
    if not _db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required.")
    if not re.match(r"^[A-Za-z0-9_.\ -]+$", ref_id) or ".." in ref_id:
        raise HTTPException(status_code=400, detail="Invalid reference id.")
    clean = _validate_ref_folder_path(body.folder) if body.folder.strip("/") else ""
    root = _storage_root()
    directory = root / ref_id
    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=404, detail="Reference not found")
    meta_path = directory / "metadata.json"
    if meta_path.exists():
        try:
            ref_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            ref_meta = {"title": ref_id, "filename": "", "pages": 0, "system_ref": False}
    else:
        ref_meta = {"title": ref_id, "filename": "", "pages": 0, "system_ref": False}
    ref_meta["folder"] = clean
    meta_path.write_text(json.dumps(ref_meta, indent=2), encoding="utf-8")
    return {"id": ref_id, "meta": ref_meta}


@router.patch("/{ref_id}/meta", response_model=ReferenceListItem)
async def patch_reference_meta(
    ref_id: str,
    body: PatchRefMetaRequest,
    current_user=Depends(get_current_user),
):
    """Update editable metadata fields (game_system, title, system_ref) on a reference. Admin only."""
    if not _db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required.")
    if not re.match(r"^[A-Za-z0-9_.\ -]+$", ref_id) or ".." in ref_id:
        raise HTTPException(status_code=400, detail="Invalid reference id.")
    root = _storage_root()
    directory = root / ref_id
    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=404, detail="Reference not found")
    meta_path = directory / "metadata.json"
    if meta_path.exists():
        try:
            ref_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            ref_meta = {"title": ref_id, "filename": "", "pages": 0, "system_ref": False}
    else:
        ref_meta = {"title": ref_id, "filename": "", "pages": 0, "system_ref": False}
    if body.game_system is not None:
        ref_meta["game_system"] = body.game_system.strip() or "global"
    if body.title is not None:
        ref_meta["title"] = body.title.strip()
    if body.system_ref is not None:
        ref_meta["system_ref"] = body.system_ref
    meta_path.write_text(json.dumps(ref_meta, indent=2), encoding="utf-8")
    return {"id": ref_id, "meta": ref_meta}


@router.get("/search", response_model=ReferenceSearchResponse)
async def search_references(q: str, top_k: int = 5, current_user=Depends(get_current_user)):
    """Search all references for the query. Returns top_k passages with score and source info.

    System reference documents (rulebooks, monster manuals, etc.) are excluded
    from this endpoint entirely for non-admin users.  Even for admins, snippets
    from system references are suppressed -- they are for internal AI context
    only and must never be quoted verbatim.
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query required")
    is_admin = _db.is_admin_user(current_user)
    root = _storage_root()
    openai_key = os.environ.get("OPENAI_API_KEY")
    query_vect: list[float] | None = None
    if openai_key:
        try:
            import openai

            openai.api_key = openai_key
            resp = openai.Embedding.create(model="text-embedding-3-small", input=q)
            query_vect = resp["data"][0]["embedding"]
        except Exception:
            logger.exception("Failed to get query embedding; falling back to text match")
            query_vect = None

    candidates: list[dict[str, object]] = []
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        pages_path = directory / "pages.json"
        emb_path = directory / "embeddings.json"
        if not pages_path.exists():
            continue
        # Check system_ref flag before returning any content.
        meta_path = directory / "metadata.json"
        is_system = False
        if meta_path.exists():
            try:
                ref_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                is_system = bool(ref_meta.get("system_ref"))
            except Exception:
                pass
        # Non-admin users never see system reference content.
        if is_system and not is_admin:
            continue
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
        embeddings = None
        if emb_path.exists():
            try:
                embeddings = json.loads(emb_path.read_text(encoding="utf-8"))
            except Exception:
                embeddings = None
        for idx, page in enumerate(pages):
            score = 0.0
            if query_vect and embeddings and embeddings[idx]:
                score = _cosine_score(query_vect, embeddings[idx])
            else:
                # fallback: simple substring scoring
                text = (page.get("text") or "").lower()
                q_lower = q.lower()
                if q_lower in text:
                    score = min(1.0, len(q_lower) / (len(text) + 1) * 50)
                else:
                    toks = set(q_lower.split())
                    ct = sum(1 for tok in toks if tok in text)
                    if toks:
                        score = ct / len(toks) * 0.2
            if score > 0:
                candidates.append(
                    {
                        "source_id": directory.name,
                        "page": page.get("page"),
                        # Verbatim snippets are never returned for system
                        # references -- agents must paraphrase from context.
                        "snippet": None if is_system else page.get("snippet"),
                        "score": float(score),
                    }
                )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {"query": q, "results": candidates[:top_k]}


@router.get("/{ref_id}/raw")
def get_reference_raw(ref_id: str, current_user=Depends(get_current_user)):
    """Return the raw file for a given reference id.

    For PDFs the browser can display inline; for other types the file is served
    for download with the appropriate media type inferred from the extension.

    System reference documents (e.g. rulebooks, monster manuals) are restricted
    to admins only -- players may never download the source material.
    """
    root = _storage_root()
    directory = root / ref_id
    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=404, detail="Reference not found")
    # Enforce system_ref access control before serving any bytes.
    meta_path = directory / "metadata.json"
    if meta_path.exists():
        try:
            ref_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if ref_meta.get("system_ref") and not _db.is_admin_user(current_user):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: system reference documents are not available to players.",
                )
        except HTTPException:
            raise
        except Exception:
            pass
    # Prefer a known document file over metadata/index files
    preferred_suffixes = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".html", ".htm", ".txt", ".md", ".csv", ".json"}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in preferred_suffixes:
            media_type = "application/pdf" if path.suffix.lower() == ".pdf" else None
            return FileResponse(str(path), media_type=media_type, filename=path.name)
    # Fallback: if any non-index file exists, return the first
    for path in directory.iterdir():
        if path.is_file() and path.name not in {"metadata.json", "pages.json", "embeddings.json"}:
            return FileResponse(str(path), filename=path.name)
    raise HTTPException(status_code=404, detail="No file found for reference")


@router.post("/{ref_id}/reindex", response_model=ReferenceReindexResponse)
def reindex_reference(ref_id: str, current_user=Depends(get_current_user)):
    """Rebuild embeddings for a reference id (requires OPENAI_API_KEY)."""
    root = _storage_root()
    directory = root / ref_id
    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=404, detail="Reference not found")
    pages_path = directory / "pages.json"
    if not pages_path.exists():
        raise HTTPException(status_code=400, detail="No pages.json for reference")
    try:
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read pages.json") from None

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY not configured")
    try:
        import openai

        openai.api_key = openai_key
        embeddings: list[list[float] | None] = []
        for page in pages:
            text = page.get("text") or ""
            if not text.strip():
                embeddings.append(None)
                continue
            resp = openai.Embedding.create(model="text-embedding-3-small", input=text)
            vect = resp["data"][0]["embedding"]
            embeddings.append(vect)
        (directory / "embeddings.json").write_text(json.dumps(embeddings), encoding="utf-8")
        return {"ok": True, "id": ref_id, "embeddings": len(embeddings)}
    except Exception:
        logger.exception("Reindex failed")
        raise HTTPException(status_code=500, detail="Reindex failed") from None


@router.delete("/{ref_id}", status_code=204)
def delete_reference(ref_id: str, current_user=Depends(get_current_user)):
    """Delete a reference document and all its indexed data. Admin only."""
    import shutil

    if not _db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required.")
    # Sanitise ref_id: must be a plain directory name with no path traversal.
    # Allow dots (e.g. folders named after filenames) but never allow "..".
    if not re.match(r"^[A-Za-z0-9_.\-]+$", ref_id) or ".." in ref_id:
        raise HTTPException(status_code=400, detail="Invalid reference id.")
    root = _storage_root()
    directory = root / ref_id
    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=404, detail="Reference not found")
    shutil.rmtree(str(directory))
    return Response(status_code=204)


def search_query(q: str, top_k: int = 5, *, system_only: bool = False, include_system: bool = True):
    """Synchronous helper for other server modules to search references.

    Returns list of result dicts: {source_id, page, snippet, score, paraphrase_required}

    Parameters
    ----------
    system_only:
        When True, search ONLY system reference documents (rulebooks, etc.).
    include_system:
        When False, skip all system reference documents.  Useful for
        user-facing queries that should not draw on restricted material.

    Notes
    -----
    The ``snippet`` field is always ``None`` for system reference results.
    The ``paraphrase_required`` flag is ``True`` for those results.
    Agents MUST paraphrase or summarise content from system references;
    they must never quote the source text verbatim.
    """
    if not q or not q.strip():
        return []
    root = _storage_root()
    openai_key = os.environ.get("OPENAI_API_KEY")
    query_vect: list[float] | None = None
    if openai_key:
        try:
            import openai

            openai.api_key = openai_key
            resp = openai.Embedding.create(model="text-embedding-3-small", input=q)
            query_vect = resp["data"][0]["embedding"]
        except Exception:
            logger.exception("Failed to get query embedding; falling back to text match")
            query_vect = None

    candidates: list[dict[str, object]] = []
    # Prepare corpus for TF-IDF fallback
    corpus_texts: list[str] = []
    corpus_meta: list[dict[str, object]] = []
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        pages_path = directory / "pages.json"
        emb_path = directory / "embeddings.json"
        if not pages_path.exists():
            continue
        # Resolve system_ref flag for this directory.
        dir_meta_path = directory / "metadata.json"
        is_system = False
        if dir_meta_path.exists():
            try:
                dir_meta = json.loads(dir_meta_path.read_text(encoding="utf-8"))
                is_system = bool(dir_meta.get("system_ref"))
            except Exception:
                pass
        if system_only and not is_system:
            continue
        if not include_system and is_system:
            continue
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
        embeddings = None
        if emb_path.exists():
            try:
                embeddings = json.loads(emb_path.read_text(encoding="utf-8"))
            except Exception:
                embeddings = None
        for idx, page in enumerate(pages):
            text = (page.get("text") or "")
            corpus_texts.append(text)
            corpus_meta.append(
                {
                    "source_id": directory.name,
                    "page": page.get("page"),
                    # Never expose raw snippet text for system references.
                    "snippet": None if is_system else page.get("snippet"),
                    "paraphrase_required": is_system,
                    "emb": embeddings[idx] if embeddings and idx < len(embeddings) else None,
                }
            )

    # If we have query embedding and page embeddings, score by cosine
    if query_vect and any(meta.get("emb") for meta in corpus_meta):
        for meta in corpus_meta:
            emb = meta.get("emb")
            if not emb:
                continue
            score = _cosine_score(query_vect, emb)  # type: ignore[arg-type]
            if score > 0:
                candidates.append(
                    {
                        "source_id": meta["source_id"],
                        "page": meta["page"],
                        "snippet": meta.get("snippet"),
                        "paraphrase_required": meta.get("paraphrase_required", False),
                        "score": float(score),
                    }
                )
    else:
        # TF-IDF fallback scoring
        # Simple tokenizer
        def tokenize(s: str):
            return list(re.findall(r"[a-z0-9]{2,}", (s or "").lower()))

        # Build IDF
        n_docs = len(corpus_texts)
        idf: dict[str, float] = {}
        df: dict[str, int] = {}
        for text in corpus_texts:
            tokens = set(tokenize(text))
            for token in tokens:
                df[token] = df.get(token, 0) + 1
        for token, count in df.items():
            idf[token] = math.log((n_docs + 1) / (count + 1)) + 1.0

        # Query vector
        q_tokens = tokenize(q)
        if q_tokens:
            q_tf: dict[str, int] = {}
            for token in q_tokens:
                q_tf[token] = q_tf.get(token, 0) + 1
            q_vec: dict[str, float] = {token: (q_tf[token] * idf.get(token, 0.0)) for token in q_tf}
            q_norm = sum(val * val for val in q_vec.values()) ** 0.5

            for idx, text in enumerate(corpus_texts):
                t_tf: dict[str, int] = {}
                toks = tokenize(text)
                if not toks:
                    continue
                for tok in toks:
                    t_tf[tok] = t_tf.get(tok, 0) + 1
                # build dot product
                dot = 0.0
                for token, q_val in q_vec.items():
                    t_val = t_tf.get(token, 0) * idf.get(token, 0.0)
                    dot += q_val * t_val
                denom_a = q_norm
                denom_b = sum((t_tf.get(tok, 0) * idf.get(tok, 0.0)) ** 2 for tok in t_tf) ** 0.5
                if denom_a > 0 and denom_b > 0:
                    score = dot / (denom_a * denom_b)
                else:
                    score = 0.0
                if score > 0:
                    meta = corpus_meta[idx]
                    candidates.append(
                        {
                            "source_id": meta["source_id"],
                            "page": meta["page"],
                            "snippet": meta.get("snippet"),
                            "paraphrase_required": meta.get("paraphrase_required", False),
                            "score": float(score),
                        }
                    )
        else:
            # As a last resort, substring match
            q_lower = q.lower()
            for idx, text in enumerate(corpus_texts):
                if q_lower in (text or "").lower():
                    meta = corpus_meta[idx]
                    candidates.append(
                        {
                            "source_id": meta["source_id"],
                            "page": meta["page"],
                            "snippet": meta.get("snippet"),
                            "paraphrase_required": meta.get("paraphrase_required", False),
                            "score": 0.5,
                        }
                    )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:top_k]
