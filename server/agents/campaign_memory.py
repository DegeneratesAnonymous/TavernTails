"""Campaign Memory System — CRUD + context API for the living world.

Entity types: npc | location | faction | backstory | story_thread | world_event

Endpoints
---------
GET/POST   /memory/{campaign_id}/entities
GET/PUT/DELETE /memory/{campaign_id}/entities/{entity_id}

GET/POST   /memory/{campaign_id}/relationships
DELETE     /memory/{campaign_id}/relationships/{rel_id}

GET/POST   /memory/{campaign_id}/hooks
PUT/DELETE /memory/{campaign_id}/hooks/{hook_id}

GET        /memory/{campaign_id}/changelog
GET        /memory/{campaign_id}/changelog/{entity_id}

POST       /memory/{campaign_id}/context            — AI-ready context summary
POST       /memory/{campaign_id}/recap              — process session recap (propose + apply)
GET        /memory/{campaign_id}/next-actions       — what will happen next
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import db
from ..auth import get_current_user
from ..db import (
    CampaignChangeLog,
    CampaignEntity,
    CampaignHook,
    CampaignRelationship,
)
from ..steward_llm import chat_complete

router = APIRouter(prefix="/memory", tags=["memory"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _require_campaign_access(campaign_id: str, current_user) -> db.Campaign:
    """Verify user owns the campaign (or is the assigned GM)."""
    campaign = db.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    user_id = getattr(current_user, "id", None)
    if campaign.owner_id != user_id and campaign.gm_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return campaign


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Entity CRUD
# ---------------------------------------------------------------------------

class EntityCreate(BaseModel):
    entity_type: str
    name: str
    status: str = "active"
    visibility: str = "gm_only"
    tags: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    visibility: str | None = None
    tags: list[str] | None = None
    data: dict[str, Any] | None = None
    change_summary: str | None = None
    session_id: str | None = None
    caused_by_player_action: bool = False


def _entity_dict(e: CampaignEntity) -> dict:
    return {
        "id": e.id,
        "campaign_id": e.campaign_id,
        "entity_type": e.entity_type,
        "name": e.name,
        "status": e.status,
        "visibility": e.visibility,
        "tags": e.tags or [],
        "data": e.data or {},
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


@router.get("/{campaign_id}/entities")
def list_entities(
    campaign_id: str,
    entity_type: str | None = None,
    status: str | None = None,
    current_user=Depends(get_current_user),
):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        stmt = select(CampaignEntity).where(CampaignEntity.campaign_id == campaign_id)
        if entity_type:
            stmt = stmt.where(CampaignEntity.entity_type == entity_type)
        if status:
            stmt = stmt.where(CampaignEntity.status == status)
        stmt = stmt.order_by(CampaignEntity.updated_at.desc())
        entities = s.exec(stmt).all()
    return [_entity_dict(e) for e in entities]


@router.post("/{campaign_id}/entities", status_code=201)
def create_entity(
    campaign_id: str,
    req: EntityCreate,
    current_user=Depends(get_current_user),
):
    _require_campaign_access(campaign_id, current_user)
    eid = _new_id()
    entity = CampaignEntity(
        id=eid,
        campaign_id=campaign_id,
        entity_type=req.entity_type,
        name=req.name.strip(),
        status=req.status,
        visibility=req.visibility,
        tags=req.tags,
        data=req.data,
        created_at=_now(),
        updated_at=_now(),
    )
    log = CampaignChangeLog(
        id=_new_id(),
        campaign_id=campaign_id,
        entity_id=eid,
        change_type="create",
        summary=f"Created {req.entity_type} '{req.name}'",
        before_data={},
        after_data=req.data,
        caused_by_player_action=False,
        created_at=_now(),
    )
    with Session(db.engine) as s:
        s.add(entity)
        s.add(log)
        s.commit()
        s.refresh(entity)
    return _entity_dict(entity)


@router.get("/{campaign_id}/entities/{entity_id}")
def get_entity(campaign_id: str, entity_id: str, current_user=Depends(get_current_user)):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        e = s.get(CampaignEntity, entity_id)
        if not e or e.campaign_id != campaign_id:
            raise HTTPException(status_code=404, detail="Entity not found")
        return _entity_dict(e)


@router.put("/{campaign_id}/entities/{entity_id}")
def update_entity(
    campaign_id: str,
    entity_id: str,
    req: EntityUpdate,
    current_user=Depends(get_current_user),
):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        e = s.get(CampaignEntity, entity_id)
        if not e or e.campaign_id != campaign_id:
            raise HTTPException(status_code=404, detail="Entity not found")
        before = dict(e.data or {})
        if req.name is not None:
            e.name = req.name.strip()
        if req.status is not None:
            e.status = req.status
        if req.visibility is not None:
            e.visibility = req.visibility
        if req.tags is not None:
            e.tags = req.tags
        if req.data is not None:
            merged = dict(e.data or {})
            merged.update(req.data)
            e.data = merged
        e.updated_at = _now()
        log = CampaignChangeLog(
            id=_new_id(),
            campaign_id=campaign_id,
            entity_id=entity_id,
            session_id=req.session_id,
            change_type="update",
            summary=req.change_summary or f"Updated {e.entity_type} '{e.name}'",
            before_data=before,
            after_data=dict(e.data or {}),
            caused_by_player_action=req.caused_by_player_action,
            created_at=_now(),
        )
        s.add(e)
        s.add(log)
        s.commit()
        s.refresh(e)
        return _entity_dict(e)


@router.delete("/{campaign_id}/entities/{entity_id}", status_code=204)
def delete_entity(campaign_id: str, entity_id: str, current_user=Depends(get_current_user)):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        e = s.get(CampaignEntity, entity_id)
        if not e or e.campaign_id != campaign_id:
            raise HTTPException(status_code=404, detail="Entity not found")
        s.delete(e)
        s.commit()


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

class RelationshipUpsert(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relationship_type: str = ""
    description: str = ""
    scores: dict[str, Any] = Field(default_factory=dict)
    secrecy_level: str = "public"


def _rel_dict(r: CampaignRelationship) -> dict:
    return {
        "id": r.id,
        "campaign_id": r.campaign_id,
        "source_entity_id": r.source_entity_id,
        "target_entity_id": r.target_entity_id,
        "relationship_type": r.relationship_type,
        "description": r.description,
        "scores": r.scores or {},
        "secrecy_level": r.secrecy_level,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("/{campaign_id}/relationships")
def list_relationships(
    campaign_id: str,
    entity_id: str | None = None,
    current_user=Depends(get_current_user),
):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        stmt = select(CampaignRelationship).where(CampaignRelationship.campaign_id == campaign_id)
        if entity_id:
            from sqlalchemy import or_
            stmt = stmt.where(
                or_(
                    CampaignRelationship.source_entity_id == entity_id,
                    CampaignRelationship.target_entity_id == entity_id,
                )
            )
        rels = s.exec(stmt).all()
    return [_rel_dict(r) for r in rels]


@router.post("/{campaign_id}/relationships", status_code=201)
def upsert_relationship(
    campaign_id: str,
    req: RelationshipUpsert,
    current_user=Depends(get_current_user),
):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        # Look for existing relationship between these two entities
        stmt = select(CampaignRelationship).where(
            CampaignRelationship.campaign_id == campaign_id,
            CampaignRelationship.source_entity_id == req.source_entity_id,
            CampaignRelationship.target_entity_id == req.target_entity_id,
        )
        existing = s.exec(stmt).first()
        if existing:
            existing.relationship_type = req.relationship_type
            existing.description = req.description
            existing.scores = req.scores
            existing.secrecy_level = req.secrecy_level
            existing.updated_at = _now()
            s.add(existing)
            s.commit()
            s.refresh(existing)
            return _rel_dict(existing)
        rel = CampaignRelationship(
            id=_new_id(),
            campaign_id=campaign_id,
            source_entity_id=req.source_entity_id,
            target_entity_id=req.target_entity_id,
            relationship_type=req.relationship_type,
            description=req.description,
            scores=req.scores,
            secrecy_level=req.secrecy_level,
            updated_at=_now(),
        )
        s.add(rel)
        s.commit()
        s.refresh(rel)
        return _rel_dict(rel)


@router.delete("/{campaign_id}/relationships/{rel_id}", status_code=204)
def delete_relationship(campaign_id: str, rel_id: str, current_user=Depends(get_current_user)):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        r = s.get(CampaignRelationship, rel_id)
        if not r or r.campaign_id != campaign_id:
            raise HTTPException(status_code=404, detail="Relationship not found")
        s.delete(r)
        s.commit()


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

class HookCreate(BaseModel):
    title: str
    description: str = ""
    hook_type: str = "unresolved"
    priority: int = 5
    entity_id: str | None = None
    deadline: str | None = None


class HookUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    hook_type: str | None = None
    priority: int | None = None
    status: str | None = None
    deadline: str | None = None


def _hook_dict(h: CampaignHook) -> dict:
    return {
        "id": h.id,
        "campaign_id": h.campaign_id,
        "entity_id": h.entity_id,
        "title": h.title,
        "description": h.description,
        "hook_type": h.hook_type,
        "priority": h.priority,
        "status": h.status,
        "deadline": h.deadline,
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "updated_at": h.updated_at.isoformat() if h.updated_at else None,
    }


@router.get("/{campaign_id}/hooks")
def list_hooks(
    campaign_id: str,
    status: str | None = None,
    hook_type: str | None = None,
    current_user=Depends(get_current_user),
):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        stmt = select(CampaignHook).where(CampaignHook.campaign_id == campaign_id)
        if status:
            stmt = stmt.where(CampaignHook.status == status)
        if hook_type:
            stmt = stmt.where(CampaignHook.hook_type == hook_type)
        stmt = stmt.order_by(CampaignHook.priority.desc(), CampaignHook.created_at.asc())
        hooks = s.exec(stmt).all()
    return [_hook_dict(h) for h in hooks]


@router.post("/{campaign_id}/hooks", status_code=201)
def create_hook(campaign_id: str, req: HookCreate, current_user=Depends(get_current_user)):
    _require_campaign_access(campaign_id, current_user)
    hook = CampaignHook(
        id=_new_id(),
        campaign_id=campaign_id,
        entity_id=req.entity_id,
        title=req.title,
        description=req.description,
        hook_type=req.hook_type,
        priority=max(1, min(10, req.priority)),
        status="active",
        deadline=req.deadline,
        created_at=_now(),
        updated_at=_now(),
    )
    with Session(db.engine) as s:
        s.add(hook)
        s.commit()
        s.refresh(hook)
    return _hook_dict(hook)


@router.put("/{campaign_id}/hooks/{hook_id}")
def update_hook(campaign_id: str, hook_id: str, req: HookUpdate, current_user=Depends(get_current_user)):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        h = s.get(CampaignHook, hook_id)
        if not h or h.campaign_id != campaign_id:
            raise HTTPException(status_code=404, detail="Hook not found")
        if req.title is not None:
            h.title = req.title
        if req.description is not None:
            h.description = req.description
        if req.hook_type is not None:
            h.hook_type = req.hook_type
        if req.priority is not None:
            h.priority = max(1, min(10, req.priority))
        if req.status is not None:
            h.status = req.status
        if req.deadline is not None:
            h.deadline = req.deadline
        h.updated_at = _now()
        s.add(h)
        s.commit()
        s.refresh(h)
        return _hook_dict(h)


@router.delete("/{campaign_id}/hooks/{hook_id}", status_code=204)
def delete_hook(campaign_id: str, hook_id: str, current_user=Depends(get_current_user)):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        h = s.get(CampaignHook, hook_id)
        if not h or h.campaign_id != campaign_id:
            raise HTTPException(status_code=404, detail="Hook not found")
        s.delete(h)
        s.commit()


# ---------------------------------------------------------------------------
# Change Log
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}/changelog")
def list_changelog(
    campaign_id: str,
    limit: int = 50,
    current_user=Depends(get_current_user),
):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        stmt = (
            select(CampaignChangeLog)
            .where(CampaignChangeLog.campaign_id == campaign_id)
            .order_by(CampaignChangeLog.created_at.desc())
            .limit(limit)
        )
        rows = s.exec(stmt).all()
    return [
        {
            "id": r.id,
            "entity_id": r.entity_id,
            "session_id": r.session_id,
            "change_type": r.change_type,
            "summary": r.summary,
            "caused_by_player_action": r.caused_by_player_action,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/{campaign_id}/changelog/{entity_id}")
def entity_changelog(
    campaign_id: str,
    entity_id: str,
    current_user=Depends(get_current_user),
):
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        stmt = (
            select(CampaignChangeLog)
            .where(
                CampaignChangeLog.campaign_id == campaign_id,
                CampaignChangeLog.entity_id == entity_id,
            )
            .order_by(CampaignChangeLog.created_at.desc())
        )
        rows = s.exec(stmt).all()
    return [
        {
            "id": r.id,
            "change_type": r.change_type,
            "summary": r.summary,
            "before_data": r.before_data,
            "after_data": r.after_data,
            "caused_by_player_action": r.caused_by_player_action,
            "session_id": r.session_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Context Summary (AI-ready)
# ---------------------------------------------------------------------------

class ContextRequest(BaseModel):
    session_id: str | None = None
    recent_chat: list[str] = Field(default_factory=list)
    focus: str = "scene"  # scene | recap | next_actions | full


@router.post("/{campaign_id}/context")
def get_context(campaign_id: str, req: ContextRequest, current_user=Depends(get_current_user)):
    _require_campaign_access(campaign_id, current_user)
    from .context_collector import collect_context
    ctx = collect_context(campaign_id, session_id=req.session_id, recent_chat=req.recent_chat)
    return ctx


@router.get("/{campaign_id}/next-actions")
def get_next_actions(campaign_id: str, current_user=Depends(get_current_user)):
    """What will NPCs, factions, and story threads do next if players don't act?"""
    _require_campaign_access(campaign_id, current_user)
    with Session(db.engine) as s:
        npc_stmt = select(CampaignEntity).where(
            CampaignEntity.campaign_id == campaign_id,
            CampaignEntity.entity_type == "npc",
            CampaignEntity.status == "active",
        )
        npcs = s.exec(npc_stmt).all()

        faction_stmt = select(CampaignEntity).where(
            CampaignEntity.campaign_id == campaign_id,
            CampaignEntity.entity_type == "faction",
            CampaignEntity.status == "active",
        )
        factions = s.exec(faction_stmt).all()

        thread_stmt = select(CampaignEntity).where(
            CampaignEntity.campaign_id == campaign_id,
            CampaignEntity.entity_type == "story_thread",
            CampaignEntity.status == "active",
        ).order_by(CampaignEntity.updated_at.desc()).limit(10)
        threads = s.exec(thread_stmt).all()

        hook_stmt = select(CampaignHook).where(
            CampaignHook.campaign_id == campaign_id,
            CampaignHook.status == "active",
        ).order_by(CampaignHook.priority.desc()).limit(10)
        hooks = s.exec(hook_stmt).all()

    actions = []

    for npc in npcs:
        d = npc.data or {}
        engine = d.get("story_engine") or {}
        next_action = engine.get("next_action") or d.get("next_likely_action") or ""
        if next_action:
            actions.append({
                "entity_type": "npc",
                "entity_id": npc.id,
                "name": npc.name,
                "action": next_action,
                "escalation": engine.get("escalation_if_ignored", ""),
            })

    for faction in factions:
        d = faction.data or {}
        engine = d.get("story_engine") or {}
        next_action = engine.get("next_action") or d.get("next_action") or ""
        if next_action:
            actions.append({
                "entity_type": "faction",
                "entity_id": faction.id,
                "name": faction.name,
                "action": next_action,
                "escalation": engine.get("escalation_if_ignored") or d.get("likely_escalation", ""),
            })

    for thread in threads:
        d = thread.data or {}
        next_beat = d.get("next_recommended_dm_move") or ""
        clock = d.get("ticking_clock") or ""
        if next_beat or clock:
            actions.append({
                "entity_type": "story_thread",
                "entity_id": thread.id,
                "name": thread.name,
                "action": next_beat,
                "escalation": clock,
            })

    ticking_clocks = [
        {
            "hook_id": h.id,
            "title": h.title,
            "description": h.description,
            "priority": h.priority,
            "deadline": h.deadline,
        }
        for h in hooks
        if h.hook_type == "ticking_clock"
    ]

    return {"next_actions": actions, "ticking_clocks": ticking_clocks}


# ---------------------------------------------------------------------------
# Session Recap Ingestion
# ---------------------------------------------------------------------------

class RecapRequest(BaseModel):
    recap_text: str
    session_id: str | None = None
    auto_apply: bool = False


@router.post("/{campaign_id}/recap")
def process_recap(campaign_id: str, req: RecapRequest, current_user=Depends(get_current_user)):
    """Extract proposed updates from a session recap text.

    Returns a list of proposed changes. If auto_apply=True, also applies them.
    The user can call PUT /entities/{id} to apply individual proposals.
    """
    _require_campaign_access(campaign_id, current_user)

    # Load current entity names for context
    with Session(db.engine) as s:
        entities = s.exec(
            select(CampaignEntity).where(CampaignEntity.campaign_id == campaign_id)
        ).all()

    entity_index = {e.name.lower(): e for e in entities}
    entity_names = [e.name for e in entities]

    system = (
        "You are a campaign memory assistant for a tabletop RPG. "
        "A Game Master has provided a session recap. "
        "Extract structured updates for NPCs, locations, factions, and story threads.\n\n"
        "For each update, produce a JSON object in this array:\n"
        "[\n"
        "  {\n"
        '    "entity_name": "<name of existing or new entity>",\n'
        '    "entity_type": "npc|location|faction|story_thread|world_event",\n'
        '    "is_new": true|false,\n'
        '    "change_summary": "<one sentence: what changed>",\n'
        '    "caused_by_player_action": true|false,\n'
        '    "data_patches": { "<field>": "<new value>" },\n'
        '    "new_hooks": ["<unresolved hook or consequence>"],\n'
        '    "resolved_hooks": ["<hook title that was resolved>"]\n'
        "  }\n"
        "]\n\n"
        f"Known entities in this campaign: {', '.join(entity_names[:40]) or 'none yet'}\n"
        "Return only the JSON array. No commentary."
    )

    text = chat_complete(
        [{"role": "system", "content": system}, {"role": "user", "content": req.recap_text[:3000]}],
        task_scope="taverntails_extraction",
        max_tokens=800,
        timeout=60.0,
    )

    proposals: list[dict] = []
    if text:
        try:
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end > start:
                proposals = json.loads(text[start:end + 1])
        except Exception:
            proposals = []

    applied: list[dict] = []
    if req.auto_apply and proposals:
        for prop in proposals:
            entity_name = str(prop.get("entity_name") or "").strip()
            entity_type = str(prop.get("entity_type") or "world_event").strip()
            data_patches = prop.get("data_patches") or {}
            change_summary = str(prop.get("change_summary") or "Session recap update")
            is_new = bool(prop.get("is_new"))
            caused_by_player = bool(prop.get("caused_by_player_action"))

            if not entity_name:
                continue

            existing = entity_index.get(entity_name.lower())
            if existing and not is_new:
                with Session(db.engine) as s:
                    e = s.get(CampaignEntity, existing.id)
                    if e:
                        before = dict(e.data or {})
                        merged = {**before, **data_patches}
                        e.data = merged
                        e.updated_at = _now()
                        log = CampaignChangeLog(
                            id=_new_id(),
                            campaign_id=campaign_id,
                            entity_id=e.id,
                            session_id=req.session_id,
                            change_type="update",
                            summary=change_summary,
                            before_data=before,
                            after_data=merged,
                            caused_by_player_action=caused_by_player,
                            created_at=_now(),
                        )
                        s.add(e)
                        s.add(log)
                        s.commit()
                        applied.append({"entity_id": e.id, "action": "updated"})
            elif is_new:
                eid = _new_id()
                entity = CampaignEntity(
                    id=eid,
                    campaign_id=campaign_id,
                    entity_type=entity_type,
                    name=entity_name,
                    status="active",
                    visibility="gm_only",
                    tags=[],
                    data=data_patches,
                    created_at=_now(),
                    updated_at=_now(),
                )
                log = CampaignChangeLog(
                    id=_new_id(),
                    campaign_id=campaign_id,
                    entity_id=eid,
                    session_id=req.session_id,
                    change_type="create",
                    summary=change_summary,
                    before_data={},
                    after_data=data_patches,
                    caused_by_player_action=caused_by_player,
                    created_at=_now(),
                )
                with Session(db.engine) as s:
                    s.add(entity)
                    s.add(log)
                    s.commit()
                applied.append({"entity_id": eid, "action": "created"})

            # Create proposed hooks
            for hook_title in prop.get("new_hooks") or []:
                if hook_title:
                    hook = CampaignHook(
                        id=_new_id(),
                        campaign_id=campaign_id,
                        title=str(hook_title)[:200],
                        description=f"From recap: {req.session_id or ''}",
                        hook_type="unresolved",
                        priority=5,
                        status="active",
                        created_at=_now(),
                        updated_at=_now(),
                    )
                    with Session(db.engine) as s:
                        s.add(hook)
                        s.commit()

    return {"proposals": proposals, "applied": applied}
