import json
import asyncio
from types import SimpleNamespace
from pathlib import Path

from server.agents import references


def test_search_tfidf_fallback(tmp_path, monkeypatch):
    root = tmp_path / "references"
    root.mkdir()
    d = root / "testref"
    d.mkdir()
    pages = [
        {"page": 1, "text": "The fireball spell deals 8d6 fire damage in an area.", "snippet": "fireball deals 8d6 fire damage"},
        {"page": 2, "text": "Short rest: spend hit dice to recover HP.", "snippet": "Short rest rules"},
    ]
    (d / "pages.json").write_text(json.dumps(pages), encoding="utf-8")
    meta = {"title": "Test Reference", "filename": "testref.pdf", "pages": len(pages)}
    (d / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    # Point the module storage root at our temp dir
    monkeypatch.setattr(references, "_storage_root", lambda: root)

    results = references.search_query("fireball", top_k=3)
    assert isinstance(results, list)
    assert len(results) >= 1
    assert results[0]["source_id"] == "testref"


def test_list_references(tmp_path, monkeypatch):
    root = tmp_path / "references"
    root.mkdir()
    d = root / "refA"
    d.mkdir()
    meta = {"title": "Ref A", "filename": "a.pdf", "pages": 1}
    (d / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    monkeypatch.setattr(references, "_storage_root", lambda: root)

    # list_references is async; run it
    current_user = SimpleNamespace(email='tester@example.com', username='tester')
    out = asyncio.run(references.list_references(current_user=current_user))
    assert isinstance(out, list)
    assert any(item.get("id") == "refA" for item in out)
