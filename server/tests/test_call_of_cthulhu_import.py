"""Call of Cthulhu (CoC 7e) PDF character sheet import tests.

These tests exercise the CoC-specific import path in ``server/agents/characters.py``
using a dedicated ``coc-import@example.com`` test user and a synthetic fixture PDF
that mirrors the Roland Carmichael character (a 1920s private investigator).

The CoC schema is distinct from D&D 5e:
- **Characteristics**: STR/CON/SIZ/DEX/APP/INT/POW/EDU (percentile, 15–99)
- **Derived stats**: HP (CON+SIZ/10), Magic Points (POW/5), Sanity (POW×5), Luck
- **Skills**: percentile integers (no proficiency bonus system)
- **Occupation**: replaces D&D class (no level system)
- **CoC-namespaced keys**: magic_points, sanity, luck, characteristics — never
  overloading D&D hp, class, or other shared schema fields

Both seed users (bilbo@example.com and admin@example.com) have characters imported
via the ``seed_call_of_cthulhu_characters`` script.
"""
from __future__ import annotations

import io
import os

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token

# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_sta_import.py conventions)
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str, username: str | None = None) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    uname = username or email.split("@")[0]
    user = db.create_user(
        email=email,
        password="secret",
        username=uname,
        profile={"name": uname, "email": email},
    )
    db.verify_user(email, user.verification_token)


# ---------------------------------------------------------------------------
# PDF builder helper
# ---------------------------------------------------------------------------


def _make_coc_pdf(fields: dict) -> bytes:
    """Build a minimal PDF containing CoC widget annotations (interactive form fields).

    Each key becomes the widget /T (field name) and each value becomes its /V (field value).
    """
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    y = 750.0
    for field_name, value in fields.items():
        annot = DictionaryObject()
        annot.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(field_name),
                NameObject("/V"): TextStringObject(str(value)),
                NameObject("/Rect"): ArrayObject(
                    [FloatObject(50.0), FloatObject(y), FloatObject(400.0), FloatObject(y + 20.0)]
                ),
            }
        )
        ref = writer._add_object(annot)  # noqa: SLF001
        annots = page.get("/Annots")
        if annots is None:
            page[NameObject("/Annots")] = ArrayObject([ref])
        else:
            annots.append(ref)
        y -= 22.0

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)
    return bio.read()


# ---------------------------------------------------------------------------
# Roland Carmichael fixture — canonical expected values
# ---------------------------------------------------------------------------

_ROLAND_FIELDS: dict[str, str] = {
    # Identity
    "Investigator Name": "Roland Carmichael",
    "Occupation": "Private Investigator",
    "Age": "38",
    "Residence": "Boston",
    "Birthplace": "Providence, RI",
    # Characteristics (percentile)
    "STR": "60",
    "CON": "65",
    "SIZ": "65",
    "DEX": "55",
    "APP": "50",
    "INT": "80",
    "POW": "65",
    "EDU": "75",
    # Derived stats
    "Hit Points": "13",
    "Hit Points Max": "13",
    "Magic Points": "13",
    "Magic Points Max": "13",
    "Sanity Points": "65",
    "Sanity Points Max": "65",
    "Luck": "55",
    # Skills (percentile)
    "Spot Hidden": "65",
    "Library Use": "70",
    "Psychology": "55",
    "Fast Talk": "45",
    "Firearms": "45",
    "Cthulhu Mythos": "5",
    # Background
    "Background": "A seasoned investigator from Boston, Roland has seen too much to sleep soundly.",
}

_COC_USER_EMAIL = "coc-import@example.com"


def _auth_headers(email: str = _COC_USER_EMAIL) -> dict:
    _ensure_user(email)
    token = create_access_token(email)
    return {"Authorization": f"Bearer {token}"}


def _import_roland(client: TestClient, email: str = _COC_USER_EMAIL) -> dict:
    """POST the Roland Carmichael PDF and return the full response JSON."""
    pdf_bytes = _make_coc_pdf(_ROLAND_FIELDS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=_auth_headers(email),
        files={"file": ("roland.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# 1. System detection
# ---------------------------------------------------------------------------


def test_coc_pdf_import_detects_call_of_cthulhu_system():
    """System detection identifies the sheet as Call of Cthulhu."""
    client = _client()
    data = _import_roland(client)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Call of Cthulhu"


# ---------------------------------------------------------------------------
# 2. Character name
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_character_name():
    """Roland's name is extracted from the 'Investigator Name' widget."""
    client = _client()
    data = _import_roland(client)
    assert data["character"]["name"] == "Roland Carmichael"


# ---------------------------------------------------------------------------
# 3. Characteristics extraction
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_all_eight_characteristics():
    """All eight CoC characteristics are stored under sheet['characteristics']."""
    client = _client()
    data = _import_roland(client)
    chars = data["character"]["sheet"]["characteristics"]
    assert chars["str"] == 60
    assert chars["con"] == 65
    assert chars["siz"] == 65
    assert chars["dex"] == 55
    assert chars["app"] == 50
    assert chars["int"] == 80
    assert chars["pow"] == 65
    assert chars["edu"] == 75


# ---------------------------------------------------------------------------
# 4. Derived stats: HP
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_hit_points():
    """HP current and max are stored under sheet['hp'] (CoC-derived, not D&D)."""
    client = _client()
    data = _import_roland(client)
    hp = data["character"]["sheet"]["hp"]
    assert hp["current"] == 13
    assert hp["max"] == 13


# ---------------------------------------------------------------------------
# 5. Derived stats: Magic Points (CoC-specific)
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_magic_points():
    """Magic Points are stored under sheet['magic_points'] — CoC-namespaced, not 'hp'."""
    client = _client()
    data = _import_roland(client)
    mp = data["character"]["sheet"]["magic_points"]
    assert mp["current"] == 13
    assert mp["max"] == 13


# ---------------------------------------------------------------------------
# 6. Derived stats: Sanity (CoC-specific)
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_sanity():
    """Sanity current and max are stored under sheet['sanity'] — CoC-namespaced."""
    client = _client()
    data = _import_roland(client)
    san = data["character"]["sheet"]["sanity"]
    assert san["current"] == 65
    assert san["max"] == 65


# ---------------------------------------------------------------------------
# 7. Derived stats: Luck (CoC-specific)
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_luck():
    """Luck is stored under sheet['luck'] as a plain integer — CoC-namespaced."""
    client = _client()
    data = _import_roland(client)
    assert data["character"]["sheet"]["luck"] == 55


# ---------------------------------------------------------------------------
# 8. Skills (percentile)
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_skills_as_percentages():
    """Skills are extracted as percentile integers under sheet['skills']."""
    client = _client()
    data = _import_roland(client)
    skills = data["character"]["sheet"]["skills"]
    assert skills["Spot Hidden"] == 65
    assert skills["Library Use"] == 70
    assert skills["Psychology"] == 55
    assert skills["Fast Talk"] == 45
    assert skills["Cthulhu Mythos"] == 5


# ---------------------------------------------------------------------------
# 9. Occupation (replaces D&D class)
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_occupation():
    """Occupation is stored in sheet['occupation'] and mapped to top-level class_name."""
    client = _client()
    data = _import_roland(client)
    sheet = data["character"]["sheet"]
    assert sheet["occupation"] == "Private Investigator"
    # class_name at the character level should also be populated from occupation
    assert data["character"]["class_name"] == "Private Investigator"


# ---------------------------------------------------------------------------
# 10. Background
# ---------------------------------------------------------------------------


def test_coc_pdf_import_extracts_background():
    """Background text is stored under sheet['background']."""
    client = _client()
    data = _import_roland(client)
    sheet = data["character"]["sheet"]
    background = sheet.get("background", "")
    assert "Roland" in background or "investigator" in background.lower(), (
        f"Expected background to mention 'Roland' or 'investigator', got: {background!r}"
    )
    assert len(background) > 20, f"Background text is suspiciously short: {background!r}"


# ---------------------------------------------------------------------------
# 11. Import source metadata
# ---------------------------------------------------------------------------


def test_coc_pdf_import_source_metadata():
    """Import source is 'pdf' and system name is 'Call of Cthulhu'."""
    client = _client()
    data = _import_roland(client)
    sheet = data["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "Call of Cthulhu"


# ---------------------------------------------------------------------------
# 12. Preview endpoint — does not persist
# ---------------------------------------------------------------------------


def test_coc_pdf_preview_returns_structure_without_persisting():
    """Preview endpoint returns CoC structure but does NOT create a character."""
    client = _client()
    preview_email = "coc-preview@example.com"
    _ensure_user(preview_email)
    token = create_access_token(preview_email)
    headers = {"Authorization": f"Bearer {token}"}
    pdf_bytes = _make_coc_pdf(_ROLAND_FIELDS)

    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("roland_preview.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["name"] == "Roland Carmichael"
    assert preview["sheet"]["system"]["name"] == "Call of Cthulhu"
    assert "characteristics" in preview["sheet"]

    # Verify the character was NOT persisted
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    assert "Roland Carmichael" not in names


# ---------------------------------------------------------------------------
# 13. Seed user imports (bilbo@example.com and admin@example.com)
# ---------------------------------------------------------------------------


def test_coc_import_for_bilbo_seed_user():
    """bilbo@example.com can import a CoC sheet and it is persisted."""
    client = _client()
    bilbo_email = "bilbo@example.com"
    _ensure_user(bilbo_email, "BilboBaggins")
    data = _import_roland(client, bilbo_email)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Call of Cthulhu"
    assert data["character"]["name"] == "Roland Carmichael"
    assert "characteristics" in sheet


def test_coc_import_for_admin_seed_user():
    """admin@example.com can import a CoC sheet and it is persisted."""
    client = _client()
    admin_email = "admin@example.com"
    _ensure_user(admin_email, "Admin")
    data = _import_roland(client, admin_email)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Call of Cthulhu"
    assert data["character"]["name"] == "Roland Carmichael"
    assert "characteristics" in sheet


# ---------------------------------------------------------------------------
# 14. Smoke test: real fixture PDF
# ---------------------------------------------------------------------------


def test_coc_real_fixture_pdf_smoke():
    """Real fixture PDF (investigator.pdf) imports without error and detects CoC."""
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "call_of_cthulhu", "investigator.pdf")
    if not os.path.exists(fixture_path):
        import pytest

        pytest.skip("investigator.pdf fixture not found — run generate_investigator.py to create it")

    client = _client()
    headers = _auth_headers()
    with open(fixture_path, "rb") as f:
        pdf_bytes = f.read()

    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("investigator.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Call of Cthulhu"
    assert data["character"]["name"] == "Roland Carmichael"
    assert "characteristics" in sheet
