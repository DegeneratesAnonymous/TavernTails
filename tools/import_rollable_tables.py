#!/usr/bin/env python3
"""Index rollable-table PDFs so TavernTails can roll on them.

Usage: python tools/import_rollable_tables.py [SOURCE_DIR] [--no-ocr]
Defaults to server/storage/rollable_tables/source.  Needs poppler (``pdftotext``, ``pdftoppm``).
Scanned PDFs are read through Steward's OCR nodes (STEWARD_HOST, default http://127.0.0.1:5555).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.agents.rollable_tables import DEFAULT_INDEX, SOURCE_DIR, build_index  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", default=SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--no-ocr", action="store_true", help="skip scanned PDFs instead of OCRing them")
    args = parser.parse_args()
    os.environ.setdefault("STEWARD_HOST", "http://127.0.0.1:5555")  # Steward brokers the OCR nodes
    if not args.source.is_dir():
        parser.error(f"source directory does not exist: {args.source}")
    def progress(page: int, total: int) -> None:
        if page % 25 == 0 or page == total:
            print(f"  OCR page {page}/{total}", file=sys.stderr, flush=True)

    result = build_index(args.source, args.output, ocr=not args.no_ocr, progress=progress)
    print(json.dumps({k: result[k] for k in ("pdf_count", "table_count", "entry_count", "sources", "errors")}, indent=2))
