import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

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
    current_user = SimpleNamespace(email='tester@example.com', username='tester', profile=None, role='player')
    out = asyncio.run(references.list_references(current_user=current_user))
    assert isinstance(out, list)
    assert any(item.get("id") == "refA" for item in out)


# ---------------------------------------------------------------------------
# Tests for multi-format text extraction
# ---------------------------------------------------------------------------

def test_extract_txt(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("Tavern rules:\n1. No fighting.\n2. Pay your tab.", encoding="utf-8")
    chunks = references._extract_pages_text(f)
    assert len(chunks) >= 1
    assert "Tavern rules" in chunks[0]


def test_extract_markdown(tmp_path):
    f = tmp_path / "readme.md"
    f.write_text("# Campaign Notes\n\nThe dark forest is dangerous.", encoding="utf-8")
    chunks = references._extract_pages_text(f)
    assert len(chunks) >= 1
    assert "Campaign Notes" in chunks[0]


def test_extract_html(tmp_path):
    f = tmp_path / "lore.html"
    f.write_text(
        "<html><body><h1>World Lore</h1><p>The realm was created eons ago.</p>"
        "<script>alert('ignored')</script></body></html>",
        encoding="utf-8",
    )
    chunks = references._extract_pages_text(f)
    assert len(chunks) >= 1
    text = chunks[0]
    assert "World Lore" in text
    assert "realm" in text
    assert "alert" not in text  # script content must be stripped


def test_extract_json(tmp_path):
    data = {"name": "Dragon", "hp": 300, "abilities": ["fire breath", "fly"]}
    f = tmp_path / "monster.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    chunks = references._extract_pages_text(f)
    assert len(chunks) >= 1
    assert "Dragon" in chunks[0]


def test_extract_csv(tmp_path):
    f = tmp_path / "items.csv"
    f.write_text("Name,Type,Cost\nSword,Weapon,15gp\nShield,Armor,10gp", encoding="utf-8")
    chunks = references._extract_pages_text(f)
    assert len(chunks) >= 1
    assert "Sword" in chunks[0]


def test_extract_docx(tmp_path):
    import docx  # python-docx

    doc_path = tmp_path / "adventure.docx"
    doc = docx.Document()
    doc.add_paragraph("Chapter 1: The Beginning")
    doc.add_paragraph("The hero set out on a quest for glory.")
    doc.save(str(doc_path))

    chunks = references._extract_pages_text(doc_path)
    assert len(chunks) >= 1
    assert "hero" in chunks[0]


def test_extract_xlsx(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Treasure"
    ws.append(["Item", "Value"])
    ws.append(["Gold Ring", "50gp"])
    wb.save(str(tmp_path / "treasure.xlsx"))

    chunks = references._extract_pages_text(tmp_path / "treasure.xlsx")
    assert len(chunks) >= 1
    assert "Gold Ring" in chunks[0]


def test_supported_extensions_set():
    """Ensure all expected formats are present in the supported set."""
    expected = {".pdf", ".txt", ".md", ".csv", ".json", ".html", ".htm", ".docx", ".doc", ".xlsx", ".xls"}
    assert expected.issubset(references.SUPPORTED_EXTENSIONS), (
        f"Missing extensions: {expected - references.SUPPORTED_EXTENSIONS}"
    )
