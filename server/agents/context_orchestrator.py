"""Context Orchestrator — assembles minimum-necessary context for each AI agent.

Replaces ad-hoc context injection with structured, relevance-scored context packets.
Each packet contains only what the target agent needs, enforcing token budgets and
preventing information leakage (NPC secrets to narrative, future plans to players, etc.)

Design principle: the AI should not remember everything — it should remember the RIGHT
things at the RIGHT moment.

Usage
-----
    from .context_orchestrator import orchestrate, ContextPacket

    packet = orchestrate(
        campaign_id="abc123",
        session_id="sess-xyz",
        scene_context={"location_name": "Greyford Market", "mood": "unease", ...},
        player_actions=["I ask the captain about the missing wagons"],
        player_name="Yungmin",
    )
    narrative_prompt_block = packet.for_narrative()
    analysis_prompt_block  = packet.for_analysis()
    visual_prompt_block    = packet.for_visual()
    debug_payload          = packet.debug_payload()
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import db
from ..db import CampaignChangeLog, CampaignEntity, CampaignHook, CampaignRelationship

_SESSION_BASE = Path(__file__).resolve().parents[1] / "sessions"
_CACHE_TTL_SECONDS = 90

# ---------------------------------------------------------------------------
# Context Section Models
# ---------------------------------------------------------------------------

class SceneContext(BaseModel):
    scene_id: str = ""
    scene_type: str = ""
    location_name: str = ""
    time_of_day: str = ""
    weather: str = ""
    mood: str = ""
    threat_level: str = ""
    current_problem: str = ""
    immediate_stakes: str = ""
    open_prompt: str = ""
    scene_summary: str = ""


class PlayerContext(BaseModel):
    name: str = ""
    level: int = 1
    class_name: str = ""
    current_condition: str = "healthy"
    active_goals: list[str] = Field(default_factory=list)
    relationships: list[dict] = Field(default_factory=list)
    known_clues: list[str] = Field(default_factory=list)
    active_resources: list[str] = Field(default_factory=list)
    relevant_backstory_hooks: list[str] = Field(default_factory=list)
    current_reputation: dict = Field(default_factory=dict)


class RecentHistoryContext(BaseModel):
    recent_actions: list[str] = Field(default_factory=list)
    last_gm_response: str = ""
    unresolved_intents: list[str] = Field(default_factory=list)
    pending_rolls: list[str] = Field(default_factory=list)
    pending_consequences: list[str] = Field(default_factory=list)


class NPCContext(BaseModel):
    name: str = ""
    role: str = ""
    current_emotional_state: str = ""
    goal: str = ""
    fear: str = ""
    known_information: list[str] = Field(default_factory=list)
    relationship_to_player: str = ""
    likely_next_action: str = ""
    secrets_count: int = 0        # count only — content never leaves here
    faction: str = ""
    relevance_score: int = 0


class LocationContext(BaseModel):
    name: str = ""
    description: str = ""
    atmosphere: str = ""
    sensory_identity: list[str] = Field(default_factory=list)
    current_tensions: list[str] = Field(default_factory=list)
    available_interactables: list[str] = Field(default_factory=list)
    visible_clues: list[str] = Field(default_factory=list)
    hidden_elements_count: int = 0  # count only
    threat_level: str = ""
    opportunities: list[str] = Field(default_factory=list)


class StoryThreadContext(BaseModel):
    title: str = ""
    current_state: str = ""
    stakes: str = ""
    next_escalation: str = ""
    ticking_clock: str = ""
    related_entities: list[str] = Field(default_factory=list)
    relevance_score: int = 0


class FactionContext(BaseModel):
    name: str = ""
    goal: str = ""
    current_plan: str = ""
    next_action_if_ignored: str = ""
    pressure_level: str = ""
    relevance_score: int = 0


class ClueContext(BaseModel):
    discovered_clues: list[str] = Field(default_factory=list)
    available_clues: list[str] = Field(default_factory=list)
    secret_constraints: list[str] = Field(default_factory=list)  # "Don't reveal X" never X itself


class RulesContext(BaseModel):
    likely_skill_checks: list[str] = Field(default_factory=list)
    difficulty_guidance: dict = Field(default_factory=dict)
    success_consequences: dict = Field(default_factory=dict)
    failure_consequences: dict = Field(default_factory=dict)
    fail_forward_options: dict = Field(default_factory=dict)


class ConstraintsContext(BaseModel):
    npc_knowledge_limits: list[str] = Field(default_factory=list)
    forbidden_reveals: list[str] = Field(default_factory=list)
    pending_roll_requirements: list[str] = Field(default_factory=list)
    active_mysteries: list[str] = Field(default_factory=list)
    continuity_warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Full Context Packet
# ---------------------------------------------------------------------------

class ContextPacket(BaseModel):
    scene: SceneContext = Field(default_factory=SceneContext)
    player_character: PlayerContext = Field(default_factory=PlayerContext)
    recent_history: RecentHistoryContext = Field(default_factory=RecentHistoryContext)
    active_npcs: list[NPCContext] = Field(default_factory=list)
    location: LocationContext = Field(default_factory=LocationContext)
    story_threads: list[StoryThreadContext] = Field(default_factory=list)
    factions: list[FactionContext] = Field(default_factory=list)
    clues: ClueContext = Field(default_factory=ClueContext)
    rules: RulesContext = Field(default_factory=RulesContext)
    constraints: ConstraintsContext = Field(default_factory=ConstraintsContext)

    # Orchestration metadata
    entity_scores: dict[str, int] = Field(default_factory=dict)
    generated_at: str = ""
    token_estimate: int = 0
    campaign_id: str = ""
    session_id: str = ""

    # ---------------------------------------------------------------------------
    # Agent-specific formatted outputs
    # ---------------------------------------------------------------------------

    def for_narrative(self) -> str:
        """Compact prompt block for the Narrative Agent (target: 2000–3500 chars)."""
        lines: list[str] = ["[CONTEXT]"]

        # Scene
        sc = self.scene
        if sc.location_name:
            loc_line = f"SCENE: {sc.location_name}"
            if sc.mood:
                loc_line += f" | mood={sc.mood}"
            if sc.threat_level and sc.threat_level not in ("safe", "low"):
                loc_line += f" | threat={sc.threat_level}"
            if sc.time_of_day:
                loc_line += f" | {sc.time_of_day}"
            lines.append(loc_line)
        if sc.current_problem:
            lines.append(f"PROBLEM: {sc.current_problem[:120]}")
        if sc.immediate_stakes:
            lines.append(f"STAKES: {sc.immediate_stakes[:100]}")

        # Player
        pc = self.player_character
        if pc.name:
            pc_line = f"PLAYER: {pc.name}"
            if pc.class_name:
                pc_line += f" ({pc.class_name})"
            if pc.current_condition and pc.current_condition != "healthy":
                pc_line += f" — {pc.current_condition}"
            lines.append(pc_line)
        if pc.active_goals:
            lines.append(f"PC GOALS: {' | '.join(pc.active_goals[:2])}")
        if pc.known_clues:
            lines.append(f"PC KNOWS: {' | '.join(pc.known_clues[:3])}")

        # Recent history
        rh = self.recent_history
        if rh.recent_actions:
            lines.append(f"RECENT ACTIONS: {' → '.join(rh.recent_actions[:3])}")
        if rh.unresolved_intents:
            lines.append(f"UNRESOLVED: {' | '.join(rh.unresolved_intents[:2])}")

        # Active NPCs (narrative doesn't get secrets — only goal/state/next_action)
        if self.active_npcs:
            npc_lines = []
            for npc in self.active_npcs[:4]:
                part = npc.name
                if npc.current_emotional_state:
                    part += f" [{npc.current_emotional_state}]"
                if npc.goal:
                    part += f" wants {npc.goal[:60]}"
                if npc.likely_next_action:
                    part += f". Next: {npc.likely_next_action[:50]}"
                npc_lines.append(part)
            lines.append("NPCS: " + " | ".join(npc_lines))

        # Location
        loc = self.location
        if loc.name and loc.current_tensions:
            lines.append(f"LOCATION TENSION: {loc.current_tensions[0][:100]}")
        if loc.visible_clues:
            lines.append(f"VISIBLE CLUES: {' | '.join(loc.visible_clues[:2])}")

        # Story threads (sorted by relevance so highest-scored appear first)
        if self.story_threads:
            thread_parts = []
            sorted_threads = sorted(self.story_threads, key=lambda t: t.relevance_score, reverse=True)
            for t in sorted_threads[:2]:
                tp = t.title
                if t.current_state:
                    tp += f": {t.current_state[:70]}"
                if t.ticking_clock:
                    tp += f" [CLOCK: {t.ticking_clock[:40]}]"
                thread_parts.append(tp)
            lines.append("THREADS: " + " | ".join(thread_parts))

        # Factions (goal/pressure only — not current_plan details)
        if self.factions:
            faction_parts = []
            for f in self.factions[:2]:
                fp = f.name
                if f.goal:
                    fp += f" ({f.goal[:50]})"
                if f.pressure_level:
                    fp += f" [{f.pressure_level}]"
                faction_parts.append(fp)
            lines.append("FACTIONS: " + " | ".join(faction_parts))

        # Clues (discovered + available — NOT secret_constraints)
        clues = self.clues
        if clues.discovered_clues:
            lines.append(f"KNOWN CLUES: {' | '.join(clues.discovered_clues[:3])}")
        if clues.available_clues:
            lines.append(f"DISCOVERABLE: {' | '.join(clues.available_clues[:2])}")

        # Constraints
        c = self.constraints
        if c.npc_knowledge_limits:
            lines.append(f"NPC LIMITS: {' | '.join(c.npc_knowledge_limits[:2])}")
        if c.forbidden_reveals:
            lines.append(f"DO NOT REVEAL: {' | '.join(c.forbidden_reveals[:2])}")
        if c.active_mysteries:
            lines.append(f"ACTIVE MYSTERIES: {' | '.join(c.active_mysteries[:2])}")
        if c.continuity_warnings:
            lines.append(f"CONTINUITY: {' | '.join(c.continuity_warnings[:2])}")

        return "\n".join(lines)

    def for_analysis(self) -> str:
        """Compact prompt block for the Analysis/Scene Agent (target: 500–800 chars)."""
        lines: list[str] = ["[SCENE ANALYSIS CONTEXT]"]
        sc = self.scene
        if sc.location_name:
            lines.append(f"Location: {sc.location_name} | threat={sc.threat_level}")
        if sc.current_problem:
            lines.append(f"Problem: {sc.current_problem[:100]}")
        rh = self.recent_history
        if rh.recent_actions:
            lines.append(f"Recent: {'; '.join(rh.recent_actions[:3])}")
        r = self.rules
        if r.likely_skill_checks:
            lines.append(f"Expected rolls: {', '.join(r.likely_skill_checks[:4])}")
        if r.difficulty_guidance:
            dc_parts = [f"{k}={v}" for k, v in list(r.difficulty_guidance.items())[:4]]
            lines.append(f"DC guidance: {', '.join(dc_parts)}")
        if r.fail_forward_options:
            lines.append("Fail-forward available")
        return "\n".join(lines)

    def for_visual(self) -> str:
        """Compact prompt block for the Visual Director (target: 300–600 chars)."""
        lines: list[str] = []
        sc = self.scene
        loc = self.location
        location_name = sc.location_name or loc.name
        if location_name:
            lines.append(f"Location: {location_name}")
        if loc.atmosphere:
            lines.append(f"Atmosphere: {loc.atmosphere[:80]}")
        if loc.current_tensions:
            lines.append(f"Tension: {loc.current_tensions[0][:60]}")
        if sc.mood:
            lines.append(f"Mood: {sc.mood}")
        if sc.threat_level:
            lines.append(f"Threat: {sc.threat_level}")
        if sc.weather:
            lines.append(f"Weather: {sc.weather}")
        if sc.time_of_day:
            lines.append(f"Time: {sc.time_of_day}")
        if loc.sensory_identity:
            lines.append(f"Sensory: {', '.join(loc.sensory_identity[:3])}")
        return "\n".join(lines)

    def for_scene_director(self) -> str:
        """Compact block for the Scene Director (includes thread + NPC + faction pressure)."""
        lines: list[str] = ["[SCENE DIRECTOR CONTEXT]"]
        if self.story_threads:
            for t in self.story_threads[:3]:
                tl = f"THREAD [{t.relevance_score}]: {t.title}"
                if t.current_state:
                    tl += f" — {t.current_state[:80]}"
                if t.next_escalation:
                    tl += f". Escalation: {t.next_escalation[:60]}"
                lines.append(tl)
        if self.active_npcs:
            for npc in self.active_npcs[:3]:
                nl = f"NPC [{npc.relevance_score}]: {npc.name} — {npc.goal[:60]}"
                if npc.likely_next_action:
                    nl += f". Next: {npc.likely_next_action[:50]}"
                lines.append(nl)
        if self.factions:
            for f in self.factions[:2]:
                lines.append(f"FACTION [{f.relevance_score}]: {f.name} — {f.current_plan[:70]}")
        return "\n".join(lines)

    def debug_payload(self) -> dict:
        """Full debug payload for frontend context viewer."""
        return {
            "entity_scores": self.entity_scores,
            "token_estimate": self.token_estimate,
            "generated_at": self.generated_at,
            "sections": {
                "scene": self.scene.model_dump(),
                "player_character": self.player_character.model_dump(),
                "recent_history": self.recent_history.model_dump(),
                "active_npcs": [n.model_dump() for n in self.active_npcs],
                "location": self.location.model_dump(),
                "story_threads": [t.model_dump() for t in self.story_threads],
                "factions": [f.model_dump() for f in self.factions],
                "clues": self.clues.model_dump(),
                "rules": self.rules.model_dump(),
                "constraints": self.constraints.model_dump(),
            },
        }


# ---------------------------------------------------------------------------
# Relevance Scoring
# ---------------------------------------------------------------------------

def _score_npc(
    entity: CampaignEntity,
    mentioned_names: set[str],
    player_actions: list[str],
    current_location: str,
    active_thread_ids: set[str],
    recent_entity_ids: set[str],
) -> int:
    """Score NPC relevance 0–300. Higher = more important right now."""
    score = 0
    name = entity.name
    first = name.split()[0] if name else ""

    # +100 currently present (name in scene text / mentioned in narration)
    if name in mentioned_names or first in mentioned_names:
        score += 100

    # +50 directly addressed or mentioned in last player action
    last_action = player_actions[0] if player_actions else ""
    if name.lower() in last_action.lower() or (first and first.lower() in last_action.lower()):
        score += 50

    # +40 mentioned by player (any recent action)
    for action in player_actions[:5]:
        if name.lower() in action.lower():
            score += 40
            break

    d = entity.data or {}
    engine = d.get("story_engine") or {}

    # +30 tied to current active thread
    if entity.id in active_thread_ids:
        score += 30

    # +20 tied to current location
    loc_match = current_location.lower() if current_location else ""
    if loc_match and loc_match in name.lower():
        score += 20

    # +15 has active goal or next_action (they'll naturally drive scenes)
    if d.get("primary_goal") or engine.get("goal"):
        score += 15
    if d.get("next_likely_action") or engine.get("next_action"):
        score += 10

    # +10 recent change
    if entity.id in recent_entity_ids:
        score += 10

    # +5 has a deadline (urgent)
    if engine.get("deadline"):
        score += 5

    return score


def _score_thread(
    entity: CampaignEntity,
    mentioned_names: set[str],
    player_actions: list[str],
    current_npc_ids: set[str],
    current_location: str,
) -> int:
    """Score story thread relevance 0–200."""
    score = 0
    d = entity.data or {}
    name_parts = set(entity.name.lower().split())
    all_action_text = " ".join(player_actions).lower()

    # +100 directly referenced in scene or player actions
    if any(p in mentioned_names for p in entity.name.split() if len(p) > 3):
        score += 100
    if any(p in all_action_text for p in name_parts if len(p) > 3):
        score += 50

    # +40 tied to NPC currently scored high
    # (approximated: thread title mentions a scored NPC name)
    if any(n in entity.name for n in mentioned_names):
        score += 40

    # +30 tied to location
    loc_lower = current_location.lower() if current_location else ""
    if loc_lower and loc_lower in entity.name.lower():
        score += 30

    # +20 ticking clock
    if d.get("ticking_clock"):
        score += 20

    # Priority multiplier (1–10 scale)
    priority = int(d.get("current_priority") or 5)
    score += priority * 2

    # +10 has a next DM move (actionable)
    if d.get("next_recommended_dm_move"):
        score += 10

    return score


def _score_faction(
    entity: CampaignEntity,
    mentioned_names: set[str],
    player_actions: list[str],
    npc_faction_ids: set[str],
    recent_entity_ids: set[str],
) -> int:
    """Score faction relevance 0–150."""
    score = 0
    name_lower = entity.name.lower()
    all_action_text = " ".join(player_actions).lower()

    if entity.name in mentioned_names:
        score += 50
    if name_lower in all_action_text:
        score += 40

    # +30 has NPCs present in scene
    if entity.id in npc_faction_ids:
        score += 30

    # +20 recent change
    if entity.id in recent_entity_ids:
        score += 20

    d = entity.data or {}
    if d.get("active_plan") or d.get("next_action"):
        score += 10

    return score


# ---------------------------------------------------------------------------
# Clue and Constraint Assembly
# ---------------------------------------------------------------------------

def _extract_clues_and_constraints(
    locations: list[CampaignEntity],
    story_threads: list[CampaignEntity],
    npcs: list[CampaignEntity],
    player_known_clues: list[str],
) -> tuple[ClueContext, ConstraintsContext]:
    """Separate discoverable clues from secrets and build constraints."""
    discovered = list(player_known_clues)
    available: list[str] = []
    secret_constraints: list[str] = []
    npc_limits: list[str] = []
    forbidden: list[str] = []
    mysteries: list[str] = []

    for loc in locations[:3]:
        d = loc.data or {}
        # Visible clues in location
        opps = d.get("opportunities") or []
        for opp in opps[:2]:
            if opp and opp not in available:
                available.append(str(opp)[:80])
        # Hidden elements become constraints
        hidden = d.get("hidden_elements") or []
        for h in hidden[:2]:
            if h:
                secret_constraints.append(f"[{loc.name}] Do not reveal: {str(h)[:60]}")

    for thread in story_threads[:3]:
        d = thread.data or {}
        engine = thread.data.get("story_engine") or {} if thread.data else {}
        # Thread clues from stakes / situation
        sit = d.get("current_situation") or ""
        if sit and len(sit) > 10:
            available.append(f"({thread.name}) {sit[:70]}")
        # Forbidden reveals
        gm_notes = d.get("gm_notes") or d.get("hidden_notes") or ""
        if gm_notes:
            forbidden.append(f"[{thread.name}] {str(gm_notes)[:60]}")

    for npc in npcs[:5]:
        d = npc.data or {}
        secrets = d.get("secrets") or []
        known = d.get("known_information") or []
        # NPC knowledge limit: they only know what's in known_information
        if known:
            npc_limits.append(f"{npc.name} knows: {'; '.join(str(k) for k in known[:2])}")
        # Secrets become constraints — never shared with narrative agent
        for secret in secrets[:2]:
            if secret:
                mysteries.append(f"{npc.name} secret not yet revealed")
                forbidden.append(f"[{npc.name}] Do not reveal their secret")

    return (
        ClueContext(
            discovered_clues=discovered[:5],
            available_clues=available[:4],
            secret_constraints=secret_constraints[:3],
        ),
        ConstraintsContext(
            npc_knowledge_limits=npc_limits[:3],
            forbidden_reveals=forbidden[:3],
            active_mysteries=mysteries[:3],
            continuity_warnings=[],
            pending_roll_requirements=[],
        ),
    )


# ---------------------------------------------------------------------------
# Rules Context Assembly
# ---------------------------------------------------------------------------

_SKILL_TRIGGERS = {
    "persuade": "Persuasion (Charisma)",
    "intimidate": "Intimidation (Charisma)",
    "deceive": "Deception (Charisma)",
    "lie": "Deception (Charisma)",
    "sneak": "Stealth (Dexterity)",
    "hide": "Stealth (Dexterity)",
    "climb": "Athletics (Strength)",
    "jump": "Athletics (Strength)",
    "search": "Investigation (Intelligence)",
    "investigate": "Investigation (Intelligence)",
    "recall": "History / Arcana (Intelligence)",
    "attack": "Attack Roll",
    "shoot": "Attack Roll (ranged)",
    "cast": "Spell Attack / Saving Throw",
    "pick": "Thieves' Tools (Dexterity)",
    "lock": "Thieves' Tools (Dexterity)",
    "sense": "Perception (Wisdom)",
    "notice": "Perception (Wisdom)",
    "heal": "Medicine (Wisdom)",
    "track": "Survival (Wisdom)",
    "insight": "Insight (Wisdom)",
    "read": "Insight / History (Wisdom/Intelligence)",
}


def _build_rules_context(player_actions: list[str], threat_level: str) -> RulesContext:
    """Derive likely skill checks from player action text."""
    combined = " ".join(player_actions).lower()
    checks: list[str] = []
    for trigger, check_name in _SKILL_TRIGGERS.items():
        if trigger in combined and check_name not in checks:
            checks.append(check_name)

    base_dc = {"safe": 10, "low": 12, "moderate": 15, "high": 18, "critical": 20}.get(threat_level, 14)

    return RulesContext(
        likely_skill_checks=checks[:5],
        difficulty_guidance={"base_dc": base_dc, "threat_level": threat_level},
        fail_forward_options={"default": "partial success reveals clue at cost"},
    )


# ---------------------------------------------------------------------------
# Token Budget
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: word count × 1.35."""
    return int(len(text.split()) * 1.35)


def _trim_to_budget(packet: ContextPacket, budget: int) -> None:
    """Trim active_npcs and story_threads until packet's for_narrative() is under budget."""
    for _ in range(10):
        text = packet.for_narrative()
        est = _estimate_tokens(text)
        packet.token_estimate = est
        if est <= budget:
            break
        if packet.active_npcs:
            packet.active_npcs.pop()
        elif packet.story_threads:
            packet.story_threads.pop()
        else:
            break


# ---------------------------------------------------------------------------
# Session data helpers
# ---------------------------------------------------------------------------

def _load_story_text(session_id: str, last_n: int = 6) -> list[str]:
    path = _SESSION_BASE / session_id / "story.json"
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text())
        lines = [
            e.get("text", "") for e in entries
            if isinstance(e, dict) and e.get("type") in ("narration", "scene") and e.get("text")
        ]
        return lines[-last_n:]
    except Exception:
        return []


def _load_scene_json(session_id: str) -> dict:
    path = _SESSION_BASE / session_id / "scene.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _load_pcs(session_id: str) -> list[dict]:
    path = _SESSION_BASE / session_id / "pcs.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text()) or []
    except Exception:
        return []


def _names_from_text(text: str) -> set[str]:
    """Heuristically extract capitalized proper names."""
    tokens = re.findall(r"\b([A-Z][a-z]{2,})\b", text)
    stop = {
        "The", "And", "But", "For", "With", "From", "That", "This", "They",
        "Their", "You", "Your", "Has", "Have", "Had", "Was", "Were", "Are",
        "Him", "Her", "His", "Into", "Upon", "Toward", "Before", "After",
    }
    return {t for t in tokens if t not in stop}


def _extract_unresolved_intents(player_actions: list[str]) -> list[str]:
    """Heuristically detect unresolved player intentions from recent actions."""
    intents = []
    intent_triggers = ["want to", "try to", "attempt to", "looking for", "need to",
                       "going to", "plan to", "would like", "i'll", "i will", "?"]
    for action in player_actions[:5]:
        action_lower = action.lower()
        if any(t in action_lower for t in intent_triggers):
            intents.append(action[:100])
    return intents[:3]


# ---------------------------------------------------------------------------
# Context Cache
# ---------------------------------------------------------------------------

def _cache_key(campaign_id: str, session_id: str, player_actions: list[str]) -> str:
    raw = f"{campaign_id}:{session_id}:{':'.join(player_actions[:3])}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _load_cache(session_id: str, key: str) -> ContextPacket | None:
    path = _SESSION_BASE / session_id / "context_cache.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
        if raw.get("key") != key:
            return None
        ts = raw.get("generated_at", "")
        if ts:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
            if age > _CACHE_TTL_SECONDS:
                return None
        return ContextPacket(**raw["packet"])
    except Exception:
        return None


def _save_cache(session_id: str, key: str, packet: ContextPacket) -> None:
    path = _SESSION_BASE / session_id / "context_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps({
            "key": key,
            "generated_at": packet.generated_at,
            "packet": packet.model_dump(),
        }))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main Orchestration Entry Point
# ---------------------------------------------------------------------------

def orchestrate(
    campaign_id: str,
    session_id: str | None = None,
    player_name: str = "",
    player_actions: list[str] | None = None,
    scene_override: dict | None = None,
    narrative_budget: int = 3000,
    use_cache: bool = True,
) -> ContextPacket:
    """Assemble a relevance-ranked ContextPacket for the current moment.

    Args:
        campaign_id:      Campaign UUID string
        session_id:       Session folder name (optional but recommended)
        player_name:      Active player character name
        player_actions:   List of recent player messages (newest first)
        scene_override:   Optional dict with scene fields to override loaded values
        narrative_budget: Token budget for narrative agent context
        use_cache:        Whether to check/update the context cache

    Returns:
        ContextPacket with all 10 sections populated and relevance scores set.
    """
    player_actions = player_actions or []
    now_str = datetime.now(timezone.utc).isoformat()

    # Check cache
    if use_cache and session_id:
        cache_key = _cache_key(campaign_id, session_id, player_actions)
        cached = _load_cache(session_id, cache_key)
        if cached:
            return cached

    # ---------------------------------------------------------------------------
    # 1. Load session data
    # ---------------------------------------------------------------------------
    story_lines = _load_story_text(session_id, last_n=6) if session_id else []
    scene_json = _load_scene_json(session_id) if session_id else {}
    if scene_override:
        scene_json.update(scene_override)
    pcs = _load_pcs(session_id) if session_id else []

    # Corpus for name extraction: player actions + story + scene text
    corpus_texts = list(player_actions) + story_lines
    if scene_json.get("text"):
        corpus_texts.append(scene_json["text"])
    full_corpus = " ".join(corpus_texts)
    mentioned_names = _names_from_text(full_corpus)

    # Visual state for mood/threat
    visual_state: dict = {}
    if session_id:
        try:
            from .visual_state import load_visual_state
            vs = load_visual_state(session_id)
            if vs:
                visual_state = vs.model_dump()
        except Exception:
            pass

    # ---------------------------------------------------------------------------
    # 2. Load campaign entities from DB
    # ---------------------------------------------------------------------------
    with db.Session(db.engine) as s:
        all_entities = s.exec(
            select(CampaignEntity)
            .where(
                CampaignEntity.campaign_id == campaign_id,
                CampaignEntity.status == "active",
            )
            .order_by(CampaignEntity.updated_at.desc())
        ).all()

        hooks = s.exec(
            select(CampaignHook)
            .where(
                CampaignHook.campaign_id == campaign_id,
                CampaignHook.status == "active",
            )
            .order_by(CampaignHook.priority.desc())
            .limit(8)
        ).all()

        recent_changes = s.exec(
            select(CampaignChangeLog)
            .where(CampaignChangeLog.campaign_id == campaign_id)
            .order_by(CampaignChangeLog.created_at.desc())
            .limit(8)
        ).all()

        # Relationships for player character (if we can identify them by name)
        player_relationships: list[dict] = []
        pc_entity = None
        if player_name:
            pc_entity = next((e for e in all_entities if e.name.lower() == player_name.lower()), None)

    # Partition by type
    npcs = [e for e in all_entities if e.entity_type == "npc"]
    locations = [e for e in all_entities if e.entity_type == "location"]
    factions = [e for e in all_entities if e.entity_type == "faction"]
    threads = [e for e in all_entities if e.entity_type == "story_thread"]

    recent_entity_ids = {c.entity_id for c in recent_changes}
    active_thread_ids = {e.id for e in threads}

    # Faction membership: which factions own scored NPCs?
    npc_faction_ids: set[str] = set()
    for npc in npcs:
        d = npc.data or {}
        affiliations = d.get("faction_affiliations") or []
        for aff in affiliations:
            # match faction name to entity
            for f in factions:
                if f.name.lower() == str(aff).lower():
                    npc_faction_ids.add(f.id)

    # ---------------------------------------------------------------------------
    # 3. Relevance scoring
    # ---------------------------------------------------------------------------
    current_location = (
        visual_state.get("location_name")
        or scene_json.get("location_name")
        or (scene_override or {}).get("location_name")
        or ""
    )

    npc_scores = {
        e.id: _score_npc(e, mentioned_names, player_actions, current_location, active_thread_ids, recent_entity_ids)
        for e in npcs
    }
    thread_scores = {
        e.id: _score_thread(e, mentioned_names, player_actions, set(npc_scores.keys()), current_location)
        for e in threads
    }
    faction_scores = {
        e.id: _score_faction(e, mentioned_names, player_actions, npc_faction_ids, recent_entity_ids)
        for e in factions
    }

    # Build combined entity_scores for debug
    entity_scores: dict[str, int] = {}
    for e in npcs:
        entity_scores[f"{e.name} (npc)"] = npc_scores[e.id]
    for e in threads:
        entity_scores[f"{e.name} (thread)"] = thread_scores[e.id]
    for e in factions:
        entity_scores[f"{e.name} (faction)"] = faction_scores[e.id]
    for e in locations:
        entity_scores[f"{e.name} (location)"] = 50 if e.name.lower() == current_location.lower() else 20

    # Sort and select top entities
    ranked_npcs = sorted(npcs, key=lambda e: npc_scores[e.id], reverse=True)[:5]
    ranked_threads = sorted(threads, key=lambda e: thread_scores[e.id], reverse=True)[:3]
    ranked_factions = sorted(factions, key=lambda e: faction_scores[e.id], reverse=True)[:2]

    # Current location entity
    current_loc_entity = next(
        (loc for loc in locations if loc.name.lower() == current_location.lower()),
        locations[0] if locations else None,
    )

    # ---------------------------------------------------------------------------
    # 4. Build Scene Context
    # ---------------------------------------------------------------------------
    scene_text = scene_json.get("text") or (story_lines[-1] if story_lines else "")
    scene_ctx = SceneContext(
        scene_id=scene_json.get("id") or "",
        scene_type=scene_json.get("scene_type") or "scene",
        location_name=current_location,
        time_of_day=visual_state.get("time_of_day") or scene_json.get("time_of_day") or "day",
        weather=visual_state.get("weather") or "clear",
        mood=visual_state.get("mood") or "unease",
        threat_level=visual_state.get("threat_level") or "low",
        current_problem=scene_json.get("problem") or (ranked_threads[0].data or {}).get("current_situation") or "" if ranked_threads else "",
        immediate_stakes=scene_json.get("stakes") or (ranked_threads[0].data or {}).get("stakes") or "" if ranked_threads else "",
        open_prompt=scene_json.get("prompt") or "",
        scene_summary=scene_text[:300] if scene_text else "",
    )

    # ---------------------------------------------------------------------------
    # 5. Build Player Context
    # ---------------------------------------------------------------------------
    pc_data: dict = {}
    if pcs:
        pc_data = pcs[0]
    sheet = pc_data.get("sheet") or {}
    pc_ctx = PlayerContext(
        name=player_name or pc_data.get("name") or pc_data.get("character_name") or "the party",
        level=int(pc_data.get("level") or sheet.get("level") or 1),
        class_name=pc_data.get("class_name") or sheet.get("class") or "",
        current_condition=sheet.get("condition") or "healthy",
        active_goals=sheet.get("active_goals") or [],
        known_clues=sheet.get("known_clues") or [],
        active_resources=[],
        relevant_backstory_hooks=sheet.get("backstory_hooks") or [],
        current_reputation=sheet.get("reputation") or {},
        relationships=player_relationships,
    )

    # ---------------------------------------------------------------------------
    # 6. Build Recent History Context
    # ---------------------------------------------------------------------------
    unresolved = _extract_unresolved_intents(player_actions)
    history_ctx = RecentHistoryContext(
        recent_actions=player_actions[:5],
        last_gm_response=story_lines[-1][:300] if story_lines else "",
        unresolved_intents=unresolved,
        pending_rolls=[],
        pending_consequences=[],
    )

    # ---------------------------------------------------------------------------
    # 7. Build NPC Contexts
    # ---------------------------------------------------------------------------
    npc_ctxs = []
    for e in ranked_npcs:
        d = e.data or {}
        engine = d.get("story_engine") or {}
        known_info = d.get("known_information") or []
        npc_ctxs.append(NPCContext(
            name=e.name,
            role=d.get("role") or d.get("archetype") or "",
            current_emotional_state=d.get("emotional_state") or "",
            goal=d.get("primary_goal") or engine.get("goal") or "",
            fear=d.get("greatest_fear") or "",
            known_information=[str(k)[:80] for k in known_info[:3]],
            relationship_to_player="",
            likely_next_action=d.get("next_likely_action") or engine.get("next_action") or "",
            secrets_count=len(d.get("secrets") or []),
            faction=(d.get("faction_affiliations") or [""])[0] if d.get("faction_affiliations") else "",
            relevance_score=npc_scores[e.id],
        ))

    # ---------------------------------------------------------------------------
    # 8. Build Location Context
    # ---------------------------------------------------------------------------
    if current_loc_entity:
        d = current_loc_entity.data or {}
        sensory_raw = d.get("visual_description") or d.get("sensory_details") or ""
        sensory_parts = [s.strip() for s in sensory_raw.split(".") if len(s.strip()) > 5][:3]
        loc_ctx = LocationContext(
            name=current_loc_entity.name,
            description=str(d.get("visual_description") or "")[:200],
            atmosphere=str(d.get("atmosphere") or "")[:100],
            sensory_identity=sensory_parts,
            current_tensions=[str(t) for t in (d.get("current_tensions") or [])[:3]],
            available_interactables=[str(o) for o in (d.get("opportunities") or [])[:3]],
            visible_clues=[],
            hidden_elements_count=len(d.get("hidden_elements") or []),
            threat_level=str((d.get("threats") or [""])[0])[:60] if d.get("threats") else "",
            opportunities=[str(o) for o in (d.get("opportunities") or [])[:2]],
        )
    else:
        loc_ctx = LocationContext(
            name=current_location,
            threat_level=scene_ctx.threat_level,
        )

    # ---------------------------------------------------------------------------
    # 9. Build Thread Contexts
    # ---------------------------------------------------------------------------
    thread_ctxs = []
    for e in ranked_threads:
        d = e.data or {}
        rel_ents = []
        # Related entities: NPCs mentioned in thread title
        for npc in ranked_npcs[:5]:
            if npc.name in e.name or any(part in e.name for part in npc.name.split()):
                rel_ents.append(npc.name)
        thread_ctxs.append(StoryThreadContext(
            title=e.name,
            current_state=str(d.get("current_situation") or "")[:120],
            stakes=str(d.get("stakes") or "")[:100],
            next_escalation=str(d.get("next_recommended_dm_move") or "")[:100],
            ticking_clock=str(d.get("ticking_clock") or "")[:60],
            related_entities=rel_ents[:3],
            relevance_score=thread_scores[e.id],
        ))

    # Also include high-priority ticking clocks from hooks
    ticking = [h for h in hooks if h.hook_type == "ticking_clock"][:2]
    for h in ticking:
        if not any(t.title == h.title for t in thread_ctxs):
            thread_ctxs.append(StoryThreadContext(
                title=h.title,
                current_state=h.description[:100],
                stakes="",
                next_escalation="",
                ticking_clock=h.deadline or "",
                relevance_score=h.priority * 10,
            ))

    # ---------------------------------------------------------------------------
    # 10. Build Faction Contexts
    # ---------------------------------------------------------------------------
    faction_ctxs = []
    for e in ranked_factions:
        d = e.data or {}
        faction_ctxs.append(FactionContext(
            name=e.name,
            goal=str(d.get("current_goal") or (d.get("story_engine") or {}).get("goal") or "")[:80],
            current_plan=str(d.get("active_plan") or "")[:100],
            next_action_if_ignored=str(d.get("likely_escalation") or (d.get("story_engine") or {}).get("escalation_if_ignored") or "")[:80],
            pressure_level=str(d.get("current_pressure") or "")[:40],
            relevance_score=faction_scores[e.id],
        ))

    # ---------------------------------------------------------------------------
    # 11. Clues and Constraints
    # ---------------------------------------------------------------------------
    clue_ctx, constraint_ctx = _extract_clues_and_constraints(
        locations=locations,
        story_threads=threads,
        npcs=ranked_npcs,
        player_known_clues=pc_ctx.known_clues,
    )

    # Add open hooks as available clues
    open_hooks = [h for h in hooks if h.hook_type != "ticking_clock"][:3]
    for h in open_hooks:
        hint = h.title
        if hint and hint not in clue_ctx.available_clues:
            clue_ctx.available_clues.append(hint[:80])

    # ---------------------------------------------------------------------------
    # 12. Rules Context
    # ---------------------------------------------------------------------------
    rules_ctx = _build_rules_context(player_actions, scene_ctx.threat_level)

    # ---------------------------------------------------------------------------
    # 13. Assemble packet and enforce budget
    # ---------------------------------------------------------------------------
    packet = ContextPacket(
        scene=scene_ctx,
        player_character=pc_ctx,
        recent_history=history_ctx,
        active_npcs=npc_ctxs,
        location=loc_ctx,
        story_threads=thread_ctxs,
        factions=faction_ctxs,
        clues=clue_ctx,
        rules=rules_ctx,
        constraints=constraint_ctx,
        entity_scores=entity_scores,
        generated_at=now_str,
        token_estimate=0,
        campaign_id=campaign_id,
        session_id=session_id or "",
    )

    _trim_to_budget(packet, narrative_budget)

    # Cache it
    if use_cache and session_id:
        _save_cache(session_id, cache_key, packet)

    return packet


# ---------------------------------------------------------------------------
# Backward-compatible shim — keep context_collector calls working elsewhere
# ---------------------------------------------------------------------------

def orchestrate_as_prompt_block(
    campaign_id: str,
    session_id: str | None = None,
    recent_chat: list[str] | None = None,
    player_name: str = "",
) -> str:
    """Drop-in replacement for context_collector.collect_context()['prompt_block'].

    Returns the narrative-formatted prompt block string.
    """
    try:
        packet = orchestrate(
            campaign_id=campaign_id,
            session_id=session_id,
            player_name=player_name,
            player_actions=recent_chat or [],
        )
        return packet.for_narrative()
    except Exception:
        # Fall back to old collector if anything goes wrong
        from .context_collector import collect_context
        ctx = collect_context(campaign_id, session_id=session_id, recent_chat=recent_chat)
        return ctx.get("prompt_block") or ""
