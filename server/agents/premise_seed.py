"""Turn the player's own premise into a concrete opening seed.

The keyword templates in ``content_bundles`` recognise a handful of premises; every other premise used
to fall through to a random pool, so a toll crossing and a vanished caravan opened in "Iron Temple".
A model can read free text, so one bounded call extracts the premise's own place, event, and people into
the same seed shape the rest of the opening already uses.  Anything it returns is checked against the
premise; on any doubt the caller keeps the pool seed.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

log = logging.getLogger("taverntails.premise_seed")

TEXT_FIELDS = (
    "starting_location", "location_type", "location_identity", "inciting_event", "named_npc_or_visible_threat",
    "immediate_problem", "specific_stakes", "first_clue_or_question", "player_decision",
)
MIN_PREMISE_WORDS = 8
MAX_FIELD_CHARS = 260
_STOP = frozenset(
    "about after again against along also because before being between could every from have into just like "
    "make many more most much must never only other over same should since some such than that their them "
    "then there these they this those through under until upon very were what when where which while will "
    "with without would your want opening begin begins start starts campaign".split()
)

SYSTEM = (
    "You turn a game master's short campaign premise into the opening situation of a tabletop RPG scene.\n"
    "Use ONLY what the premise states or directly implies. Do not add monsters, magic, factions or "
    "locations the premise does not suggest, and never default to a tavern unless the premise says so.\n"
    "Reply with ONLY a JSON object whose values are short strings (each under 220 characters):\n"
    '  "starting_location": a specific named place for the first scene, 2-6 words, named from the premise\'s own description\n'
    '  "location_type": the kind of place, 1-4 words\n'
    '  "location_identity": one sentence describing the place as the player sees it\n'
    '  "inciting_event": one sentence: what is visibly happening as the scene opens (use the premise\'s own opening moment if it gives one)\n'
    '  "named_npc_or_visible_threat": "Full Name (role)" of one person present who matters; invent a fitting name only if the premise names no one\n'
    '  "immediate_problem": one sentence\n'
    '  "specific_stakes": one sentence: what is lost if nothing is done soon\n'
    '  "first_clue_or_question": one question the player can start investigating\n'
    '  "player_decision": one sentence offering two or three concrete options'
)


def _premise(settings: dict[str, Any], contract: dict[str, Any]) -> str:
    """The player's own words, each sentence once (the stored text repeats the summary)."""
    from .content_bundles import _campaign_premise_text

    seen: set[str] = set()
    parts: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", _campaign_premise_text(settings, contract)):
        key = sentence.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            parts.append(sentence.strip())
    return " ".join(parts)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{5,}", text.lower()) if w not in _STOP}


def _parse(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def validate(data: dict[str, Any], premise: str) -> dict[str, str] | None:
    """The cleaned fields, or None when the answer is incomplete or ignores the premise."""
    out: dict[str, str] = {}
    for field in TEXT_FIELDS:
        value = " ".join(str(data.get(field) or "").split())
        if not value:
            return None
        out[field] = value[:MAX_FIELD_CHARS]
    if not 1 <= len(out["starting_location"].split()) <= 8:
        return None
    if len(_tokens(premise) & _tokens(" ".join(out[f] for f in ("starting_location", "location_identity", "inciting_event")))) < 2:
        return None  # it did not use the premise
    if "(" not in out["named_npc_or_visible_threat"]:
        out["named_npc_or_visible_threat"] += " (local contact)"
    return out


def extract_premise_seed(
    settings: dict[str, Any] | None,
    contract: dict[str, Any] | None,
    *,
    complete: Callable[..., str | None] | None = None,
    timeout: float = 45.0,
) -> dict[str, Any] | None:
    """One model call -> an opening seed in the shape ``generate_starter_seed`` returns, or None."""
    settings, contract = settings or {}, contract or {}
    premise = _premise(settings, contract)
    if len(premise.split()) < MIN_PREMISE_WORDS:
        return None
    if complete is None:
        from ..steward_llm import chat_complete as complete
    genre = str(settings.get("genre") or (contract.get("campaign_dna") or {}).get("genre") or "fantasy")
    tone = str(settings.get("tone") or (contract.get("campaign_dna") or {}).get("tone") or "balanced")
    try:
        raw = complete(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": f"Genre: {genre}\nTone: {tone}\nPremise: {premise}"}],
            task_scope="taverntails_plot", max_tokens=520, temperature=0.5, timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - the pool seed is always an acceptable answer
        log.warning("premise extraction call failed", exc_info=True)
        return None
    fields = validate(_parse(raw) or {}, premise)
    if not fields:
        log.info("premise extraction rejected (incomplete or ungrounded)")
        return None

    from .content_bundles import annotate_seed
    from .generation_intent import build_opening_intent

    npc_name = fields["named_npc_or_visible_threat"].split("(")[0].strip()
    seed = {
        **fields,
        "memory_updates": [
            {"type": "location", "name": fields["starting_location"], "status": "campaign_opening"},
            {"type": "npc", "name": npc_name, "status": "campaign_opening"},
        ],
        "generated_by": "premise_seed",
        "freshness_consumed": {"location_type": fields["location_type"], "event": fields["inciting_event"]},
    }
    return annotate_seed(seed, build_opening_intent(settings, contract), mode="premise_model")
