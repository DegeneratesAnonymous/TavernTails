"""Document storage abstraction with local filesystem implementation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


@dataclass
class DocumentMeta:
    id: str
    session_id: str
    name: str
    category: str = "core"
    visibility: str = "shared"  # shared|hidden
    filename: str = ""
    size: int = 0
    created_at: str = ""


class DocumentStore:
    def list_documents(self, session_id: str) -> List[DocumentMeta]:
        raise NotImplementedError

    def save_document(self, *, session_id: str, name: str, content: bytes | str, filename: Optional[str] = None, category: str = "core", visibility: str = "shared") -> DocumentMeta:
        raise NotImplementedError

    def delete_document(self, session_id: str, doc_id: str) -> bool:
        raise NotImplementedError

    def read_document(self, session_id: str, doc_id: str) -> Optional[tuple[DocumentMeta, str]]:
        raise NotImplementedError

    def generate_presigned_post(self, session_id: str, filename: str, content_type: str | None = None, expires_in: int = 3600) -> dict:
        raise NotImplementedError

    def register_existing_object(self, session_id: str, filename: str, name: str, size: int, category: str = "core", visibility: str = "shared") -> DocumentMeta:
        raise NotImplementedError


class LocalDocumentStore(DocumentStore):
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        folder = self.base_dir / session_id / "docs"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _meta_file(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "meta.json"

    def _load_meta(self, session_id: str) -> List[DocumentMeta]:
        meta_path = self._meta_file(session_id)
        if not meta_path.exists():
            return []
        data = json.loads(meta_path.read_text())
        return [DocumentMeta(**entry) for entry in data]

    def _write_meta(self, session_id: str, entries: List[DocumentMeta]) -> None:
        meta_path = self._meta_file(session_id)
        meta_path.write_text(json.dumps([asdict(entry) for entry in entries], indent=2))

    def list_documents(self, session_id: str) -> List[DocumentMeta]:
        return self._load_meta(session_id)

    def save_document(self, *, session_id: str, name: str, content: bytes | str, filename: Optional[str] = None, category: str = "core", visibility: str = "shared") -> DocumentMeta:
        doc_id = uuid.uuid4().hex[:8]
        folder = self._session_dir(session_id)
        # If client provided a filename, preserve its extension
        if filename:
            ext = Path(filename).suffix or '.dat'
            stored_name = f"{doc_id}{ext}"
        else:
            stored_name = f"{doc_id}.txt"
        target = folder / stored_name
        if isinstance(content, str):
            encoded = content.encode("utf-8")
        else:
            encoded = content
        target.write_bytes(encoded)
        meta = self._load_meta(session_id)
        created = DocumentMeta(
            id=doc_id,
            session_id=session_id,
            name=name,
            category=category,
            visibility=visibility,
            filename=stored_name,
            size=len(encoded),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        meta.append(created)
        self._write_meta(session_id, meta)
        return created

    def register_existing_object(self, session_id: str, filename: str, name: str, size: int, category: str = "core", visibility: str = "shared") -> DocumentMeta:
        # used for external uploads (e.g., S3 direct upload) to register metadata
        meta = self._load_meta(session_id)
        doc_id = uuid.uuid4().hex[:8]
        created = DocumentMeta(
            id=doc_id,
            session_id=session_id,
            name=name,
            category=category or 'core',
            visibility=visibility or 'shared',
            filename=filename,
            size=size,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        meta.append(created)
        self._write_meta(session_id, meta)
        return created

    def delete_document(self, session_id: str, doc_id: str) -> bool:
        folder = self._session_dir(session_id)
        meta = self._load_meta(session_id)
        remaining: List[DocumentMeta] = []
        deleted = False
        for entry in meta:
            if entry.id == doc_id:
                deleted = True
                try:
                    (folder / entry.filename).unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                remaining.append(entry)
        if deleted:
            self._write_meta(session_id, remaining)
        return deleted

    def read_document(self, session_id: str, doc_id: str) -> Optional[tuple[DocumentMeta, str]]:
        folder = self._session_dir(session_id)
        for entry in self._load_meta(session_id):
            if entry.id == doc_id:
                target = folder / entry.filename
                if not target.exists():
                    return None
                try:
                    content = target.read_text(encoding="utf-8")
                except Exception:
                    # fallback to binary-safe read
                    content = target.read_bytes().hex()
                return entry, content
        return None


class S3DocumentStore(DocumentStore):
    """S3-backed document store. Requires boto3 to be installed and AWS creds configured via env."""

    def __init__(self, bucket: str, prefix: str = "") -> None:
        try:
            import boto3  # noqa: F401  - ensure dependency exists
        except Exception as exc:  # pragma: no cover - defensive guard
            raise RuntimeError("boto3 is required for S3DocumentStore") from exc
        self.s3 = __import__('boto3').client('s3')
        self.bucket = bucket
        self.prefix = prefix.strip('/')

    def _session_root(self, session_id: str) -> str:
        rel = f"{session_id}/docs"
        return f"{self.prefix}/{rel}" if self.prefix else rel

    def _meta_key(self, session_id: str) -> str:
        return f"{self._session_root(session_id)}/meta.json"

    def _normalize_filename(self, session_id: str, filename: str) -> str:
        if not filename:
            return ""
        normalized = filename.strip('/')
        if self.prefix and normalized.startswith(f"{self.prefix}/"):
            normalized = normalized[len(self.prefix) + 1 :]
        bare_root = f"{session_id}/docs"
        if normalized.startswith(bare_root):
            normalized = normalized[len(bare_root):].lstrip('/')
        if not normalized:
            return Path(filename).name
        if '/' in normalized:
            return normalized.split('/')[-1]
        return normalized

    def _object_key(self, session_id: str, stored_name: str) -> str:
        stored = stored_name.strip('/')
        session_root = self._session_root(session_id)
        if not stored:
            return session_root
        if stored.startswith(session_root):
            return stored
        bare_root = f"{session_id}/docs"
        if stored.startswith(bare_root):
            return f"{self.prefix}/{stored}" if self.prefix else stored
        if self.prefix and stored.startswith(self.prefix):
            return stored
        return f"{session_root}/{stored}"

    def generate_presigned_post(self, session_id: str, filename: str, content_type: str | None = None, expires_in: int = 3600) -> dict:
        """Generate a presigned POST for direct browser upload to S3.

        Returns a dict with `url` and `fields` suitable for FormData uploads.
        """
        stored_name = filename or f"upload-{uuid.uuid4().hex}"
        key = self._object_key(session_id, stored_name)
        params = {"key": key}
        if content_type:
            params['ContentType'] = content_type
        try:
            resp = self.s3.generate_presigned_post(
                Bucket=self.bucket,
                Key=key,
                Fields=params,
                Conditions=[["content-length-range", 1, 50 * 1024 * 1024]],
                ExpiresIn=expires_in,
            )
            # resp contains 'url' and 'fields'
            return resp
        except Exception as exc:  # pragma: no cover - boto surfaces ClientError text
            raise exc

    def register_existing_object(self, session_id: str, filename: str, name: str, size: int, category: str = "core", visibility: str = "shared") -> DocumentMeta:
        metas = self.list_documents(session_id)
        doc_id = uuid.uuid4().hex[:8]
        stored_name = self._normalize_filename(session_id, filename)
        meta = DocumentMeta(
            id=doc_id,
            session_id=session_id,
            name=name,
            category=category or 'core',
            visibility=visibility or 'shared',
            filename=stored_name,
            size=size,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        metas.append(meta)
        meta_key = self._meta_key(session_id)
        try:
            self.s3.put_object(Bucket=self.bucket, Key=meta_key, Body=json.dumps([asdict(m) for m in metas], indent=2).encode('utf-8'))
        except Exception:
            pass
        return meta

    def list_documents(self, session_id: str) -> List[DocumentMeta]:
        key = self._meta_key(session_id)
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            body = resp['Body'].read()
            entries = json.loads(body)
            return [DocumentMeta(**e) for e in entries]
        except Exception:
            return []

    def save_document(self, *, session_id: str, name: str, content: bytes | str, filename: Optional[str] = None, category: str = "core", visibility: str = "shared") -> DocumentMeta:
        doc_id = uuid.uuid4().hex[:8]
        if filename:
            ext = Path(filename).suffix or '.dat'
            stored_name = f"{doc_id}{ext}"
        else:
            stored_name = f"{doc_id}.bin"
        key = self._object_key(session_id, stored_name)
        if isinstance(content, str):
            payload = content.encode('utf-8')
        else:
            payload = content
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=payload)
        # update meta.json
        metas = self.list_documents(session_id)
        meta = DocumentMeta(id=doc_id, session_id=session_id, name=name, category=category, visibility=visibility, filename=stored_name, size=len(payload), created_at=datetime.now(timezone.utc).isoformat())
        metas.append(meta)
        meta_key = self._meta_key(session_id)
        self.s3.put_object(Bucket=self.bucket, Key=meta_key, Body=json.dumps([asdict(m) for m in metas], indent=2).encode('utf-8'))
        return meta

    def delete_document(self, session_id: str, doc_id: str) -> bool:
        metas = self.list_documents(session_id)
        remaining = []
        deleted = False
        for m in metas:
            if m.id == doc_id:
                deleted = True
                try:
                    self.s3.delete_object(Bucket=self.bucket, Key=self._object_key(session_id, m.filename))
                except Exception:
                    pass
            else:
                remaining.append(m)
        if deleted:
            meta_key = self._meta_key(session_id)
            self.s3.put_object(Bucket=self.bucket, Key=meta_key, Body=json.dumps([asdict(m) for m in remaining], indent=2).encode('utf-8'))
        return deleted

    def read_document(self, session_id: str, doc_id: str) -> Optional[tuple[DocumentMeta, str]]:
        metas = self.list_documents(session_id)
        for m in metas:
            if m.id == doc_id:
                try:
                    key = self._object_key(session_id, m.filename)
                    resp = self.s3.get_object(Bucket=self.bucket, Key=key)
                    body = resp['Body'].read()
                    try:
                        text = body.decode('utf-8')
                    except Exception:
                        text = body.hex()
                    return m, text
                except Exception:
                    return None
        return None


class NullDocumentStore(DocumentStore):
    def list_documents(self, session_id: str) -> List[DocumentMeta]:  # pragma: no cover - placeholder
        return []

    def save_document(self, *, session_id: str, name: str, content: bytes | str, filename: Optional[str] = None, category: str = "core", visibility: str = "shared") -> DocumentMeta:  # pragma: no cover - placeholder
        raise NotImplementedError("S3 storage not configured")

    def delete_document(self, session_id: str, doc_id: str) -> bool:  # pragma: no cover - placeholder
        raise NotImplementedError("S3 storage not configured")

    def read_document(self, session_id: str, doc_id: str) -> Optional[tuple[DocumentMeta, str]]:  # pragma: no cover - placeholder
        raise NotImplementedError("S3 storage not configured")


_store: Optional[DocumentStore] = None


def get_document_store() -> DocumentStore:
    global _store
    if _store:
        return _store
    base_sessions = Path(__file__).resolve().parents[1] / 'sessions'
    mode = os.environ.get('TAVERNTAILS_STORAGE_MODE', 'local').lower()
    if mode == 's3':
        # configure S3 from environment
        bucket = os.environ.get('TAVERNTAILS_S3_BUCKET')
        prefix = os.environ.get('TAVERNTAILS_S3_PREFIX', '')
        if not bucket:
            _store = NullDocumentStore()
        else:
            try:
                _store = S3DocumentStore(bucket=bucket, prefix=prefix)
            except Exception:
                _store = NullDocumentStore()
    else:
        _store = LocalDocumentStore(base_sessions)
    return _store
