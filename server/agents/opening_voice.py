"""Turn a player's first-person setup answers into narration.

Character setup answers are written by the player in the first person ("I came to understand what is
happening here before committing to a side").  Quoting them back into a scene reads like a character
sheet, and splicing them into third-person grammar breaks sentences.  Restating them with the character's
name and singular "they" keeps every word the player chose, works for any pronouns, and needs no model.
"""
from __future__ import annotations

import re

# Longest patterns first so "I'm" is not read as "I" + "'m".
_CONTRACTIONS = (
    (r"\bI['’]m\b", "they're"),
    (r"\bI['’]ve\b", "they've"),
    (r"\bI['’]d\b", "they'd"),
    (r"\bI['’]ll\b", "they'll"),
    (r"\bI am\b", "they are"),
    (r"\bI was\b", "they were"),
    (r"\bI\b", "they"),
    (r"\bmyself\b", "themself"),
    (r"\bmine\b", "theirs"),
    (r"\bmy\b", "their"),
    (r"\bme\b", "them"),
)

_FIRST_PERSON = re.compile(r"\b(?:I|I['’](?:m|ve|d|ll)|my|me|myself|mine)\b", re.IGNORECASE)


def is_first_person(text: str) -> bool:
    """True when ``text`` is spoken in the first person ("I...", "my...")."""
    return bool(_FIRST_PERSON.search(str(text or "")))


def first_to_third(text: str) -> str:
    """Restate ``text`` with singular "they" in place of first-person words.

    Only an obvious first-person answer is rewritten; anything else is returned unchanged.
    """
    value = " ".join(str(text or "").split())
    if not value or not is_first_person(value):
        return value
    for pattern, replacement in _CONTRACTIONS:
        # "I" is the one word that is capitalised everywhere; leave other case-sensitive matches alone.
        flags = 0 if pattern.startswith(r"\bI") else re.IGNORECASE
        value = re.sub(pattern, replacement, value, flags=flags)
    return value


def lead_sentence(text: str) -> str:
    """Capitalise the first letter and end with a full stop, keeping an existing ``.``, ``!`` or ``?``."""
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return ""
    value = value[0].upper() + value[1:]
    return value if value.endswith((".", "!", "?")) else value + "."


_PLACEHOLDER = re.compile(
    r"has not yet decided|have not yet decided|not (?:yet )?established|remains the player.s choice|"
    r"established background gives|without assuming|the campaign has not",
    re.IGNORECASE,
)
# The exact "nothing here" forms our own defaults produce. A player's own answer that merely starts with
# "no" or "never" ("Never let my sister vanish again") is a real stake and is kept.
_NOTHING = re.compile(
    r"^\s*(?:no extra complication|no complication|no one here has an assumed history|nothing (?:has )?followed me|"
    r"nobody (?:here )?(?:followed|knows) me|none of (?:them|it) followed me)\b",
    re.IGNORECASE,
)


def usable_answer(text: object) -> str:
    """The player's own words, or ``""`` for an empty answer, a "nothing here" default or a system placeholder."""
    value = " ".join(str(text or "").split()).strip()
    if not value or _NOTHING.match(value) or _PLACEHOLDER.search(value):
        return ""
    return value


_CLAUSE = re.compile(r"^(?:I|I['\u2019](?:m|ve|d|ll)|my|we|we['\u2019]re)\b", re.IGNORECASE)
# A plain statement about the world ("A rival is close behind.") reads as narration when used as written.
_STATEMENT = re.compile(
    r"^(?:a|an|the|someone|something|somebody|nobody|everyone|no one|they|he|she|it|there|their|his|her)\b", re.IGNORECASE
)


def _kind(answer: str) -> str:
    """``clause`` (first person), ``statement`` (about the world) or ``thought`` (a question, an order, a fragment)."""
    if answer.rstrip().endswith(("?", "!")):
        return "thought"
    if _CLAUSE.match(answer):
        return "clause"
    if _STATEMENT.match(answer):
        return "statement"
    return "thought"


def _inner_voice(frame: str, answer: str) -> str:
    """The answer, unchanged, as one thought the character keeps: used for questions, orders and fragments."""
    answer = answer.replace('"', "'").rstrip()
    answer = answer if answer.endswith((".", "?", "!")) else answer + "."
    return f'{frame}: "{answer}"'


# (field, frame for a first-person clause, frame for a thought)
_FRAMES = (
    ("arrival_reason", "{pc} did not come by chance: {text}.", "{pc} came with one thought"),
    ("personal_stake", "The reason this matters to {pcm}: {text}.", "{pc} keeps coming back to this"),
    ("followed_complication", "Something followed {pcm} here: {text}.", "What followed {pcm} here"),
    ("fear_of_loss", "{pc} is here with something to lose: {text}.", "{pc} will not let go of this"),
)


def anchor_sentences(anchor: dict | None, name: str, limit: int = 2) -> str:
    """Narration that carries the character's own reasons for being here: at most ``limit`` short sentences.

    Answers are restated with the character's name and "they" when they are plain first-person statements, used
    as written when they are statements about the world, and otherwise kept word for word as one thought, so a
    question or a fragment never becomes broken grammar.  Two sentences are enough for the opening checks; more
    would read as a recital of the character's setup answers.
    """
    anchor = anchor or {}
    pcm = (name or str(anchor.get("character_name") or "")).strip() or "the party"  # mid-sentence form
    pc = pcm[0].upper() + pcm[1:]  # start-of-sentence form: "the party" -> "The party"
    out: list[str] = []
    for key, clause_frame, thought_frame in _FRAMES:
        answer = usable_answer(anchor.get(key))
        if not answer:
            continue
        kind = _kind(answer)
        if kind == "clause":
            out.append(clause_frame.format(pc=pc, pcm=pcm, text=first_to_third(answer).rstrip(".")))
        elif kind == "statement":
            out.append(lead_sentence(answer))
        else:
            out.append(_inner_voice(thought_frame.format(pc=pc, pcm=pcm), answer))
        if len(out) >= limit:
            break
    return " ".join(out)


def anchor_sentence(anchor: dict | None, name: str) -> str:
    """Just the single most useful sentence from :func:`anchor_sentences`."""
    return anchor_sentences(anchor, name, limit=1)
