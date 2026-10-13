"""Keep what the table established steady from scene to scene, and keep scenes from echoing each other.

Two mechanical checks, run on every continuation before it is shown:

* **Names.** A language model drifts: "the Salt Court" becomes "the Salt Council", "Hale Orrin" becomes "Harl Orrin".
  The names the players and the world established are locked.  A near-miss of a locked name is repaired in place.
* **Repetition.** A scene that reuses long runs of wording from the last few scenes is sent back once with that
  feedback; the story is never left with a half-repaired scene because of it.

Neither check judges quality.  They catch the two failures that a reader notices first and can be found by looking.
"""
from __future__ import annotations

import difflib
import re
from collections.abc import Iterable

from .. import db
from . import world_skeleton
from .generation_intent import clean_text

_RUN = re.compile(r"[A-Z][a-z][\w'’-]*(?: [A-Z][a-z][\w'’-]*)+")
_WORD = re.compile(r"[a-z']+")
SIMILAR = 0.72
SHINGLE = 4
REPEAT_LIMIT = 0.15


def locked_names(campaign: db.Campaign | None, thread_names: Iterable[str] = ()) -> list[str]:
    """Multi-word names the table established: the world, its factions and people, and the players' own ties."""
    if campaign is None:
        return []
    meta = dict(campaign.metadata_json or {})
    settings = meta.get("settings") or {}
    card = meta.get("campaign_card") or {}
    names: list[str] = [clean_text(settings.get("world_name")), clean_text(settings.get("starting_location"))]
    names += [clean_text(f.get("name") if isinstance(f, dict) else f) for f in card.get("factions") or []]
    names += [clean_text(p.get("name")) for p in card.get("people") or [] if isinstance(p, dict)]
    state = world_skeleton._state(campaign)
    names += [f["name"] for f in world_skeleton._ready_contents(state, "factions") or []]
    names += [n["name"] for n in world_skeleton._ready_contents(state, "npcs") or []]
    truth = world_skeleton._ready_contents(state, "truth")
    if truth:
        names.append(truth["thread_name"])
    names += [clean_text(n).split(",")[0] for n in thread_names]
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        name = name.removeprefix("the ").removeprefix("The ").strip()
        if len(name.split()) >= 2 and name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out


def name_drifts(text: str, names: Iterable[str]) -> list[tuple[str, str]]:
    """``(variant, locked name)`` for capitalised phrases in ``text`` that are near-misses of a locked name."""
    locked = [n for n in names if n]
    exact = {n.casefold() for n in locked}
    found: list[tuple[str, str]] = []
    for match in _RUN.finditer(text or ""):
        run = match.group(0)
        words = run.split()
        if words[0].casefold() in {"the", "a", "an"}:
            run = " ".join(words[1:])
        if len(run.split()) < 2 or run.casefold() in exact:
            continue
        for name in locked:
            parts, locked_parts = run.split(), name.split()
            if parts[0] == locked_parts[0] or parts[-1] == locked_parts[-1]:
                if run != name and difflib.SequenceMatcher(None, run.casefold(), name.casefold()).ratio() >= SIMILAR:
                    if (run, name) not in found:
                        found.append((run, name))
                    break
    return found


def repair_names(text: str, drifts: Iterable[tuple[str, str]]) -> str:
    for variant, name in drifts:
        text = re.sub(rf"(?<![\w'’-]){re.escape(variant)}(?![\w'’-])", name, text)
    return text


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = _WORD.findall(text.lower())
    return {tuple(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def repeated_wording(text: str, recent: Iterable[str]) -> float:
    """The largest share of this scene's 4-word runs that also appear in one recent scene."""
    mine = _shingles(text)
    if not mine:
        return 0.0
    return max((len(mine & _shingles(prev)) / len(mine) for prev in recent if prev), default=0.0)


def check_scene(text: str, names: Iterable[str], recent: Iterable[str]) -> dict[str, object]:
    """``{"issues": [...], "drifts": [...]}``.  Drifts are repaired by the caller; issues are sent back for a rewrite."""
    issues: list[str] = []
    if repeated_wording(text, recent) > REPEAT_LIMIT:
        issues.append("Repeats wording from the previous scenes. Use new images and vary the sentence shapes.")
    return {"issues": issues, "drifts": name_drifts(text, names)}
