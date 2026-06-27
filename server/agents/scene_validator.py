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


def validate_campaign_expectations(
    narrative_text: str,
    campaign_contract: dict | None = None,
    *,
    invented_entities: list[str] | None = None,
) -> dict:
    """Validate a scene against the persistent Campaign Contract.

    This augments the generic quality score with campaign-specific expectations:
    canon strictness, mystery pacing, agency, tone, and backstory boundaries.
    """
    contract = campaign_contract or {}
    policy = contract.get("validator_policy") or {}
    canon = contract.get("canon_policy") or {}
    backstory = contract.get("backstory_policy") or {}
    text = narrative_text or ""
    lower = text.lower()
    failed: list[str] = []
    canon_violations: list[str] = []
    backstory_violations: list[str] = []
    agency_issues: list[str] = []
    tone_issues: list[str] = []

    if policy.get("reject_single_solution", True):
        forced_phrases = ["must go", "must follow", "must ask", "only way", "no choice", "have to obey"]
        if any(p in lower for p in forced_phrases):
            agency_issues.append("single_solution")

    if policy.get("require_concrete_clues"):
        clue_words = ["clue", "mark", "track", "receipt", "letter", "symbol", "stain", "footprint", "witness", "record"]
        if not any(w in lower for w in clue_words):
            failed.append("missing_concrete_clue")

    if policy.get("preserve_unanswered_questions"):
        reveal_phrases = ["the truth is", "it was all", "the real culprit is", "the central mystery is solved"]
        if any(p in lower for p in reveal_phrases):
            failed.append("premature_central_reveal")

    if canon.get("mode") == "strict_canon" and policy.get("flag_major_inventions", True):
        invented = [e for e in (invented_entities or []) if e]
        if invented:
            canon_violations.append(f"strict_canon_invention_requires_approval: {', '.join(invented[:5])}")
        major_words = ["new kingdom", "new god", "ancient empire", "forgotten pantheon", "secret faction"]
        if any(w in lower for w in major_words):
            canon_violations.append("strict_canon_major_lore_invention")

    protect_family = backstory.get("allow_family_danger") is False or backstory.get("protect_family_content") is True
    if protect_family and any(p in lower for p in ("your mother is in danger", "your father is in danger", "your family will die", "sibling hostage", "mother is murdered", "father is murdered")):
        backstory_violations.append("family_danger_requires_permission")
    if backstory.get("allow_secret_reveals") == "with_setup" and any(p in lower for p in ("your secret is revealed", "everyone learns your secret")):
        backstory_violations.append("secret_reveal_requires_setup")

    rating = (contract.get("safety_policy") or {}).get("content_rating")
    if rating == "family" and any(p in lower for p in ("gore", "entrails", "explicit torture")):
        tone_issues.append("Family content rating conflicts with graphic violence.")

    failed_expectations = failed + agency_issues + canon_violations + backstory_violations + tone_issues
    score = max(0, 100 - (15 * len(failed_expectations)))
    return {
        "score": score,
        "failed_expectations": failed_expectations,
        "canon_violations": canon_violations,
        "backstory_boundary_violations": backstory_violations,
        "agency_issues": agency_issues,
        "tone_issues": tone_issues,
        "recommended_fix": "Revise the scene to obey the campaign contract." if failed_expectations else "",
    }


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
    loc = location_name or "the current location"
    # Fallback NPC must be named, but must not drag old canned content into new campaigns.
    npc = npc_name if npc_name else "Mira Vale"
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

    premise_hay = " ".join([
        loc,
        campaign_name or "",
        inciting_incident or "",
        central_conflict or "",
        immediate_stakes or "",
    ]).lower()
    if any(w in premise_hay for w in ("slave army", "forced army", "pressed army", "conscript", "escape", "pursuit")):
        evidence_object = "fresh bootprints pressed into the needle-strewn mud beside a snapped branch"
        sensory = sensory_detail or "Cold sap, wet bark, and old campfire ash hang under the trees"
        return (
            f"{sensory.rstrip('.')} at {loc}; the hidden camp is quiet except for breath held too long and canvas stirred by the north wind.\n\n"
            f"{npc} arrives {state}, one hand clamped around a torn strip of army cloth, and points to {evidence_object} where {pc} can see it.\n\n"
            f'"{incident_line}," {npc} says, voice barely above the creak of branches. '
            f'"They should not be this close unless someone found our trail."\n\n'
            f"{conflict_evidence}. {stakes_line}, and the next choice is no longer theoretical: "
            f"break camp, hide and watch, or turn the woods themselves into a false trail."
        )

    evidence_object = "a sealed packet marked with a symbol no one nearby wants to explain"
    if any(w in (campaign_name or "").lower() for w in ("winter", "frost", "ice", "snow")):
        evidence_object = "a frost-stiff packet wrapped around a shard of dark glass"
    elif any(w in (campaign_name or "").lower() for w in ("fire", "ember", "ash", "burn")):
        evidence_object = "a scorched ledger page curled around a brass token"
    elif any(w in (campaign_name or "").lower() for w in ("storm", "rain", "flood")):
        evidence_object = "a waterlogged dispatch tube sealed with split red wax"

    return (
        f"{sensory.rstrip('.')} at {loc}; conversation falters as attention turns toward the same point of trouble.\n\n"
        f"{npc} arrives {state}, and sets down {evidence_object} where {pc} can see it.\n\n"
        f'"{incident_line}," {npc} says, voice low enough that the nearest witnesses lean in. '
        f'"This was not supposed to reach us like this."\n\n'
        f"{conflict_evidence}. {stakes_line}, and everyone nearby is already deciding who will risk being seen helping."
    )
