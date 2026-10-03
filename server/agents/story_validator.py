"""Story Validator — Part 20 of the Narrative Intelligence System.

Scores generated scene prose against the Director's intent and campaign story state.
Complementary to scene_validator.py (prose quality) — this validates story structure.

Scoring:
  +10  Concrete scene (named location, specific time, clear action)
  +15  Advances story thread
  +10  Introduces a clue
  +15  Pays off a setup
  +10  Uses existing NPC
  +10  Uses existing location
  +15  Creates consequence
  +15  Advances character arc
  +10  Supports current pacing goal (scene type matches director recommendation)
  +15  Supports campaign DNA (themes/symbols present)
  +10  Uses spotlight recommendation
  +10  Supports emotional target

Penalties:
  -25  Meta narration ("the story takes a turn", "your adventure begins")
  -25  Generic fantasy statements ("the world is dangerous", "adventure awaits")
  -20  Thread regression (ignores highest-priority thread entirely)
  -15  Ignored consequence (pending consequence not acknowledged)
  -15  Ignored spotlight recommendation
  -25  Narrative drift (scene doesn't match campaign DNA at all)

Target: 80+
"""
from __future__ import annotations

import re
from typing import Any

from .narrative_director import DirectorOutput
from .story_state import CampaignStoryState

# ---------------------------------------------------------------------------
# Pattern lists
# ---------------------------------------------------------------------------

_META_NARRATION = [
    r"\bthe story takes a turn\b",
    r"\byour adventure begins\b",
    r"\bthe adventure continues\b",
    r"\byour journey\b",
    r"\bchoices matter\b",
    r"\bpaths branch ahead\b",
    r"\bfate has other plans\b",
    r"\bas the session begins\b",
    r"\bthe narrative shifts\b",
    r"\bthe plot thickens\b",
    r"\bthus begins\b",
    r"\bour story opens\b",
    r"\bthe tale unfolds\b",
]

_GENERIC_FANTASY = [
    r"\bthe world is dangerous\b",
    r"\badventure awaits\b",
    r"\bheroic fantasy\b",
    r"\bhigh fantasy\b",
    r"\bthe stakes are high\b",
    r"\ba mysterious threat\b",
    r"\ban epic quest\b",
    r"\bgreat evil\b",
    r"\bchosen one\b",
    r"\bdestiny awaits\b",
    r"\blegendary hero\b",
]

_REPEATED_STRUCTURE_CLICHES = [
    r"\bvisibly shaken\b",
    r"\bshaken (npc|guard|messenger|villager|traveler|traveller)\b",
    r"\bmysterious stranger\b",
    r"\b(cloaked|hooded) figure\b",
    r"\burgent request\b",
    r"\bwe need help\b",
    r"\bsomething has gone wrong\b",
    r"\bsomething is wrong\b",
    r"\bmissing caravan\b",
    r"\bsealed packet\b",
    r"\bwayward lantern\b",
    r"\btavern\b",
    r"\binn\b",
]

_CONCRETENESS_INDICATORS = [
    # Named location patterns (capitalized noun phrases)
    r"\bat the [A-Z][a-z]+",
    r"\binside the [A-Z][a-z]+",
    r"\bnear the [A-Z][a-z]+",
    r"\bthe [A-Z][a-z]+ (inn|tavern|market|gate|square|keep|hall|road|bridge|tower|temple|guild)\b",
    # Time of day / weather
    r"\b(dawn|dusk|midnight|midday|morning|evening|afternoon|twilight)\b",
    r"\b(rain|fog|snow|storm|mist|wind)\b",
    # Specific sensory details
    r"\b(smell|stench|aroma|scent|reek)\b",
    r"\b(sound|noise|clatter|murmur|rumble)\b",
]

_CONSEQUENCE_INDICATORS = [
    r"\bbecause (you|he|she|they|Yungmin)",
    r"\bas a result\b",
    r"\bbecause of (what|your|his|her|their)",
    r"\bfor (sparing|saving|attacking|insulting|breaking|stealing|betraying|helping|lying)\b",
    r"\bconsequence\b",
    r"\brepercussion\b",
    r"\banswer for\b",
    r"\byou (burned|broke|promised|swore|agreed|owed|insulted|helped|saved|stole|killed)\b",
]

_ARC_INDICATORS = [
    r"\bremember(s|ing)?\b",
    r"\b(father|mother|family|kin|brother|sister|home)\b",
    r"\b(past|history|before|once was|used to)\b",
    r"\bwho (you|he|she|they) (are|were|have become)\b",
    r"\bchange(d|s)?\b",
    r"\b(grief|guilt|pride|shame|love|loss|fear|hope)\b",
    r"\bwhat (you|he|she|they) (want|wanted|need|needed|fear|feared)\b",
]


def _count_pattern_matches(text: str, patterns: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for p in patterns if re.search(p, text_lower, re.IGNORECASE))


def _names_in_text(text: str, names: list[str]) -> list[str]:
    found = []
    for name in names:
        if name and name.lower() in text.lower():
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class StoryValidationResult:
    def __init__(self) -> None:
        self.score: int = 0
        self.bonuses: list[tuple[str, int]] = []
        self.penalties: list[tuple[str, int]] = []
        self.passed: bool = False
        self.issues: list[str] = []

    def add_bonus(self, label: str, points: int) -> None:
        self.score += points
        self.bonuses.append((label, points))

    def add_penalty(self, label: str, points: int) -> None:
        self.score -= abs(points)
        self.penalties.append((label, -abs(points)))
        self.issues.append(label)

    def finalize(self, threshold: int = 80) -> None:
        self.score = max(0, self.score)
        self.passed = self.score >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "bonuses": self.bonuses,
            "penalties": self.penalties,
            "issues": self.issues,
        }


def validate_story_quality(
    scene_text: str,
    director: DirectorOutput,
    state: CampaignStoryState,
    scene_type: str = "",
    npc_names: list[str] | None = None,
    location_names: list[str] | None = None,
    clue_keywords: list[str] | None = None,
) -> StoryValidationResult:
    """Score narrative prose against director intent and campaign story state."""
    result = StoryValidationResult()
    text_lower = scene_text.lower()

    if not npc_names:
        npc_names = list(state.npc_activity.keys())
    if not location_names:
        location_names = []

    # --- Bonuses ---

    # +10 Concrete scene
    concreteness = sum(1 for p in _CONCRETENESS_INDICATORS if re.search(p, scene_text, re.IGNORECASE))
    if concreteness >= 2:
        result.add_bonus("Concrete Scene", 10)

    # +15 Advances story thread
    threads_found = _names_in_text(scene_text, list(state.threads.keys()))
    if threads_found:
        result.add_bonus("Advances Story Thread", 15)
    if len(threads_found) >= 2:
        result.add_bonus("Multi-Thread Weave", 5)

    # +10 Introduces clue
    if clue_keywords:
        clues_hit = _names_in_text(scene_text, clue_keywords)
        if clues_hit:
            result.add_bonus("Introduces Clue", 10)
    else:
        clue_patterns = [r"\b(clue|evidence|mark|symbol|sign|note|letter|map|key)\b"]
        if _count_pattern_matches(scene_text, clue_patterns) >= 1:
            result.add_bonus("Introduces Clue", 10)

    # +15 Pays off a setup
    setups_due = [s.description for s in state.setups if s.payoff_due and not s.resolved]
    setups_hit = _names_in_text(scene_text, setups_due)
    if setups_hit:
        result.add_bonus("Pays Off Setup", 15)

    # +10 Uses existing NPC
    npcs_found = _names_in_text(scene_text, npc_names)
    if npcs_found:
        result.add_bonus("Uses Existing NPC", 10)

    # +10 Uses existing location
    if location_names:
        locs_found = _names_in_text(scene_text, location_names)
        if locs_found:
            result.add_bonus("Uses Existing Location", 10)

    # +15 Creates consequence (player actions have weight)
    consequence_matches = _count_pattern_matches(scene_text, _CONSEQUENCE_INDICATORS)
    if consequence_matches >= 1:
        result.add_bonus("Creates Consequence", 15)

    # +15 Advances character arc
    arc_matches = _count_pattern_matches(scene_text, _ARC_INDICATORS)
    if arc_matches >= 2:
        result.add_bonus("Advances Character Arc", 15)

    # +10 Supports current pacing goal (scene type matches director)
    if scene_type and director.recommended_scene_type:
        if scene_type.lower() == director.recommended_scene_type.lower():
            result.add_bonus("Supports Pacing Goal", 10)
        # Partial credit for compatible types
        elif _types_compatible(scene_type, director.recommended_scene_type):
            result.add_bonus("Pacing Goal Approximate", 5)

    # +15 Supports campaign DNA (themes/symbols)
    dna_hits = _names_in_text(scene_text, state.campaign_dna.themes + state.campaign_dna.recurring_symbols)
    if len(dna_hits) >= 1:
        result.add_bonus("Supports Campaign DNA", 15)
    if len(dna_hits) >= 3:
        result.add_bonus("Rich Campaign DNA", 5)

    # +10 Uses spotlight recommendation
    if director.spotlight_target and director.spotlight_target.lower() in text_lower:
        result.add_bonus("Uses Spotlight", 10)

    # +10 Supports emotional target
    if director.emotional_target:
        target_emotion = max(director.emotional_target.items(), key=lambda kv: kv[1], default=("", 0))
        if target_emotion[0]:
            emotion_name = target_emotion[0]
            emotion_patterns = _emotion_to_patterns(emotion_name)
            if _count_pattern_matches(scene_text, emotion_patterns) >= 1:
                result.add_bonus("Supports Emotional Target", 10)

    # --- Penalties ---

    # -25 Meta narration
    meta_hits = _count_pattern_matches(scene_text, _META_NARRATION)
    if meta_hits >= 1:
        result.add_penalty("Meta Narration", 25)

    # -25 Generic fantasy statements
    generic_hits = _count_pattern_matches(scene_text, _GENERIC_FANTASY)
    if generic_hits >= 2:
        result.add_penalty("Generic Fantasy", 25)
    elif generic_hits == 1:
        result.add_penalty("Generic Fantasy (minor)", 10)

    repeated_structure_hits = _count_pattern_matches(scene_text, _REPEATED_STRUCTURE_CLICHES)
    if repeated_structure_hits >= 2:
        result.add_penalty("Repeated Generic Structure", 20)
    elif repeated_structure_hits == 1:
        result.add_penalty("Repeated Generic Structure (minor)", 8)

    # -20 Thread regression (highest priority thread entirely ignored)
    if state.threads:
        highest_thread = max(state.threads.items(), key=lambda kv: kv[1].importance)
        title, thread = highest_thread
        if thread.importance >= 7 and title.lower() not in text_lower:
            if not threads_found:  # No threads at all in the scene
                result.add_penalty("Thread Regression", 20)

    # -15 Ignored pending consequence
    pending_cons = [c.action for c in state.consequences if c.consequence_due and not c.resolved]
    if pending_cons and consequence_matches == 0:
        if director.recommended_consequence:
            result.add_penalty("Ignored Consequence", 15)

    # -15 Ignored spotlight recommendation
    if director.spotlight_target and director.spotlight_target.lower() not in text_lower:
        # Only penalize if spotlight was strongly recommended
        hooks_due = [h for h in state.character_hooks if h.spotlight_recommended]
        if hooks_due:
            result.add_penalty("Ignored Spotlight", 15)

    # -25 Narrative drift (scene doesn't match campaign DNA at all)
    if state.campaign_dna.themes and not dna_hits and len(state.scene_history) > 3:
        result.add_penalty("Narrative Drift", 25)

    result.finalize(threshold=80)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TYPE_COMPAT = {
    "Combat": {"Escalation", "Climax"},
    "Escalation": {"Combat", "Climax"},
    "Investigation": {"Discovery", "Mystery"},
    "Discovery": {"Investigation", "Revelation"},
    "Mystery": {"Investigation", "Discovery"},
    "Revelation": {"Discovery", "Climax"},
    "Social": {"Downtime", "Consequence"},
    "Downtime": {"Social", "Consequence"},
    "Consequence": {"Social", "Downtime"},
    "Resolution": {"Downtime", "Consequence"},
}


def _types_compatible(a: str, b: str) -> bool:
    return b in _TYPE_COMPAT.get(a, set()) or a in _TYPE_COMPAT.get(b, set())


def _emotion_to_patterns(emotion: str) -> list[str]:
    emotion_map = {
        "fear": [r"\b(fear|afraid|terror|dread|horror|panic|flee|flee)\b"],
        "hope": [r"\b(hope|hopeful|promise|light|salvation|trust)\b"],
        "wonder": [r"\b(wonder|awe|marvels?|strange|beautiful|extraordinary|impossible)\b"],
        "urgency": [r"\b(hurry|urgent|time|running out|must|now|quick|immediately)\b"],
        "triumph": [r"\b(triumph|victory|succeed|won|defeated|overcome|prevail)\b"],
        "curiosity": [r"\b(curious|wonder|question|why|how|mystery|strange|unusual)\b"],
        "trust": [r"\b(trust|reliable|loyal|honest|true|faith|believe)\b"],
    }
    return emotion_map.get(emotion, [])
