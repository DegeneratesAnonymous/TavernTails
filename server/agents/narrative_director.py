"""Narrative Director Agent — the story brain.

Responsibilities: pacing, thread progression, tension management, emotional flow,
setup/payoff tracking, spotlight rotation, mystery pacing, consequence scheduling.

The Director never writes prose. It tells the Scene Director what TYPE of scene
should happen next and WHY, based on the full campaign story state.

LLM scope: taverntails_director
Deterministic fallback: always available — rules-based analysis of story state
"""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from .story_state import (
    SCENE_PURPOSES,
    SCENE_TYPES,
    CampaignStoryState,
    SceneHistoryEntry,
    ThreadState,
    thread_health_score,
)

try:
    from ..steward_llm import chat_complete
except Exception:
    chat_complete = None  # type: ignore


# ---------------------------------------------------------------------------
# Director Output Model (Part 1)
# ---------------------------------------------------------------------------

class DirectorOutput(BaseModel):
    recommended_scene_type: str = "Social"
    target_tension: int = 40
    threads_to_advance: list[str] = Field(default_factory=list)
    threads_to_resolve: list[str] = Field(default_factory=list)
    recommended_reveal: str = ""
    recommended_complication: str = ""
    recommended_consequence: str = ""
    spotlight_target: str = ""
    mystery_guidance: str = ""
    pacing_notes: str = ""
    next_story_beat: str = ""
    scene_purpose: str = "Advance Plot"
    emotional_target: dict[str, int] = Field(default_factory=dict)
    # Derived fields (added by deterministic layer)
    source: str = "deterministic"   # "llm" | "deterministic"
    confidence: float = 0.8


# ---------------------------------------------------------------------------
# Deterministic Director (rules-based fallback)
# ---------------------------------------------------------------------------

_SCENE_TYPE_TO_TENSION = {
    "Introduction": 20,
    "Social": -10,
    "Investigation": 5,
    "Travel": 0,
    "Discovery": 10,
    "Mystery": 5,
    "Combat": 25,
    "Consequence": -5,
    "Downtime": -20,
    "Escalation": 20,
    "Revelation": 15,
    "Climax": 40,
    "Resolution": -30,
}

_TENSION_REDUCING_TYPES = {"Social", "Downtime", "Consequence", "Resolution"}
_TENSION_BUILDING_TYPES = {"Combat", "Escalation", "Climax"}
_MYSTERY_TYPES = {"Investigation", "Discovery", "Mystery", "Revelation"}


def _recent_consecutive(history: list[SceneHistoryEntry], scene_type: str) -> int:
    """Count consecutive trailing scenes of the given type."""
    count = 0
    for entry in reversed(history):
        if entry.scene_type == scene_type:
            count += 1
        else:
            break
    return count


def _type_count_in_recent(history: list[SceneHistoryEntry], n: int = 8) -> dict[str, int]:
    recent = history[-n:]
    counts: dict[str, int] = {}
    for e in recent:
        counts[e.scene_type] = counts.get(e.scene_type, 0) + 1
    return counts


def _dominant_type(history: list[SceneHistoryEntry], n: int = 5) -> str | None:
    counts = _type_count_in_recent(history, n)
    if not counts:
        return None
    best, best_count = max(counts.items(), key=lambda kv: kv[1])
    return best if best_count >= 3 else None


def _recommend_scene_type_for_variety(history: list[SceneHistoryEntry], tension: int) -> str:
    """Recommend a scene type that provides narrative variety."""
    dominant = _dominant_type(history, 5)
    recent_types = {e.scene_type for e in history[-4:]}

    # Explicit anti-repetition: avoid whatever was last 3+ times
    avoid = set()
    if dominant:
        avoid.add(dominant)

    # Tension-aware selection
    if tension > 75:
        # Need relief
        candidates = ["Consequence", "Social", "Downtime", "Investigation"]
    elif tension > 55:
        candidates = ["Investigation", "Social", "Discovery", "Mystery"]
    elif tension < 25:
        candidates = ["Investigation", "Travel", "Discovery", "Escalation"]
    else:
        candidates = ["Investigation", "Social", "Discovery", "Mystery", "Escalation"]

    # Filter out recent and dominant
    filtered = [c for c in candidates if c not in avoid and c not in recent_types]
    if filtered:
        return filtered[0]

    # Fall back to any non-dominant candidate
    all_candidates = [t for t in candidates if t not in avoid]
    if all_candidates:
        return all_candidates[0]

    return "Social"


def _find_most_neglected_thread(
    threads: dict[str, ThreadState],
    scene_count: int,
    exclude_resolved: bool = True,
) -> tuple[str, ThreadState] | tuple[None, None]:
    """Find the thread most in need of advancement (highest health score)."""
    best: tuple[str, ThreadState] | tuple[None, None] = (None, None)
    best_score = -1

    for title, thread in threads.items():
        if exclude_resolved and thread.stage == "Resolution":
            continue
        score = thread_health_score(thread, scene_count)
        if score > best_score:
            best_score = score
            best = (title, thread)

    return best


def _pending_consequences(state: CampaignStoryState) -> list[str]:
    return [c.action for c in state.consequences if c.consequence_due and not c.resolved]


def _spotlight_needed(state: CampaignStoryState) -> str:
    for hook in state.character_hooks:
        if hook.spotlight_recommended:
            return hook.owner or hook.hook
    return ""


def _determine_emotional_target(
    state: CampaignStoryState,
    scene_type: str,
    tension: int,
) -> dict[str, int]:
    """Return target emotional values for this scene type."""
    es = state.emotional_state.model_dump()
    targets: dict[str, int] = {}

    if scene_type in ("Combat", "Escalation", "Climax"):
        targets = {"fear": min(80, es["fear"] + 20), "urgency": min(90, es["urgency"] + 25), "hope": max(20, es["hope"] - 10)}
    elif scene_type in ("Social", "Downtime"):
        targets = {"trust": min(80, es["trust"] + 15), "hope": min(75, es["hope"] + 15), "urgency": max(10, es["urgency"] - 20)}
    elif scene_type in ("Discovery", "Revelation"):
        targets = {"wonder": min(85, es["wonder"] + 20), "curiosity": max(20, es["curiosity"] - 15), "fear": min(70, es["fear"] + 10)}
    elif scene_type in ("Investigation", "Mystery"):
        targets = {"curiosity": min(85, es["curiosity"] + 20), "wonder": min(70, es["wonder"] + 10)}
    elif scene_type == "Resolution":
        targets = {"triumph": min(80, es["triumph"] + 30), "fear": max(10, es["fear"] - 25), "urgency": max(5, es["urgency"] - 30)}
    elif scene_type == "Consequence":
        targets = {"fear": min(60, es["fear"] + 15), "trust": max(20, es["trust"] - 10)}
    elif scene_type == "Travel":
        targets = {"wonder": min(70, es["wonder"] + 15), "hope": min(70, es["hope"] + 10)}
    else:
        targets = {}

    return targets


def _deterministic_director(state: CampaignStoryState) -> DirectorOutput:
    """Rules-based scene recommendation with no LLM required."""
    tension = state.metrics.tension
    scene_count = state.scene_count
    history = state.scene_history

    # --- Scene type selection ---
    scene_type = _recommend_scene_type_for_variety(history, tension)

    # Consequence override: if high-severity consequence pending and player has been avoiding it
    pending_cons = _pending_consequences(state)
    if pending_cons:
        recent_types = {e.scene_type for e in history[-3:]}
        if "Consequence" not in recent_types:
            cons = state.consequences[0] if state.consequences else None
            if cons and cons.severity in ("major", "critical"):
                scene_type = "Consequence"

    # Spotlight override: if a character hook needs spotlight urgently
    spotlight = _spotlight_needed(state)
    if spotlight and scene_type not in ("Combat", "Climax"):
        if scene_type in _TENSION_BUILDING_TYPES:
            pass  # Don't interrupt intense scenes for spotlight
        elif "Social" not in {e.scene_type for e in history[-2:]}:
            scene_type = "Social"

    # --- Thread selection ---
    thread_name, thread = _find_most_neglected_thread(state.threads, scene_count)
    threads_to_advance = [thread_name] if thread_name else []

    # --- Scene purpose ---
    if pending_cons and scene_type == "Consequence":
        purpose = "Show Consequences"
    elif scene_type in ("Investigation", "Mystery"):
        purpose = "Build Mystery"
    elif scene_type == "Revelation":
        purpose = "Reveal Information"
    elif scene_type in ("Combat", "Escalation"):
        purpose = "Escalate Conflict"
    elif scene_type == "Climax":
        purpose = "Escalate Conflict"
    elif scene_type == "Resolution":
        purpose = "Resolve Conflict"
    elif scene_type in ("Social",):
        purpose = "Develop Character" if spotlight else "Advance Relationship"
    elif scene_type == "Discovery":
        purpose = "Reveal Information"
    elif scene_type == "Downtime":
        purpose = "Reduce Tension"
    else:
        purpose = "Advance Plot"

    # --- Target tension ---
    current_tension = tension
    delta = _SCENE_TYPE_TO_TENSION.get(scene_type, 0)
    target_tension = max(0, min(100, current_tension + delta))

    # Health-check: prevent runaway tension or flatline
    if current_tension > 80 and scene_type not in _TENSION_REDUCING_TYPES:
        target_tension = max(50, current_tension - 20)  # gentle push down
    if current_tension < 20 and scene_count > 3 and scene_type not in _TENSION_BUILDING_TYPES:
        target_tension = min(45, current_tension + 15)  # nudge up

    # --- Pacing notes ---
    pacing_notes_parts = []
    counts = _type_count_in_recent(history, 8)
    for scene_t, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
        if cnt >= 3:
            pacing_notes_parts.append(f"Too many {scene_t} scenes recently ({cnt}) — recommend variety.")
    if tension > 75:
        pacing_notes_parts.append("Tension is very high — consider a relief scene soon.")
    if tension < 20 and scene_count > 2:
        pacing_notes_parts.append("Tension is low — should build momentum.")

    # Thread health warnings
    for title, t in state.threads.items():
        if t.needs_attention:
            pacing_notes_parts.append(f"Thread '{title}' has been neglected — needs attention.")

    pacing_notes = " ".join(pacing_notes_parts) or "Pacing nominal."

    # --- Next story beat ---
    next_beat = ""
    if thread and thread_name:
        next_beat = thread.next_story_beat or f"Advance '{thread_name}' from {thread.stage} stage."

    # --- Mystery guidance ---
    mystery_guidance = ""
    for title, mystery in state.mysteries.items():
        found = len(mystery.clues_found)
        total = found + len(mystery.clues_remaining)
        if total > 0 and found / total >= 0.6 and not mystery.reveal_ready:
            mystery_guidance = f"Mystery '{title}' has enough clues ({found}/{total}) — consider revelation."
            break
        elif found < 2:
            mystery_guidance = f"Mystery '{title}' needs more clues — only {found} found so far."
            break

    # --- Recommended consequence ---
    recommended_consequence = pending_cons[0] if pending_cons else ""

    # --- Emotional target ---
    emotional_target = _determine_emotional_target(state, scene_type, tension)

    return DirectorOutput(
        recommended_scene_type=scene_type,
        target_tension=target_tension,
        threads_to_advance=threads_to_advance,
        threads_to_resolve=[],
        recommended_consequence=recommended_consequence,
        spotlight_target=spotlight,
        mystery_guidance=mystery_guidance,
        pacing_notes=pacing_notes,
        next_story_beat=next_beat,
        scene_purpose=purpose,
        emotional_target=emotional_target,
        source="deterministic",
        confidence=0.75,
    )


# ---------------------------------------------------------------------------
# LLM Director
# ---------------------------------------------------------------------------

_SYSTEM = """You are the Narrative Director for a tabletop RPG campaign.

Your job: analyze the story state and recommend the MOST DRAMATICALLY APPROPRIATE
type of scene for this exact moment in the campaign.

You never write prose. You make structural storytelling decisions.

Consider:
- Pacing (don't repeat scene types)
- Tension curve (escalation needs release; release needs re-escalation)
- Player emotional experience (avoid constant panic or constant comedy)
- Thread health (important threads can't be ignored)
- Consequences (player actions must have consequences)
- Payoffs (setups must eventually pay off)
- Campaign identity (every scene should feel like THIS campaign)

Respond with ONLY valid JSON matching this schema exactly:
{
  "recommended_scene_type": string (one of the scene types listed),
  "target_tension": integer 0-100,
  "threads_to_advance": [list of thread titles],
  "threads_to_resolve": [list of thread titles],
  "recommended_reveal": string,
  "recommended_complication": string,
  "recommended_consequence": string,
  "spotlight_target": string,
  "mystery_guidance": string,
  "pacing_notes": string,
  "next_story_beat": string,
  "scene_purpose": string,
  "emotional_target": {"hope": int, "fear": int, "wonder": int, "trust": int, "urgency": int, "triumph": int, "curiosity": int}
}"""


def _build_director_prompt(
    state: CampaignStoryState,
    player_name: str,
    player_actions: list[str],
    deterministic: DirectorOutput,
) -> str:
    """Build the LLM prompt from story state — compact but complete."""
    tension = state.metrics.tension
    es = state.emotional_state.model_dump()

    # Recent scene types
    recent = " → ".join(e.scene_type for e in state.scene_history[-6:]) or "none"

    # Thread summary
    thread_lines = []
    for title, t in sorted(state.threads.items(), key=lambda kv: -kv[1].importance):
        if t.stage == "Resolution":
            continue
        scenes_since = state.scene_count - t.last_progressed_scene
        thread_lines.append(f"  [{t.stage}] '{title}' (importance {t.importance}/10, {scenes_since} scenes idle)")
    threads_block = "\n".join(thread_lines[:5]) if thread_lines else "  none"

    # Pending consequences
    pending = [f"  — {c.action} ({c.severity})" for c in state.consequences if c.consequence_due and not c.resolved]
    pending_block = "\n".join(pending[:3]) or "  none"

    # Setups awaiting payoff
    setups = [f"  — {s.description}" for s in state.setups if s.payoff_due and not s.resolved]
    setups_block = "\n".join(setups[:3]) or "  none"

    # Campaign DNA
    dna = state.campaign_dna
    dna_block = f"Themes: {', '.join(dna.themes[:4])}; Moods: {', '.join(dna.recurring_moods[:3])}"

    # Mysteries
    mysteries_block = ""
    for title, m in state.mysteries.items():
        total = len(m.clues_found) + len(m.clues_remaining)
        mysteries_block += f"  [{title}] clues: {len(m.clues_found)}/{total}\n"
    mysteries_block = mysteries_block.strip() or "  none"

    # Deterministic recommendation as context
    det = f"Rules-based recommendation: {deterministic.recommended_scene_type} (purpose: {deterministic.scene_purpose}, target tension: {deterministic.target_tension})"

    player_block = f"Player: {player_name}" + (f"\nRecent actions: {'; '.join(player_actions[-3:])}" if player_actions else "")

    return f"""CAMPAIGN STORY STATE

Tension: {tension}/100
Emotional State: {', '.join(f'{k}:{v}' for k, v in es.items())}
Scene Count: {state.scene_count}
Recent Pacing: {recent}

{player_block}

ACTIVE THREADS
{threads_block}

PENDING CONSEQUENCES
{pending_block}

PENDING PAYOFFS
{setups_block}

MYSTERIES
{mysteries_block}

CAMPAIGN DNA
{dna_block}

AVAILABLE SCENE TYPES: {', '.join(SCENE_TYPES)}
AVAILABLE SCENE PURPOSES: {', '.join(SCENE_PURPOSES)}

{det}

Given this campaign state, recommend the most dramatically appropriate next scene.
Respond with JSON only."""


def direct_scene(
    state: CampaignStoryState,
    player_name: str = "",
    player_actions: list[str] | None = None,
) -> DirectorOutput:
    """Run the Narrative Director — LLM with deterministic fallback."""
    if player_actions is None:
        player_actions = []

    # Always compute deterministic output first
    deterministic = _deterministic_director(state)

    if chat_complete is None:
        return deterministic

    user_prompt = _build_director_prompt(state, player_name, player_actions, deterministic)

    try:
        response = chat_complete(
            messages=[{"role": "user", "content": user_prompt}],
            system=_SYSTEM,
            task_scope="taverntails_director",
            max_tokens=400,
        )

        raw = response.get("content", "").strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        data = json.loads(raw)

        # Validate required fields
        scene_type = data.get("recommended_scene_type", deterministic.recommended_scene_type)
        if scene_type not in SCENE_TYPES:
            scene_type = deterministic.recommended_scene_type

        purpose = data.get("scene_purpose", deterministic.scene_purpose)
        if purpose not in SCENE_PURPOSES:
            purpose = deterministic.scene_purpose

        target_tension = data.get("target_tension", deterministic.target_tension)
        if not isinstance(target_tension, int) or not 0 <= target_tension <= 100:
            target_tension = deterministic.target_tension

        emotional_target = data.get("emotional_target") or deterministic.emotional_target
        if isinstance(emotional_target, dict):
            emotional_target = {k: int(v) for k, v in emotional_target.items() if isinstance(v, (int, float))}

        return DirectorOutput(
            recommended_scene_type=scene_type,
            target_tension=target_tension,
            threads_to_advance=data.get("threads_to_advance") or deterministic.threads_to_advance,
            threads_to_resolve=data.get("threads_to_resolve") or [],
            recommended_reveal=data.get("recommended_reveal") or "",
            recommended_complication=data.get("recommended_complication") or "",
            recommended_consequence=data.get("recommended_consequence") or deterministic.recommended_consequence,
            spotlight_target=data.get("spotlight_target") or deterministic.spotlight_target,
            mystery_guidance=data.get("mystery_guidance") or deterministic.mystery_guidance,
            pacing_notes=data.get("pacing_notes") or deterministic.pacing_notes,
            next_story_beat=data.get("next_story_beat") or deterministic.next_story_beat,
            scene_purpose=purpose,
            emotional_target=emotional_target,
            source="llm",
            confidence=0.90,
        )

    except Exception:
        # Fall back to deterministic — never fail the caller
        return deterministic
