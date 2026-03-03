"""Generate the Ja'pel STA fixture PDF for the star_trek_adventures fixture directory.

Run from the repo root::

    python server/tests/fixtures/star_trek_adventures/generate_japel.py

The resulting ``japelsta.pdf`` is used by
``test_star_trek_adventures_import.py::test_sta_committed_fixture_pdf_imports_correctly``
as a filesystem smoke test.  The main test suite generates PDFs in-memory so
CI passes without this file present; the smoke test skips gracefully when absent.

Re-run whenever the expected field values change.
"""
import io
import os
import sys

# Allow running from the repo root or from this directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from server.scripts.seed_star_trek_adventures_characters import build_japel_pdf  # noqa: E402

if __name__ == "__main__":
    out_path = os.path.join(os.path.dirname(__file__), "japelsta.pdf")
    pdf_bytes = build_japel_pdf()
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written {len(pdf_bytes)} bytes to {out_path}")
