"""Canonical generation intent, fact provenance, and claim-support checks.

The generation stack has several independent layers that can each add detail
(campaign interpretation, starter seeds, opening setup, scene director,
narrative composer, QA/repair).  Without one shared source of truth,
"specific" quietly turns into "invented".  This module is that source of truth.

Pipeline contract::

    player intent -> canonical facts -> provisional facts -> scene plan -> prose

* A :class:`Fact` records *what* is claimed, *who* said so (its provenance) and
  which fact it was derived from.
* A downstream layer may **elaborate** a fact.  The elaboration is always
  ``generated_provisional``; it never inherits the authority of its parent.
* A guess becomes canon only through :func:`promote_fact`, which demands an
  explicit confirmation.  Nothing is promoted silently.
* "Unknown / not established" is a first-class state (:class:`Unknown`); empty
  fields are not filled with invented lore just to satisfy a schema.

Everything here is deterministic and cheap so it can run inside QA and tests.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

Provenance = Literal["user", "imported", "seed", "generated_provisional", "confirmed_canon"]

PROVENANCES: tuple[str, ...] = ("user", "imported", "seed", "generated_provisional", "confirmed_canon")

# Facts a player (or their imported lore) actually established.  Only these can
# vouch for personal history, class lore, factions, and other "load-bearing"
# claims.  A seed or a provisional elaboration cannot.
ESTABLISHED: frozenset[str] = frozenset({"user", "imported", "confirmed_canon"})

# Higher number = more authority.  Used to pick the strongest supporting fact.
AUTHORITY: dict[str, int] = {
    "generated_provisional": 0,
    "seed": 1,
    "imported": 2,
    "user": 3,
    "confirmed_canon": 4,
}

NOT_ESTABLISHED = "not yet established"

# Mapping onto the vocabulary already used by ``canon_manager``.
_TO_CANON_STATUS = {
    "user": "player_canon",
    "imported": "player_canon",
    "confirmed_canon": "confirmed_canon",
    "seed": "provisional",
    "generated_provisional": "provisional",
}
_FROM_CANON_STATUS = {
    "player_canon": "user",
    "confirmed_canon": "confirmed_canon",
    "canon": "confirmed_canon",
    "provisional": "generated_provisional",
    "background": "generated_provisional",
}


def to_canon_status(provenance: str) -> str:
    """Translate a provenance label to a ``canon_manager`` status."""
    return _TO_CANON_STATUS.get(provenance, "provisional")


def from_canon_status(status: str) -> str:
    """Translate a ``canon_manager`` status to a provenance label."""
    return _FROM_CANON_STATUS.get(status, "generated_provisional")


class PromotionError(ValueError):
    """Raised when a fact is promoted without an allowed path or confirmation."""


class Fact(BaseModel):
    id: str
    kind: str
    text: str
    provenance: Provenance
    source: str = ""
    derived_from: list[str] = Field(default_factory=list)
    confirmed_by: str = ""

    @property
    def established(self) -> bool:
        return self.provenance in ESTABLISHED


class Unknown(BaseModel):
    field: str
    reason: str = "The player has not established this."


# Fact kind -> OpeningIntent bucket.  Anything unlisted lands in ``conflicts``
# (clues, objects, time pressure, ... are all part of "what is going on").
_BUCKETS = {
    "location": "locations",
    "actor": "actors",
    "conflict": "conflicts",
    "stakes": "stakes",
    "constraint": "constraints",
}


def fact_id(kind: str, text: str) -> str:
    digest = hashlib.sha1(f"{kind}:{clean_text(text).lower()}".encode()).hexdigest()[:10]
    return f"f_{digest}"


def make_fact(
    kind: str,
    text: str,
    provenance: str,
    source: str = "",
    derived_from: Iterable[str] = (),
    confirmed_by: str = "",
) -> Fact:
    if provenance not in PROVENANCES:
        raise ValueError(f"unknown provenance: {provenance!r}")
    return Fact(
        id=fact_id(kind, text),
        kind=kind,
        text=clean_text(text),
        provenance=provenance,  # type: ignore[arg-type]
        source=source,
        derived_from=list(derived_from),
        confirmed_by=confirmed_by,
    )


def can_promote(from_provenance: str, to_provenance: str) -> bool:
    """Allowed promotions.  Only ``confirmed_canon`` is reachable by promotion.

    ``user`` and ``imported`` are origins, not destinations: a fact is ``user``
    because a player wrote it, never because the system decided it was true.
    """
    if to_provenance != "confirmed_canon":
        return False
    return from_provenance in {"seed", "generated_provisional", "imported", "user"}


def promote_fact(fact: Fact, to_provenance: str, *, confirmed_by: str) -> Fact:
    """Promote ``fact`` to ``confirmed_canon`` with an explicit confirmation."""
    if not clean_text(confirmed_by):
        raise PromotionError("promotion requires an explicit confirmation (confirmed_by)")
    if fact.provenance == to_provenance:
        return fact
    if not can_promote(fact.provenance, to_provenance):
        raise PromotionError(f"cannot promote {fact.provenance!r} -> {to_provenance!r}")
    return fact.model_copy(update={"provenance": to_provenance, "confirmed_by": clean_text(confirmed_by)})


def elaborate_fact(parent: Fact, text: str, *, kind: str | None = None, source: str = "") -> Fact:
    """Derive a more detailed fact from ``parent``.

    The result is always ``generated_provisional``: adding detail to a fact is a
    guess, however well-founded the parent is.
    """
    return make_fact(
        kind or parent.kind,
        text,
        "generated_provisional",
        source=source or f"elaboration of {parent.id}",
        derived_from=[parent.id],
    )


# ---------------------------------------------------------------------------
# Shared text helpers (single implementation for every generation module)
# ---------------------------------------------------------------------------

STOP_WORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "also", "am", "an", "and", "any",
    "are", "around", "as", "at", "back", "be", "because", "been", "before", "being", "between",
    "both", "but", "by", "can", "could", "did", "do", "does", "down", "during", "each", "either",
    "ever", "few", "for", "from", "had", "has", "have", "he", "her", "here", "him", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "just", "least", "less", "many", "may", "me",
    "might", "more", "most", "much", "must", "my", "neither", "never", "no", "not", "now", "of",
    "off", "on", "once", "only", "or", "other", "our", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "up", "very", "was", "we",
    "were", "what", "when", "where", "which", "while", "who", "will", "with", "would", "you",
    "your",
})

_WORD = re.compile(r"[a-z0-9]+")


def clean_text(raw: Any) -> str:
    """Collapse whitespace and trim trailing periods (shared ``_clean_raw``)."""
    return " ".join(str(raw or "").replace("\n", " ").split()).strip(" .")


def trim_sentence(text: Any) -> str:
    """Return ``text`` as a single sentence ending in terminal punctuation."""
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."


def text_of(*values: Any) -> str:
    """Lower-cased haystack from strings / lists / dict values (shared ``_text``)."""
    parts: list[str] = []
    for value in values:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif isinstance(value, dict):
            parts.extend(str(v) for v in value.values())
    return " ".join(parts).lower()


def unique(items: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = str(item or "").strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def content_tokens(text: Any) -> set[str]:
    """Stemmed, stop-word-free tokens used for support comparisons."""
    return {
        _stem(t)
        for t in _WORD.findall(str(text or "").lower())
        if t not in STOP_WORDS and len(t) > 2
    }


def premise_text(
    settings: dict[str, Any] | None,
    contract: dict[str, Any] | None,
    *,
    player_authored: bool = False,
) -> str:
    """The single definition of "what the campaign author said the premise is".

    With ``player_authored=True`` only text the author actually wrote is
    returned.  The campaign title and the generated output contract are left
    out, so a title (or boilerplate) can never select a setting template.
    """
    settings = settings or {}
    contract = contract or {}
    dna = contract.get("campaign_dna") or {}
    name = clean_text(contract.get("campaign_name"))
    pitch = clean_text(contract.get("campaign_pitch"))
    if player_authored:
        if pitch.lower() == name.lower():
            pitch = ""  # the pitch defaults to the title when nothing was written
        return " ".join([
            str(settings.get("setting_summary") or ""),
            str(settings.get("world_name") or ""),
            pitch,
            str(dna.get("setting_summary") or ""),
        ]).strip()
    return " ".join([
        str(settings.get("setting_summary") or ""),
        str(settings.get("world_name") or ""),
        str(contract.get("campaign_name") or ""),
        str(contract.get("campaign_pitch") or ""),
        str(dna.get("setting_summary") or ""),
        str(dna.get("starting_promise") or ""),
        " ".join(str(x) for x in (dna.get("central_questions") or [])[:4]),
        str(contract.get("agent_output_contract") or "")[:1200],
    ]).strip()


# ---------------------------------------------------------------------------
# Opening intent
# ---------------------------------------------------------------------------

class OpeningIntent(BaseModel):
    """Structured player intent for a campaign opening.

    ``premise``, ``locations``, ``actors``, ``conflicts``, ``stakes`` and
    ``constraints`` hold facts with provenance.  ``unknowns`` lists what has
    *not* been established, so downstream layers can leave it open instead of
    inventing it.
    """

    premise: Fact | None = None
    locations: list[Fact] = Field(default_factory=list)
    actors: list[Fact] = Field(default_factory=list)
    conflicts: list[Fact] = Field(default_factory=list)
    stakes: list[Fact] = Field(default_factory=list)
    constraints: list[Fact] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)
    allowed_names: list[str] = Field(default_factory=list)

    def facts(self) -> list[Fact]:
        out: list[Fact] = [self.premise] if self.premise else []
        for bucket in _BUCKETS.values():
            out.extend(getattr(self, bucket))
        return out

    def get(self, fact_id_: str) -> Fact | None:
        return next((f for f in self.facts() if f.id == fact_id_), None)

    def add(self, fact: Fact) -> Fact:
        """Add ``fact``; if the same fact exists keep the stronger provenance."""
        if fact.kind == "premise":
            if self.premise is None or AUTHORITY[fact.provenance] >= AUTHORITY[self.premise.provenance]:
                self.premise = fact
            return fact
        bucket = getattr(self, _BUCKETS.get(fact.kind, "conflicts"))
        result = fact
        for idx, existing in enumerate(bucket):
            if existing.id == fact.id:
                if AUTHORITY[fact.provenance] > AUTHORITY[existing.provenance]:
                    bucket[idx] = fact
                else:
                    result = existing
                break
        else:
            bucket.append(fact)
        # An established fact resolves the matching unknown, whether it was appended
        # or replaced a weaker version of itself.
        if result.established:
            self.unknowns = [u for u in self.unknowns if u.field != result.kind]
        return result

    def add_unknown(self, field: str, reason: str = "The player has not established this.") -> None:
        if not any(u.field == field for u in self.unknowns):
            self.unknowns.append(Unknown(field=field, reason=reason))

    def is_unknown(self, field: str) -> bool:
        return any(u.field == field for u in self.unknowns)

    def tokens(self, *, established_only: bool = False) -> set[str]:
        out: set[str] = set()
        for fact in self.facts():
            if established_only and not fact.established:
                continue
            out |= content_tokens(fact.text)
        return out

    def allowed_tokens(self) -> set[str]:
        out: set[str] = set()
        for name in self.allowed_names:
            out |= content_tokens(name)
        return out


_PERSON_TYPES = frozenset({"npc", "person", "character", "villain", "ally", "enemy", "contact", "boss", "patron"})


def _entity_fact_kind(entity_type: str) -> str:
    """Map a lore entity type to a fact kind.

    Only people are ``actor`` facts (candidates for the opening's primary NPC).
    A faction or an item is just as established, but it is not someone who can
    stand in the opening scene, so it must not be selected as one.
    """
    kind = str(entity_type or "").strip().lower()
    if kind in {"place", "location"}:
        return "location"
    if kind in _PERSON_TYPES:
        return "actor"
    return "faction" if kind == "faction" else (kind or "entity")


def build_opening_intent(
    settings: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    *,
    character: dict[str, Any] | None = None,
    allowed_names: Iterable[str] = (),
) -> OpeningIntent:
    """Build the canonical intent from what the player actually provided.

    Only player-authored text (settings, the campaign pitch, imported lore,
    backstory) becomes ``user`` / ``imported`` facts.  Interpretation output
    (themes, central questions) is ``seed``-level framing.  Anything missing is
    recorded as an :class:`Unknown`.
    """
    settings = settings or {}
    contract = contract or {}
    dna = contract.get("campaign_dna") or {}
    world = contract.get("world_contract") or {}
    intent = OpeningIntent(allowed_names=[clean_text(n) for n in allowed_names if clean_text(n)])

    pitch = clean_text(contract.get("campaign_pitch") or settings.get("setting_summary") or "")
    summary = clean_text(settings.get("setting_summary") or "")
    name = clean_text(contract.get("campaign_name") or "")
    premise_bits = unique([summary, pitch])
    if premise_bits:
        intent.add(make_fact("premise", " ".join(premise_bits), "user", source="settings/campaign_pitch"))
    if name:
        # The title is the author's own word, so it may be repeated in prose, but
        # it only counts as the premise when nothing richer was provided.
        if intent.premise is None:
            intent.add(make_fact("premise", name, "user", source="campaign_name"))
        else:
            intent.allowed_names.append(name)

    for source, value in (
        ("settings.starting_location", settings.get("starting_location")),
        ("campaign_dna.starting_location", dna.get("starting_location")),
        ("world_contract.known_starting_location", world.get("known_starting_location")),
    ):
        if clean_text(value):
            intent.add(make_fact("location", clean_text(value), "user", source=source))

    for entity in contract.get("player_canon") or []:
        if not isinstance(entity, dict) or not clean_text(entity.get("name")):
            continue
        origin = "user" if entity.get("source") in {"backstory", "player_backstory"} else "imported"
        intent.add(make_fact(
            _entity_fact_kind(str(entity.get("type") or "")),
            clean_text(entity.get("name")),
            origin,
            source=f"player_canon:{entity.get('source') or 'lore'}",
        ))
    for entity in contract.get("provisional_entities") or []:
        if not isinstance(entity, dict) or not clean_text(entity.get("name")):
            continue
        intent.add(make_fact(
            _entity_fact_kind(str(entity.get("type") or "")),
            clean_text(entity.get("name")),
            "generated_provisional",
            source=f"provisional_entities:{entity.get('source') or 'inline_mention'}",
        ))

    for conflict in unique(list(dna.get("core_conflicts") or []) + list(dna.get("central_questions") or [])):
        intent.add(make_fact("conflict", conflict, "seed", source="campaign_dna"))
    for rule in unique(
        str(v)
        for key, value in (contract.get("safety_policy") or {}).items()
        if any(w in str(key).lower() for w in ("avoid", "exclude", "lines", "veil"))
        for v in (value if isinstance(value, list) else [value])
    ):
        intent.add(make_fact("constraint", rule, "user", source="safety_policy"))

    if character:
        sheet = character.get("sheet") if isinstance(character.get("sheet"), dict) else {}
        backstory = clean_text(" ".join(
            str(part or "")
            for part in (
                character.get("backstory"), character.get("bonds"), character.get("personality_traits"),
                character.get("ideals"), character.get("flaws"),
                sheet.get("backstory"), sheet.get("bonds"), sheet.get("personality_traits"),
                sheet.get("ideals"), sheet.get("flaws"),
            )
        ))
        if backstory:
            # Background about the character is something the story must respect;
            # it is not a named actor and must not be mistaken for one.
            intent.add(make_fact("constraint", backstory, "user", source="character.backstory"))
        if clean_text(character.get("name")):
            intent.allowed_names.append(clean_text(character.get("name")))

    for field in ("location", "actor", "conflict", "stakes"):
        if not any(f.established for f in getattr(intent, _BUCKETS[field])):
            intent.add_unknown(field)
    return intent


# seed field -> (fact kind, how to label it)
_SEED_FIELDS: tuple[tuple[str, str], ...] = (
    ("starting_location", "location"),
    ("location_identity", "location"),
    ("named_npc_or_visible_threat", "actor"),
    ("inciting_event", "conflict"),
    ("immediate_problem", "conflict"),
    ("first_clue_or_question", "conflict"),
    ("player_decision", "conflict"),
    ("specific_stakes", "stakes"),
    ("approved_object", "conflict"),
    ("time_pressure", "conflict"),
)

_SEED_PROVENANCE = {
    "premise_seed": "seed",
    "starter_seed": "generated_provisional",
}


def seed_provenance(seed: dict[str, Any]) -> str:
    """Provenance a seed's own fields deserve, from its ``generated_by`` tag."""
    return _SEED_PROVENANCE.get(str(seed.get("generated_by") or ""), "generated_provisional")


def _covering_fact(text: str, intent: OpeningIntent, *, threshold: float = 0.8) -> Fact | None:
    """The established fact that already says (nearly) all of ``text``."""
    tokens = content_tokens(text)
    if not tokens:
        return None
    best: tuple[float, Fact] | None = None
    for fact in intent.facts():
        if not fact.established:
            continue
        coverage = len(tokens & content_tokens(fact.text)) / len(tokens)
        if coverage >= threshold and (best is None or coverage > best[0]):
            best = (coverage, fact)
    return best[1] if best else None


def _seed_value(seed: dict[str, Any], field: str) -> str:
    raw = seed.get(field)
    if field == "named_npc_or_visible_threat" and isinstance(raw, str):
        raw = raw.split("(")[0]
    return clean_text(raw)


def seed_field_provenance(seed: dict[str, Any] | None, intent: OpeningIntent) -> dict[str, str]:
    """Provenance of every populated seed field.

    A value the player already established keeps the player's provenance;
    anything else carries the seed's own (weaker) provenance.
    """
    seed = seed or {}
    default = seed_provenance(seed)
    out: dict[str, str] = {}
    for field, _kind in _SEED_FIELDS:
        value = _seed_value(seed, field)
        if not value:
            continue
        covering = _covering_fact(value, intent)
        out[field] = covering.provenance if covering is not None else default
    return out


def intent_with_seed(intent: OpeningIntent, seed: dict[str, Any] | None) -> OpeningIntent:
    """Return a copy of ``intent`` extended with the facts in an opening seed.

    A seed value the player already stated keeps the player's provenance.
    Everything else is recorded with the seed's own (weaker) provenance, so a
    template can never masquerade as something the player decided.
    """
    out = intent.model_copy(deep=True)
    seed = seed or {}
    default = seed_provenance(seed)
    for field, kind in _SEED_FIELDS:
        value = _seed_value(seed, field)
        if not value:
            continue
        covering = _covering_fact(value, out)
        if covering is not None:
            out.add(make_fact(kind, value, covering.provenance, source=f"seed.{field}", derived_from=[covering.id]))
        else:
            out.add(make_fact(kind, value, default, source=f"seed.{field}"))
    return out


_ANCHOR_FIELDS = (
    "arrival_reason", "pre_scene_activity", "personal_stake", "known_npc_connection",
    "party_bond", "followed_complication", "fear_of_loss",
)


def intent_from_opening(
    *,
    required: dict[str, Any] | None,
    brief: dict[str, Any] | None = None,
    anchor: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    character: dict[str, Any] | None = None,
    player_name: str = "",
) -> OpeningIntent:
    """Everything an opening scene is allowed to say, with provenance.

    Layers, strongest first: what the player wrote (settings, pitch, lore,
    backstory, *answered* setup questions), then the opening seed, then the
    campaign brief derived from that seed.  Auto-generated setup answers are only
    ``generated_provisional``: they cannot vouch for personal history.
    """
    intent = build_opening_intent(settings, contract, character=character)
    intent = intent_with_seed(intent, required)
    anchor = anchor or {}
    answered = str(anchor.get("source") or "player_answered") == "player_answered"
    # Provenance is per answer: a "player_answered" questionnaire can still contain
    # fields the player skipped or handed to the AI, which hold generated defaults.
    field_sources = anchor.get("field_sources") if isinstance(anchor.get("field_sources"), dict) else {}
    for key in _ANCHOR_FIELDS:
        value = clean_text(anchor.get(key))
        if value:
            from_player = field_sources.get(key, "player" if answered else "default") == "player"
            intent.add(make_fact(
                "constraint", value, "user" if answered and from_player else "generated_provisional",
                source=f"anchor.{key}",
            ))
    for name in (anchor.get("character_name"), player_name):
        if clean_text(name):
            intent.allowed_names.append(clean_text(name))
    for fact_text in (brief or {}).get("known_facts") or []:
        text = clean_text(fact_text)
        if not text:
            continue
        covering = _covering_fact(text, intent, threshold=0.6)
        intent.add(make_fact(
            "conflict",
            text,
            covering.provenance if covering else "generated_provisional",
            source="brief.known_facts",
            derived_from=[covering.id] if covering else [],
        ))
    intent.allowed_names = list(dict.fromkeys(intent.allowed_names))
    return intent


def fact_discipline_prompt(intent: OpeningIntent, *, max_facts: int = 8) -> str:
    """Prompt text that tells a generator what is canon and what it may not invent."""
    established = [f for f in intent.facts() if f.established and f.kind != "premise"]
    premise = intent.premise.text if intent.premise and intent.premise.established else ""
    provisional = [f for f in intent.facts() if not f.established and f.kind in {"location", "actor", "stakes"}]
    lines = ["FACT DISCIPLINE (source of truth for this scene):"]
    if premise:
        lines.append(f"  Premise written by the player: {premise[:300]}")
    if established:
        lines.append("  Established by the player (canon - do not contradict or embellish):")
        lines.extend(f"    - {f.text[:160]}" for f in established[:max_facts])
    if provisional:
        lines.append("  Provisional placeholders (usable, but never expand them into backstory):")
        lines.extend(f"    - {f.text[:120]}" for f in provisional[:max_facts])
    if intent.unknowns:
        lines.append("  Not established: " + ", ".join(u.field for u in intent.unknowns) + ". Leave these open rather than inventing lore.")
    lines.append(
        "  Never invent: personal history for the player character, prior relationships, debts or oaths, "
        "knowledge a character class supposedly grants, or named factions / organizations that are not listed above."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal planning / QA language must never reach player-facing prose
# ---------------------------------------------------------------------------

_INTERNAL_PATTERNS = tuple(
    re.compile(p, re.I)
    for p in (
        r"\bthe scene (?:turns on|should|must|needs to|is meant to|will)\b",
        r"\binstead of resetting\b",
        r"\banchors the moment\b",
        r"\bmake this problem local rather than interchangeable\b",
        r"\bhas a concrete role here\b",
        r"\bimmediate consequence is concrete\b",
        r"\bthe clearest clue is this\b",
        r"\bthe pressure in the moment becomes visible\b",
        r"\b(?:concrete )?table details?\b",
        r"\btruth[- ]table\b",
        r"\bapproved (?:location|npc|clue|object|stakes|threat)\b",
        r"\brequired[_ ]content\b",
        r"\bscene[_ ]beat\b",
        r"\bstory plan\b",
        r"\bvalidator\b",
        r"\bregenerat(?:e|ed|ing|ion)\b(?=[^.!?]{0,20}\b(?:scene|narrative|prose|response|opening)\b)",
        r"\b(?:scene|narrative|prose|opening) regenerat\w+\b",
        r"\bplaceholder\b",
        r"\bcampaign contract\b",
        r"\bspecificity\b",
        r"\bplayer agency\b",
        r"\bdetail budget\b",
        r"\bmust_(?:not_)?include\b",
        r"\bgenerated_provisional\b",
        r"\bprovisional (?:fact|canon|anchor)\b",
        r"\bas an ai\b",
        r"\bquality[_ ](?:repair|check|gate)\b",
    )
)


def find_internal_language(text: Any) -> list[str]:
    """Snippets of planner / QA / repair language found in player-facing text."""
    body = str(text or "")
    hits: list[str] = []
    for pattern in _INTERNAL_PATTERNS:
        match = pattern.search(body)
        if match:
            hits.append(match.group(0).lower())
    return list(dict.fromkeys(hits))


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(str(text or "")) if s and s.strip()]


def strip_internal_language(text: Any) -> str:
    """Drop every sentence that carries planner / QA language."""
    body = str(text or "")
    if not find_internal_language(body):
        return body
    kept = [s for s in split_sentences(body) if not find_internal_language(s)]
    return " ".join(kept).strip()


_ABBREVIATIONS = frozenset({"e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "st", "no"})
_SENTENCE_BREAK = re.compile(r"([.!?][\"'\u201d\u2019)]*)(\s+)([a-z])")
_DETERMINERS = ("the ", "a ", "an ", "this ", "that ", "these ", "those ", "his ", "her ", "their ", "my ", "our ", "your ", "its ")


def capitalize_sentences(text: Any) -> str:
    """Capitalize the first letter of every paragraph and sentence.

    Generated text splices names / pronouns in at sentence starts, which leaves
    openings like "the party arrives ...".  Known abbreviations are left alone.
    """
    body = str(text or "")

    def paragraph(par: str) -> str:
        match = re.search(r"[A-Za-z]", par)
        if not match or par[: match.start()].strip(" \"'\u201c\u2018(\u2014-"):
            return par
        return par[: match.start()] + par[match.start()].upper() + par[match.start() + 1:]

    body = "\n\n".join(paragraph(p) for p in body.split("\n\n"))

    def sentence(match: re.Match[str]) -> str:
        before = body[: match.start()].rsplit(None, 1)
        previous = (before[-1] if before else "").lower().rstrip(".")
        following = body[match.end(3) - 1: match.end(3) + 3].lower()
        if previous in _ABBREVIATIONS or following.startswith(("e.g", "i.e")):
            return match.group(0)
        return f"{match.group(1)}{match.group(2)}{match.group(3).upper()}"

    return _SENTENCE_BREAK.sub(sentence, body)


def definite(noun_phrase: Any) -> str:
    """"marked clue" -> "the marked clue"; leaves determiners and proper nouns alone."""
    text = clean_text(noun_phrase)
    if not text:
        return text
    if text.lower().startswith(_DETERMINERS) or text[0].isupper():
        return text
    return f"the {text}"


_MALFORMED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("doubled_punctuation", re.compile(r"[?!]\.|\.\.(?!\.)|\.,|,\.|\?\?|!!(?!!)")),
    ("lowercase_start", re.compile(r"(?:^|\n\n|(?<=[.!?]) )(?:the|a|an) [a-z]+ (?:arrives|reaches|recognizes|slows|waits|acts)\b")),
    ("first_person_splice", re.compile(r"\b(?:because|that|until) I (?:came|am|was|want|will|do)\b")),
    ("lowercase_pronoun_i", re.compile(r"\b(?:to|and|but|because|that) i (?:came|am|was|want|will|do)\b")),
    ("title_splice", re.compile(r"\bbegins at [^.!?\n]{1,60}\b(?:is|are) (?:a|an|the|where)\b")),
    ("article_a_before_vowel", re.compile(r"\b[Aa] (?:underground|surface|enemy|animal|army|axe|inn|ally|artifact)\b")),
    ("article_an_before_consonant", re.compile(r"\b[Aa]n (?:surface|road|crowd|guard|witness|clerk|seal|bell)\b")),
    ("repeated_word", re.compile(r"\b(?!had\b|that\b)(\w{3,})\s+\1\b", re.I)),
)


ADVISORY_DEFECTS = frozenset({"repeated_word"})


def blocking_defects(text: Any) -> list[dict[str, str]]:
    """Malformed-sentence defects that production QA treats as failures."""
    return [d for d in find_malformed_sentences(text) if d["defect"] not in ADVISORY_DEFECTS]


def polish_prose(text: Any) -> str:
    """Mechanically repair the unambiguous defects (case, doubled punctuation)."""
    body = str(text or "")
    body = re.sub(r"([?!])\.", r"\1", body)
    body = re.sub(r"\.,", ",", body)
    body = re.sub(r",\.", ".", body)
    body = re.sub(r"\.\.(?!\.)", ".", body)
    return capitalize_sentences(body)


def find_malformed_sentences(text: Any) -> list[dict[str, str]]:
    """High-confidence grammar / assembly defects in generated prose.

    Quoted speech is ignored (a character may say "I came here to ...").
    """
    body = re.sub(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d', " ", str(text or ""))
    found: list[dict[str, str]] = []
    for label, pattern in _MALFORMED_PATTERNS:
        for match in pattern.finditer(body):
            found.append({"defect": label, "text": match.group(0).strip()[:80]})
            break
    return found


def map_paragraphs(text: Any, fn: Any) -> str:
    """Apply ``fn`` to each paragraph, dropping paragraphs that end up empty."""
    paragraphs = [fn(p) for p in str(text or "").split("\n\n")]
    return "\n\n".join(p.strip() for p in paragraphs if p and p.strip())


def strip_internal_paragraphs(text: Any) -> str:
    """:func:`strip_internal_language` that keeps the paragraph structure."""
    return map_paragraphs(text, strip_internal_language)


# ---------------------------------------------------------------------------
# Semantic QA: do the claims in the prose follow from the source facts?
# ---------------------------------------------------------------------------

BLOCKING_KINDS = frozenset({"history", "class_lore", "faction", "named_entity"})

_CLASSES = (
    "paladin", "warlock", "wizard", "rogue", "ranger", "cleric", "fighter", "bard", "druid",
    "monk", "sorcerer", "barbarian", "artificer",
)
# A claim is not a claim when it is negated right where it is made ("no prior
# relationship is assumed").  Modal framing ("may", "whether", "if") also makes a
# sentence hypothetical, except for presuppositions such as "will settle an old
# debt", which assert the debt exists - those patterns are ``strong``.
_NEGATION = re.compile(
    r"\b(?:no|not|never|without|nothing|none|neither|nor|assum\w*|unknown|undecided|rather than)\b|n't",
    re.I,
)
# "...but nothing establishes one", "no debt is assumed": the sentence disclaims the claim.
_DISCLAIMER = re.compile(
    r"\bnothing (?:has |yet )?establish\w*|\bnot (?:yet )?establish\w*|\bassum(?:e|es|ed|ing|ption)\b|\bno\b[^.!?]{0,40}\b(?:is|has been|are) established\b",
    re.I,
)
_MODAL = re.compile(
    r"\b(?:unless|if|whether|may|might|could|can decide|can choose|player'?s choice)\b",
    re.I,
)
_NAME_POSSESSIVE = r"(?:(?-i:[A-Z][\w-]*['’]s)|their|his|her|your|my)"
# (pattern, strong)
_HISTORY_PATTERNS: tuple[tuple[re.Pattern[str], bool], ...] = tuple(
    (re.compile(p, re.I), strong)
    for p, strong in (
        (r"\bowes?\s+(?:a|an|the)?\s*(?:old\s+)?(?:debt|favou?r|life)\b[^.!?]{0,60}", True),
        (r"\bowed\s+(?:a|an|the)?\s*(?:old\s+)?(?:debt|favou?r|life)\b[^.!?]{0,60}", True),
        (r"\b(?:old|ancient|unpaid|hidden|secret)\s+debts?\b", True),
        (r"\bdebts?\s+(?:older|owed|unpaid)\b|\b(?:hid(?:ing|es|den)|settle[sd]?|repay(?:ing|s)?)\s+(?:a\s+|an\s+|the\s+)?(?:\w+\s+)?debts?\b", True),
        (r"\bold\s+(?:friend|rival|ally|enemy|flame|oath|grudge|wound|mentor)\b[^.!?]{0,40}", False),
        (r"\b(?:swore|sworn|broke|broken|betrayed|abandoned)\s+(?:an?\s+|the\s+|his\s+|her\s+|their\s+|my\s+)?(?:oath|vow|pact|promise)\b[^.!?]{0,50}", False),
        (rf"\b{_NAME_POSSESSIVE}\s+(?:patron|mentor|sibling|brother|sister|mother|father|spouse|lover|master)\b[^.!?]{{0,50}}", False),
        (r"\bonce\s+(?:served|knew|loved|trusted|fought|helped|saved)\b[^.!?]{0,50}", False),
        (r"\b(?:was|were)\s+(?:raised|trained|taught)\s+by\b[^.!?]{0,40}", False),
        (r"\bprior\s+(?:relationship|history|connection)\b[^.!?]{0,40}", False),
        (r"\b(?:remembers?|recalls?)\s+(?:this|the|that)\b[^.!?]{0,40}\bfrom\s+(?:years|long|before|another|their|his|her)\b[^.!?]{0,40}", False),
    )
)
_FACTION_CAPITAL = re.compile(
    r"\b(?:the\s+)?((?:[A-Z][\w'’-]+\s+){1,3}(?:Guild|Order|Cult|House|Clan|Council|Brotherhood|Syndicate|Watch|"
    r"Wardens?|Company|Circle|Covenant|Conclave|Court|Legion|Militia|Compact))\b"
    r"|\b((?:Guild|Order|Cult|House|Clan|Council|Brotherhood|Syndicate|Company|Circle|Covenant|Conclave|Court|Legion|Compact)"
    r"\s+of\s+(?:the\s+)?[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){0,2})\b"
)
_FACTION_GENERIC = re.compile(
    r"\b(guilds?|factions?|cults?|councils?|syndicates?|brotherhoods?|clans?|cabals?|covens?|conclaves?)\b", re.I
)
# Institutions the fallback templates have been caught inserting from one keyword.
_INSTITUTION_PHRASES = re.compile(
    r"\b(wardens|refuge keepers|harbor office|civic watch|local authority|envoy guard|observatory staff)\b", re.I
)
_TITLED_NAME = re.compile(
    r"\b(?:Captain|Lord|Lady|Warden|Master|Elder|Sergeant|Commander|General|King|Queen|Duke|Duchess|Count|Baron|"
    r"Brother|Sister|Father|Mother|Magister|Inquisitor|Envoy|Archivist|Quartermaster|Reeve|Marshal)\s+"
    r"([A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+)?)\b"
)
_CAP_PHRASE = re.compile(r"\b([A-Z][a-z'’-]+(?:\s+(?:of|the)\s+[A-Z][a-z'’-]+|\s+[A-Z][a-z'’-]+){0,3})\b")
_COMMON_CAPS = frozenset({
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march",
    "april", "may", "june", "july", "august", "september", "october", "november", "december", "north", "south",
    "east", "west", "i", "the", "a", "an", "what", "who", "where", "when", "why", "how", "it", "he", "she", "they",
    "we", "you", "his", "her", "their", "this", "that", "these", "those", "there", "here", "then", "but", "and",
    "or", "if", "as", "at", "by", "in", "on", "of", "to", "no", "yes", "one", "two", "three", "every", "some",
    "dawn", "dusk", "noon", "midnight", "winter", "summer", "spring", "autumn", "fall",
})
_LEADING_DETERMINER = re.compile(r"^(?:The|A|An)\s+")
# Capitalized words that ordinarily open a sentence without being a name.
_SENTENCE_STARTERS = frozenset(w.lower() for w in (
    "after", "again", "all", "although", "always", "among", "another", "any", "anyone", "around", "as", "at", "before",
    "behind", "below", "beneath", "beside", "between", "beyond", "both", "but", "by", "each", "either", "even",
    "every", "everyone", "everything", "few", "for", "from", "here", "however", "in", "inside", "instead", "just",
    "last", "many", "maybe", "meanwhile", "more", "most", "much", "neither", "next", "no", "nobody", "nothing",
    "now", "of", "on", "once", "one", "only", "other", "others", "outside", "over", "perhaps", "several", "since",
    "so", "some", "someone", "something", "soon", "still", "suddenly", "such", "that", "then", "there", "these",
    "they", "this", "those", "through", "throughout", "to", "today", "tonight", "under", "until", "up", "very",
    "what", "when", "where", "which", "while", "who", "why", "with", "within", "without", "you", "your",
    "rain", "snow", "smoke", "wind", "fog", "mist", "dust", "ash", "silence", "darkness", "light", "shadow",
    "shadows", "night", "morning", "evening", "cold", "heat", "steam", "blood", "fire", "flames", "thunder",
    "lightning", "water", "mud", "ice", "frost", "sunlight", "moonlight", "lantern", "lanterns", "torch", "candle",
    "bells", "voices", "footsteps", "people", "travelers", "guards", "crowds", "merchants", "children", "salt",
    "wet", "dry", "old", "new", "fresh", "heavy", "thin", "quiet", "slowly", "quickly", "carefully", "gently",
))
# A name is usually followed by a verb: "Vell watches the gate", "Mara slammed the door".
_VERB_AFTER_NAME = re.compile(r"^\s+[a-z]+(?:s|ed|es)\b")


def _sentence_start(body: str, index: int) -> bool:
    prefix = body[:index].rstrip(" \t\"'“‘(")
    return not prefix or prefix[-1] in ".!?:\n"


def _supported(claim_tokens: set[str], support: set[str], threshold: float) -> bool:
    if not claim_tokens:
        return True
    return len(claim_tokens & support) / len(claim_tokens) >= threshold


def _claim(kind: str, text: str, reason: str) -> dict[str, str]:
    return {"kind": kind, "text": clean_text(text), "reason": reason, "blocking": "yes" if kind in BLOCKING_KINDS else "no"}


def find_unsupported_claims(
    text: Any,
    intent: OpeningIntent,
    *,
    allow: Iterable[str] = (),
    classes: Iterable[str] = _CLASSES,
) -> list[dict[str, str]]:
    """Claims in ``text`` that do not follow from the facts in ``intent``.

    * ``history`` / ``class_lore`` claims need *established* support.  A seed or
      a provisional elaboration can never vouch for a relationship, a debt, or
      what a class "just knows".
    * ``faction`` and ``named_entity`` claims may be supported by any fact,
      including explicitly provisional ones (which the trace reports).
    * Hedged / negated sentences ("no prior relationship is assumed") are not
      claims and are skipped.
    """
    body = str(text or "")
    if not body.strip():
        return []
    any_support = intent.tokens() | intent.allowed_tokens() | {t for a in allow for t in content_tokens(a)}
    established = intent.tokens(established_only=True) | intent.allowed_tokens() | {
        t for a in allow for t in content_tokens(a)
    }
    claims: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def record(kind: str, span: str, reason: str) -> None:
        key = (kind, clean_text(span).lower())
        if key not in seen:
            seen.add(key)
            claims.append(_claim(kind, span, reason))

    class_alt = "|".join(re.escape(c) for c in classes)
    class_lore = re.compile(
        rf"\b(?:as an?\s+)?(?:{class_alt})(?:'s|’s)?\b[^.!?]{{0,80}}?\b(?:knows?|recogni[sz]es?|senses?|remembers?|"
        rf"understands?|realizes?|can tell|instantly|immediately)\b[^.!?]{{0,100}}",
        re.I,
    )
    # A class's concepts (oath, pact, patron, rite) reacting to the scene, or a
    # character perceiving a supernatural property of an object, are world
    # facts the player never established.
    concept_lore = re.compile(
        r"\b(?:oath|vow|pact|patron|rite|prayer|formulae|sigil)s?\b[^.!?]{0,50}\b(?:stirs?|whispers?|answers?|demands?|"
        r"warns?|names?|recogni[sz]es?|senses?|notices?)\b[^.!?]{0,80}"
        r"|\b(?:feels?|senses?|notices?|recogni[sz]es?|perceives?)\b[^.!?]{0,40}\b(?:answer|pressure|power|magic|curse|"
        r"aura|binding|taint|bargain|debt|formulae|ward)\b[^.!?]{0,60}",
        re.I,
    )

    def negated(sentence: str, start: int) -> bool:
        return bool(_NEGATION.search(sentence[max(0, start - 40):start]))

    for sentence in split_sentences(body):
        if _DISCLAIMER.search(sentence):
            continue
        modal = bool(_MODAL.search(sentence))
        hedged = modal or bool(_NEGATION.search(sentence))

        for pattern, strong in _HISTORY_PATTERNS:
            for match in pattern.finditer(sentence):
                if negated(sentence, match.start()) or (modal and not strong):
                    continue
                span = match.group(0)
                if not _supported(content_tokens(span), established, 0.7):
                    record("history", span, "personal history is not in any established fact")
        if not modal:
            for pattern in (class_lore, concept_lore):
                for match in pattern.finditer(sentence):
                    if negated(sentence, match.start()):
                        continue
                    span = match.group(0)
                    tokens = content_tokens(span) - {_stem(c) for c in classes}
                    if not _supported(tokens, established, 0.7):
                        record("class_lore", span, "a character class cannot establish world facts or secret knowledge")

        named_faction = False
        for match in _FACTION_CAPITAL.finditer(sentence):
            named_faction = True
            name = clean_text(match.group(1) or match.group(2))
            name = _LEADING_DETERMINER.sub("", name)
            if not _supported(content_tokens(name), any_support, 1.0):
                record("faction", name, "faction or institution is not in the source facts")
        if not hedged and not named_faction:
            for match in _FACTION_GENERIC.finditer(sentence):
                if _stem(match.group(1).lower()) not in any_support:
                    record("faction", sentence, "faction language appears without a source faction")
                    break
            for match in _INSTITUTION_PHRASES.finditer(sentence):
                if not _supported(content_tokens(match.group(1)), any_support, 1.0):
                    record("faction", match.group(1), "institution is not in the source facts")



        for match in _TITLED_NAME.finditer(sentence):
            name = clean_text(match.group(0))
            if not _supported(content_tokens(match.group(1)), any_support, 1.0):
                record("named_entity", name, "named character is not in the source facts")

    class_words = {c.lower() for c in classes}
    for match in _CAP_PHRASE.finditer(body):
        phrase = _LEADING_DETERMINER.sub("", match.group(1))
        words = phrase.split()
        if not words:
            continue
        if all(w.lower() in class_words for w in words):
            continue  # a class label is a role, not a named entity
        starts = _sentence_start(body, match.start())
        if len(words) == 1 and words[0].lower() in _COMMON_CAPS:
            continue
        if len(words) == 1 and starts:
            # "Vell watches the gate." opens with an invented name; "Smoke curls ..." does not.
            if words[0].lower() in _SENTENCE_STARTERS or not _VERB_AFTER_NAME.match(body[match.end():match.end() + 24]):
                continue
        if _FACTION_CAPITAL.search(phrase) or _TITLED_NAME.search(phrase):
            continue  # already judged above
        tokens = content_tokens(phrase)
        if tokens and not _supported(tokens, any_support, 1.0):
            record("named_entity", phrase, "name does not appear in the source facts")
    return claims


def blocking_claims(claims: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return [c for c in claims if c.get("blocking") == "yes"]


def strip_unsupported_sentences(text: Any, claims: Iterable[dict[str, str]]) -> str:
    """Remove each sentence that contains an unsupported claim."""
    spans = [c["text"].lower() for c in claims if c.get("text")]
    if not spans:
        return str(text or "")
    kept = [s for s in split_sentences(str(text or "")) if not any(span in s.lower() for span in spans)]
    return " ".join(kept).strip()


def semantic_report(text: Any, intent: OpeningIntent, *, allow: Iterable[str] = ()) -> dict[str, Any]:
    """QA-friendly summary: ``ok`` is False when any blocking claim is unsupported."""
    claims = find_unsupported_claims(text, intent, allow=allow)
    leaks = find_internal_language(text)
    malformed = find_malformed_sentences(text)
    blocking = blocking_claims(claims)
    return {
        "ok": not blocking and not leaks and not malformed,
        "claims": claims,
        "blocking": blocking,
        "internal_language": leaks,
        "malformed": malformed,
    }


# ---------------------------------------------------------------------------
# Source trace: which fact produced each opening card?
# ---------------------------------------------------------------------------

def build_source_trace(
    cards: dict[str, Any],
    intent: OpeningIntent,
    *,
    allow_provisional: bool = True,
    traced_threshold: float = 0.75,
) -> dict[str, Any]:
    """Explain where every player-facing card came from.

    Each entry reports the strongest supporting fact(s) and a ``status``:

    * ``traced`` - the card follows from existing facts (provenance reported),
    * ``provisional`` - the card is an explicit elaboration; it is recorded as
      ``generated_provisional`` and derived from its closest fact,
    * ``unsupported`` - nothing in the intent supports it (and provisional
      elaboration was not allowed for this caller).
    """
    facts = intent.facts()
    entries: list[dict[str, Any]] = []
    for card, raw in cards.items():
        text = clean_text(raw)
        if not text:
            continue
        tokens = content_tokens(text)
        scored: list[tuple[int, int, Fact]] = []
        for fact in facts:
            overlap = len(tokens & content_tokens(fact.text))
            if overlap:
                scored.append((overlap, AUTHORITY[fact.provenance], fact))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        union: set[str] = set()
        for fact in facts:
            union |= content_tokens(fact.text)
        coverage = (len(tokens & union) / len(tokens)) if tokens else 1.0
        primary = scored[0][2] if scored else None
        if coverage >= traced_threshold and primary is not None:
            entry = {
                "status": "traced",
                "provenance": primary.provenance,
                "sources": [s[2].id for s in scored[:3]],
                "source_text": primary.text,
            }
        elif allow_provisional:
            entry = {
                "status": "provisional",
                "provenance": "generated_provisional",
                "sources": [primary.id] if primary else [],
                "source_text": primary.text if primary else "",
            }
        else:
            entry = {"status": "unsupported", "provenance": "unsupported", "sources": [], "source_text": ""}
        entries.append({"card": card, "text": text, "coverage": round(coverage, 2), **entry})
    summary = {
        "traced": sum(1 for e in entries if e["status"] == "traced"),
        "provisional": sum(1 for e in entries if e["status"] == "provisional"),
        "unsupported": sum(1 for e in entries if e["status"] == "unsupported"),
    }
    return {
        "entries": entries,
        "summary": summary,
        "facts": [f.model_dump() for f in facts],
        "unknowns": [u.model_dump() for u in intent.unknowns],
    }
