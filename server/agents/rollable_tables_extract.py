"""Extract numbered random tables from text-layer PDFs.

The books lay tables out as a gutter of die results (``1``, ``2-3``, ``12``)
with the result text to its right, often in several side-by-side columns.
Reading order from plain text extraction scrambles that, so this works from
word coordinates (``pdftotext -bbox-layout``) and keeps a table only when its
gutter forms a believable die sequence (1..N, or contiguous ranges).
"""
from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path
from typing import Any, Iterator

_PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
_WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>')
_NUM = re.compile(r"^(\d{1,3})(?:\s*[-–—]\s*(\d{1,3}))?$")
_DIE = re.compile(r"^(?:\d{0,2})d(4|6|8|10|12|20|66|100|%)$", re.I)
_DICE_SIZES = (4, 6, 8, 10, 12, 20, 30, 40, 50, 100)
_X_TOL = 4.0


def _words(pdf: Path, first: int | None = None, last: int | None = None) -> Iterator[tuple[int, float, float, list[tuple[float, float, float, float, str]]]]:
    cmd = ["pdftotext", "-bbox-layout"]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    cmd += [str(pdf), "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=900)
    page_no = (first or 1) - 1
    for match in _PAGE.finditer(proc.stdout):
        page_no += 1
        words = [
            (float(a), float(b), float(c), float(d), html.unescape(text))
            for a, b, c, d, text in _WORD.findall(match.group(3))
        ]
        yield page_no, float(match.group(1)), float(match.group(2)), words


def _parse_num(text: str) -> tuple[int, int] | None:
    m = _NUM.match(text.strip())
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if hi < lo:
        return None
    return lo, hi


def _gutter_candidates(words: list[tuple]) -> list[list[tuple]]:
    """Group numeric words into vertical stacks sharing a right edge."""
    nums = [w for w in words if _parse_num(w[4])]
    stacks: list[list[tuple]] = []
    for w in sorted(nums, key=lambda w: (round(w[2] / _X_TOL), w[1])):
        for stack in stacks:
            if abs(stack[-1][2] - w[2]) <= _X_TOL and w[1] >= stack[-1][1]:
                stack.append(w)
                break
        else:
            stacks.append([w])
    return stacks


def _runs(stack: list[tuple]) -> list[list[tuple]]:
    """Maximal stretches of a gutter that count up (each row starts where the last ended)."""
    runs: list[list[tuple]] = []
    run: list[tuple] = []
    for w in stack:
        lo, hi = _parse_num(w[4])  # type: ignore[misc]
        prev_hi = _parse_num(run[-1][4])[1] if run else None  # type: ignore[index]
        if run and lo == prev_hi + 1:  # type: ignore[operator]
            run.append(w)
            continue
        if run:
            runs.append(run)
        run = [w]
    if run:
        runs.append(run)
    return runs


def _plausible_die(first_lo: int, last_hi: int, count: int) -> bool:
    if first_lo not in (0, 1):
        return False
    if last_hi in (4, 6, 8, 10, 12, 20, 30, 100):
        return count >= 4
    return count >= 6 and last_hi in (14, 16, 18, 24, 36, 66)


def _segments(words: list[tuple], gap: float = 14.0) -> list[list[tuple]]:
    segs: list[list[tuple]] = []
    for w in sorted(words, key=lambda w: w[0]):
        if segs and w[0] - segs[-1][-1][2] <= gap:
            segs[-1].append(w)
        else:
            segs.append([w])
    return segs


def _lines(words: list[tuple], anchor_x: float | None = None, line_tol: float = 2.5) -> list[dict[str, Any]]:
    """Group words into text lines; with anchor_x keep only the segment beside the gutter."""
    out: list[dict[str, Any]] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        mid = (w[1] + w[3]) / 2
        if out and abs(out[-1]["mid"] - mid) <= line_tol:
            out[-1]["words"].append(w)
        else:
            out.append({"mid": mid, "words": [w]})
    kept = []
    for line in out:
        ws = line["words"]
        if anchor_x is not None:
            segs = _segments(ws)
            near = [s for s in segs if s[0][0] - anchor_x <= 60]
            if not near:
                continue
            ws = min(near, key=lambda s: abs(s[0][0] - anchor_x))
        line["words"] = sorted(ws, key=lambda w: w[0])
        line["x0"] = line["words"][0][0]
        line["height"] = max(w[3] - w[1] for w in line["words"])
        kept.append(line)
    return kept


def _join(words: list[tuple]) -> str:
    text = " ".join(w[4] for w in words)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"(\w)- (\w)", r"\1-\2", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _line_text(line: dict[str, Any]) -> str:
    return _join(line["words"])


def _starts_row(prev: str, cur: str) -> float:
    score = 0.0
    if prev.rstrip().endswith((".", "!", "?", "”", '"', ")", "…", ":")):
        score += 2.0
    elif prev.rstrip().endswith("-"):
        score -= 2.0
    if cur[:1].isupper() or cur.startswith(("...", "…", "“", '"', "(", "•")) or cur[:1].isdigit():
        score += 2.0
    elif cur[:1].islower():
        score -= 2.0
    return score


def _extract_columns(seq: list[tuple], words: list[tuple], page_w: float, *, x_lo: float | None = None, x_hi: float | None = None, tol: float = _X_TOL) -> dict[str, Any] | None:
    gx = max(w[2] for w in seq)
    left_x = min(w[0] for w in seq)
    mids = [(w[1] + w[3]) / 2 for w in seq]
    row_h = (mids[-1] - mids[0]) / max(1, len(mids) - 1)
    left = gx + 0.5 if x_lo is None else x_lo
    body = [w for w in words if w[0] >= left and (x_hi is None or w[2] <= x_hi + 1)
            and not (_parse_num(w[4]) and abs(w[2] - gx) <= tol)]
    region = [w for w in body if mids[0] - 70 <= (w[1] + w[3]) / 2 <= mids[-1] + max(row_h * 1.8, 34.0)]
    lines = _lines(region, anchor_x=left if x_lo is not None else gx)
    if not lines:
        return None
    line_h = max(1.0, sum(ln["height"] for ln in lines) / len(lines))
    # Header: a die token (1d6, 1d20) sitting just above the first row marks the title line.
    header_mid = None
    for w in words:
        if _DIE.match(w[4]) and left_x - 70 <= w[0] <= gx + 4 and mids[0] - 60 <= (w[1] + w[3]) / 2 < mids[0] - line_h * 0.5:
            header_mid = max(header_mid or 0, (w[1] + w[3]) / 2)
    title = ""
    if header_mid is not None:
        title_lines = [ln for ln in lines if abs(ln["mid"] - header_mid) <= line_h * 0.6]
        title = _join([x for ln in title_lines for x in ln["words"]])
        lines = [ln for ln in lines if ln["mid"] > header_mid + line_h * 0.6]
    if not lines:
        return None
    texts = [_line_text(ln) for ln in lines]
    n = len(lines)
    starts = [0] * len(seq)
    # Row 0: first line of the block at or above the first number.
    cand0 = [i for i, ln in enumerate(lines) if ln["mid"] <= mids[0] + line_h * 0.4 and ln["mid"] >= mids[0] - max(line_h * 2.6, row_h * 0.6)]
    if cand0:
        first_idx = min(cand0)
        if header_mid is None and first_idx > 0:
            best = max(cand0, key=lambda i: (_starts_row(texts[i - 1], texts[i]) - abs(lines[i]["mid"] - mids[0]) / line_h * 0.4))
            first_idx = best
        starts[0] = first_idx
    else:
        starts[0] = min(range(n), key=lambda i: abs(lines[i]["mid"] - mids[0]))
    for i in range(1, len(seq)):
        lo_i = starts[i - 1] + 1
        cands = [j for j in range(lo_i, n) if mids[i - 1] < lines[j]["mid"] <= mids[i] + line_h * 0.4]
        if not cands:
            nxt = [j for j in range(lo_i, n) if lines[j]["mid"] > mids[i - 1]]
            starts[i] = nxt[0] if nxt else min(lo_i, n - 1)
            continue
        midpoint = (mids[i - 1] + mids[i]) / 2
        starts[i] = max(cands, key=lambda j: _starts_row(texts[j - 1], texts[j]) - abs(lines[j]["mid"] - midpoint) / line_h * 0.35)
    rows: list[dict[str, Any]] = []
    for i, w in enumerate(seq):
        lo, hi = _parse_num(w[4])  # type: ignore[misc]
        a = starts[i]
        b = starts[i + 1] if i + 1 < len(seq) else n
        if i + 1 == len(seq):
            b = a + 1
            while b < n and lines[b]["mid"] - lines[b - 1]["mid"] <= line_h * 1.7 and lines[b]["mid"] <= mids[-1] + row_h * 1.5 + line_h:
                b += 1
        rows.append({"lo": lo, "hi": hi, "text": _join([x for ln in lines[a:b] for x in ln["words"]])})
    return {"rows": rows, "title": title, "x": gx, "y": mids[0]}


def extract_page_tables(words: list[tuple], page_w: float) -> list[dict[str, Any]]:
    heads: list[list[tuple]] = []
    tails: list[list[tuple]] = []
    for stack in _gutter_candidates(words):
        for run in _runs(stack):
            lo = _parse_num(run[0][4])[0]  # type: ignore[index]
            if lo in (0, 1) and len(run) >= 3:
                heads.append(run)
            elif len(run) >= 3:
                tails.append(run)
    tables = []
    for head in heads:
        chain = [head]
        while True:
            want = _parse_num(chain[-1][-1][4])[1] + 1  # type: ignore[index]
            nxt = next((t for t in tails if _parse_num(t[0][4])[0] == want and t is not chain[-1]), None)  # type: ignore[index]
            if nxt is None or nxt in chain:
                break
            chain.append(nxt)
        total = sum(len(c) for c in chain)
        last_hi = _parse_num(chain[-1][-1][4])[1]  # type: ignore[index]
        if not _plausible_die(_parse_num(head[0][4])[0], last_hi, total):  # type: ignore[index]
            continue
        parts = [_extract_columns(c, words, page_w) for c in chain]
        if not all(parts):
            continue
        rows = [r for p in parts for r in p["rows"]]  # type: ignore[index]
        tables.append({"rows": rows, "title": parts[0]["title"], "x": parts[0]["x"], "y": parts[0]["y"]})  # type: ignore[index]
    return tables


def extract_pdf_tables(pdf: Path) -> list[dict[str, Any]]:
    """All usable tables from one PDF, with provenance."""
    found: list[dict[str, Any]] = []
    for page_no, page_w, _page_h, words in _words(pdf):
        if len(words) < 20:
            continue
        for table in extract_page_tables(words, page_w):
            rows = [r for r in table["rows"] if r["text"]]
            if len(rows) < 4 or len(rows) < len(table["rows"]) * 0.8:
                continue
            found.append({
                "title": table["title"], "rows": table["rows"], "page": page_no,
                "source": pdf.name,
            })
    return found


# --------------------------------------------------------------------------- scanned books (OCR)
#
# Scanned books are read through an OCR node that returns word boxes.  Their tables are
# wider than the text-layer ones: one d100 gutter with several independent result columns,
# running over many pages.  Each column becomes its own table.

_OCR_DPI = 150
_COLUMN_GAP = 7.0  # points of empty space that separate result columns
_OCR_MIN_CONF = 10.0


_DICT: set[str] | None = None


def _dictionary() -> set[str]:
    global _DICT
    if _DICT is None:
        try:
            _DICT = {w.strip().lower() for w in Path("/usr/share/dict/words").read_text(errors="ignore").splitlines()}
        except OSError:
            _DICT = set()
    return _DICT


def repair_ocr_word(text: str) -> str:
    """Split the lone article OCR glues to the next word ("Agroup" -> "A group"); needs a system word list."""
    words = _dictionary()
    m = re.match(r"^([Aa])([a-z]{3,})([’'][a-z]+)?([,.;:!?]*)$", text)
    if words and m and (m.group(1) + m.group(2)).lower() not in words and m.group(2) in words:
        return f"{m.group(1)} {m.group(2)}{m.group(3) or ''}{m.group(4)}"
    if text == "0n":
        return "on"
    return text


def words_from_tsv(tsv: str, dpi: int = _OCR_DPI) -> list[tuple[float, float, float, float, str]]:
    """Tesseract TSV -> word boxes in PDF points (so the thresholds above carry over)."""
    scale = 72.0 / dpi
    words = []
    for line in tsv.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) < 12 or not cols[11].strip():
            continue
        try:
            left, top, width, height, conf = int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9]), float(cols[10])
        except ValueError:
            continue
        if conf < _OCR_MIN_CONF:
            continue
        words.append((left * scale, top * scale, (left + width) * scale, (top + height) * scale, repair_ocr_word(cols[11].strip())))
    return words


def render_page_png(pdf: Path, page: int, dpi: int = _OCR_DPI) -> bytes:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        prefix = str(Path(tmp) / "p")
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-png", "-singlefile", str(pdf), prefix],
                       check=True, capture_output=True, timeout=300)
        return Path(prefix + ".png").read_bytes()


def page_count(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, errors="replace", timeout=60).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m.group(1)) if m else 0


def is_scanned(pdf: Path, sample: int = 20) -> bool:
    """True when the PDF has (almost) no text layer, so only OCR can read it."""
    pages = page_count(pdf)
    if not pages:
        return False
    last = min(pages, sample)
    text = subprocess.run(["pdftotext", "-f", "1", "-l", str(last), str(pdf), "-"], capture_output=True, text=True, errors="replace", timeout=300).stdout
    return len(re.findall(r"[A-Za-z]{3,}", text)) < 40 * last


def _numbers_only(words: list[tuple]) -> list[tuple]:
    return [w for w in words if _parse_num(w[4])]


def _merge_numbers(base: list[tuple], extra: list[tuple]) -> list[tuple]:
    """Add the die numbers a second OCR pass found that the first one missed."""
    have = _numbers_only(base)
    added = [w for w in _numbers_only(extra)
             if not any(abs(w[0] - h[0]) < 8 and abs(w[1] - h[1]) < 8 for h in have)]
    return base + added


def _has_gutter(words: list[tuple]) -> bool:
    return any(len(stack) >= 3 for stack in _center_stacks(words))


def ocr_pdf_pages(pdf: Path, read_tsv, *, cache_dir: Path | None = None, workers: int = 3, dpi: int = _OCR_DPI, progress=None) -> list[tuple[int, float, float, list[tuple]]]:
    """OCR every page (cached on disk so an interrupted run resumes) -> (page, width, height, words).

    ``read_tsv(png, psm)`` returns tesseract TSV.  The default sparse pass reads body text best but
    drops isolated single-digit die numbers; on pages that have a number gutter a block-layout pass
    is run too and the numbers it found are merged in.
    """
    from concurrent.futures import ThreadPoolExecutor

    total = page_count(pdf)
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)

    def cached_read(page: int, png_fn, psm: int, suffix: str) -> str:
        path = cache_dir / f"{page:04d}{suffix}.tsv" if cache_dir else None
        if path and path.exists():
            return path.read_text(encoding="utf-8")
        tsv = read_tsv(png_fn(), psm) or ""
        if tsv and path:
            path.write_text(tsv, encoding="utf-8")
        return tsv

    def one(page: int):
        png_cache: list[bytes] = []

        def png() -> bytes:
            if not png_cache:
                png_cache.append(render_page_png(pdf, page, dpi))
            return png_cache[0]

        words = words_from_tsv(cached_read(page, png, 11, ""), dpi)
        if _has_gutter(words):
            words = _merge_numbers(words, words_from_tsv(cached_read(page, png, 6, ".b"), dpi))
        if progress:
            progress(page, total)
        return page, max([w[2] for w in words] or [612.0]) + 20, 792.0, words

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, range(1, total + 1)))


def _center_stacks(words: list[tuple], tol: float = 7.0) -> list[list[tuple]]:
    """Numeric words stacked vertically by centre (the scans centre their die numbers)."""
    nums = sorted((w for w in words if _parse_num(w[4])), key=lambda w: w[1])
    stacks: list[list[tuple]] = []
    for w in nums:
        c = (w[0] + w[2]) / 2
        for stack in stacks:
            last = stack[-1]
            if abs((last[0] + last[2]) / 2 - c) <= tol and w[1] > last[1]:
                stack.append(w)
                break
        else:
            stacks.append([w])
    return stacks


def _fill_gaps(stack: list[tuple]) -> list[list[tuple]]:
    """Like ``_runs`` but repairs what OCR got wrong in a gutter that otherwise counts up evenly.

    A number it dropped is filled in from the row spacing; one it misread ("7" for "77") is
    corrected when it sits exactly where the next number should be and shares its digits.
    """
    runs: list[list[tuple]] = []
    run: list[tuple] = []
    for w in stack:
        lo, _hi = _parse_num(w[4])  # type: ignore[misc]
        if run:
            prev_hi = _parse_num(run[-1][4])[1]  # type: ignore[index]
            missing = lo - prev_hi - 1
            step = ((run[-1][1] - run[0][1]) / (len(run) - 1)) if len(run) > 1 else None
            gap = w[1] - run[-1][1]
            if missing == 0:
                run.append(w)
                continue
            want = str(prev_hi + 1)
            if step and abs(gap - step) <= step * 0.35 and len(run) >= 2 and (want.startswith(w[4]) or want.endswith(w[4])):
                run.append((w[0], w[1], w[2], w[3], want))
                continue
            if 0 < missing <= 2 and step and abs(gap - step * (missing + 1)) <= step * 0.45:
                for k in range(1, missing + 1):
                    y = run[-1][1] + step * k
                    run.append((w[0], y, w[2], y + (w[3] - w[1]), str(prev_hi + k)))
                run.append(w)
                continue
            runs.append(run)
        run = [w]
    if run:
        runs.append(run)
    return runs


def _result_columns(body: list[tuple], rows: int) -> list[tuple[float, float]]:
    """Column x-ranges of the result area: the vertical strips no word crosses."""
    spans = sorted((w[0], w[2]) for w in body)
    merged: list[list[float]] = []
    for a, b in spans:
        if merged and a - merged[-1][1] < _COLUMN_GAP:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    cols = [(a, b) for a, b in merged if sum(1 for w in body if a - 1 <= w[0] and w[2] <= b + 1) >= rows]
    return cols


def _page_wide_runs(words: list[tuple]) -> list[dict[str, Any]]:
    """Gutter runs on a page with their per-column rows, header names and extent."""
    found = []
    for stack in _center_stacks(words):
        for run in _fill_gaps(stack):
            if len(run) < 3:
                continue
            gx = max(w[2] for w in run)
            first, last = run[0][1], run[-1][3]
            row_h = (run[-1][1] - run[0][1]) / max(1, len(run) - 1)
            body = [w for w in words if w[0] > gx + 2 and first - row_h * 0.7 <= (w[1] + w[3]) / 2 <= last + row_h * 0.7
                    and not _parse_num(w[4])]
            if len(body) < len(run) * 2:
                continue
            columns = _result_columns([w for w in words if w[0] > gx + 2 and first - row_h * 0.7 <= (w[1] + w[3]) / 2 <= last + row_h * 0.7], len(run))
            if not columns:
                continue
            cols = []
            for x_lo, x_hi in columns:
                part = _extract_columns(run, words, 0.0, x_lo=x_lo - 1, x_hi=x_hi, tol=8.0)
                if not part:
                    continue
                head = [w for w in words if x_lo - 1 <= w[0] and w[2] <= x_hi + 1 and first - max(70.0, row_h * 3.2) <= (w[1] + w[3]) / 2 < first - row_h * 0.3]
                head_lines = _lines(head)
                title = ""
                for ln in reversed(head_lines):
                    text = _join(ln["words"])
                    if text and not _parse_num(text) and len(text.split()) <= 8:
                        title = text
                        break
                cols.append({"x": (x_lo + x_hi) / 2, "rows": part["rows"], "title": title})
            if cols:
                found.append({"gx": (run[0][0] + run[0][2]) / 2, "lo": _parse_num(run[0][4])[0], "hi": _parse_num(run[-1][4])[1],  # type: ignore[index]
                              "y": first, "cols": cols})
    return found


def _slot_for(slots: list[dict[str, Any]], x: float) -> dict[str, Any] | None:
    best = min(slots, key=lambda sl: abs(sl["x"] - x))
    return best if abs(best["x"] - x) <= 45 else None


def extract_scanned_tables(pages: list[tuple[int, float, float, list[tuple]]], source: str) -> list[dict[str, Any]]:
    """Tables from OCR'd pages: chain gutters across pages, one table per result column.

    A continuation may skip up to three numbers (rows the OCR lost) and may lose or regain a
    result column; columns are matched to the table's own by position.
    """
    open_tables: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []
    for page_no, _w, _h, words in pages:
        runs = _page_wide_runs(words) if len(words) >= 20 else []
        extended: set[int] = set()
        for run in sorted(runs, key=lambda r: r["y"]):
            target: dict[str, Any] | None
            target = None
            if run["lo"] not in (0, 1):
                target = next((t for t in open_tables if 0 <= run["lo"] - t["next"] <= 3 and abs(t["gx"] - run["gx"]) <= 14
                               and id(t) not in extended), None)
            if target is None:
                # A new table.  When it opens a little past row 1 (the OCR lost the single-digit rows at
                # the foot of the previous page) it is kept, with those opening rows blank.
                if run["lo"] > 12 or (run["lo"] > 1 and run["hi"] - run["lo"] < 5):
                    continue
                target = {"gx": run["gx"], "page": page_no, "next": 1,
                          "cols": [{"title": c["title"], "x": c["x"], "rows": []} for c in run["cols"]]}
                open_tables.append(target)
            for number in range(target["next"], run["lo"]):  # rows the OCR never saw
                for slot in target["cols"]:
                    slot["rows"].append({"lo": number, "hi": number, "text": ""})
            by_slot: dict[int, list[dict[str, Any]]] = {id(slot): [] for slot in target["cols"]}
            for col in run["cols"]:
                slot = _slot_for(target["cols"], col["x"])
                if slot is not None and not by_slot[id(slot)]:
                    by_slot[id(slot)] = col["rows"]
            for slot in target["cols"]:
                slot["rows"].extend(by_slot[id(slot)] or [{"lo": r, "hi": r, "text": ""} for r in range(run["lo"], run["hi"] + 1)])
            target["next"] = run["hi"] + 1
            extended.add(id(target))
        still: list[dict[str, Any]] = []
        for t in open_tables:
            (still if id(t) in extended else done).append(t)
        open_tables = still
    done.extend(open_tables)
    out: list[dict[str, Any]] = []
    for t in done:
        last_hi = t["next"] - 1
        for col in t["cols"]:
            rows = col["rows"]
            filled = [r for r in rows if r["text"]]
            if not _plausible_die(1, last_hi, len(rows)) or len(filled) < max(4, int(len(rows) * 0.6)):
                continue
            out.append({"title": col["title"], "rows": rows, "page": t["page"], "source": source})
    return out
