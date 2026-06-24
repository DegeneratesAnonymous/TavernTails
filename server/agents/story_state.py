"""Story State — persistent campaign-level narrative metrics.

All 22 systems from the Narrative Intelligence work order are modeled here.
Story state lives at campaigns/{campaign_id}/story_state.json and is updated
after every generated scene.

Design: the story state is the campaign's memory of WHAT HAPPENED and HOW IT FELT.
The Narrative Director reads this state to decide WHAT SHOULD HAPPEN NEXT.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_CAMPAIGN_BASE = Path(__file__).resolve().parents[1] / "campaigns"

SCENE_TYPES = [
    "Introduction", "Social", "Investigation", "Travel", "Discovery",
    "Mystery", "Combat", "Consequence", "Downtime", "Escalation",
    "Revelation", "Climax", "Resolution",
]

SCENE_PURPOSES = [
    "Advance Plot", "Reveal Information", "Increase Tension", "Reduce Tension",
    "Develop Character", "Show Consequences", "Introduce Threat", "Reward Players",
    "Deliver Payoff", "Build Mystery", "Advance Relationship", "World Building",
    "Escalate Conflict", "Resolve Conflict",
]

THREAD_STAGES = [
    "Introduction", "Investigation", "Discovery", "Complication",
    "Escalation", "Revelation", "Climax", "Resolution",
]

_THREAD_STAGE_ORDER = {s: i for i, s in enumerate(THREAD_STAGES)}


# ---------------------------------------------------------------------------
# Part 2: Story Metrics
# ---------------------------------------------------------------------------

class StoryMetrics(BaseModel):
    tension: int = 20        # 0-100: narrative pressure on the players
    mystery: int = 30        # 0-100: unresolved questions in play
    danger: int = 15         # 0-100: immediate physical/political threat
    player_agency: int = 60  # 0-100: how much the players feel in control
    thread_momentum: int = 40
    npc_activity: int = 30
    world_pressure: int = 25


# ---------------------------------------------------------------------------
# Part 3: Emotional State
# ---------------------------------------------------------------------------

class EmotionalState(BaseModel):
    hope: int = 50
    fear: int = 20
    wonder: int = 35
    trust: int = 55
    urgency: int = 25
    triumph: int = 10
    curiosity: int = 45


# ---------------------------------------------------------------------------
# Part 5: Scene History
# ---------------------------------------------------------------------------

class SceneHistoryEntry(BaseModel):
    scene_id: str = ""
    scene_number: int = 0
    scene_type: str = ""
    scene_purpose: str = ""
    tension_before: int = 0
    tension_after: int = 0
    tension_change: int = 0
    emotional_shift: dict[str, int] = Field(default_factory=dict)
    threads_advanced: list[str] = Field(default_factory=list)
    threads_resolved: list[str] = Field(default_factory=list)
    npcs_featured: list[str] = Field(default_factory=list)
    location: str = ""
    story_score: int = 0
    director_recommendation_followed: bool = True
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Part 7: Story Thread Lifecycle
# ---------------------------------------------------------------------------

class ThreadState(BaseModel):
    title: str = ""
    importance: int = 5  # 1-10
    stage: str = "Introduction"
    last_progressed_scene: int = 0
    next_story_beat: str = ""
    needs_attention: bool = False
    player_interest: int = 5   # 1-10
    related_npcs: list[str] = Field(default_factory=list)
    related_locations: list[str] = Field(default_factory=list)


def thread_health_score(thread: ThreadState, current_scene: int) -> int:
    """Calculate how urgently this thread needs attention (higher = more urgent)."""
    scenes_since = max(0, current_scene - thread.last_progressed_scene)
    max_gap = max(3, 10 - thread.importance)  # important threads need more frequent attention
    neglect = min(100, int((scenes_since / max_gap) * 100)) if max_gap > 0 else 100
    urgency = (thread.importance * 10) + (neglect // 2)
    return min(100, urgency)


# ---------------------------------------------------------------------------
# Part 9: Player Intent
# ---------------------------------------------------------------------------

class PlayerIntent(BaseModel):
    intent: str = ""
    owner: str = ""
    priority: int = 5         # 1-10
    created_scene: int = 0
    last_referenced: int = 0
    status: str = "active"    # active|resolved|abandoned


# ---------------------------------------------------------------------------
# Part 10: Character Spotlight
# ---------------------------------------------------------------------------

class CharacterHook(BaseModel):
    hook: str = ""
    owner: str = ""
    last_used_scene: int = 0
    importance: int = 5
    spotlight_recommended: bool = False


def check_spotlight_needed(hook: CharacterHook, current_scene: int) -> bool:
    scenes_since = current_scene - hook.last_used_scene
    return scenes_since >= max(4, 8 - hook.importance)


# ---------------------------------------------------------------------------
# Part 11: Setup / Payoff
# ---------------------------------------------------------------------------

class SetupPayoff(BaseModel):
    setup_id: str = ""
    description: str = ""
    introduced_scene: int = 0
    payoff_due: bool = False
    resolved: bool = False
    hint_count: int = 0  # how many times foreshadowed


# ---------------------------------------------------------------------------
# Part 12: Promise Tracking
# ---------------------------------------------------------------------------

class StoryPromise(BaseModel):
    promise: str = ""
    introduced_scene: int = 0
    resolved: bool = False
    importance: int = 5


# ---------------------------------------------------------------------------
# Part 13: Foreshadowing
# ---------------------------------------------------------------------------

class ForeshadowElement(BaseModel):
    element: str = ""
    foreshadow_count: int = 0
    payoff_ready: bool = False
    introduced_scene: int = 0


# ---------------------------------------------------------------------------
# Part 14: Mystery Management
# ---------------------------------------------------------------------------

class MysteryState(BaseModel):
    title: str = ""
    central_question: str = ""
    clues_found: list[str] = Field(default_factory=list)
    clues_remaining: list[str] = Field(default_factory=list)
    suspects: list[str] = Field(default_factory=list)
    reveal_ready: bool = False


# ---------------------------------------------------------------------------
# Part 15: Consequence System
# ---------------------------------------------------------------------------

class ConsequenceState(BaseModel):
    action: str = ""
    actor: str = ""            # who caused it
    scene: int = 0
    severity: str = "minor"   # minor|moderate|major|critical
    consequence_due: bool = True
    consequence_type: str = ""
    resolved: bool = False


# ---------------------------------------------------------------------------
# Part 16: NPC Activity
# ---------------------------------------------------------------------------

class NPCActivityState(BaseModel):
    name: str = ""
    goal: str = ""
    plan: str = ""
    progress: int = 0          # 0-100
    last_active_scene: int = 0
    activity_recommended: bool = False


# ---------------------------------------------------------------------------
# Part 17: Faction Pressure
# ---------------------------------------------------------------------------

class FactionPressureState(BaseModel):
    name: str = ""
    goal: str = ""
    plan: str = ""
    progress: int = 0
    deadline: str = ""
    next_action: str = ""


# ---------------------------------------------------------------------------
# Part 18: Campaign DNA
# ---------------------------------------------------------------------------

class CampaignDNA(BaseModel):
    themes: list[str] = Field(default_factory=list)
    recurring_symbols: list[str] = Field(default_factory=list)
    recurring_questions: list[str] = Field(default_factory=list)
    recurring_moods: list[str] = Field(default_factory=list)
    core_conflicts: list[str] = Field(default_factory=list)


def derive_campaign_dna(
    campaign_settings: dict,
    campaign_variables: dict,
    entity_names: list[str] | None = None,
) -> CampaignDNA:
    """Derive initial Campaign DNA from campaign settings + variables."""
    themes: list[str] = []
    genre = str(campaign_settings.get("genre") or "").lower()
    tone = str(campaign_settings.get("tone") or "").lower()

    # Map genre/tone to themes
    if "dark" in genre or "gritty" in tone:
        themes.extend(["survival", "corruption", "sacrifice"])
    if "high" in genre or "epic" in tone:
        themes.extend(["destiny", "heroism", "sacrifice"])
    if "political" in genre or "intrigue" in tone:
        themes.extend(["power", "betrayal", "loyalty"])
    if "mystery" in genre or "mystery" in tone:
        themes.extend(["secrets", "truth", "identity"])

    # From campaign variables
    var_themes = [str(t) for t in (campaign_variables.get("themes") or []) if t]
    themes.extend(var_themes)

    # Setting summary for recurring questions
    setting = str(campaign_settings.get("setting_summary") or "")
    recurring_questions = []
    if "corrupt" in setting.lower():
        recurring_questions.append("Can power be trusted?")
    if "war" in setting.lower():
        recurring_questions.append("What is worth dying for?")
    if "family" in setting.lower() or "kin" in setting.lower():
        recurring_questions.append("What is family worth?")

    moods = []
    if "dark" in tone or "gritty" in tone:
        moods = ["grim", "tense", "atmospheric"]
    elif "heroic" in tone:
        moods = ["dramatic", "triumphant", "epic"]
    else:
        moods = ["dramatic", "mysterious"]

    return CampaignDNA(
        themes=list(set(themes))[:6],
        recurring_symbols=[],
        recurring_questions=recurring_questions[:3],
        recurring_moods=moods,
        core_conflicts=[],
    )


# ---------------------------------------------------------------------------
# Part 21: Session Review
# ---------------------------------------------------------------------------

class SessionReview(BaseModel):
    session_id: str = ""
    scene_range: tuple[int, int] = (0, 0)
    threads_advanced: list[str] = Field(default_factory=list)
    threads_stalled: list[str] = Field(default_factory=list)
    setups_introduced: list[str] = Field(default_factory=list)
    setups_resolved: list[str] = Field(default_factory=list)
    promises_made: list[str] = Field(default_factory=list)
    promises_resolved: list[str] = Field(default_factory=list)
    clues_discovered: list[str] = Field(default_factory=list)
    consequences_triggered: list[str] = Field(default_factory=list)
    spotlight_distribution: dict[str, int] = Field(default_factory=dict)
    emotional_curve: list[dict] = Field(default_factory=list)
    tension_curve: list[int] = Field(default_factory=list)
    campaign_dna_score: int = 0
    story_health_score: int = 0
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Full Campaign Story State
# ---------------------------------------------------------------------------

class CampaignStoryState(BaseModel):
    campaign_id: str = ""
    scene_count: int = 0
    session_scene_start: int = 0    # scene count at start of current session

    # Core metrics
    metrics: StoryMetrics = Field(default_factory=StoryMetrics)
    emotional_state: EmotionalState = Field(default_factory=EmotionalState)

    # History (last 20 scenes)
    scene_history: list[SceneHistoryEntry] = Field(default_factory=list)
    tension_curve: list[int] = Field(default_factory=list)  # last 20 tension values

    # Story systems
    threads: dict[str, ThreadState] = Field(default_factory=dict)
    player_intents: list[PlayerIntent] = Field(default_factory=list)
    character_hooks: list[CharacterHook] = Field(default_factory=list)
    setups: list[SetupPayoff] = Field(default_factory=list)
    promises: list[StoryPromise] = Field(default_factory=list)
    foreshadowing: list[ForeshadowElement] = Field(default_factory=list)
    mysteries: dict[str, MysteryState] = Field(default_factory=dict)
    consequences: list[ConsequenceState] = Field(default_factory=list)
    npc_activity: dict[str, NPCActivityState] = Field(default_factory=dict)
    faction_pressure: dict[str, FactionPressureState] = Field(default_factory=dict)
    campaign_dna: CampaignDNA = Field(default_factory=CampaignDNA)

    # Session reviews
    session_reviews: list[dict] = Field(default_factory=list)

    updated_at: str = ""


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _story_state_path(campaign_id: str) -> Path:
    p = _CAMPAIGN_BASE / campaign_id / "story_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_story_state(campaign_id: str) -> CampaignStoryState:
    path = _story_state_path(campaign_id)
    if not path.exists():
        return CampaignStoryState(campaign_id=campaign_id)
    try:
        return CampaignStoryState(**json.loads(path.read_text()))
    except Exception:
        return CampaignStoryState(campaign_id=campaign_id)


def save_story_state(state: CampaignStoryState) -> None:
    path = _story_state_path(state.campaign_id)
    state.updated_at = datetime.now(timezone.utc).isoformat()
    path.write_text(state.model_dump_json())


# ---------------------------------------------------------------------------
# State Update After Scene
# ---------------------------------------------------------------------------

def update_state_after_scene(
    state: CampaignStoryState,
    scene_type: str,
    scene_purpose: str,
    scene_id: str,
    location: str,
    npcs_featured: list[str],
    threads_advanced: list[str],
    threads_resolved: list[str],
    emotional_target: dict[str, int],
    director_tension_target: int,
    story_score: int,
    director_recommendation_followed: bool = True,
) -> CampaignStoryState:
    """Update all story metrics after a scene completes."""
    scene_num = state.scene_count + 1
    state.scene_count = scene_num

    # Tension: move 25% toward director target
    old_tension = state.metrics.tension
    new_tension = int(old_tension + (director_tension_target - old_tension) * 0.25)
    new_tension = max(0, min(100, new_tension))
    state.metrics.tension = new_tension

    # Tension curve (last 20)
    state.tension_curve.append(new_tension)
    state.tension_curve = state.tension_curve[-20:]

    # Emotional state: move 20% toward target
    if emotional_target:
        es = state.emotional_state.model_dump()
        for emotion, target_val in emotional_target.items():
            if emotion in es:
                current = es[emotion]
                es[emotion] = int(current + (target_val - current) * 0.20)
        state.emotional_state = EmotionalState(**es)

    # Other metrics based on scene type
    if scene_type in ("Combat", "Escalation", "Climax"):
        state.metrics.danger = min(100, state.metrics.danger + 10)
        state.metrics.npc_activity = min(100, state.metrics.npc_activity + 8)
    elif scene_type in ("Investigation", "Discovery", "Mystery"):
        state.metrics.mystery = max(0, state.metrics.mystery + 15)
    elif scene_type in ("Resolution", "Consequence", "Downtime"):
        state.metrics.danger = max(0, state.metrics.danger - 10)
        state.metrics.mystery = max(0, state.metrics.mystery - 10)
    elif scene_type == "Social":
        state.metrics.player_agency = min(100, state.metrics.player_agency + 5)

    # Update mystery metric based on mysteries open
    open_mysteries = sum(1 for m in state.mysteries.values() if not m.reveal_ready)
    state.metrics.mystery = min(100, max(state.metrics.mystery, open_mysteries * 20))

    # Thread updates
    for title in threads_advanced:
        if title in state.threads:
            t = state.threads[title]
            t.last_progressed_scene = scene_num
            t.needs_attention = False
            # Advance stage if possible
            current_idx = _THREAD_STAGE_ORDER.get(t.stage, 0)
            if current_idx < len(THREAD_STAGES) - 2:
                t.stage = THREAD_STAGES[current_idx + 1]
        else:
            state.threads[title] = ThreadState(
                title=title,
                stage="Investigation",
                last_progressed_scene=scene_num,
            )

    for title in threads_resolved:
        if title in state.threads:
            state.threads[title].stage = "Resolution"
            state.threads[title].needs_attention = False

    # Thread health check
    for _title, thread in state.threads.items():
        if thread.stage == "Resolution":
            thread.needs_attention = False
            continue
        health = thread_health_score(thread, scene_num)
        thread.needs_attention = health > 70

    state.metrics.thread_momentum = min(100, len([t for t in state.threads.values() if not t.needs_attention]) * 20)

    # NPC activity tracking
    for npc in npcs_featured:
        if npc not in state.npc_activity:
            state.npc_activity[npc] = NPCActivityState(name=npc)
        state.npc_activity[npc].last_active_scene = scene_num
        state.npc_activity[npc].activity_recommended = False

    # Flag NPCs inactive for too long
    for _name, npc_state in state.npc_activity.items():
        if scene_num - npc_state.last_active_scene > 8:
            npc_state.activity_recommended = True

    # Consequence: mark due consequences as overdue if they've been waiting too long
    for cons in state.consequences:
        if not cons.resolved and cons.consequence_due:
            scenes_waiting = scene_num - cons.scene
            if scenes_waiting > 3:
                cons.severity = "major" if cons.severity == "moderate" else cons.severity

    # Spotlight check
    for hook in state.character_hooks:
        hook.spotlight_recommended = check_spotlight_needed(hook, scene_num)

    # Add to scene history
    entry = SceneHistoryEntry(
        scene_id=scene_id,
        scene_number=scene_num,
        scene_type=scene_type,
        scene_purpose=scene_purpose,
        tension_before=old_tension,
        tension_after=new_tension,
        tension_change=new_tension - old_tension,
        emotional_shift=emotional_target,
        threads_advanced=list(threads_advanced),
        threads_resolved=list(threads_resolved),
        npcs_featured=list(npcs_featured),
        location=location,
        story_score=story_score,
        director_recommendation_followed=director_recommendation_followed,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    state.scene_history.append(entry)
    state.scene_history = state.scene_history[-20:]

    return state


# ---------------------------------------------------------------------------
# Thread sync from campaign DB entities
# ---------------------------------------------------------------------------

def sync_threads_from_entities(
    state: CampaignStoryState,
    entity_threads: list[dict],
) -> CampaignStoryState:
    """Sync thread state from DB entities (non-destructive — preserves stage/progress)."""
    for entity in entity_threads:
        title = entity.get("title") or entity.get("name") or ""
        if not title:
            continue
        if title not in state.threads:
            state.threads[title] = ThreadState(
                title=title,
                importance=int(entity.get("priority") or entity.get("importance") or 5),
                stage="Introduction",
            )
        else:
            # Update importance from DB if provided
            new_imp = entity.get("priority") or entity.get("importance")
            if new_imp:
                state.threads[title].importance = int(new_imp)
    return state


# ---------------------------------------------------------------------------
# Session-end review generation
# ---------------------------------------------------------------------------

def generate_session_review(
    state: CampaignStoryState,
    session_id: str,
) -> SessionReview:
    """Generate a review of the current session's scenes."""
    start = state.session_scene_start
    end = state.scene_count
    session_scenes = [e for e in state.scene_history if e.scene_number > start]

    threads_advanced = list({t for s in session_scenes for t in s.threads_advanced})
    threads_stalled = [
        title for title, t in state.threads.items()
        if t.needs_attention and title not in threads_advanced
    ]

    # Emotional curve from session scenes
    emotional_curve = [
        {"scene": s.scene_number, "emotional_shift": s.emotional_shift}
        for s in session_scenes
    ]

    tension_curve = [s.tension_after for s in session_scenes]

    # Story health: avg of scores if available
    scores = [s.story_score for s in session_scenes if s.story_score > 0]
    story_health_score = int(sum(scores) / len(scores)) if scores else 0

    # Campaign DNA score: are scenes advancing themes?
    dna_score = min(100, len(threads_advanced) * 15 + len([s for s in session_scenes if s.director_recommendation_followed]) * 10)

    review = SessionReview(
        session_id=session_id,
        scene_range=(start, end),
        threads_advanced=threads_advanced,
        threads_stalled=threads_stalled,
        setups_introduced=[s.description for s in state.setups if s.introduced_scene > start and not s.resolved],
        setups_resolved=[s.description for s in state.setups if s.introduced_scene <= start and s.resolved],
        promises_made=[p.promise for p in state.promises if p.introduced_scene > start],
        promises_resolved=[p.promise for p in state.promises if p.resolved],
        emotional_curve=emotional_curve,
        tension_curve=tension_curve,
        campaign_dna_score=dna_score,
        story_health_score=story_health_score,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    return review


# ---------------------------------------------------------------------------
# Story dashboard summary (for frontend)
# ---------------------------------------------------------------------------

def story_dashboard_payload(state: CampaignStoryState) -> dict[str, Any]:
    """Produce the full story dashboard payload for dev mode display."""
    scene_num = state.scene_count

    # Thread health for each
    thread_health = {}
    for title, thread in state.threads.items():
        health = thread_health_score(thread, scene_num)
        thread_health[title] = {
            "stage": thread.stage,
            "importance": thread.importance,
            "health_score": health,
            "needs_attention": thread.needs_attention,
            "scenes_since_progress": scene_num - thread.last_progressed_scene,
            "next_beat": thread.next_story_beat,
        }

    # Recent pacing pattern
    recent_types = [e.scene_type for e in state.scene_history[-6:]]

    return {
        "scene_count": scene_num,
        "metrics": state.metrics.model_dump(),
        "emotional_state": state.emotional_state.model_dump(),
        "tension_curve": state.tension_curve,
        "threads": thread_health,
        "recent_scene_types": recent_types,
        "player_intents": [i.model_dump() for i in state.player_intents if i.status == "active"],
        "character_hooks": [h.model_dump() for h in state.character_hooks],
        "setups": [s.model_dump() for s in state.setups if not s.resolved],
        "promises": [p.model_dump() for p in state.promises if not p.resolved],
        "mysteries": {k: v.model_dump() for k, v in state.mysteries.items()},
        "consequences": [c.model_dump() for c in state.consequences if not c.resolved],
        "npc_activity": {k: v.model_dump() for k, v in state.npc_activity.items()},
        "campaign_dna": state.campaign_dna.model_dump(),
        "scene_history_summary": [
            {
                "scene_number": e.scene_number,
                "scene_type": e.scene_type,
                "scene_purpose": e.scene_purpose,
                "tension": e.tension_after,
                "threads_advanced": e.threads_advanced,
                "story_score": e.story_score,
            }
            for e in state.scene_history[-10:]
        ],
    }
