from fastapi import APIRouter, Body, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any
import re
import random

from ..auth import get_current_user

router = APIRouter(tags=["rolls"])


class RollRequest(BaseModel):
    expression: str
    reason: str | None = None


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


@router.post('/rolls')
def do_roll(req: RollRequest, current_user=Depends(get_current_user)):
    try:
        parsed = _parse_roll(req.expression)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    return {'result': result}


@router.post('/integrations/beyond20/roll')
def ingest_beyond20(payload: Dict[str, Any] = Body(...)):
    # Minimal bridge: accept a payload with 'expression' or 'total' and 'player' fields
    expr = payload.get('expression')
    if expr:
        # forward to local parser and persist
        try:
            parsed = _parse_roll(expr)
            rolls = _roll(parsed['n'], parsed['sides'])
            total = sum(rolls) + parsed['mod']
            from .. import db
            by = payload.get('player') or payload.get('by')
            try:
                db.create_roll(campaign_id=payload.get('campaign_id'), expression=expr, rolls=rolls, mod=parsed['mod'], total=total, by=by)
            except Exception:
                pass
            return {'result': {'expression': expr, 'rolls': rolls, 'mod': parsed['mod'], 'total': total, 'ingested': True}}
        except ValueError:
            return {'result': {'ingested': False, 'reason': 'invalid expression'}}
    # if total is supplied, accept it as-is
    if 'total' in payload:
        from .. import db
        by = payload.get('player') or payload.get('by')
        try:
            db.create_roll(campaign_id=payload.get('campaign_id'), expression=payload.get('expression') or '', rolls=[], mod=0, total=int(payload.get('total') or 0), by=by)
        except Exception:
            pass
        return {'result': {'total': payload.get('total'), 'ingested': True}}
    return {'result': {'ingested': False, 'reason': 'no usable fields'}}
