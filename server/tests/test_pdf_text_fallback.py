"""A scanned PDF with no OCR is reported as unreadable, never decoded as text."""
from __future__ import annotations

import io
import stat

import pytest
from PIL import Image

import server.main  # noqa: F401  (import order)
from server.agents.characters import _read_pdf_text


def _scanned_pdf() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(buf, "PDF")
    return buf.getvalue()


def test_scan_without_ocr_returns_none_not_pdf_bytes(monkeypatch):
    monkeypatch.setenv("TAVERNTAILS_ENABLE_OCR", "0")
    assert _read_pdf_text(_scanned_pdf()) is None


def test_scan_with_missing_tesseract_returns_none(monkeypatch):
    monkeypatch.setenv("TAVERNTAILS_ENABLE_OCR", "1")
    monkeypatch.setenv("TAVERNTAILS_TESSERACT_CMD", "/nonexistent/tesseract")
    assert _read_pdf_text(_scanned_pdf()) is None


@pytest.mark.skipif(not __import__("shutil").which("pdftoppm"), reason="pdftoppm not installed")
def test_scan_text_comes_from_the_ocr_command(monkeypatch, tmp_path):
    stub = tmp_path / "tesseract"
    stub.write_text('#!/bin/sh\n[ -s "$1" ] || exit 1\necho "Valeros Fighter Level 5"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("TAVERNTAILS_ENABLE_OCR", "1")
    monkeypatch.setenv("TAVERNTAILS_TESSERACT_CMD", str(stub))
    assert "Valeros Fighter Level 5" in (_read_pdf_text(_scanned_pdf()) or "")


def test_plain_text_upload_still_decodes():
    assert _read_pdf_text(b"Name: Valeros\nClass: Fighter") == "Name: Valeros\nClass: Fighter"


def test_spell_text_heuristic_ignores_form_labels():
    from server.agents.characters import _extract_spells_from_text

    page = "ATTACKS & SPELLCASTING\nAcrobatics (Dex)\nArcana (Int)\nFEATURES & TRAITS\nSTRENGTH\nCANTRIPS\nFire Bolt\nMage Hand"
    assert _extract_spells_from_text(page) == ["Fire Bolt", "Mage Hand"]


def test_inline_feature_lines_split_into_name_and_description():
    from server.agents.characters import _inline_feature

    assert _inline_feature("Darkvision: See in dim light within 60 feet.") == {
        "name": "Darkvision", "source": None, "description": "See in dim light within 60 feet.",
    }
    assert _inline_feature("Source: Player's Handbook page 114") is None  # metadata, not a feature
    assert _inline_feature("Fey Ancestry") is None
