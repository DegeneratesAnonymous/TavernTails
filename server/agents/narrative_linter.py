"""Narrative quality linter and scene validator.

Enforces professional RPG narrative standards — concrete events, named NPCs,
specific stakes, and zero generic fantasy boilerplate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Banned phrase lists
# ---------------------------------------------------------------------------

BANNED_GENERIC: list[str] = [
    "heroic fantasy",
    "epic fantasy",
    "high fantasy",
    "dark fantasy world",
    "dark-fantasy",
    "fantasy world",
    "mysterious threat",
    "a disturbance",
    "urgent request",
    "the region demands attention",
    "demands the party",
    "demands your attention",
    "choices matter",
    "outcomes stay flexible",
    "danger looms",
    "the world is dangerous",
    "personal stakes",
    "the adventure begins",
    "a figure approaches",
    "a nearby figure",
    "an old acquaintance",
    "the party must",
    "a dark force",
    "evil is stirring",
    "disturbing the peace",
    "something stirs",
    "something is wrong",
    "something is amiss",
    "unrest grows",
    "threatens the peace",
    "broken the routine",
    "routine of the inn",
    "routine of the",
]

BANNED_META: list[str] = [
    "you are in a fantasy",
    "this adventure",
    "this story",
    "this world",
    "the players",
    "the party",
    "the campaign",
    "the narrative",
    "this campaign",
    "in the world of",
    "in this setting",
]

BANNED_ABSTRACT_STAKES: list[str] = [
    "things will get worse",
    "danger is coming",
    "the threat grows",
    "the situation is worsening",
    "the situation will worsen",
    "something must be done",
    "if nothing is done",
    "if no one acts",
    "the situation grows",
    "tensions are rising",
]

# Words that indicate sensory grounding
_SENSORY: list[str] = [
    "smell", "stench", "aroma", "reek", "odor", "scent",
    "sound", "creak", "crack", "clang", "shout", "whisper", "crash", "clatter", "rumble",
    "cold", "warm", "heat", "chill", "frost", "damp", "humid", "sweat",
    "rough", "smooth", "sharp", "slick", "sticky",
    "flicker", "torchlight", "candlelight", "shadow", "moonlight", "darkness", "glare",
    "smoke", "rain", "dust", "mud", "ash", "blood",
    "hearth", "lantern", "torch",
]

# Verbs signalling something actually happens
_VISIBLE_EVENTS: list[str] = [
    "slams", "bursts", "collapses", "rushes", "draws", "strikes", "falls",
    "grabs", "runs", "shouts", "screams", "pulls", "pushes", "throws",
    "breaks", "shatters", "explodes", "crashes", "tumbles", "lunges",
    "drags", "sprints", "staggers", "leaps", "clutches", "hurls", "spills",
    "bleeds", "coughs", "stumbles", "charges", "fires", "swings",
]

# Non-NPC words that look like proper nouns
_NOT_NPC: frozenset[str] = frozenset({
    "The", "At", "In", "On", "If", "A", "An", "What", "How", "Who",
    "Why", "When", "Where", "And", "Or", "But", "For", "So", "Yet",
    "She", "He", "They", "You", "Your", "His", "Her", "Its",
    "Opening", "Scene", "Act", "Part", "Chapter",
})


# ---------------------------------------------------------------------------
# Score result
# ---------------------------------------------------------------------------

@dataclass
class ScoreResult:
    score: int = 0
    failed_checks: list[str] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)
    banned_phrases_found: list[str] = field(default_factory=list)
    has_sensory_detail: bool = False
    has_visible_event: bool = False
    has_named_npc: bool = False
    has_location: bool = False
    has_immediate_problem: bool = False
    passes_threshold: bool = False

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "passes": self.passes_threshold,
            "failed_checks": self.failed_checks,
            "passed_checks": self.passed_checks,
            "banned_phrases_found": self.banned_phrases_found,
            "has_sensory_detail": self.has_sensory_detail,
            "has_visible_event": self.has_visible_event,
            "has_named_npc": self.has_named_npc,
            "has_location": self.has_location,
            "has_immediate_problem": self.has_immediate_problem,
        }


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_scene(text: str, title: str = "", threshold: int = 75) -> ScoreResult:
    """Score a scene text. Returns ScoreResult with detailed breakdown."""
    result = ScoreResult()
    lower_text = text.lower()
    lower_title = title.lower()
    combined = lower_title + " " + lower_text
    score = 0

    # ── Banned phrases (penalties) ──────────────────────────────────────
    for phrase in BANNED_GENERIC:
        if phrase in combined:
            result.banned_phrases_found.append(phrase)
            score -= 25
            result.failed_checks.append(f"Generic phrase: '{phrase}'")

    for phrase in BANNED_META:
        if phrase in combined:
            result.banned_phrases_found.append(phrase)
            score -= 25
            result.failed_checks.append(f"Meta narration: '{phrase}'")

    for phrase in BANNED_ABSTRACT_STAKES:
        if phrase in combined:
            result.banned_phrases_found.append(phrase)
            score -= 15
            result.failed_checks.append(f"Abstract stakes: '{phrase}'")

    # ── Named location +10 ───────────────────────────────────────────────
    location_types = r'\b(inn|tavern|market|tower|dungeon|forest|road|village|city|bridge|cellar|hall|keep|temple|harbor|street|alley|plaza|gate|ruins|manor|warehouse|docks|cave|mine|camp|barracks|shrine|library|bathhouse|harbor|wharf|rooftop)\b'
    if re.search(location_types, lower_text):
        score += 10
        result.has_location = True
        result.passed_checks.append("Location type present")
    elif title and len(title) > 4 and not title.lower().startswith(("scene", "opening")):
        score += 10
        result.has_location = True
        result.passed_checks.append(f"Named location in title: '{title}'")
    else:
        result.failed_checks.append("No named location")

    # ── Sensory detail +10 ───────────────────────────────────────────────
    for word in _SENSORY:
        if word in lower_text:
            score += 10
            result.has_sensory_detail = True
            result.passed_checks.append(f"Sensory detail: '{word}'")
            break
    if not result.has_sensory_detail:
        result.failed_checks.append("No sensory grounding (smell/sound/texture/light)")

    # ── Named NPC +10, unnamed figure -15 ───────────────────────────────
    # Look for capitalised multi-char proper noun not at sentence start
    npc_candidates = re.findall(r'(?<![.!?]\s)(?<!\n)\b([A-Z][a-z]{2,})(?:\s+[A-Z][a-z]{2,})?\b', text)
    named = [n for n in npc_candidates if n not in _NOT_NPC]
    if named:
        score += 10
        result.has_named_npc = True
        result.passed_checks.append(f"Named NPC: '{named[0]}'")
    else:
        score -= 15
        result.failed_checks.append("No named NPC — 'a figure' is not enough")

    # ── Visible event +15 ────────────────────────────────────────────────
    for word in _VISIBLE_EVENTS:
        if word in lower_text:
            score += 15
            result.has_visible_event = True
            result.passed_checks.append(f"Visible event: '{word}'")
            break
    if not result.has_visible_event:
        result.failed_checks.append("No visible event (nothing happens on-screen)")

    # ── Immediate problem +15 ────────────────────────────────────────────
    problem_words = [
        "missing", "wounded", "murdered", "dead ", "fire ", "flood", "stolen",
        "trapped", "bleeding", "collapsed", "burning", "attacked", "poisoned",
        "injured", "dying", "escaped", "arrested", "broken", "destroyed",
        "unconscious", "captured", "fleeing", "pursued", "accused",
    ]
    for w in problem_words:
        if w in lower_text:
            score += 15
            result.has_immediate_problem = True
            result.passed_checks.append(f"Concrete problem: '{w.strip()}'")
            break
    if not result.has_immediate_problem:
        result.failed_checks.append("No immediate concrete problem")

    # ── Player agency / prompt +15 ───────────────────────────────────────
    prompt_matches = re.findall(r'what does\s+\w+\s+do', lower_text)
    if len(prompt_matches) == 1:
        score += 15
        result.passed_checks.append("Player agency prompt (once)")
    elif len(prompt_matches) > 1:
        score -= 10
        result.failed_checks.append(f"Duplicate player prompt ({len(prompt_matches)}x)")
    else:
        # Check for dialogue hook which also signals agency
        if '"' in text or "'" in text:
            score += 8
            result.passed_checks.append("Dialogue hook (implied agency)")

    # ── Specific time-bound stakes +15 ───────────────────────────────────
    if re.search(r'\b(by\s+(dusk|dawn|morning|nightfall|midnight|sunset|noon|tonight)|within\s+\w+\s+(hours?|minutes?|days?))\b', lower_text):
        score += 15
        result.passed_checks.append("Time-bound stakes")
    elif re.search(r'\b(before|unless|until|if\s+\w+\s+(doesn|don\'t|fail|act))', lower_text):
        score += 8
        result.passed_checks.append("Conditional stakes")

    result.score = score
    result.passes_threshold = score >= threshold
    return result


def feedback_for_regeneration(result: ScoreResult) -> str:
    """Build a concise correction string to inject into a retry prompt."""
    lines = ["SCENE QUALITY CORRECTIONS REQUIRED:"]
    for check in result.failed_checks[:6]:
        lines.append(f"  — {check}")
    if result.banned_phrases_found:
        lines.append(f"  — Remove these generic phrases: {', '.join(repr(p) for p in result.banned_phrases_found[:4])}")
    lines.append("")
    lines.append("Fix these specific issues in your rewrite. Do not repeat the same phrasing.")
    return "\n".join(lines)
