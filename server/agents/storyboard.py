"""Storyboard agent: track beats and hooks, and generate story plots from campaign context.

The storyboard layer plans pressure, opportunities, and open questions. It must
never decide what the players do or pre-select outcomes.
"""


from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from ..steward_llm import chat_complete as _chat_complete
except Exception:
    _chat_complete = None  # type: ignore

router = APIRouter(tags=["storyboard"])


SUPPORTED_BEAT_TYPES = (
    "warning",
    "arrival",
    "discovery",
    "investigation",
    "social_pressure",
    "resource_pressure",
    "faction_move",
    "npc_request",
    "npc_conflict",
    "mystery_clue",
    "false_lead",
    "backstory_callback",
    "combat_threat",
    "combat_setup",
    "chase",
    "escape",
    "moral_choice",
    "downtime",
    "travel_complication",
    "rest_interruption",
    "reveal",
    "consequence",
    "aftermath",
    "session_climax",
    "session_close",
)

_BEAT_TO_SITUATION: dict[str, str] = {
    "warning": "new_scene_opening",
    "arrival": "arrival",
    "discovery": "discovery",
    "investigation": "investigation",
    "social_pressure": "social_conflict",
    "resource_pressure": "new_scene_opening",
    "faction_move": "faction_move",
    "npc_request": "conversation",
    "npc_conflict": "social_conflict",
    "mystery_clue": "investigation",
    "false_lead": "investigation",
    "backstory_callback": "backstory_callback",
    "combat_threat": "combat_setup",
    "combat_setup": "combat_setup",
    "chase": "travel",
    "escape": "travel",
    "moral_choice": "social_conflict",
    "downtime": "downtime",
    "travel_complication": "travel",
    "rest_interruption": "new_scene_opening",
    "reveal": "mystery_reveal",
    "consequence": "consequence",
    "aftermath": "consequence",
    "session_climax": "combat_setup",
    "session_close": "downtime",
}

_BEAT_TO_BUNDLE: dict[str, str] = {
    "warning": "OpeningBundle",
    "arrival": "TravelBundle",
    "discovery": "DiscoveryBundle",
    "investigation": "InvestigationBundle",
    "social_pressure": "DialogueBundle",
    "resource_pressure": "ThreatBundle",
    "faction_move": "FactionMoveBundle",
    "npc_request": "DialogueBundle",
    "npc_conflict": "DialogueBundle",
    "mystery_clue": "InvestigationBundle",
    "false_lead": "InvestigationBundle",
    "backstory_callback": "BackstoryHookBundle",
    "combat_threat": "CombatBundle",
    "combat_setup": "CombatBundle",
    "chase": "TravelBundle",
    "escape": "TravelBundle",
    "moral_choice": "DialogueBundle",
    "downtime": "DowntimeBundle",
    "travel_complication": "TravelBundle",
    "rest_interruption": "DowntimeBundle",
    "reveal": "InvestigationBundle",
    "consequence": "ConsequenceBundle",
    "aftermath": "ConsequenceBundle",
    "session_climax": "CombatBundle",
    "session_close": "DowntimeBundle",
}

_REPETITION_PATTERNS: dict[str, tuple[str, ...]] = {
    "repeated shaken NPC arrival": ("shaken", "visibly shaken", "burst", "stumbles in"),
    "repeated mysterious stranger": ("mysterious stranger", "cloaked figure", "hooded figure", "a stranger"),
    "repeated urgent request": ("urgent request", "we need help", "begs for help", "pleads for aid"),
    "repeated tavern/inn": ("tavern", " inn", "alehouse", "taproom", "flagon", "tankard"),
    "repeated abstract danger": ("danger looms", "the stakes are high", "great evil", "dark force"),
    "repeated something has gone wrong": ("something has gone wrong", "something is wrong", "a disturbance"),
    "repeated missing caravan/packet/lantern structure": ("missing caravan", "sealed packet", "lantern"),
}


class CampaignStoryboard(BaseModel):
    campaign_id: str
    campaign_premise: str = ""
    central_question: str = ""
    major_threat: str = ""
    major_factions: list[str] = Field(default_factory=list)
    act_structure: dict = Field(default_factory=lambda: {
        "current_act": 1,
        "act_goal": "",
        "act_exit_conditions": [],
    })
    active_clocks: list[dict] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    possible_future_beats: list[dict] = Field(default_factory=list)
    backstory_hooks_available: list[str] = Field(default_factory=list)
    do_not_force: list[str] = Field(default_factory=list)


class SessionStoryboard(BaseModel):
    session_id: str
    campaign_id: str
    session_goal: str = ""
    session_theme: str = ""
    starting_pressure: str = ""
    desired_tension_curve: list[int] = Field(default_factory=list)
    candidate_beats: list[dict] = Field(default_factory=list)
    likely_scene_types: list[str] = Field(default_factory=list)
    threads_to_touch: list[str] = Field(default_factory=list)
    threads_to_avoid_for_now: list[str] = Field(default_factory=list)
    possible_climaxes: list[dict] = Field(default_factory=list)
    fallback_beats: list[dict] = Field(default_factory=list)
    do_not_force: list[str] = Field(default_factory=list)
    recent_pattern_warnings: list[str] = Field(default_factory=list)


class SceneBeatPlan(BaseModel):
    scene_id: str
    scene_type: str
    scene_purpose: str
    primary_scene_purpose: str = ""
    secondary_scene_purpose: str = ""
    gm_move: str = ""
    target_emotion: str
    tension_level: int
    location: str = ""
    active_npcs: list[str] = Field(default_factory=list)
    visible_event: str = ""
    immediate_problem: str = ""
    concrete_stakes: str = ""
    player_choice_pressure: str = ""
    required_content_bundle: str
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    possible_player_approaches: list[str] = Field(default_factory=list)
    success_consequences: list[str] = Field(default_factory=list)
    failure_consequences: list[str] = Field(default_factory=list)


class BeatTypeDefinition(BaseModel):
    beat_type: str
    required_inputs: list[str] = Field(default_factory=list)
    preferred_situation_contract: str = ""
    required_content_fields: list[str] = Field(default_factory=list)
    likely_ui_widgets: list[str] = Field(default_factory=list)
    validator_rules: list[str] = Field(default_factory=list)
    required_content_bundle: str = ""


class PacingPatternState(BaseModel):
    recent_scene_types: list[str] = Field(default_factory=list)
    recent_motifs: list[str] = Field(default_factory=list)
    recent_npc_roles: list[str] = Field(default_factory=list)
    recent_opening_shapes: list[str] = Field(default_factory=list)
    recent_locations: list[str] = Field(default_factory=list)


class SceneBeatSelectionInput(BaseModel):
    session_storyboard: SessionStoryboard
    campaign_storyboard: CampaignStoryboard
    player_actions: list[str] = Field(default_factory=list)
    world_tick_delta: dict = Field(default_factory=dict)
    current_situation_type: str = ""
    active_clocks: list[dict] = Field(default_factory=list)
    current_location: str = ""
    npcs_present: list[str] = Field(default_factory=list)
    recent_scene_types: list[str] = Field(default_factory=list)
    unresolved_threads: list[str] = Field(default_factory=list)
    backstory_spotlight_tracker: dict = Field(default_factory=dict)
    recent_patterns: PacingPatternState = Field(default_factory=PacingPatternState)


class SceneBeatSelectionResult(BaseModel):
    selected_plan: SceneBeatPlan
    beat_type_chosen: str
    beat_selection_reason: str
    rejected_candidate_beats: list[dict] = Field(default_factory=list)
    repetition_warnings: list[str] = Field(default_factory=list)
    threads_advanced: list[str] = Field(default_factory=list)


_BASE_BEAT_DEFS: dict[str, dict] = {
    "mystery_clue": {
        "required_inputs": [
            "mystery_question",
            "clue_object",
            "discovery_method",
            "what_it_suggests",
            "what_it_does_not_reveal",
            "possible_misinterpretation",
        ],
        "required_content_fields": ["mystery_question", "scene_location", "visible_clues", "required_conclusions"],
        "likely_ui_widgets": ["visible_clues", "leads", "theories", "available_checks"],
        "validator_rules": ["visible_clues_are_concrete", "clues_dont_reveal_everything"],
    },
    "social_pressure": {
        "required_inputs": [
            "npcs_involved",
            "conflicting_wants",
            "stakes",
            "what_each_npc_knows",
            "what_each_npc_hides",
            "possible_checks",
            "relationship_consequences",
        ],
        "required_content_fields": ["npc", "conflict_topic", "stakes", "possible_checks", "failure_forward_options"],
        "likely_ui_widgets": ["npc_attitude", "leverage", "possible_checks"],
        "validator_rules": ["npc_wants_something", "failure_forward_exists"],
    },
    "combat_threat": {
        "required_inputs": [
            "enemy_presence",
            "enemy_goal",
            "terrain",
            "warning_signs",
            "avoidance_option",
            "combat_trigger",
            "stakes",
        ],
        "required_content_fields": ["combatants", "battlefield", "stakes", "victory_conditions", "failure_consequences"],
        "likely_ui_widgets": ["initiative", "enemy_cards", "terrain", "actions"],
        "validator_rules": ["battlefield_has_features", "combat_has_stakes", "non_combat_options_present"],
    },
}


def beat_type_library() -> dict[str, BeatTypeDefinition]:
    """Return the reusable beat type library."""
    library: dict[str, BeatTypeDefinition] = {}
    for beat_type in SUPPORTED_BEAT_TYPES:
        base = dict(_BASE_BEAT_DEFS.get(beat_type, {}))
        library[beat_type] = BeatTypeDefinition(
            beat_type=beat_type,
            required_inputs=base.get("required_inputs") or ["active_thread_or_pressure"],
            preferred_situation_contract=_BEAT_TO_SITUATION.get(beat_type, "new_scene_opening"),
            required_content_fields=base.get("required_content_fields") or [
                "visible_event",
                "immediate_problem",
                "concrete_stakes",
            ],
            likely_ui_widgets=base.get("likely_ui_widgets") or ["objective", "suggested_actions"],
            validator_rules=base.get("validator_rules") or ["requires_concrete_stakes"],
            required_content_bundle=_BEAT_TO_BUNDLE.get(beat_type, "OpeningBundle"),
        )
    return library


def flag_repetition(patterns: PacingPatternState | dict) -> list[str]:
    """Detect repeated scene structures that make generated scenes feel samey."""
    state = patterns if isinstance(patterns, PacingPatternState) else PacingPatternState(**(patterns or {}))
    warnings: list[str] = []
    checks = {
        "repeated scene type": state.recent_scene_types,
        "repeated motif": state.recent_motifs,
        "repeated NPC role": state.recent_npc_roles,
        "repeated opening shape": state.recent_opening_shapes,
        "repeated location": state.recent_locations,
    }
    for label, values in checks.items():
        if len(values) >= 2 and values[-1] == values[-2]:
            warnings.append(f"{label}: {values[-1]}")
    hay = " ".join(state.recent_motifs + state.recent_opening_shapes + state.recent_locations).lower()
    for warning, terms in _REPETITION_PATTERNS.items():
        if any(term in hay for term in terms):
            warnings.append(warning)
    return warnings


def create_campaign_storyboard(
    campaign_id: str,
    campaign_premise: str = "",
    central_question: str = "",
    major_threat: str = "",
    major_factions: list[str] | None = None,
    open_threads: list[str] | None = None,
    backstory_hooks_available: list[str] | None = None,
) -> CampaignStoryboard:
    """Create broad campaign pressure without fixing player outcomes."""
    threads = list(open_threads or [])
    question = central_question or (f"What is really happening with {threads[0]}?" if threads else "What pressure will define this campaign?")
    return CampaignStoryboard(
        campaign_id=campaign_id,
        campaign_premise=campaign_premise,
        central_question=question,
        major_threat=major_threat,
        major_factions=list(major_factions or []),
        act_structure={
            "current_act": 1,
            "act_goal": "Bring the central pressure into play while preserving multiple paths.",
            "act_exit_conditions": [
                "players resolve or redefine the opening pressure",
                "a major faction move changes the situation",
                "the central question gains an earned clue",
            ],
        },
        open_threads=threads,
        possible_future_beats=[
            {"beat_type": "mystery_clue", "thread": threads[0], "optional": True}
        ] if threads else [],
        backstory_hooks_available=list(backstory_hooks_available or []),
        do_not_force=[],
    )


def generate_session_storyboard(
    session_id: str,
    campaign: CampaignStoryboard,
    campaign_contract: dict | None = None,
    recent_patterns: PacingPatternState | dict | None = None,
) -> SessionStoryboard:
    """Generate a loose session plan with candidate beats, not fixed outcomes."""
    contract = campaign_contract or {}
    patterns = recent_patterns if isinstance(recent_patterns, PacingPatternState) else PacingPatternState(**(recent_patterns or {}))
    pacing = str(contract.get("pacing_profile") or contract.get("pacing") or "rising").lower()
    theme = _session_theme_from_contract(contract, campaign)
    tension_curve = [25, 40, 55, 70] if pacing != "slow-burn" else [20, 30, 45, 60]
    warnings = flag_repetition(patterns)
    beat_types = _candidate_beat_types_for_campaign(campaign, contract)
    if warnings:
        beat_types = [b for b in beat_types if not _beat_matches_repetition(b, warnings)] or ["discovery", "consequence", "downtime"]
    candidate_beats = [
        {
            "beat_type": beat_type,
            "purpose": _purpose_for_beat(beat_type, campaign),
            "thread": (campaign.open_threads or [""])[0],
            "optional": True,
        }
        for beat_type in beat_types[:6]
    ]
    return SessionStoryboard(
        session_id=session_id,
        campaign_id=campaign.campaign_id,
        session_goal=f"Apply pressure to: {campaign.central_question}",
        session_theme=theme,
        starting_pressure=campaign.open_threads[0] if campaign.open_threads else campaign.major_threat,
        desired_tension_curve=tension_curve,
        candidate_beats=candidate_beats,
        likely_scene_types=[_BEAT_TO_SITUATION.get(b["beat_type"], "new_scene_opening") for b in candidate_beats],
        threads_to_touch=campaign.open_threads[:3],
        threads_to_avoid_for_now=[],
        possible_climaxes=[
            {"beat_type": "session_climax", "purpose": "force a decision about pressure, not a predetermined outcome", "optional": True}
        ],
        fallback_beats=[
            {"beat_type": "consequence", "purpose": "show an offscreen consequence of ignored pressure", "optional": True},
            {"beat_type": "downtime", "purpose": "let players choose reflection, recovery, or preparation", "optional": True},
        ],
        do_not_force=list(campaign.do_not_force),
        recent_pattern_warnings=warnings,
    )


def select_scene_beat(selection: SceneBeatSelectionInput | dict) -> SceneBeatSelectionResult:
    """Select the next scene beat while giving player action priority."""
    data = selection if isinstance(selection, SceneBeatSelectionInput) else SceneBeatSelectionInput(**selection)
    warnings = flag_repetition(data.recent_patterns)
    candidates = list(data.session_storyboard.candidate_beats or [])
    candidates.extend(data.campaign_storyboard.possible_future_beats or [])
    candidates.extend(data.session_storyboard.fallback_beats or [])
    if not candidates:
        candidates = [{"beat_type": "discovery", "purpose": "surface a concrete opportunity", "optional": True}]

    player_override = _beat_from_player_actions(data.player_actions)
    if player_override:
        candidates.insert(0, {"beat_type": player_override, "purpose": "respond to player action", "optional": True, "source": "player_action"})

    scored: list[tuple[int, dict, list[str]]] = []
    rejected: list[dict] = []
    do_not_force = set(data.campaign_storyboard.do_not_force + data.session_storyboard.do_not_force)
    recent_types = [t.lower() for t in data.recent_scene_types + data.recent_patterns.recent_scene_types]
    unresolved = set(data.unresolved_threads or data.campaign_storyboard.open_threads)
    for candidate in candidates:
        beat_type = str(candidate.get("beat_type") or candidate.get("type") or "")
        if beat_type not in SUPPORTED_BEAT_TYPES:
            rejected.append({"candidate": candidate, "reason": "unsupported beat type"})
            continue
        labels = {beat_type, str(candidate.get("thread") or ""), str(candidate.get("hook") or "")}
        if any(label and label in do_not_force for label in labels):
            rejected.append({"candidate": candidate, "reason": "listed in do_not_force"})
            continue
        reasons: list[str] = []
        score = 10
        situation = _BEAT_TO_SITUATION.get(beat_type, "new_scene_opening")
        if candidate.get("source") == "player_action":
            score += 60
            reasons.append("responds to player action")
        if candidate.get("thread") in unresolved or beat_type in ("consequence", "mystery_clue", "faction_move"):
            score += 15
            reasons.append("advances active pressure")
        if data.current_location and data.current_location.lower() in str(candidate).lower():
            score += 10
            reasons.append("fits current location")
        if any(n.lower() in str(candidate).lower() for n in data.npcs_present):
            score += 10
            reasons.append("uses present NPC")
        if situation.lower() in recent_types[-3:] or beat_type.lower() in recent_types[-3:]:
            score -= 30
            reasons.append("penalized for recent scene type")
        if warnings and _beat_matches_repetition(beat_type, warnings):
            score -= 40
            reasons.append("penalized for repeated motif")
        if beat_type == "backstory_callback" and not _backstory_allowed(data.backstory_spotlight_tracker):
            score -= 35
            reasons.append("backstory policy/spotlight not ready")
        scored.append((score, candidate, reasons))

    if not scored:
        fallback = {"beat_type": "discovery", "purpose": "offer a fresh, concrete choice", "optional": True}
        scored = [(1, fallback, ["fallback after rejected candidates"])]

    scored.sort(key=lambda row: row[0], reverse=True)
    score, selected, reasons = scored[0]
    beat_type = str(selected.get("beat_type"))
    plan = _plan_from_candidate(
        selected,
        selection=data,
        tension=_tension_for_next_scene(data.session_storyboard, len(data.recent_scene_types)),
    )
    return SceneBeatSelectionResult(
        selected_plan=plan,
        beat_type_chosen=beat_type,
        beat_selection_reason=", ".join(reasons) or f"highest scoring available beat ({score})",
        rejected_candidate_beats=rejected + [
            {"candidate": candidate, "reason": ", ".join(reason_list) or "lower score", "score": candidate_score}
            for candidate_score, candidate, reason_list in scored[1:4]
        ],
        repetition_warnings=warnings,
        threads_advanced=[str(selected.get("thread"))] if selected.get("thread") else [],
    )


def update_storyboards_after_scene(
    campaign: CampaignStoryboard,
    session: SessionStoryboard,
    scene_plan: SceneBeatPlan,
    player_intent: str = "",
    resolved_threads: list[str] | None = None,
    ignored_hooks: list[str] | None = None,
    new_possible_beats: list[dict] | None = None,
    unresolved_questions: list[str] | None = None,
) -> tuple[CampaignStoryboard, SessionStoryboard]:
    """Update storyboard state after a scene without re-forcing rejected hooks."""
    resolved = set(resolved_threads or [])
    ignored = set(ignored_hooks or [])
    campaign.open_threads = [t for t in campaign.open_threads if t not in resolved]
    campaign.open_threads.extend(q for q in (unresolved_questions or []) if q and q not in campaign.open_threads)
    campaign.possible_future_beats = [
        beat for beat in campaign.possible_future_beats
        if (
            beat.get("beat_type") != scene_plan.scene_type
            and _BEAT_TO_SITUATION.get(str(beat.get("beat_type") or "")) != scene_plan.scene_type
            and beat.get("thread") not in resolved
        )
    ]
    campaign.possible_future_beats.extend(new_possible_beats or [])
    for hook in ignored:
        if hook and hook not in campaign.do_not_force:
            campaign.do_not_force.append(hook)
    if player_intent:
        campaign.active_clocks.append({"type": "player_intent", "intent": player_intent, "status": "observed"})

    session.candidate_beats = [
        beat for beat in session.candidate_beats
        if (
            beat.get("beat_type") != scene_plan.scene_type
            and _BEAT_TO_SITUATION.get(str(beat.get("beat_type") or "")) != scene_plan.scene_type
            and beat.get("thread") not in resolved
        )
    ]
    for hook in ignored:
        if hook and hook not in session.do_not_force:
            session.do_not_force.append(hook)
    return campaign, session


def _session_theme_from_contract(contract: dict, campaign: CampaignStoryboard) -> str:
    dna = contract.get("campaign_dna") or {}
    themes = contract.get("themes") or dna.get("themes") or []
    if themes:
        return str(themes[0])
    if campaign.major_threat:
        return f"pressure from {campaign.major_threat}"
    return "agency under pressure"


def _candidate_beat_types_for_campaign(campaign: CampaignStoryboard, contract: dict) -> list[str]:
    text = " ".join([
        campaign.campaign_premise,
        campaign.central_question,
        campaign.major_threat,
        str(contract.get("campaign_pitch") or ""),
        str(contract.get("pacing_profile") or ""),
        " ".join(campaign.open_threads),
    ]).lower()
    beats = ["discovery", "social_pressure", "consequence", "faction_move", "mystery_clue", "downtime"]
    if any(term in text for term in ("mystery", "secret", "clue", "question", "vanished", "missing")):
        beats = ["mystery_clue", "investigation", "false_lead", "social_pressure", "consequence", "reveal"]
    if any(term in text for term in ("war", "raider", "monster", "enemy", "combat", "battle")):
        beats = ["warning", "combat_threat", "faction_move", "resource_pressure", "consequence", "aftermath"]
    if any(term in text for term in ("travel", "road", "journey", "wilderness", "survival")):
        beats = ["travel_complication", "resource_pressure", "arrival", "discovery", "consequence", "downtime"]
    if campaign.backstory_hooks_available:
        beats.insert(2, "backstory_callback")
    return beats


def _beat_matches_repetition(beat_type: str, warnings: list[str]) -> bool:
    hay = " ".join(warnings).lower()
    if "tavern" in hay and beat_type in {"npc_request", "social_pressure"}:
        return True
    if "urgent request" in hay and beat_type == "npc_request":
        return True
    if "mysterious stranger" in hay and beat_type in {"warning", "npc_request"}:
        return True
    if "shaken npc" in hay and beat_type in {"warning", "npc_request"}:
        return True
    if "abstract danger" in hay and beat_type in {"warning", "combat_threat"}:
        return True
    if "missing caravan" in hay and beat_type in {"mystery_clue", "travel_complication"}:
        return True
    return False


def _purpose_for_beat(beat_type: str, campaign: CampaignStoryboard) -> str:
    thread = campaign.open_threads[0] if campaign.open_threads else campaign.central_question
    purposes = {
        "mystery_clue": f"offer an earned clue about {thread} without answering the whole mystery",
        "investigation": f"let players choose how to examine {thread}",
        "combat_threat": "make danger visible with terrain, warning signs, and an avoidance option",
        "social_pressure": "put conflicting NPC wants in the player's path",
        "faction_move": "show a faction changing the world offscreen or nearby",
        "consequence": "show what changed because of prior choices or ignored pressure",
        "downtime": "give players room to recover, plan, and reveal priorities",
    }
    return purposes.get(beat_type, f"apply pressure around {thread}")


def _beat_from_player_actions(actions: list[str]) -> str:
    text = " ".join(actions).lower()
    if any(term in text for term in ("attack", "strike", "shoot", "cast fireball", "draw my sword")):
        return "combat_setup"
    if any(term in text for term in ("search", "inspect", "investigate", "examine", "look for clues")):
        return "investigation"
    if any(term in text for term in ("travel", "go to", "head to", "leave for", "ride to")):
        return "travel_complication"
    if any(term in text for term in ("talk", "ask", "persuade", "interrogate", "negotiate")):
        return "social_pressure"
    if any(term in text for term in ("rest", "sleep", "camp", "long rest")):
        return "rest_interruption"
    return ""


def _backstory_allowed(tracker: dict) -> bool:
    if not tracker:
        return True
    policy = str(tracker.get("policy") or tracker.get("backstory_policy") or "allowed").lower()
    if policy in {"none", "off", "disabled", "do_not_use"}:
        return False
    if tracker.get("player_opted_out"):
        return False
    if tracker.get("recently_spotlit"):
        return False
    return True


def _tension_for_next_scene(session: SessionStoryboard, scene_index: int) -> int:
    if not session.desired_tension_curve:
        return 40
    return session.desired_tension_curve[min(scene_index, len(session.desired_tension_curve) - 1)]


def _plan_from_candidate(candidate: dict, selection: SceneBeatSelectionInput, tension: int) -> SceneBeatPlan:
    beat_type = str(candidate.get("beat_type") or "discovery")
    situation = _BEAT_TO_SITUATION.get(beat_type, "new_scene_opening")
    bundle = _BEAT_TO_BUNDLE.get(beat_type, "OpeningBundle")
    thread = str(candidate.get("thread") or (selection.unresolved_threads or selection.campaign_storyboard.open_threads or ["the active pressure"])[0])
    location = str(candidate.get("location") or selection.current_location or "")
    npcs = [str(n) for n in (candidate.get("npcs") or selection.npcs_present or [])]
    must_not = [
        "do not decide player choices",
        "do not pre-decide outcomes",
        "do not force a single path",
        "do not reveal mysteries before earned clues",
    ] + list(selection.campaign_storyboard.do_not_force) + list(selection.session_storyboard.do_not_force)
    if "tavern/inn" not in " ".join(must_not).lower():
        must_not.append("do not default to a tavern or inn unless established by context")
    purpose = str(candidate.get("purpose") or _purpose_for_beat(beat_type, selection.campaign_storyboard))
    primary_purpose = str(candidate.get("primary_scene_purpose") or _primary_purpose_for_beat(beat_type))
    gm_move = str(candidate.get("gm_move") or _gm_move_for_beat(beat_type))
    return SceneBeatPlan(
        scene_id=str(candidate.get("scene_id") or f"{selection.session_storyboard.session_id}:{beat_type}:{len(selection.recent_scene_types) + 1}"),
        scene_type=situation,
        scene_purpose=purpose,
        primary_scene_purpose=primary_purpose,
        secondary_scene_purpose=str(candidate.get("secondary_scene_purpose") or ""),
        gm_move=gm_move,
        target_emotion=_emotion_for_beat(beat_type),
        tension_level=max(0, min(100, tension)),
        location=location,
        active_npcs=npcs,
        visible_event=str(candidate.get("visible_event") or _visible_event_for_beat(beat_type, thread)),
        immediate_problem=str(candidate.get("immediate_problem") or f"{thread} has produced a choice the players can act on now."),
        concrete_stakes=str(candidate.get("concrete_stakes") or f"If ignored, {thread} advances offscreen and changes the next opportunity."),
        player_choice_pressure=str(candidate.get("player_choice_pressure") or "Players can engage, redirect, delay, investigate, negotiate, avoid, or create a new approach."),
        required_content_bundle=bundle,
        must_include=[thread] if thread else [],
        must_not_include=must_not,
        possible_player_approaches=list(candidate.get("possible_player_approaches") or [
            "engage directly",
            "investigate first",
            "seek leverage or allies",
            "avoid the pressure and accept consequences",
        ]),
        success_consequences=list(candidate.get("success_consequences") or ["the active thread becomes clearer or safer"]),
        failure_consequences=list(candidate.get("failure_consequences") or ["the pressure advances without dead-ending the scene"]),
    )


def _primary_purpose_for_beat(beat_type: str) -> str:
    if beat_type in {"mystery_clue", "investigation", "false_lead", "reveal"}:
        return "reveal_clue"
    if beat_type in {"combat_threat", "combat_setup", "chase", "escape", "rest_interruption"}:
        return "introduce_threat"
    if beat_type in {"social_pressure", "npc_conflict", "moral_choice"}:
        return "force_decision"
    if beat_type in {"downtime", "recovery"}:
        return "offer_recovery"
    if beat_type in {"travel", "journey"}:
        return "transition_location"
    if beat_type in {"consequence", "aftermath"}:
        return "show_consequence"
    return "seed_thread"


def _gm_move_for_beat(beat_type: str) -> str:
    if beat_type in {"mystery_clue", "investigation", "false_lead", "reveal"}:
        return "reveal_clue"
    if beat_type in {"combat_threat", "combat_setup", "chase", "escape", "rest_interruption"}:
        return "show_approaching_threat"
    if beat_type in {"social_pressure", "npc_conflict"}:
        return "put_someone_in_a_spot"
    if beat_type == "moral_choice":
        return "present_moral_choice"
    if beat_type in {"downtime", "recovery"}:
        return "offer_recovery"
    if beat_type in {"consequence", "aftermath"}:
        return "show_consequence"
    return "introduce_complication"


def _emotion_for_beat(beat_type: str) -> str:
    if beat_type in {"combat_threat", "combat_setup", "chase", "escape", "rest_interruption"}:
        return "urgency"
    if beat_type in {"mystery_clue", "investigation", "false_lead", "reveal"}:
        return "curiosity"
    if beat_type in {"social_pressure", "npc_conflict", "moral_choice"}:
        return "tension"
    if beat_type in {"downtime", "aftermath", "session_close"}:
        return "reflection"
    return "intrigue"


def _visible_event_for_beat(beat_type: str, thread: str) -> str:
    if beat_type == "mystery_clue":
        return f"A concrete clue tied to {thread} appears where players can examine it."
    if beat_type == "combat_threat":
        return "Warning signs show an enemy presence, goal, terrain, and a non-combat exit."
    if beat_type == "social_pressure":
        return "NPCs with incompatible wants make the pressure visible through action."
    if beat_type == "faction_move":
        return "A faction changes the local situation in a way the players can notice."
    if beat_type == "consequence":
        return "A prior choice or ignored hook produces an observable consequence."
    return f"{thread} becomes visible through a specific event."


def _model_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class StoryboardRequest(BaseModel):
    scene: str
    choices: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    completed: list[str] = Field(default_factory=list)


class StoryboardResponse(BaseModel):
    storyboard: dict
    next_focus: str


@router.post("/storyboard/update", response_model=StoryboardResponse)
def update_storyboard(payload: StoryboardRequest) -> StoryboardResponse:
    next_focus = payload.unresolved[0] if payload.unresolved else "Introduce a fresh complication."
    storyboard = {
        "scene": payload.scene,
        "choices": payload.choices,
        "unresolved": payload.unresolved,
        "completed": payload.completed,
    }
    return StoryboardResponse(storyboard=storyboard, next_focus=next_focus)


class StoryboardPlotRequest(BaseModel):
    """Input for generating an initial story plot (New Session Workflow, Step 1).

    Data sources:
    - ``players`` — session members' character names (from ``pcs.json`` / session meta)
    - ``campaign_settings`` — :class:`CampaignSettings` dict from
      ``/campaigns/{id}/settings`` (genre, tone, setting_summary, world_name, …)
    - ``campaign_variables`` — :class:`CampaignVariables` dict from
      ``/campaigns/{id}/variables`` (narrative_style, themes, factions, pacing, …)
    - ``campaign_docs`` — document content from the session document store
    """

    session_id: str | None = Field(default=None, description="Session context, used for logging")
    players: list[str] = Field(default_factory=list, description="Player/character names involved")
    campaign_settings: dict = Field(
        default_factory=dict,
        description=(
            "CampaignSettings fields: genre, tone, setting_summary, world_name, "
            "ruleset, starting_level, house_rules, player_run_mode"
        ),
    )
    campaign_variables: dict = Field(
        default_factory=dict,
        description=(
            "CampaignVariables fields: narrative_style, themes, pacing, "
            "factions, npc_archetypes, naming_style, content_rating"
        ),
    )
    campaign_docs: list[str] = Field(default_factory=list, description="Campaign document texts to draw story hooks from")


class StoryboardPlotResponse(BaseModel):
    """Raw campaign material produced for the Scene Director (New Session Workflow, Step 1 output)."""

    plot: str = Field(..., description="Evocative plot seed — passed to Scene Director as context")
    hooks: list[str] = Field(default_factory=list, description="Active story hooks from campaign docs/memory")
    npcs_mentioned: list[str] = Field(default_factory=list, description="NPC names extracted from docs/factions")

    # Structured candidate lists for the Scene Director
    candidate_story_threads: list[str] = Field(default_factory=list, description="Unresolved threads / quests from docs")
    candidate_npcs: list[str] = Field(default_factory=list, description="Alias for npcs_mentioned — for Scene Director")
    candidate_locations: list[str] = Field(default_factory=list, description="Named locations extracted from docs/settings")
    candidate_factions: list[str] = Field(default_factory=list, description="Faction names from campaign variables")
    recent_events: list[str] = Field(default_factory=list, description="Recent-event lines from campaign docs")
    open_hooks: list[str] = Field(default_factory=list, description="Player-facing hooks (not yet resolved)")
    recommended_scene_purpose: str = Field(
        default="opening",
        description="Suggested scene type: opening | consequence | discovery | social | travel",
    )
    campaign_storyboard: dict = Field(default_factory=dict, description="Loose campaign pressure plan")
    session_storyboard: dict = Field(default_factory=dict, description="Loose session plan with candidate beats")


_DEFAULT_HOOKS = [
    "The road ahead is quiet — too quiet for a busy trade route.",
    "Smoke rises from a direction it shouldn't.",
    "A sealed letter arrived last night, addressed to no one.",
]

_MIN_HOOK_LENGTH = 10
_MAX_HOOK_LENGTH = 120

# Doc-line prefixes that mark candidate entities
_NPC_PREFIXES = ("npc:", "enemy:", "villain:", "ally:", "contact:", "boss:", "patron:")
_LOCATION_PREFIXES = ("location:", "place:", "town:", "city:", "village:", "dungeon:", "inn:", "keep:", "fortress:", "region:")
_THREAD_PREFIXES = ("thread:", "quest:", "hook:", "mission:", "task:", "objective:", "conflict:", "problem:")
_EVENT_PREFIXES = ("event:", "recent:", "news:", "rumor:", "rumour:", "happening:", "incident:")


@router.get("/storyboard/beat-library")
def get_beat_library() -> dict[str, dict]:
    return {key: _model_to_dict(value) for key, value in beat_type_library().items()}


@router.post("/storyboard/select-beat", response_model=SceneBeatSelectionResult)
def select_beat_endpoint(payload: SceneBeatSelectionInput) -> SceneBeatSelectionResult:
    return select_scene_beat(payload)


def _extract_hooks_from_docs(docs: list[str]) -> list[str]:
    """Pull meaningful lines from campaign documents to use as story hooks."""
    hooks: list[str] = []
    for doc in docs:
        for line in doc.splitlines():
            stripped = line.strip(" -#*\t")
            lower = stripped.lower()
            if (
                len(stripped) > _MIN_HOOK_LENGTH
                and not lower.startswith(("use this", "(ai gm", "session notes"))
                and not _is_contract_heading_line(stripped)
            ):
                hooks.append(stripped[:_MAX_HOOK_LENGTH])
                break
    return hooks


def _is_contract_heading_line(line: str) -> bool:
    normalized = line.strip().strip("[]").strip().lower().rstrip(":")
    if not normalized:
        return True
    if normalized in {
        "campaign contract",
        "campaign output contract",
        "agent output contract",
        "requirements",
        "contract",
    }:
        return True
    return normalized.startswith(("campaign output contract", "requirements for "))


def _extract_prefixed(docs: list[str], prefixes: tuple[str, ...]) -> list[str]:
    """Extract values after labelled prefixes (e.g. 'NPC: Elira Voss') from docs."""
    found: list[str] = []
    for doc in docs:
        for line in doc.splitlines():
            lower = line.lower().strip()
            for prefix in prefixes:
                if lower.startswith(prefix):
                    value = line[len(prefix):].split(",")[0].split(".")[0].strip()
                    if value and value not in found:
                        found.append(value)
                    break
    return found


@router.post("/storyboard/generate", response_model=StoryboardPlotResponse)
def generate_plot(payload: StoryboardPlotRequest) -> StoryboardPlotResponse:
    """Step 1 of New Session Workflow.

    Reads player roster, campaign settings, campaign variables, and campaign
    documents to produce a structured story plot that the Narrative Agent will
    use to craft the opening scene.

    Data consumed and where it originates:
    - ``genre`` / ``tone`` / ``setting_summary`` / ``world_name``
        → ``campaign_settings`` (set via ``PUT /campaigns/{id}/settings``)
    - ``narrative_style`` / ``themes`` / ``factions`` / ``pacing``
        → ``campaign_variables`` (set via ``PUT /campaigns/{id}/variables``)
    - ``players`` → session members' character names
    - ``campaign_docs`` → session document store content
    """
    # -- Campaign settings (genre, tone, setting) --
    genre = str(payload.campaign_settings.get("genre") or "fantasy").strip() or "fantasy"
    tone = (
        str(payload.campaign_settings.get("tone") or "").strip()
        or str(payload.campaign_variables.get("narrative_style") or "balanced").strip()
        or "balanced"
    )
    setting = str(
        payload.campaign_settings.get("setting_summary")
        or payload.campaign_settings.get("setting") or ""
    ).strip()
    world_name = str(payload.campaign_settings.get("world_name") or "").strip()

    # -- Campaign variables (themes, factions) --
    themes: list[str] = [str(t) for t in (payload.campaign_variables.get("themes") or []) if t]
    factions: list[dict] = [
        f for f in (payload.campaign_variables.get("factions") or [])
        if isinstance(f, dict) and f.get("name")
    ]
    player_list = ", ".join(p for p in payload.players if p) if payload.players else "the party"

    # -- Extract structured candidates from docs --
    doc_hooks = _extract_hooks_from_docs(payload.campaign_docs)
    candidate_locations = _extract_prefixed(payload.campaign_docs, _LOCATION_PREFIXES)
    candidate_npcs_from_docs = _extract_prefixed(payload.campaign_docs, _NPC_PREFIXES)
    candidate_threads = _extract_prefixed(payload.campaign_docs, _THREAD_PREFIXES)
    recent_events = _extract_prefixed(payload.campaign_docs, _EVENT_PREFIXES)

    # Faction names from variables
    faction_names = [str(f.get("name", "")).strip() for f in factions if f.get("name")]
    # Faction members as NPC candidates
    npcs_mentioned: list[str] = list(candidate_npcs_from_docs)
    for faction in factions:
        for member in faction.get("members") or []:
            if member and member not in npcs_mentioned:
                npcs_mentioned.append(member)

    # -- Open hooks: prefer thread / quest lines over generic doc hooks --
    open_hooks = candidate_threads[:3] or doc_hooks[:3]
    hooks: list[str] = []
    if themes:
        hooks.extend(themes[:3])
    for h in (candidate_threads or doc_hooks):
        if h not in hooks:
            hooks.append(h)
    if not hooks:
        hooks = list(_DEFAULT_HOOKS[:2])

    # -- Determine recommended scene purpose --
    if candidate_threads or open_hooks:
        recommended_purpose = "consequence" if recent_events else "opening"
    else:
        recommended_purpose = "opening"

    # -- Build rule-based plot seed from structured data --
    # Don't write "A heroic fantasy adventure awaits." — be specific.
    world_ref = world_name or setting
    plot_parts: list[str] = []
    if candidate_threads:
        plot_parts.append(candidate_threads[0][:200])
    elif open_hooks:
        plot_parts.append(open_hooks[0][:200])
    if factions:
        fname = factions[0].get("name", "")
        fgoals = [str(g) for g in (factions[0].get("goals") or []) if g]
        if fname and fgoals:
            plot_parts.append(f"The {fname} is moving: {fgoals[0][:80]}.")
        elif fname:
            plot_parts.append(f"The {fname} casts a long shadow over events.")
    if not plot_parts:
        loc = candidate_locations[0] if candidate_locations else (world_ref or "the region")
        flavor = f"{genre} world of {tone}" if tone and tone not in ("balanced", "moderate") else f"{genre} world"
        plot_parts.append(f"In the {flavor}, {loc} demands the party's immediate attention.")
    if recent_events:
        plot_parts.append(recent_events[0][:120])
    plot = " ".join(plot_parts)

    # -- LLM enrichment: produce a specific, grounded plot seed --
    if _chat_complete:
        try:
            ctx: list[str] = []
            if world_ref:
                ctx.append(f"Setting: {world_ref[:150]}")
            ctx.append(f"Genre/Tone: {genre}, {tone}")
            ctx.append(f"Player character: {player_list}")
            if candidate_threads:
                ctx.append("Active story threads:\n" + "\n".join(f"  • {t}" for t in candidate_threads[:3]))
            if open_hooks:
                ctx.append("Open hooks:\n" + "\n".join(f"  • {h}" for h in open_hooks[:3]))
            if npcs_mentioned:
                ctx.append(f"Known NPCs: {', '.join(npcs_mentioned[:5])}")
            if candidate_locations:
                ctx.append(f"Known locations: {', '.join(candidate_locations[:4])}")
            if faction_names:
                ctx.append(f"Factions: {', '.join(faction_names[:3])}")
            if recent_events:
                ctx.append(f"Recent events: {'; '.join(recent_events[:2])}")

            llm_sys = (
                "You are a tabletop RPG campaign architect. Write a SPECIFIC, GROUNDED plot seed "
                f"(2–3 sentences, max 80 words) for the opening of this {genre} session.\n\n"
                "Requirements:\n"
                "  — Name a SPECIFIC location from the context (or invent one that fits) — do NOT default to a tavern or inn unless the context mentions one\n"
                "  — Name a SPECIFIC NPC from the context (or invent one with a real name)\n"
                "  — Describe what is ACTIVELY HAPPENING right now — a concrete event, not a vague mood\n"
                "  — Create immediate urgency or tension\n"
                "  — Do NOT start with 'The party'. Do NOT say 'heroic fantasy adventure' or similar.\n"
                "  — Do NOT describe the genre or campaign structure\n\n"
                "Return only the plot text. No JSON, no commentary, no title."
            )
            llm_result = _chat_complete(
                [{"role": "system", "content": llm_sys},
                 {"role": "user", "content": "\n".join(ctx)}],
                task_scope="taverntails_plot",
                max_tokens=200,
                timeout=90.0,
            )
            if llm_result and len(llm_result.strip()) > 20:
                plot = llm_result.strip()
        except Exception:
            pass

    # Ensure genre/tone always appear in the plot so downstream consumers and tests
    # can identify the requested style (especially when deterministic fallback ran).
    if genre.lower() not in plot.lower():
        plot = f"({genre}, {tone}) {plot}"

    campaign_storyboard = create_campaign_storyboard(
        campaign_id=str(payload.campaign_settings.get("campaign_id") or payload.session_id or "campaign"),
        campaign_premise=plot,
        central_question=(candidate_threads[0] if candidate_threads else (open_hooks[0] if open_hooks else "")),
        major_threat=str(payload.campaign_variables.get("major_threat") or ""),
        major_factions=faction_names,
        open_threads=open_hooks or candidate_threads,
        backstory_hooks_available=[
            str(h)
            for h in (payload.campaign_variables.get("backstory_hooks") or [])
            if h
        ],
    )
    session_storyboard = generate_session_storyboard(
        session_id=payload.session_id or "session",
        campaign=campaign_storyboard,
        campaign_contract=payload.campaign_variables,
    )

    return StoryboardPlotResponse(
        plot=plot,
        hooks=hooks,
        npcs_mentioned=npcs_mentioned,
        candidate_story_threads=candidate_threads,
        candidate_npcs=npcs_mentioned,
        candidate_locations=candidate_locations,
        candidate_factions=faction_names,
        recent_events=recent_events,
        open_hooks=open_hooks,
        recommended_scene_purpose=recommended_purpose,
        campaign_storyboard=_model_to_dict(campaign_storyboard),
        session_storyboard=_model_to_dict(session_storyboard),
    )
