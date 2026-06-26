"""Scene quality validator — scores narrative text and flags generic/low-quality output.

Minimum acceptable score: 75.
  < 75 on first try → retry Narrative Agent with validator feedback injected
  < 75 after retry  → use deterministic fallback template populated from Scene Director JSON
"""
from __future__ import annotations

import re

# Phrases that indicate meta-genre framing instead of in-world scene writing
FORBIDDEN_PHRASES: list[str] = [
    "heroic fantasy adventure",
    "high fantasy",
    "mysterious threat looms",
    "mysterious threat",
    "choices matter",
    "outcomes stay flexible",
    "the world is dangerous",
    "an urgent request appears",
    "urgent request",
    "the stakes are personal",
    "adventure begins",
    "paths branch ahead",
    "moment holds",
    "waiting for what comes next",
    "at here",
    "genre",
    "campaign",
    "you see a",
]

# Patterns that mark a sentence as abstract/meta rather than concrete in-world prose
_ABSTRACT_PATTERNS: list[str] = [
    r"\b(campaign|adventure|story|narrative)\b.{0,50}(begins|unfolds|awaits|is set)",
    r"(paths|choices|options)\s+(branch|await|lie ahead)",
    r"the\s+(world|land|realm|age)\s+(is|was|turns|grows)\s+(dark|dangerous|vast|mysterious)",
    r"\bgenre\b",
    r"you\s+see\s+a\s+\w+\s+fantasy",
    r"this\s+is\s+a\s+\w+\s+(rpg|campaign|adventure|session)",
]

# Concrete action words that indicate a real conflict is described
_CONFLICT_WORDS = re.compile(
    r"\b(vanished|missing|dead|killed|attacked|stolen|burning|collapsed|wounded|fled|warned|"
    r"murdered|arrested|betrayed|escaped|ambushed|revealed|discovered|destroyed|poisoned|"
    r"kidnapped|trapped|threatened|chased|broke|fell|crashed|exploded|bleeding)\b",
    re.IGNORECASE,
)

# Physical sensory words
_SENSORY_WORDS = re.compile(
    r"\b(smell|scent|reek|stench|sound|noise|echo|silence|creak|groan|cold|warm|heat|"
    r"dust|smoke|mud|blood|damp|mist|rain|wind|rough|worn|cracked|flickering|shadows|"
    r"glare|lantern|torch|distant|bitter|acrid|damp|frost|ash|soot)\b",
    re.IGNORECASE,
)

_PROPER_STOP = {
    "The", "And", "But", "For", "With", "From", "That", "This", "They", "Their",
    "You", "Your", "Has", "Have", "Had", "Was", "Were", "Are", "Him", "Her", "His",
    "What", "When", "Where", "Who", "Why", "How", "Its",
}

MINIMUM_SCORE = 75


def _count_abstract_sentences(text: str) -> int:
    count = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if any(re.search(p, sentence, re.IGNORECASE) for p in _ABSTRACT_PATTERNS):
            count += 1
    return count


def _real_proper_nouns(text: str) -> list[str]:
    found = re.findall(r"\b[A-Z][a-z]{2,}\b", text)
    return [n for n in found if n not in _PROPER_STOP]


def validate_scene_quality(
    narrative_text: str,
    location_name: str = "",
    npc_name: str = "",
    player_name: str = "",
    conflict: str = "",
    campaign_entities: list[str] | None = None,
) -> tuple[int, list[str]]:
    """Score a scene narrative 0–100. Returns (score, issues_list).

    Scoring criteria:
      +15  named location present in text
      +15  named NPC from scene director present (or +8 for any proper-name pair)
      +20  concrete conflict action word detected
      +10  player character named directly
      +10  sensory detail present
      +10  player-facing question at end
      +10  campaign memory entity referenced
      +10  no forbidden generic phrases

    Penalties:
      -25  any forbidden generic phrase
      -15  'mysterious threat' without specifics
      -15  'urgent request' without a named requester
      -25  fewer than 2 proper nouns total
      -20  2+ abstract/meta sentences
    """
    score = 0
    issues: list[str] = []
    tl = narrative_text.lower()
    if "moment holds" in tl or "waiting for what comes next" in tl or "at here" in tl:
        return 0, ["Placeholder narrative returned instead of playable scene content"]

    # --- Positive criteria ---

    if location_name and location_name.lower() in tl:
        score += 15
    else:
        issues.append(f"Named location '{location_name or '(none)'}' not found in narrative")

    if npc_name and npc_name.lower() in tl:
        score += 15
    else:
        pairs = re.findall(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b", narrative_text)
        if pairs:
            score += 8
            issues.append(f"Scene-director NPC '{npc_name or '(none)'}' not named; found other proper names")
        else:
            issues.append(f"No named NPC visible (expected '{npc_name or '?'}')")

    if _CONFLICT_WORDS.search(narrative_text):
        score += 20
    elif conflict and any(w.lower() in tl for w in conflict.split()[:6] if len(w) > 4):
        score += 10
        issues.append("Conflict present but not rendered with concrete action word")
    else:
        issues.append("No concrete conflict action detected in narrative")

    if player_name and player_name.lower() in tl:
        score += 10
    else:
        issues.append(f"Player character '{player_name or '?'}' not addressed directly")

    if _SENSORY_WORDS.search(narrative_text):
        score += 10
    else:
        issues.append("No concrete sensory detail detected")

    ends_with_question = bool(
        re.search(r"(what (does|do|will|would|should)|how (does|do|will)|what (is|are) your).{3,60}\?", tl)
        or tl.rstrip().endswith("?")
    )
    if ends_with_question:
        score += 10
    else:
        issues.append("No player-facing question or prompt at end")

    if campaign_entities:
        used = sum(1 for e in campaign_entities if e and e.lower() in tl)
        if used > 0:
            score += 10
        else:
            issues.append("No campaign memory entities referenced")
    else:
        score += 5  # neutral — nothing to check against

    forbidden_hits = [p for p in FORBIDDEN_PHRASES if p.lower() in tl]
    if not forbidden_hits:
        score += 10
    else:
        issues.append(f"Generic forbidden phrases: {', '.join(forbidden_hits[:3])}")

    # --- Penalties ---

    if forbidden_hits:
        score -= 25

    if "mysterious threat" in tl:
        if not re.search(r"mysterious (threat|figure|stranger) (named|called|known as|of [A-Z]|in [A-Z])", tl):
            score -= 15
            issues.append("'Mysterious threat' used without specifics")

    if "urgent request" in tl:
        if not re.search(r"urgent request (from|by) [A-Z]", narrative_text):
            score -= 15
            issues.append("'Urgent request' without a named requester")

    proper = _real_proper_nouns(narrative_text)
    if len(proper) < 2:
        score -= 25
        issues.append(f"Only {len(proper)} proper noun(s) — narrative likely has no named entities")

    abstract_count = _count_abstract_sentences(narrative_text)
    if abstract_count >= 2:
        score -= 20
        issues.append(f"{abstract_count} abstract/meta sentences detected")

    return max(0, min(100, score)), issues


def build_retry_feedback(issues: list[str], score: int, location_name: str, npc_name: str, player_name: str) -> str:
    """Format validator feedback for the Narrative Agent retry prompt."""
    lines = [
        f"QUALITY CHECK FAILED (score {score}/{MINIMUM_SCORE} required). Rewrite the scene fixing these issues:",
    ]
    for issue in issues:
        lines.append(f"  — {issue}")
    lines.append("")
    lines.append("REQUIRED fixes:")
    if location_name:
        lines.append(f"  — Mention '{location_name}' by name in the opening sentence")
    if npc_name:
        lines.append(f"  — Name '{npc_name}' directly in the scene")
    if player_name:
        lines.append(f"  — Address '{player_name}' directly in the closing prompt")
    lines.append("  — Include at least one concrete sensory detail (what you see, smell, or hear right now)")
    lines.append("  — Describe the conflict with a specific visible action or piece of evidence")
    lines.append("  — End with a player-facing question")
    lines.append("  — Do NOT describe the genre, campaign structure, or adventure tone")
    return "\n".join(lines)


_FALLBACK_FORBIDDEN = [
    "fantasy world", "dark-fantasy", "dark fantasy", "heroic fantasy",
    "the region demands", "demands the party", "the party",
    "genre", "campaign", "adventure begins",
    "[simulation state]",
    "i kneel",
    "i ask",
    "i scan",
    "i quietly",
    "i tell",
    "i compare",
    "i prepare",
    "i send",
    "i turn",
    "[character:",  # unresolved template token from a weak LLM generation
]


def _sdd_field_clean(text: str) -> str:
    """Return text if clean, empty string if it contains forbidden abstract phrases."""
    if not text:
        return ""
    if "\n" in text:
        return ""
    tl = text.lower()
    if text.strip().startswith("{") or text.strip().startswith("[") or "campaign_day" in tl or "elapsed_minutes" in tl:
        return ""
    if any(p in tl for p in _FALLBACK_FORBIDDEN):
        return ""
    return text


def build_fallback_scene(
    location_name: str,
    npc_name: str,
    player_name: str,
    emotional_state: str,
    inciting_incident: str,
    central_conflict: str,
    immediate_stakes: str,
    sensory_detail: str = "",
    campaign_name: str = "",
) -> str:
    """Return a quality-guaranteed opening scene from template + Scene Director data.

    Used when two Narrative Agent attempts both score below MINIMUM_SCORE.
    Template follows the Golden Scene Rule: named location, sensory detail, visible event,
    named NPC entering through action, specific problem, concrete stakes, player-facing decision.
    """
    loc = location_name or "the inn"
    # Fallback NPC must be named — never "A figure nearby"
    npc = npc_name if npc_name else "Torven"
    pc = player_name or "you"
    state = emotional_state or "out of breath, eyes wide"

    # Clean forbidden phrases from all input fields before embedding in prose
    inciting_incident = _sdd_field_clean(inciting_incident)
    central_conflict = _sdd_field_clean(central_conflict)
    immediate_stakes = _sdd_field_clean(immediate_stakes)

    # Derive sensory atmosphere from campaign name keywords when no explicit detail is given
    if not sensory_detail and campaign_name:
        name_lower = campaign_name.lower()
        if any(w in name_lower for w in ("winter", "howl", "frost", "cold", "snow", "blizzard", "ice")):
            sensory_detail = "The wind howls through the shutters and frost creeps along the windowpanes"
        elif any(w in name_lower for w in ("dark", "shadow", "night", "midnight", "dusk", "black")):
            sensory_detail = "The torchlight gutters in the draft, casting lurching shadows across the walls"
        elif any(w in name_lower for w in ("fire", "flame", "ember", "ash", "burn")):
            sensory_detail = "Smoke stings the eyes and the air tastes of char"
        elif any(w in name_lower for w in ("storm", "thunder", "rain", "flood", "tempest")):
            sensory_detail = "Rain hammers against the shutters and the floor planks are slick with mud"
    sensory = sensory_detail or "Cold air bites through the cracks in the shutters."

    def _cap(s: str) -> str:
        """Capitalize only the first character, preserving proper nouns in the rest."""
        return s[0].upper() + s[1:] if s else s

    # Inciting incident should be a concrete event, not a vague description
    if inciting_incident and len(inciting_incident) > 10:
        incident_line = _cap(inciting_incident.rstrip("."))
    else:
        incident_line = f"Something has gone very wrong at {loc}"

    # Conflict as physical evidence, not summary
    if central_conflict and len(central_conflict) > 10:
        conflict_evidence = _cap(central_conflict.rstrip("."))
    else:
        conflict_evidence = f"The trouble that brought {npc} here is not finished"

    # Stakes must name who suffers — strip abstract "if nothing is done" framing
    if immediate_stakes and len(immediate_stakes) > 10:
        stakes_text = immediate_stakes.strip().rstrip(".")
        for prefix in ("if no one acts,", "if nothing is done:", "if nothing changes,"):
            if stakes_text.lower().startswith(prefix):
                stakes_text = stakes_text[len(prefix):].strip()
        stakes_line = _cap(stakes_text)
    else:
        stakes_line = "What happens next will be hard to undo"

    evidence_object = "a cracked lantern wrapped in a torn strip of harness leather"
    if any(w in (campaign_name or "").lower() for w in ("winter", "frost", "ice", "snow")):
        evidence_object = "a frozen lantern with dark wool caught in its hinge"
    elif any(w in (campaign_name or "").lower() for w in ("fire", "ember", "ash", "burn")):
        evidence_object = "a scorched ledger page curled around a brass token"
    elif any(w in (campaign_name or "").lower() for w in ("storm", "rain", "flood")):
        evidence_object = "a waterlogged dispatch tube sealed with split red wax"

    return (
        f"{sensory.rstrip('.')} at {loc}; every table goes quiet as the door bangs open.\n\n"
        f"{npc} stumbles inside, {state}, and drops {evidence_object} where {pc} can see it.\n\n"
        f'"{incident_line}," {npc} says, voice low enough that the nearest patrons lean in. '
        f'"This was not supposed to come back without its owner."\n\n'
        f"{conflict_evidence}. {stakes_line}, and the room is already deciding who will risk being seen helping."
    )
