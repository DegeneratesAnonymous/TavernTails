import json
import random
import re
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..realtime import broadcaster

router = APIRouter(tags=["rolls"])


class RollRequest(BaseModel):
    expression: str
    reason: str | None = None
    session_id: str | None = None


def _parse_roll(expr: str) -> Dict[str, Any]:
    # Simple parser: supports NdM +/- K
    m = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", expr.replace(' ', ''))
    if not m:
        raise ValueError("Invalid roll expression")
    n = int(m.group(1) or '1')
    sides = int(m.group(2))
    mod = int(m.group(3) or '0')
    return {'n': n, 'sides': sides, 'mod': mod}


def _roll(n: int, sides: int) -> list[int]:
    return [random.randint(1, sides) for _ in range(n)]


def _coerce_roll_values(raw: Any) -> List[int]:
    if raw is None:
        return []
    payload = raw
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = [payload]
    if not isinstance(payload, list):
        payload = [payload]
    values: List[int] = []
    for entry in payload:
        candidate = entry
        if isinstance(entry, dict):
            candidate = entry.get('value') or entry.get('result') or entry.get('total') or entry.get('die')
        try:
            values.append(int(candidate))
        except (TypeError, ValueError):
            continue
    return values


def _normalize_beyond20_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    expr = (payload.get('expression') or payload.get('label') or payload.get('name') or '').strip()
    rolls = _coerce_roll_values(payload.get('rolls') or payload.get('dice') or payload.get('results'))
    try:
        raw_mod = payload.get('modifier') if payload.get('modifier') is not None else payload.get('mod')
        mod = int(raw_mod) if raw_mod is not None else 0
    except (TypeError, ValueError):
        mod = 0
    total = payload.get('total')
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    if total is None and rolls:
        total = sum(rolls) + mod
    if total is None and expr:
        try:
            parsed = _parse_roll(expr)
            rolls = _roll(parsed['n'], parsed['sides'])
            mod = parsed['mod']
            total = sum(rolls) + mod
        except ValueError:
            total = 0
    by = payload.get('player') or payload.get('character') or payload.get('by') or 'Beyond20'
    reason = payload.get('reason') or payload.get('label') or payload.get('title')
    return {
        'expression': expr,
        'rolls': rolls,
        'mod': mod,
        'total': int(total or 0),
        'by': by,
        'reason': reason,
        'source': 'beyond20',
    }


@router.post('/rolls')
async def do_roll(req: RollRequest, current_user=Depends(get_current_user)):
    try:
        parsed = _parse_roll(req.expression)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    rolls = _roll(parsed['n'], parsed['sides'])
    total = sum(rolls) + parsed['mod']
    result = {
        'expression': req.expression,
        'rolls': rolls,
        'mod': parsed['mod'],
        'total': total,
        'by': getattr(current_user, 'email', None) or getattr(current_user, 'username', None),
    }
    # persist the roll
    from .. import db
    by = result.get('by')
    campaign_id = None
    try:
        db.create_roll(campaign_id=campaign_id, expression=req.expression, rolls=rolls, mod=parsed['mod'], total=total, by=by)
    except Exception:
        # non-fatal on persistence failure
        pass
    if req.session_id:
        await broadcaster.broadcast_json(req.session_id, {
            'type': 'rolls.result',
            'session_id': req.session_id,
            'result': result,
        })
    return {'result': result}


@router.post('/integrations/beyond20/roll')
async def ingest_beyond20(payload: Dict[str, Any] = Body(...)):
    session_id = payload.get('session_id')
    result = _normalize_beyond20_payload(payload)
    from .. import db
    try:
        db.create_roll(
            campaign_id=payload.get('campaign_id'),
            expression=result['expression'],
            rolls=result['rolls'],
            mod=result['mod'],
            total=result['total'],
            by=result['by'],
        )
    except Exception:
        pass
    envelope = {
        'type': 'rolls.result',
        'session_id': session_id,
        'result': result,
        'source': 'beyond20',
    }
    if session_id:
        await broadcaster.broadcast_json(session_id, envelope)
        await broadcaster.broadcast_json(session_id, {
            'type': 'beyond20.roll',
            'session_id': session_id,
            'expression': result['expression'],
            'total': result['total'],
            'by': result['by'],
            'reason': result.get('reason') or payload.get('reason'),
        })
    return {'result': result}
