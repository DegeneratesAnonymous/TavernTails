"""Document storage abstraction with local filesystem implementation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Document category & visibility model
# ---------------------------------------------------------------------------
#
# Documents in TavernTAIls carry two orthogonal metadata attributes:
#
# category   — *what type of information* the document contains
# visibility — *who may read* the document ("hidden" = host/GM only; "shared" = all members)
#
# The category drives the **default** visibility.  Callers may override the
# default, but the rules below represent the intended design:
#
# ┌────────────────────┬───────────────────┬───────────────────────────────────────────────────────────────┐
# │ Category           │ Default visibility│ Description & agent(s) that write / read it                   │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ gm_plot            │ hidden            │ Full storyline, arcs, unresolved threads, major secrets.       │
# │                    │                   │ Written by Storyboard Agent; read only by GM/host.             │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ gm_npc             │ hidden            │ Full NPC profile: name, factions, motivations, personality,    │
# │                    │                   │ attitude ranks, secrets, class, gear, appearance, backstory.   │
# │                    │                   │ Written by NPC Manager Agent; never visible to players.        │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ gm_location        │ hidden            │ Full location detail: description, type, key_npcs, connected   │
# │                    │                   │ locations, known_to_players, hidden areas, traps, true history. │
# │                    │                   │ Written by Storyboard / GM; players only see player_location.  │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ gm_quest           │ hidden            │ Full quest outline: title, giver, objective, stakes, stages,   │
# │                    │                   │ rewards, complications, linked_npcs, linked_locations, secrets. │
# │                    │                   │ Written by Storyboard Agent; read only by GM/host.             │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ gm_notes           │ hidden            │ Miscellaneous GM notes, reminders, session prep.               │
# │                    │                   │ Written by GM directly; inaccessible to players.               │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ player_npc         │ shared            │ Player-perspective NPC entry: only physical appearance,        │
# │                    │                   │ dialogue heard, and relationship status.  Stats/secrets omitted.│
# │                    │                   │ Written by NPC Manager when an NPC is first encountered.       │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ player_location    │ shared            │ Player-discovered location notes: shops, contacts, layout       │
# │                    │                   │ as the party has explored it.  Written by Notes Agent.          │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ player_quest_log   │ shared            │ Living quest log from the players' perspective.                  │
# │                    │                   │ Appended by Notes Agent after each scene transition.            │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ player_journal     │ shared            │ Free-text player notes / in-character journal entries.          │
# │                    │                   │ Written directly by players; never auto-generated.              │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ world_lore         │ shared            │ Publicly known world lore: history, religions, factions.        │
# │                    │                   │ Written by GM / Storyboard; readable by everyone.               │
# ├────────────────────┼───────────────────┼───────────────────────────────────────────────────────────────┤
# │ core               │ shared            │ General campaign documents (default / catch-all).               │
# └────────────────────┴───────────────────┴───────────────────────────────────────────────────────────────┘
#
# Summary of player information isolation:
#   - Players NEVER see gm_plot, gm_npc, gm_location, gm_notes (visibility=hidden enforced in API).
#   - Players see player_npc documents which contain ONLY the information their character has
#     gathered (appearance, dialogue, relationship) — no stats, motivations, or secrets.
#   - Each NPC encounter creates/updates player_npc alongside the hidden gm_npc.
#   - Quest log (player_quest_log) and journals (player_journal) are player-visible and grow
#     as the campaign progresses; they never contain GM-reserved information.
#   - The GM can always read all categories regardless of visibility setting.
#

#: Categories whose default visibility is "hidden" (GM / host only).
_GM_CATEGORIES: frozenset[str] = frozenset({"gm_plot", "gm_npc", "gm_location", "gm_quest", "gm_notes"})

#: Categories whose default visibility is "shared" (all session members).
_PLAYER_CATEGORIES: frozenset[str] = frozenset({
    "player_npc",
    "player_location",
    "player_quest_log",
    "player_journal",
    "world_lore",
    "core",
})

#: All recognised category strings.
KNOWN_CATEGORIES: frozenset[str] = _GM_CATEGORIES | _PLAYER_CATEGORIES

#: Default visibility per category.  Anything not listed here falls back to "shared".
CATEGORY_DEFAULT_VISIBILITY: dict[str, str] = {
    **{cat: "hidden" for cat in _GM_CATEGORIES},
    **{cat: "shared" for cat in _PLAYER_CATEGORIES},
}


def default_visibility_for_category(category: str) -> str:
    """Return the default visibility for *category*.

    GM categories default to ``"hidden"``; all player / world / core categories
    default to ``"shared"``.  Unknown categories fall back to ``"shared"`` so
    that forward-compatibility is maintained for custom category names.
    """
    return CATEGORY_DEFAULT_VISIBILITY.get(category, "shared")


@dataclass
class DocumentMeta:
    id: str
    session_id: str
    name: str
    category: str = "core"       # see KNOWN_CATEGORIES for valid values
    visibility: str = "shared"   # "shared" = all members | "hidden" = host/GM only
    filename: str = ""
    size: int = 0
    created_at: str = ""
    folder: str = ""             # virtual folder path (e.g. "rules/combat"); empty = root


class DocumentStore:
    def list_documents(self, session_id: str) -> list[DocumentMeta]:
        raise NotImplementedError

    def save_document(self, *, session_id: str, name: str, content: bytes | str, filename: str | None = None, category: str = "core", visibility: str = "shared", folder: str = "") -> DocumentMeta:
        raise NotImplementedError

    def delete_document(self, session_id: str, doc_id: str) -> bool:
        raise NotImplementedError

    def read_document(self, session_id: str, doc_id: str) -> tuple[DocumentMeta, str] | None:
        raise NotImplementedError

    def generate_presigned_post(self, session_id: str, filename: str, content_type: str | None = None, expires_in: int = 3600) -> dict:
        raise NotImplementedError

    def register_existing_object(self, session_id: str, filename: str, name: str, size: int, category: str = "core", visibility: str = "shared", folder: str = "") -> DocumentMeta:
        raise NotImplementedError

    def generate_presigned_get_url(self, session_id: str, filename: str, expires_in: int = 3600) -> str:
        raise NotImplementedError

    def list_folders(self, session_id: str) -> list[str]:
        return []

    def create_folder(self, session_id: str, folder_path: str) -> bool:
        return True

    def delete_folder(self, session_id: str, folder_path: str) -> bool:
        return True

    def move_document(self, session_id: str, doc_id: str, folder: str) -> DocumentMeta | None:
        return None


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

    def _load_meta(self, session_id: str) -> list[DocumentMeta]:
        meta_path = self._meta_file(session_id)
        if not meta_path.exists():
            return []
        data = json.loads(meta_path.read_text())
        # Filter to known fields for forward-compatible schema evolution
        _fields = set(DocumentMeta.__dataclass_fields__)
        return [DocumentMeta(**{k: v for k, v in entry.items() if k in _fields}) for entry in data]

    def _write_meta(self, session_id: str, entries: list[DocumentMeta]) -> None:
        meta_path = self._meta_file(session_id)
        meta_path.write_text(json.dumps([asdict(entry) for entry in entries], indent=2))

    def list_documents(self, session_id: str) -> list[DocumentMeta]:
        return self._load_meta(session_id)

    def save_document(self, *, session_id: str, name: str, content: bytes | str, filename: str | None = None, category: str = "core", visibility: str = "shared", folder: str = "") -> DocumentMeta:
        doc_id = uuid.uuid4().hex[:8]
        session_dir = self._session_dir(session_id)
        # If client provided a filename, preserve its extension
        if filename:
            ext = Path(filename).suffix or '.dat'
            stored_name = f"{doc_id}{ext}"
        else:
            stored_name = f"{doc_id}.txt"
        target = session_dir / stored_name
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
            folder=folder.strip('/'),
        )
        meta.append(created)
        self._write_meta(session_id, meta)
        return created

    def register_existing_object(self, session_id: str, filename: str, name: str, size: int, category: str = "core", visibility: str = "shared", folder: str = "") -> DocumentMeta:
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
            folder=folder.strip('/') if folder else '',
        )
        meta.append(created)
        self._write_meta(session_id, meta)
        return created

    def delete_document(self, session_id: str, doc_id: str) -> bool:
        folder = self._session_dir(session_id)
        meta = self._load_meta(session_id)
        remaining: list[DocumentMeta] = []
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

    def read_document(self, session_id: str, doc_id: str) -> tuple[DocumentMeta, str] | None:
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

    def _folders_file(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "folders.json"

    def _load_folders(self, session_id: str) -> list[str]:
        f = self._folders_file(session_id)
        if not f.exists():
            return []
        try:
            return json.loads(f.read_text())
        except Exception:
            return []

    def _write_folders(self, session_id: str, folders: list[str]) -> None:
        self._folders_file(session_id).write_text(json.dumps(sorted(set(folders)), indent=2))

    def list_folders(self, session_id: str) -> list[str]:
        stored = self._load_folders(session_id)
        doc_folders = {d.folder for d in self._load_meta(session_id) if d.folder}
        return sorted(set(stored) | doc_folders)

    def create_folder(self, session_id: str, folder_path: str) -> bool:
        clean = folder_path.strip('/')
        if not clean:
            return False
        folders = self._load_folders(session_id)
        if clean not in folders:
            folders.append(clean)
            self._write_folders(session_id, folders)
        return True

    def delete_folder(self, session_id: str, folder_path: str) -> bool:
        clean = folder_path.strip('/')
        docs = self._load_meta(session_id)
        if any(
            d.folder == clean or (d.folder or '').startswith(clean + '/')
            for d in docs
        ):
            return False
        folders = [
            f for f in self._load_folders(session_id)
            if f != clean and not f.startswith(clean + '/')
        ]
        self._write_folders(session_id, folders)
        return True

    def move_document(self, session_id: str, doc_id: str, folder: str) -> DocumentMeta | None:
        clean = folder.strip('/')
        meta = self._load_meta(session_id)
        for i, doc in enumerate(meta):
            if doc.id == doc_id:
                updated = DocumentMeta(
                    id=doc.id,
                    session_id=doc.session_id,
                    name=doc.name,
                    category=doc.category,
                    visibility=doc.visibility,
                    filename=doc.filename,
                    size=doc.size,
                    created_at=doc.created_at,
                    folder=clean,
                )
                meta[i] = updated
                self._write_meta(session_id, meta)
                return updated
        return None

    def generate_presigned_get_url(self, session_id: str, filename: str, expires_in: int = 3600) -> str:
        raise NotImplementedError


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

    def list_documents(self, session_id: str) -> list[DocumentMeta]:
        key = self._meta_key(session_id)
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            body = resp['Body'].read()
            entries = json.loads(body)
            return [DocumentMeta(**e) for e in entries]
        except Exception:
            return []

    def save_document(self, *, session_id: str, name: str, content: bytes | str, filename: str | None = None, category: str = "core", visibility: str = "shared") -> DocumentMeta:
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

    def read_document(self, session_id: str, doc_id: str) -> tuple[DocumentMeta, str] | None:
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

    def generate_presigned_get_url(self, session_id: str, filename: str, expires_in: int = 3600) -> str:
        key = self._object_key(session_id, filename)
        return self.s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': self.bucket, 'Key': key},
            ExpiresIn=expires_in,
        )


class NullDocumentStore(DocumentStore):
    def list_documents(self, session_id: str) -> list[DocumentMeta]:  # pragma: no cover - placeholder
        return []

    def save_document(self, *, session_id: str, name: str, content: bytes | str, filename: str | None = None, category: str = "core", visibility: str = "shared") -> DocumentMeta:  # pragma: no cover - placeholder
        raise NotImplementedError("S3 storage not configured")

    def delete_document(self, session_id: str, doc_id: str) -> bool:  # pragma: no cover - placeholder
        raise NotImplementedError("S3 storage not configured")

    def read_document(self, session_id: str, doc_id: str) -> tuple[DocumentMeta, str] | None:  # pragma: no cover - placeholder
        raise NotImplementedError("S3 storage not configured")


_store: DocumentStore | None = None


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
