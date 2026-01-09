"""Simple turn queue management for sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..realtime import broadcaster
from . import sessions as session_module

router = APIRouter(prefix="/turns", tags=["turns"])

BASE = session_module.BASE


class TurnState(BaseModel):
    session_id: str
    order: List[str] = Field(default_factory=list)
    active_index: int = Field(default=0, ge=0)
    active: str | None = None

    def set_active(self) -> None:
        if not self.order:
            self.active = None
        else:
            self.active = self.order[self.active_index % len(self.order)]


class TurnUpdateRequest(BaseModel):
    order: List[str] = Field(default_factory=list)
    active_index: int = Field(default=0, ge=0)


class AdvanceRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=10)


def _turn_file(session_id: str) -> Path:
    return BASE / session_id / 'turns.json'


def _load_state(session_id: str) -> TurnState:
    file_path = _turn_file(session_id)
    if file_path.exists():
        data = json.loads(file_path.read_text())
        data.pop('session_id', None)
        state = TurnState(session_id=session_id, **data)
    else:
        state = TurnState(session_id=session_id)
    state.set_active()
    return state


def _save_state(state: TurnState) -> TurnState:
    file_path = _turn_file(state.session_id)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    state.set_active()
    file_path.write_text(state.model_dump_json())
    return state


def _ensure_member(session_id: str, user) -> None:
    meta_path = BASE / session_id / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        raise HTTPException(status_code=500, detail='Failed to read session meta')
    identifier = session_module._identifier_for_user(user)
    if not session_module._user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not authorized for this session')


def _emit_state(state: TurnState):
    return broadcaster.broadcast_json(state.session_id, {
        'type': 'turns.update',
        'session_id': state.session_id,
        'order': state.order,
        'active_index': state.active_index,
        'active': state.active,
    })


@router.get('/{session_id}', response_model=TurnState)
async def read_turns(session_id: str, current_user=Depends(get_current_user)):
    _ensure_member(session_id, current_user)
    state = _load_state(session_id)
    await _emit_state(state)
    return state


@router.post('/{session_id}', response_model=TurnState)
async def update_turns(session_id: str, payload: TurnUpdateRequest, current_user=Depends(get_current_user)):
    _ensure_member(session_id, current_user)
    divisor = max(1, len(payload.order) or 1)
    state = TurnState(session_id=session_id, order=payload.order, active_index=payload.active_index % divisor)
    _save_state(state)
    await _emit_state(state)
    return state


@router.post('/{session_id}/advance', response_model=TurnState)
async def advance_turn(session_id: str, payload: AdvanceRequest, current_user=Depends(get_current_user)):
    _ensure_member(session_id, current_user)
    state = _load_state(session_id)
    if not state.order:
        return state
    state.active_index = (state.active_index + payload.steps) % len(state.order)
    _save_state(state)
    await _emit_state(state)
    return state
