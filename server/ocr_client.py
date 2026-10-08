"""Read scanned pages: Steward's OCR nodes first, a local tesseract command as the fallback.

This server runs on a small board with no OCR engine.  Steward, which already brokers every model call for
TavernTails (``STEWARD_HOST``), forwards each page image to an OCR node (ColemanPC, then HeatherPC) and
returns tesseract's word table.  Pages are read in parallel so both nodes work at once.  When Steward is
not configured or no node answers, the local ``TAVERNTAILS_TESSERACT_CMD`` is used; with neither, the page
reads as empty and the caller treats the PDF as unreadable.
"""
from __future__ import annotations

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .agents.ocr_sheet import layout_text

log = logging.getLogger("taverntails.ocr")
PAGE_WORKERS = 3
REMOTE_TIMEOUT = 180.0


def remote_enabled() -> bool:
    return bool(os.environ.get("STEWARD_HOST")) and os.environ.get("TAVERNTAILS_OCR_REMOTE", "1") != "0"


def _remote(image: bytes, fmt: str, psm: int = 11) -> str | None:
    """One page read by a Steward OCR node, or ``None`` when no node could."""
    url = os.environ["STEWARD_HOST"].rstrip("/") + "/api/games/taverntails/ocr"
    try:
        reply = httpx.post(url, params={"psm": psm, "format": fmt}, content=image, timeout=REMOTE_TIMEOUT,
                           headers={"Content-Type": "application/octet-stream"})
    except httpx.HTTPError as exc:
        log.warning("remote OCR unreachable: %s", type(exc).__name__)
        return None
    if reply.status_code != 200:
        log.warning("remote OCR returned %s", reply.status_code)
        return None
    text = reply.json().get("text")
    return text if isinstance(text, str) else None


def _local(path: str, tesseract_cmd: str, fmt: str) -> str:
    args = [tesseract_cmd, path, "stdout"] + (["--psm", "11", "tsv"] if fmt == "tsv" else [])
    return subprocess.run(args, check=True, capture_output=True).stdout.decode("utf-8", errors="ignore")


def read_page(path: str, tesseract_cmd: str = "tesseract") -> str:
    """The page's text with each word kept on the line of its label; plain text when positions are unavailable."""
    image = Path(path).read_bytes() if remote_enabled() else b""
    for fmt in ("tsv", "text"):
        raw = _remote(image, fmt) if remote_enabled() else None
        if raw is None:
            try:
                raw = _local(path, tesseract_cmd, fmt)
            except (OSError, subprocess.CalledProcessError):
                raw = ""
        text = layout_text(raw) if fmt == "tsv" else raw
        if text.strip():
            return text
    return ""


def read_pages(paths: list[str], tesseract_cmd: str = "tesseract") -> list[str]:
    """Every page's text in page order, reading pages in parallel; an unreadable page is empty."""
    def one(path: str) -> str:
        try:
            return read_page(path, tesseract_cmd)
        except Exception:  # noqa: BLE001 - one bad page must not lose the others
            log.exception("OCR failed for %s", path)
            return ""

    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as pool:
        return list(pool.map(one, paths))
