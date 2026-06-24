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


def build_fallback_scene(
    location_name: str,
    npc_name: str,
    player_name: str,
    emotional_state: str,
    inciting_incident: str,
    central_conflict: str,
    immediate_stakes: str,
    sensory_detail: str = "",
) -> str:
    """Return a quality-guaranteed opening scene from template + Scene Director data.

    Used when two Narrative Agent attempts both score below MINIMUM_SCORE.
    """
    loc = location_name or "the tavern"
    npc = npc_name or "A figure nearby"
    pc = player_name or "You"
    sensory = sensory_detail or "The air is cold and still."
    incident = inciting_incident or "Something has gone wrong."
    conflict = central_conflict or "The situation is dangerous."
    stakes = immediate_stakes or "Time is running out."
    state = emotional_state or "urgent and pale"

    return (
        f"At {loc}, {sensory}\n\n"
        f"{npc} pushes through the crowd toward {pc}, {state}.\n\n"
        f"\"{incident}\"\n\n"
        f"{conflict}\n\n"
        f"If nothing is done: {stakes}\n\n"
        f"What does {pc} do?"
    )
