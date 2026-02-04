import json
import logging
import math
import os
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pypdf import PdfReader

from ..auth import get_current_user

logger = logging.getLogger("taverntails.references")

router = APIRouter(prefix="/references", tags=["references"])


class ReferenceMeta(BaseModel):
    title: str
    filename: str
    pages: int


class ReferenceListItem(BaseModel):
    id: str
    meta: ReferenceMeta


class ReferenceSearchResult(BaseModel):
    source_id: str
    page: Optional[int] = None
    snippet: Optional[str] = None
    score: float


class ReferenceSearchResponse(BaseModel):
    query: str
    results: List[ReferenceSearchResult]


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


def _extract_pages_text(pdf_path: Path) -> List[str]:
    try:
        reader = PdfReader(str(pdf_path))
        pages = []
        for p in reader.pages:
            text = p.extract_text() or ""
            pages.append(text)
        return pages
    except Exception:
        logger.exception("Failed to extract PDF text")
        return []


def _cosine_score(a: List[float], b: List[float]) -> float:
    # Avoid numpy dependency; compute cosine similarity manually
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def _make_snippet(text: str, max_len: int = 400) -> str:
    t = " ".join(text.split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rsplit(" ", 1)[0] + "…"


@router.post("/upload", response_model=ReferenceUploadResponse)
async def upload_reference(
    file: UploadFile = File(...),
    title: str = Form(None),
    current_user=Depends(get_current_user),
):
    """Upload a reference PDF (PHB/DMG/MM). This will extract per-page text and create an embedding index if OPENAI_API_KEY is set."""
    root = _storage_root()
    safe_name = (title or Path(file.filename).stem).strip().replace(" ", "_")
    dest_dir = root / f"{safe_name}"
    if dest_dir.exists():
        # create a new unique folder
        i = 1
        while (root / f"{safe_name}_{i}").exists():
            i += 1
        dest_dir = root / f"{safe_name}_{i}"
    dest_dir.mkdir(parents=True)
    dest_pdf = dest_dir / file.filename
    _save_uploaded_file(dest_pdf, file)

    pages = _extract_pages_text(dest_pdf)

    # prepare pages JSON
    pages_json = []
    for idx, text in enumerate(pages):
        pages_json.append({"page": idx + 1, "text": text, "snippet": _make_snippet(text)})

    meta = {"title": title or file.filename, "filename": file.filename, "pages": len(pages)}
    (dest_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (dest_dir / "pages.json").write_text(json.dumps(pages_json, ensure_ascii=False), encoding="utf-8")

    # Try to build embeddings if OPENAI_API_KEY is present
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            import openai

            openai.api_key = openai_key
            embeddings = []
            for p in pages_json:
                text = p["text"] or ""
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


@router.get("/list", response_model=List[ReferenceListItem])
async def list_references(current_user=Depends(get_current_user)):
    root = _storage_root()
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        if meta_path.exists():
            try:
                m = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                m = {"title": d.name, "filename": "", "pages": 0}
        else:
            m = {"title": d.name, "filename": "", "pages": 0}
        out.append({"id": d.name, "meta": m})
    return out


@router.get("/search", response_model=ReferenceSearchResponse)
async def search_references(q: str, top_k: int = 5, current_user=Depends(get_current_user)):
    """Search all references for the query. Returns top_k passages with score and source info."""
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query required")
    root = _storage_root()
    openai_key = os.environ.get("OPENAI_API_KEY")
    query_vect = None
    if openai_key:
        try:
            import openai

            openai.api_key = openai_key
            resp = openai.Embedding.create(model="text-embedding-3-small", input=q)
            query_vect = resp["data"][0]["embedding"]
        except Exception:
            logger.exception("Failed to get query embedding; falling back to text match")
            query_vect = None

    candidates = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        pages_path = d / "pages.json"
        emb_path = d / "embeddings.json"
        if not pages_path.exists():
            continue
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
        embeddings = None
        if emb_path.exists():
            try:
                embeddings = json.loads(emb_path.read_text(encoding="utf-8"))
            except Exception:
                embeddings = None
        for i, p in enumerate(pages):
            score = 0.0
            if query_vect and embeddings and embeddings[i]:
                score = _cosine_score(query_vect, embeddings[i])
            else:
                # fallback: simple substring scoring
                text = (p.get("text") or "").lower()
                ql = q.lower()
                if ql in text:
                    # score by fraction of context matched
                    score = min(1.0, len(ql) / (len(text) + 1) * 50)
                else:
                    # small partial score for token overlap
                    toks = set(ql.split())
                    ct = sum(1 for t in toks if t in text)
                    if toks:
                        score = ct / len(toks) * 0.2
            if score > 0:
                candidates.append(
                    {
                        "source_id": d.name,
                        "page": p.get("page"),
                        "snippet": p.get("snippet"),
                        "score": float(score),
                    }
                )

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return {"query": q, "results": candidates[:top_k]}


@router.get("/{ref_id}/raw")
def get_reference_raw(ref_id: str):
    """Return the raw PDF file for a given reference id (served for embedding/viewing in the frontend).

    The frontend may open this URL and include a `#page=` fragment to jump to a page.
    """
    root = _storage_root()
    d = root / ref_id
    if not d.exists() or not d.is_dir():
        raise HTTPException(status_code=404, detail="Reference not found")
    # Find a PDF file in the directory
    for p in d.iterdir():
        if p.is_file() and p.suffix.lower() == '.pdf':
            return FileResponse(str(p), media_type='application/pdf', filename=p.name)
    # Fallback: if any file exists, return the first
    for p in d.iterdir():
        if p.is_file():
            return FileResponse(str(p), filename=p.name)
    raise HTTPException(status_code=404, detail='No file found for reference')


@router.post("/{ref_id}/reindex", response_model=ReferenceReindexResponse)
def reindex_reference(ref_id: str, current_user=Depends(get_current_user)):
    """Rebuild embeddings for a reference id (requires OPENAI_API_KEY)."""
    root = _storage_root()
    d = root / ref_id
    if not d.exists() or not d.is_dir():
        raise HTTPException(status_code=404, detail="Reference not found")
    pages_path = d / "pages.json"
    if not pages_path.exists():
        raise HTTPException(status_code=400, detail="No pages.json for reference")
    try:
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
    except Exception as err:
        raise HTTPException(status_code=500, detail="Failed to read pages.json") from err

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY not configured")
    try:
        import openai

        openai.api_key = openai_key
        embeddings = []
        for p in pages:
            text = p.get("text") or ""
            if not text.strip():
                embeddings.append(None)
                continue
            resp = openai.Embedding.create(model="text-embedding-3-small", input=text)
            vect = resp["data"][0]["embedding"]
            embeddings.append(vect)
        (d / "embeddings.json").write_text(json.dumps(embeddings), encoding="utf-8")
        return {"ok": True, "id": ref_id, "embeddings": len(embeddings)}
    except Exception as err:
        logger.exception("Reindex failed")
        raise HTTPException(status_code=500, detail="Reindex failed") from err


def search_query(q: str, top_k: int = 5):
    """Synchronous helper for other server modules to search references.

    Returns list of result dicts: {source_id, page, snippet, score}
    """
    if not q or not q.strip():
        return []
    root = _storage_root()
    openai_key = os.environ.get("OPENAI_API_KEY")
    query_vect = None
    if openai_key:
        try:
            import openai

            openai.api_key = openai_key
            resp = openai.Embedding.create(model="text-embedding-3-small", input=q)
            query_vect = resp["data"][0]["embedding"]
        except Exception:
            logger.exception("Failed to get query embedding; falling back to text match")
            query_vect = None

    candidates = []
    # Prepare corpus for TF-IDF fallback
    corpus_texts = []
    corpus_meta = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        pages_path = d / "pages.json"
        emb_path = d / "embeddings.json"
        if not pages_path.exists():
            continue
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
        embeddings = None
        if emb_path.exists():
            try:
                embeddings = json.loads(emb_path.read_text(encoding="utf-8"))
            except Exception:
                embeddings = None
        for i, p in enumerate(pages):
            text = (p.get("text") or "")
            corpus_texts.append(text)
            corpus_meta.append({"source_id": d.name, "page": p.get("page"), "snippet": p.get("snippet"), "emb": (embeddings[i] if embeddings and i < len(embeddings) else None)})

    # If we have query embedding and page embeddings, score by cosine
    if query_vect and any(m.get("emb") for m in corpus_meta):
        for meta in corpus_meta:
            emb = meta.get("emb")
            if not emb:
                continue
            score = _cosine_score(query_vect, emb)
            if score > 0:
                candidates.append({"source_id": meta["source_id"], "page": meta["page"], "snippet": meta.get("snippet"), "score": float(score)})
    else:
        # TF-IDF fallback scoring
        # Simple tokenizer
        def tokenize(s: str):
            return list(re.findall(r"[a-z0-9]{2,}", (s or "").lower()))

        # Build IDF
        total_docs = len(corpus_texts)
        idf = {}
        df = {}
        for text in corpus_texts:
            tokens = set(tokenize(text))
            for t in tokens:
                df[t] = df.get(t, 0) + 1
        for t, cnt in df.items():
            idf[t] = math.log((total_docs + 1) / (cnt + 1)) + 1.0

        # Query vector
        q_tokens = tokenize(q)
        if q_tokens:
            q_tf = {}
            for t in q_tokens:
                q_tf[t] = q_tf.get(t, 0) + 1
            q_vec = {t: (q_tf[t] * idf.get(t, 0.0)) for t in q_tf}
            q_norm = sum(v * v for v in q_vec.values()) ** 0.5

            for idx, text in enumerate(corpus_texts):
                t_tf = {}
                toks = tokenize(text)
                if not toks:
                    continue
                for t in toks:
                    t_tf[t] = t_tf.get(t, 0) + 1
                # build dot product
                dot = 0.0
                denom_a = 0.0
                denom_b = 0.0
                for t, qv in q_vec.items():
                    tv = (t_tf.get(t, 0) * idf.get(t, 0.0))
                    dot += qv * tv
                denom_a = q_norm
                denom_b = sum((t_tf.get(t, 0) * idf.get(t, 0.0)) ** 2 for t in t_tf) ** 0.5
                if denom_a > 0 and denom_b > 0:
                    score = dot / (denom_a * denom_b)
                else:
                    score = 0.0
                if score > 0:
                    meta = corpus_meta[idx]
                    candidates.append({"source_id": meta["source_id"], "page": meta["page"], "snippet": meta.get("snippet"), "score": float(score)})
        else:
            # As a last resort, substring match
            ql = q.lower()
            for idx, text in enumerate(corpus_texts):
                if ql in (text or "").lower():
                    meta = corpus_meta[idx]
                    candidates.append({"source_id": meta["source_id"], "page": meta["page"], "snippet": meta.get("snippet"), "score": 0.5})

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]
