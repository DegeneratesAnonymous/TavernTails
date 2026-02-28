import html as _html_stdlib
import json
import logging
import math
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pypdf import PdfReader

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


class ReferenceListItem(BaseModel):
    id: str
    meta: ReferenceMeta


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
    current_user=Depends(get_current_user),
):
    """Upload a reference document for AI lookup.

    Supported formats: PDF, Word (.docx), Excel (.xlsx), HTML (.html/.htm),
    plain text (.txt), Markdown (.md), CSV (.csv), and JSON (.json).
    Text is extracted and optionally embedded for semantic search if
    OPENAI_API_KEY is set.
    """
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

    meta = {"title": title or filename, "filename": filename, "pages": len(pages)}
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
    out: list[ReferenceListItem] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        meta_path = directory / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {"title": directory.name, "filename": "", "pages": 0}
        else:
            meta = {"title": directory.name, "filename": "", "pages": 0}
        out.append({"id": directory.name, "meta": meta})
    return out


@router.get("/search", response_model=ReferenceSearchResponse)
async def search_references(q: str, top_k: int = 5, current_user=Depends(get_current_user)):
    """Search all references for the query. Returns top_k passages with score and source info."""
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query required")
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
                    # score by fraction of context matched
                    score = min(1.0, len(q_lower) / (len(text) + 1) * 50)
                else:
                    # small partial score for token overlap
                    toks = set(q_lower.split())
                    ct = sum(1 for tok in toks if tok in text)
                    if toks:
                        score = ct / len(toks) * 0.2
            if score > 0:
                candidates.append(
                    {
                        "source_id": directory.name,
                        "page": page.get("page"),
                        "snippet": page.get("snippet"),
                        "score": float(score),
                    }
                )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {"query": q, "results": candidates[:top_k]}


@router.get("/{ref_id}/raw")
def get_reference_raw(ref_id: str):
    """Return the raw file for a given reference id.

    For PDFs the browser can display inline; for other types the file is served
    for download with the appropriate media type inferred from the extension.
    """
    root = _storage_root()
    directory = root / ref_id
    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=404, detail="Reference not found")
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


def search_query(q: str, top_k: int = 5):
    """Synchronous helper for other server modules to search references.

    Returns list of result dicts: {source_id, page, snippet, score}
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
                    "snippet": page.get("snippet"),
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
                            "score": 0.5,
                        }
                    )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:top_k]
