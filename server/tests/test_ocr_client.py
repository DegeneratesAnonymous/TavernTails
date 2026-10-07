"""Scanned pages are read by Steward's OCR nodes first, then by a local tesseract command."""
from __future__ import annotations

import stat

import httpx
import pytest

import server.main  # noqa: F401  (import order: sessions before narrative)
from server import ocr_client

TSV = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
       "5\t1\t1\t1\t1\t1\t100\t100\t60\t30\t90\tHP\n5\t1\t1\t1\t1\t2\t300\t102\t60\t30\t90\t27\n")


class _Reply:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "page-1.png"
    path.write_bytes(b"PNG")
    return str(path)


@pytest.fixture
def stub(tmp_path):
    """A local tesseract stand-in that answers TSV for `tsv` and plain text otherwise."""
    script = tmp_path / "tesseract"
    script.write_text('#!/bin/sh\nif echo "$*" | grep -q tsv; then printf "$TSV_OUT"; else echo "LOCAL plain text"; fi\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


def test_remote_ocr_is_used_when_steward_is_configured(monkeypatch, image):
    monkeypatch.setenv("STEWARD_HOST", "http://steward:5555")
    seen = {}

    def post(url, params, content, **kw):
        seen.update(url=url, params=params, content=content)
        return _Reply(200, {"text": TSV, "host": "http://pc:8766"})

    monkeypatch.setattr(httpx, "post", post)
    text = ocr_client.read_page(image, "/nonexistent/tesseract")
    assert seen["url"] == "http://steward:5555/api/games/taverntails/ocr"
    assert seen["params"] == {"psm": 11, "format": "tsv"} and seen["content"] == b"PNG"
    assert text.split() == ["HP", "27"]  # rebuilt onto one line by position


def test_falls_back_to_the_local_command_when_no_node_answers(monkeypatch, image, stub):
    monkeypatch.setenv("STEWARD_HOST", "http://steward:5555")
    monkeypatch.setenv("TSV_OUT", TSV.replace("\n", "\\n"))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Reply(503, {"error": "ocr_unavailable"}))
    assert ocr_client.read_page(image, stub).split() == ["HP", "27"]


def test_remote_errors_do_not_raise(monkeypatch, image):
    monkeypatch.setenv("STEWARD_HOST", "http://steward:5555")

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    assert ocr_client.read_page(image, "/nonexistent/tesseract") == ""


def test_remote_can_be_switched_off(monkeypatch, image, stub):
    monkeypatch.setenv("STEWARD_HOST", "http://steward:5555")
    monkeypatch.setenv("TAVERNTAILS_OCR_REMOTE", "0")
    monkeypatch.setenv("TSV_OUT", TSV.replace("\n", "\\n"))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("remote OCR must not be called"))
    assert ocr_client.read_page(image, stub).split() == ["HP", "27"]


def test_without_steward_the_local_command_reads_the_page(monkeypatch, image, stub):
    monkeypatch.delenv("STEWARD_HOST", raising=False)
    monkeypatch.setenv("TSV_OUT", TSV.replace("\n", "\\n"))
    assert ocr_client.read_page(image, stub).split() == ["HP", "27"]


def test_pages_are_read_in_parallel_and_returned_in_order(monkeypatch, tmp_path):
    monkeypatch.setenv("STEWARD_HOST", "http://steward:5555")
    paths = []
    for n in range(5):
        p = tmp_path / f"page-{n}.png"
        p.write_bytes(bytes([n]))
        paths.append(str(p))

    def post(url, params, content, **kw):
        n = content[0]
        return _Reply(200, {"text": TSV.replace("27", str(n)), "host": "x"})

    monkeypatch.setattr(httpx, "post", post)
    pages = ocr_client.read_pages(paths)
    assert [p.split()[-1] for p in pages] == ["0", "1", "2", "3", "4"]


def test_one_unreadable_page_does_not_lose_the_others(monkeypatch, tmp_path):
    monkeypatch.setenv("STEWARD_HOST", "http://steward:5555")
    good, bad = tmp_path / "page-1.png", tmp_path / "page-2.png"
    good.write_bytes(b"1")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Reply(200, {"text": TSV}))
    pages = ocr_client.read_pages([str(good), str(bad)])  # `bad` does not exist
    assert pages[0].split() == ["HP", "27"] and pages[1] == ""
