"""A campaign's voice: how its scenes should sound, written from the tone the table chose and its own words.

Built the same way every time from the campaign's settings, so no model call is involved and the voice cannot
drift.  It is added to the campaign contract that every scene prompt already carries.
"""
from __future__ import annotations

import re
from typing import Any

from .generation_intent import clean_text

BASE_RULES = (
    "Plain, concrete sentences; show what the character can see, hear, smell or touch.",
    "Vary sentence length. Do not reuse an image, opening or sentence shape from the last scene.",
    "No stock phrases ('a chill ran down', 'little did they know'). Name things specifically.",
    "Let people want things and say less than they mean.",
)

TONE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("grim", "gritty", "dark", "bleak", "somber"), "Restrained and heavy. Let small details and silence carry the dread. No jokes in the narration."),
    (("cozy", "warm", "gentle", "wholesome"), "Warm and unhurried. Prefer homely, specific detail. Danger is real but never cruel."),
    (("heroic", "cinematic", "epic", "adventur"), "Bold verbs and forward motion. Stakes are clear and high; courage is noticed."),
    (("witty", "light", "comic", "humor", "humour", "whimsical"), "A dry, light touch. Humour comes from specifics, never from winking at the reader."),
    (("horror", "dread", "strange", "eerie", "weird"), "Slow dread. Wrongness hides in ordinary things; do not explain it."),
    (("mystery", "noir", "detective"), "Fair play: describe what can be noticed and let the players draw conclusions."),
    (("political", "intrigue"), "Speech carries subtext. Everyone has an angle and a reason to hide it."),
)


def _excerpts(text: str, limit: int = 2, width: int = 140) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text(text)) if len(s.strip()) > 30]
    return [s[:width].rstrip(" ,;") for s in sentences[:limit]]


def voice_sheet(meta: dict[str, Any] | None) -> str:
    """The voice rules for a campaign, from its tone, its genre and a sample of the table's own words."""
    meta = meta or {}
    settings = meta.get("settings") or {}
    mood = f"{settings.get('tone', '')} {settings.get('genre', '')}".lower()
    rules = [rule for keys, rule in TONE_RULES if any(k in mood for k in keys)][:2]
    lines = [*rules, *BASE_RULES]
    own = _excerpts(str(settings.get("setting_summary") or ""))
    if own:
        lines.append("The table described its world like this (match the register, not the facts): " + " / ".join(f"“{s}”" for s in own))
    return "VOICE:\n" + "\n".join(f"- {line}" for line in lines)


def with_voice(contract: dict[str, Any] | None, meta: dict[str, Any] | None) -> dict[str, Any]:
    """The contract with the voice appended to its output rules (the contract itself is not changed)."""
    out = dict(contract or {})
    base = str(out.get("agent_output_contract") or "").rstrip()
    sheet = voice_sheet(meta)
    if sheet not in base:
        out["agent_output_contract"] = f"{base}\n\n{sheet}".strip()
    return out
