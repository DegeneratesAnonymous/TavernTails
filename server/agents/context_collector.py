"""Context Collector — assembles ranked campaign memory for agent prompts.

Called before any major LLM generation step. Reads recent chat, active story
threads, NPC goals, faction pressures, and ticking clocks, then returns a
concise structured summary that agents can inject into their system prompts.

Usage
-----
    from .context_collector import collect_context, format_for_prompt

    ctx = collect_context(campaign_id, session_id=session_id, recent_chat=messages)
    prompt_block = format_for_prompt(ctx)   # ~300–600 chars, safe to inject
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from .. import db
from ..db import CampaignChangeLog, CampaignEntity, CampaignHook, CampaignRelationship

_BASE = Path(__file__).resolve().parents[1] / "sessions"

# Maximum tokens contributed by any single section
_MAX_NPCS = 5
_MAX_THREADS = 4
_MAX_FACTIONS = 3
_MAX_HOOKS = 5
_MAX_CHANGES = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_session_story(session_id: str, last_n: int = 6) -> list[str]:
    """Return the last N narration lines from story.json."""
    path = _BASE / session_id / "story.json"
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text())
        narration = [
            e.get("text", "") for e in entries
            if isinstance(e, dict) and e.get("type") in ("narration", "scene") and e.get("text")
        ]
        return narration[-last_n:]
    except Exception:
        return []


def _load_session_scene(session_id: str) -> str:
    path = _BASE / session_id / "scene.json"
    if not path.exists():
        return ""
    try:
        return json.loads(path.read_text()).get("text", "")
    except Exception:
        return ""


def _names_from_text(text: str) -> set[str]:
    """Heuristically extract capitalized proper names from text."""
    tokens = re.findall(r"\b([A-Z][a-z]{2,})\b", text)
    # Filter common English words that happen to be capitalized
    stop = {"The", "And", "But", "For", "With", "From", "That", "This", "They", "Their",
            "You", "Your", "Has", "Have", "Had", "Was", "Were", "Are", "Him", "Her", "His"}
    return {t for t in tokens if t not in stop}


def _entity_short_summary(e: CampaignEntity) -> dict[str, Any]:
    """Return the fields most useful for agent context."""
    d = e.data or {}
    engine = d.get("story_engine") or {}
    out: dict[str, Any] = {
        "id": e.id,
        "name": e.name,
        "type": e.entity_type,
        "status": e.status,
    }
    if e.entity_type == "npc":
        out["goal"] = d.get("primary_goal") or engine.get("goal") or ""
        out["fear"] = d.get("greatest_fear") or ""
        out["emotional_state"] = d.get("emotional_state") or ""
        out["next_action"] = d.get("next_likely_action") or engine.get("next_action") or ""
        out["escalation"] = engine.get("escalation_if_ignored") or ""
        out["secrets_count"] = len(d.get("secrets") or [])
        out["faction"] = (d.get("faction_affiliations") or [""])[0] if d.get("faction_affiliations") else ""
    elif e.entity_type == "location":
        out["current_tension"] = (d.get("current_tensions") or [""])[0] if d.get("current_tensions") else ""
        out["threat"] = (d.get("threats") or [""])[0] if d.get("threats") else ""
        out["opportunity"] = (d.get("opportunities") or [""])[0] if d.get("opportunities") else ""
    elif e.entity_type == "faction":
        out["goal"] = d.get("current_goal") or engine.get("goal") or ""
        out["active_plan"] = d.get("active_plan") or ""
        out["next_action"] = d.get("next_action") or engine.get("next_action") or ""
        out["escalation"] = d.get("likely_escalation") or engine.get("escalation_if_ignored") or ""
        out["internal_pressure"] = d.get("current_pressure") or ""
    elif e.entity_type == "story_thread":
        out["situation"] = d.get("current_situation") or ""
        out["stakes"] = d.get("stakes") or ""
        out["next_beat"] = d.get("next_recommended_dm_move") or ""
        out["clock"] = d.get("ticking_clock") or ""
        out["priority"] = d.get("current_priority") or 5
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_context(
    campaign_id: str,
    session_id: str | None = None,
    recent_chat: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble ranked campaign memory for the current scene.

    Returns a structured dict with:
    - active_threads:  top story threads by priority
    - relevant_npcs:   NPCs mentioned recently or with active goals
    - faction_pressures: factions with active plans
    - ticking_clocks:  active high-priority hooks
    - recent_changes:  what changed recently
    - recent_story:    last few narration lines
    - open_hooks:      unresolved story hooks
    - current_scene:   current scene text (if session_id given)
    - prompt_block:    pre-formatted string for LLM injection
    """
    recent_chat = recent_chat or []

    # Text corpus to extract mentioned names from
    corpus_texts = list(recent_chat)
    if session_id:
        corpus_texts += _load_session_story(session_id, last_n=4)
        scene_text = _load_session_scene(session_id)
        if scene_text:
            corpus_texts.append(scene_text)
    full_corpus = " ".join(corpus_texts)
    mentioned_names = _names_from_text(full_corpus)

    with Session(db.engine) as s:
        # All active entities for this campaign
        all_entities = s.exec(
            select(CampaignEntity)
            .where(CampaignEntity.campaign_id == campaign_id, CampaignEntity.status == "active")
            .order_by(CampaignEntity.updated_at.desc())
        ).all()

        # Active hooks by priority
        hooks = s.exec(
            select(CampaignHook)
            .where(CampaignHook.campaign_id == campaign_id, CampaignHook.status == "active")
            .order_by(CampaignHook.priority.desc())
            .limit(_MAX_HOOKS + 5)
        ).all()

        # Recent changelog entries
        changes = s.exec(
            select(CampaignChangeLog)
            .where(CampaignChangeLog.campaign_id == campaign_id)
            .order_by(CampaignChangeLog.created_at.desc())
            .limit(_MAX_CHANGES)
        ).all()

    # Partition entities by type
    npcs = [e for e in all_entities if e.entity_type == "npc"]
    locations = [e for e in all_entities if e.entity_type == "location"]
    factions = [e for e in all_entities if e.entity_type == "faction"]
    threads = [e for e in all_entities if e.entity_type == "story_thread"]

    # Score NPCs: boost if mentioned in recent text or have active goal/action
    def _npc_score(e: CampaignEntity) -> float:
        score = 0.0
        if e.name in mentioned_names or any(
            part in mentioned_names
            for part in e.name.split()
        ):
            score += 10.0
        d = e.data or {}
        engine = d.get("story_engine") or {}
        if d.get("primary_goal") or engine.get("goal"):
            score += 2.0
        if d.get("next_likely_action") or engine.get("next_action"):
            score += 3.0
        if engine.get("deadline"):
            score += 2.0
        return score

    # Score story threads: most recently updated + highest priority
    def _thread_score(e: CampaignEntity) -> float:
        d = e.data or {}
        priority = float(d.get("current_priority") or 5)
        has_clock = 1.0 if d.get("ticking_clock") else 0.0
        has_beat = 1.0 if d.get("next_recommended_dm_move") else 0.0
        mentioned = 2.0 if any(p in mentioned_names for p in e.name.split()) else 0.0
        return priority + has_clock * 3 + has_beat + mentioned

    ranked_npcs = sorted(npcs, key=_npc_score, reverse=True)[:_MAX_NPCS]
    ranked_threads = sorted(threads, key=_thread_score, reverse=True)[:_MAX_THREADS]
    ranked_factions = factions[:_MAX_FACTIONS]  # ordered by updated_at already

    ticking_clocks = [h for h in hooks if h.hook_type == "ticking_clock"][:_MAX_HOOKS]
    open_hooks = [h for h in hooks if h.hook_type != "ticking_clock"][:_MAX_HOOKS]

    recent_story = _load_session_story(session_id, last_n=4) if session_id else []
    current_scene = _load_session_scene(session_id) if session_id else ""

    ctx = {
        "campaign_id": campaign_id,
        "session_id": session_id,
        "active_threads": [_entity_short_summary(e) for e in ranked_threads],
        "relevant_npcs": [_entity_short_summary(e) for e in ranked_npcs],
        "faction_pressures": [_entity_short_summary(e) for e in ranked_factions],
        "ticking_clocks": [
            {"id": h.id, "title": h.title, "description": h.description, "priority": h.priority, "deadline": h.deadline}
            for h in ticking_clocks
        ],
        "open_hooks": [
            {"id": h.id, "title": h.title, "description": h.description, "hook_type": h.hook_type, "priority": h.priority}
            for h in open_hooks
        ],
        "recent_changes": [
            {"entity_id": c.entity_id, "summary": c.summary, "caused_by_player": c.caused_by_player_action}
            for c in changes
        ],
        "recent_story": recent_story,
        "current_scene": current_scene[:500] if current_scene else "",
        "locations": [_entity_short_summary(e) for e in locations[:3]],
    }
    ctx["prompt_block"] = format_for_prompt(ctx)
    return ctx


def format_for_prompt(ctx: dict[str, Any]) -> str:
    """Produce a compact, LLM-ready context block (≈ 400–800 chars).

    Designed to be injected into the narrative agent's system or user prompt
    without ballooning token count.
    """
    lines: list[str] = ["[WORLD STATE]"]

    threads = ctx.get("active_threads") or []
    if threads:
        thread_parts = []
        for t in threads[:3]:
            label = t["name"]
            sit = t.get("situation") or t.get("stakes") or ""
            if sit:
                label += f": {sit[:80]}"
            thread_parts.append(label)
        lines.append("THREADS: " + " | ".join(thread_parts))

    npcs = ctx.get("relevant_npcs") or []
    if npcs:
        npc_parts = []
        for n in npcs[:4]:
            part = n["name"]
            goal = n.get("goal") or ""
            action = n.get("next_action") or ""
            if goal:
                part += f" wants {goal[:50]}"
            if action:
                part += f". Next: {action[:50]}"
            npc_parts.append(part)
        lines.append("NPCS: " + " | ".join(npc_parts))

    factions = ctx.get("faction_pressures") or []
    if factions:
        faction_parts = []
        for f in factions[:2]:
            part = f["name"]
            plan = f.get("active_plan") or f.get("goal") or ""
            if plan:
                part += f" — {plan[:60]}"
            faction_parts.append(part)
        lines.append("FACTIONS: " + " | ".join(faction_parts))

    clocks = ctx.get("ticking_clocks") or []
    if clocks:
        clock_parts = [c["title"] + (f" [{c['deadline']}]" if c.get("deadline") else "") for c in clocks[:3]]
        lines.append("CLOCKS: " + " | ".join(clock_parts))

    hooks = ctx.get("open_hooks") or []
    if hooks:
        hook_parts = [h["title"] for h in hooks[:3]]
        lines.append("HOOKS: " + " | ".join(hook_parts))

    changes = ctx.get("recent_changes") or []
    if changes:
        change_parts = [c["summary"] for c in changes[:3]]
        lines.append("RECENT: " + " | ".join(change_parts))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summarization helpers (callable by agents)
# ---------------------------------------------------------------------------

def summarize_npc_for_roleplay(campaign_id: str, npc_name: str) -> str:
    """Return a roleplay-ready NPC summary string for the given name."""
    with Session(db.engine) as s:
        stmt = select(CampaignEntity).where(
            CampaignEntity.campaign_id == campaign_id,
            CampaignEntity.entity_type == "npc",
            CampaignEntity.name == npc_name,
        )
        npc = s.exec(stmt).first()
    if not npc:
        return f"No memory record for NPC '{npc_name}'."
    d = npc.data or {}
    engine = d.get("story_engine") or {}
    parts = [f"**{npc.name}**"]
    if d.get("personality"):
        parts.append(f"Personality: {d['personality'][:120]}")
    if d.get("primary_goal"):
        parts.append(f"Goal: {d['primary_goal'][:100]}")
    if d.get("greatest_fear"):
        parts.append(f"Fear: {d['greatest_fear'][:80]}")
    if d.get("emotional_state"):
        parts.append(f"Currently: {d['emotional_state'][:80]}")
    if d.get("next_likely_action") or engine.get("next_action"):
        action = d.get("next_likely_action") or engine.get("next_action")
        parts.append(f"Next likely: {action[:100]}")
    secrets = d.get("secrets") or []
    if secrets:
        parts.append(f"Secrets: {len(secrets)} known to GM")
    return "\n".join(parts)


def summarize_location_for_scene(campaign_id: str, location_name: str) -> str:
    """Return a scene-setting location summary string."""
    with Session(db.engine) as s:
        stmt = select(CampaignEntity).where(
            CampaignEntity.campaign_id == campaign_id,
            CampaignEntity.entity_type == "location",
            CampaignEntity.name == location_name,
        )
        loc = s.exec(stmt).first()
    if not loc:
        return f"No memory record for location '{location_name}'."
    d = loc.data or {}
    parts = [f"**{loc.name}**"]
    if d.get("visual_description"):
        parts.append(d["visual_description"][:150])
    if d.get("atmosphere"):
        parts.append(f"Atmosphere: {d['atmosphere'][:80]}")
    tensions = d.get("current_tensions") or []
    if tensions:
        parts.append(f"Tension: {tensions[0][:100]}")
    threats = d.get("threats") or []
    if threats:
        parts.append(f"Threat: {threats[0][:100]}")
    return "\n".join(parts)


def summarize_active_threads(campaign_id: str) -> str:
    """Return a summary of all active story threads."""
    with Session(db.engine) as s:
        threads = s.exec(
            select(CampaignEntity).where(
                CampaignEntity.campaign_id == campaign_id,
                CampaignEntity.entity_type == "story_thread",
                CampaignEntity.status == "active",
            )
        ).all()
    if not threads:
        return "No active story threads."
    lines = []
    for t in threads:
        d = t.data or {}
        priority = d.get("current_priority", 5)
        situation = d.get("current_situation") or d.get("stakes") or ""
        next_beat = d.get("next_recommended_dm_move") or ""
        clock = d.get("ticking_clock") or ""
        line = f"[P{priority}] {t.name}"
        if situation:
            line += f" — {situation[:80]}"
        if next_beat:
            line += f". DM move: {next_beat[:60]}"
        if clock:
            line += f". CLOCK: {clock[:60]}"
        lines.append(line)
    return "\n".join(sorted(lines, reverse=True))


def get_next_likely_actions(campaign_id: str) -> list[str]:
    """Return what will happen in the world if players do nothing."""
    with Session(db.engine) as s:
        entities = s.exec(
            select(CampaignEntity).where(
                CampaignEntity.campaign_id == campaign_id,
                CampaignEntity.status == "active",
                CampaignEntity.entity_type.in_(["npc", "faction"]),
            )
        ).all()
    actions = []
    for e in entities:
        d = e.data or {}
        engine = d.get("story_engine") or {}
        action = d.get("next_likely_action") or d.get("next_action") or engine.get("next_action") or ""
        if action:
            actions.append(f"{e.name} ({e.entity_type}): {action[:100]}")
    return actions


def get_known_information_for_npc(campaign_id: str, npc_name: str) -> dict[str, Any]:
    """Return what an NPC knows — used to keep dialogue authentic."""
    with Session(db.engine) as s:
        npc = s.exec(
            select(CampaignEntity).where(
                CampaignEntity.campaign_id == campaign_id,
                CampaignEntity.entity_type == "npc",
                CampaignEntity.name == npc_name,
            )
        ).first()
    if not npc:
        return {"known": [], "secrets": [], "rumors_believed": []}
    d = npc.data or {}
    return {
        "known": d.get("known_information") or [],
        "secrets": d.get("secrets") or [],
        "rumors_believed": d.get("rumors_believed") or [],
    }


def get_entity_relationships(campaign_id: str, entity_id: str) -> list[dict[str, Any]]:
    """Return all relationships involving this entity."""
    from sqlalchemy import or_
    with Session(db.engine) as s:
        rels = s.exec(
            select(CampaignRelationship).where(
                CampaignRelationship.campaign_id == campaign_id,
                or_(
                    CampaignRelationship.source_entity_id == entity_id,
                    CampaignRelationship.target_entity_id == entity_id,
                ),
            )
        ).all()
        entity_ids = set()
        for r in rels:
            entity_ids.add(r.source_entity_id)
            entity_ids.add(r.target_entity_id)
        entity_ids.discard(entity_id)
        entities = {
            e.id: e.name
            for e in s.exec(
                select(CampaignEntity).where(CampaignEntity.id.in_(list(entity_ids)))
            ).all()
        }
    return [
        {
            "other_entity_id": r.target_entity_id if r.source_entity_id == entity_id else r.source_entity_id,
            "other_entity_name": entities.get(
                r.target_entity_id if r.source_entity_id == entity_id else r.source_entity_id, "Unknown"
            ),
            "direction": "outgoing" if r.source_entity_id == entity_id else "incoming",
            "relationship_type": r.relationship_type,
            "description": r.description,
            "scores": r.scores or {},
        }
        for r in rels
    ]


def summarize_recent_world_changes(campaign_id: str, limit: int = 10) -> str:
    """Return a human-readable summary of recent entity changes."""
    with Session(db.engine) as s:
        changes = s.exec(
            select(CampaignChangeLog)
            .where(CampaignChangeLog.campaign_id == campaign_id)
            .order_by(CampaignChangeLog.created_at.desc())
            .limit(limit)
        ).all()
    if not changes:
        return "No recent changes recorded."
    lines = []
    for c in changes:
        player_tag = " (player action)" if c.caused_by_player_action else ""
        lines.append(f"• {c.summary}{player_tag}")
    return "\n".join(lines)
